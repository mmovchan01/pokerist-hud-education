import json
import threading

import cv2
import numpy as np
import pytest

from capture_worker import CaptureWorker
from screenshot_album import Album, CARD_LABELS, read_image, validate_rect
from windows_capture import validate_render


def make_album(tmp_path):
    album = Album(tmp_path/'альбом', tmp_path/'шаблоны')
    image = np.full((100, 200, 3), 180, np.uint8)
    cv2.putText(image, 'A', (25, 55), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    record = album.add(image, {'hero1': [.1, .1, .3, .6]}, {'window_title': 'Texas Poker'})
    return album, record, image


def test_capture_round_trip_and_frozen_rois(tmp_path):
    album = Album(tmp_path/'inbox', tmp_path/'templates')
    rois = {'hero1': [.1, .1, .3, .6]}
    record = album.add(np.full((100, 200, 3), 150, np.uint8), rois, {'method': 'test'})
    rois['hero1'][0] = .8
    reloaded = album.load(record['id'])
    assert reloaded['items']['hero1']['rect'][0] == .1
    records, errors = album.records()
    assert len(records) == 1 and not errors
    assert np.array_equal(album.image(record), np.full((100, 200, 3), 150, np.uint8))


def test_export_relabel_skip_and_resume(tmp_path):
    album, record, image = make_album(tmp_path)
    identifier = record['id']
    record = album.annotate(identifier, 'hero1', 'card', 'Ah', revision=0)
    first = album.templates/record['items']['hero1']['export']
    assert first.exists()
    assert read_image(first).shape == (60, 60, 3)
    record = album.annotate(identifier, 'hero1', 'card', 'Kd', revision=1)
    second = album.templates/record['items']['hero1']['export']
    assert second.exists() and not first.exists()
    # Labels are not append-only; repeated saves don't create duplicates.
    record = album.annotate(identifier, 'hero1', 'card', 'Kd', revision=2)
    assert len(list(album.templates.glob('card/Kd/*.png'))) == 1
    record = album.annotate(identifier, 'hero1', 'card', '', skip=True, revision=3)
    assert not second.exists()
    assert record['items']['hero1']['status'] == 'skipped'
    resumed = Album(album.folder, album.templates).load(identifier)
    assert resumed['revision'] == 4
    assert resumed['items']['hero1']['label'] is None


def test_bad_label_and_rect_dont_export(tmp_path):
    album, record, _ = make_album(tmp_path)
    for kind, label in [('card', 'XX'), ('glyph', '12'), ('empty', 'Ah'), ('card', '../x')]:
        with pytest.raises(ValueError):
            album.annotate(record['id'], 'hero1', kind, label)
    with pytest.raises(ValueError):
        album.annotate(record['id'], 'hero1', 'card', 'Ah', rect=[0, 0, 3, 1])
    assert not album.templates.exists()
    assert album.load(record['id'])['revision'] == 0


@pytest.mark.parametrize('rect', [[0, 0, 0, 1], [-1, 0, 1, 1], [0, 0, float('nan'), 1], [0, 0, 1], [0, 0, float('inf'), 1]])
def test_invalid_rect(rect):
    with pytest.raises(ValueError):
        validate_rect(rect)


def test_extra_glyph_and_unicode_paths(tmp_path):
    album, record, _ = make_album(tmp_path)
    record, item_id = album.add_region(record['id'], [.3, .3, .1, .1])
    record = album.annotate(record['id'], item_id, 'glyph', '.')
    path = album.templates/record['items'][item_id]['export']
    assert path.parent.name == 'dot'
    assert read_image(path).shape == (10, 20, 3)


def test_stale_revision_and_path_guards(tmp_path):
    album, record, _ = make_album(tmp_path)
    album.annotate(record['id'], 'hero1', 'card', 'Ah')
    with pytest.raises(ValueError, match='другим редактором'):
        album.annotate(record['id'], 'hero1', 'card', 'Kd', revision=0)
    with pytest.raises(ValueError):
        album.load('../outside')
    record = album.load(record['id'])
    record['image'] = '../outside.png'
    (album.folder/f'{record["id"]}.json').write_text(json.dumps(record))
    records, errors = album.records()
    assert not records and errors


def test_skipping_does_not_delete_other_templates(tmp_path):
    album, record, _ = make_album(tmp_path)
    manual = album.templates/'card'/'Ah'/'manual.png'
    manual.parent.mkdir(parents=True)
    manual.write_bytes(b'manual')
    album.annotate(record['id'], 'hero1', 'card', 'Ah')
    album.annotate(record['id'], 'hero1', 'card', '', skip=True)
    assert manual.read_bytes() == b'manual'


def test_black_render_rejected():
    with pytest.raises(RuntimeError, match='чёрный'):
        validate_render(np.zeros((100, 200, 3), np.uint8))
    validate_render(np.full((100, 200, 3), 100, np.uint8))


def test_all_52_choices():
    assert len(CARD_LABELS) == len(set(CARD_LABELS)) == 52


def test_capture_worker_busy_and_errors(tmp_path):
    album = Album(tmp_path/'inbox', tmp_path/'templates')
    entered, release = threading.Event(), threading.Event()

    def capture(title):
        assert title == 'Texas Poker'
        entered.set()
        assert release.wait(2)
        return np.full((100, 200, 3), 150, np.uint8), {'window_title': title}

    worker = CaptureWorker(album, tmp_path/'absent.json', 'Texas Poker', capture=capture)
    try:
        worker.request()
        assert entered.wait(2)
        worker.request()
        assert worker.events.get(timeout=2)[0] == 'status'
        release.set()
        assert worker.events.get(timeout=2)[0] == 'saved'
        records, errors = album.records()
        assert len(records) == 1 and not errors
        assert records[0]['suggested_rois']
    finally:
        release.set()
        worker.close()


def test_capture_worker_does_not_save_on_failure(tmp_path):
    def capture(title):
        raise RuntimeError('window not found')
    album = Album(tmp_path/'inbox', tmp_path/'templates')
    worker = CaptureWorker(album, tmp_path/'absent.json', 'Texas Poker', capture=capture)
    try:
        worker.request()
        kind, error = worker.events.get(timeout=2)
        assert kind == 'error' and 'window not found' in error
        assert album.records() == ([], [])
    finally:
        worker.close()
