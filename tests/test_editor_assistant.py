import cv2
import numpy as np
import pytest

from card_choices import CARD_CHOICES, EMPTY_CHOICE, display_choice, filtered_choices
from editor_assistant import EditorAssistant, has_card_template
from profile_support import BUILTIN
from screenshot_album import Album


def sample():
    return cv2.imread(str(next((BUILTIN/'templates/card/Ks').glob('*.png'))))


def put(root, kind, label, image, filename='sample.png'):
    folder = root/kind/label
    folder.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(folder/filename), image)


def test_exact_duplicate_is_known_and_catalog_updates(tmp_path):
    image = sample()
    assistant = EditorAssistant(tmp_path)
    prediction, known = assistant.analyze(image)
    assert prediction is None and not known
    put(tmp_path, 'card', 'Ks', image)
    prediction, known = assistant.analyze(image)
    assert prediction.label == 'Ks'
    assert prediction.automatic and prediction.method == 'exact pixels'
    assert prediction.confidence == 1
    assert known == {'Ks'}
    assert has_card_template(tmp_path, 'Ks')
    assert not has_card_template(tmp_path, '../x')
    (tmp_path/'card/Ks/sample.png').unlink()
    _, known = assistant.analyze(image)
    assert not known


def test_conflicting_exact_labels_are_not_guessed(tmp_path):
    image = sample()
    put(tmp_path, 'card', 'Ks', image)
    put(tmp_path, 'card', 'Ah', image)
    prediction, known = EditorAssistant(tmp_path).analyze(image)
    assert prediction is None
    assert known == {'Ks', 'Ah'}


def test_unknown_blank_does_not_turn_into_known_card(tmp_path):
    put(tmp_path, 'card', 'Ks', sample())
    prediction, _ = EditorAssistant(tmp_path).analyze(np.full((47, 24, 3), (50, 90, 40), np.uint8))
    assert prediction is None


def test_empty_duplicate_supported(tmp_path):
    image = np.full((40, 30, 3), (50, 90, 40), np.uint8)
    put(tmp_path, 'empty', 'empty', image)
    prediction, known = EditorAssistant(tmp_path).analyze(image)
    assert prediction.kind == 'empty' and prediction.label == 'empty'
    assert prediction.automatic and not known


def test_missing_filter_never_hides_empty_or_current_suggestion():
    values = filtered_choices({'Ks', 'Ah'}, True)
    assert values[0] == EMPTY_CHOICE
    assert display_choice('Ks') not in values
    assert display_choice('Ah') not in values
    assert len(values) == 51
    assert display_choice('Ks') in filtered_choices({'Ks'}, True, 'Ks')
    assert filtered_choices(set(CARD_CHOICES.values()), True) == [EMPTY_CHOICE]
    assert len(filtered_choices({'Ks'}, False)) == 53


def test_accept_known_is_non_training_and_reversible(tmp_path):
    album = Album(tmp_path/'inbox', tmp_path/'templates')
    record = album.add(np.full((60, 80, 3), 120, np.uint8), {'hero1': [0, 0, .5, .5]}, {})
    record = album.accept_known(record['id'], 'hero1', 'card', 'Ks', .97, 'template matching', 0)
    assert record['items']['hero1']['status'] == 'reused'
    assert record['items']['hero1']['export'] is None
    assert record['items']['hero1']['recognition']['automatic']
    assert not album.templates.exists()
    resumed = Album(album.folder, album.templates).load(record['id'])
    assert resumed['items']['hero1']['label'] == 'Ks'
    record = album.annotate(record['id'], 'hero1', 'card', 'Ah')
    assert record['items']['hero1']['status'] == 'exported'
    assert 'recognition' not in record['items']['hero1']
    assert list((album.templates/'card/Ah').glob('*.png'))


def test_accept_known_rejects_low_confidence_and_stale_state(tmp_path):
    album = Album(tmp_path/'inbox', tmp_path/'templates')
    record = album.add(np.full((60, 80, 3), 120, np.uint8), {'hero1': [0, 0, .5, .5]}, {})
    with pytest.raises(ValueError):
        album.accept_known(record['id'], 'hero1', 'card', 'Ks', .80, 'weak', 0)
    with pytest.raises(ValueError):
        album.accept_known(record['id'], 'hero1', 'card', 'Ks', .97, 'stale', 2)
    album.annotate(record['id'], 'hero1', 'card', 'Ah')
    with pytest.raises(ValueError):
        album.accept_known(record['id'], 'hero1', 'card', 'Ks', .97, 'overwrite', 1)


def test_human_reuse_preserves_adjusted_crop(tmp_path):
    album = Album(tmp_path/'inbox', tmp_path/'templates')
    record = album.add(np.full((60, 80, 3), 120, np.uint8), {'hero1': [0, 0, .5, .5]}, {})
    rect = [.1, .1, .4, .4]
    record = album.accept_known(record['id'], 'hero1', 'card', 'Ks', 1., 'human confirmed existing', 0, automatic=False, rect=rect)
    assert record['items']['hero1']['rect'] == rect
    assert not record['items']['hero1']['recognition']['automatic']
    assert not album.templates.exists()
