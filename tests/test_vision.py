import json

import cv2
import numpy as np
import pytest

from screen import Rect, load_config, preprocess
from vision import (Reading, Recognizer, Stabilizer, TableState, TemplateBank,
                    color_profile, match_score, parse_amount)


@pytest.mark.parametrize('text,expected', [('1.5K', 1500), ('1,5K', 1500), ('1,234', 1234),
    ('1.234', 1234), ('1,234.50', 1234.5), ('1.234,50', 1234.5),
    ('2M', 2000000), ('3B', 3000000000), ('0', 0), ('12,345,678', 12345678), ('0.25K', 250)])
def test_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize('text', ['', 'K', '12x', '-2', '1..2', '1,23,4', '1,234,'])
def test_bad_amount(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def sample_state():
    return TableState(('Ah', 'Kd'), (), 1000, 10000, 100, 1, 10000)


def test_temporal_debounce():
    s = Stabilizer()
    state = sample_state()
    assert s.update(state, 0) is None
    assert s.update(state, .20) is None
    assert s.update(state, .275) is state
    assert s.update(None, .55) is None
    assert s.update(state, .825) is None
    assert s.update(state, 1.1) is state
    state.call = 200
    assert s.update(state, 1.375) is None


def test_normalized_rect():
    r = Rect(.1, .2, .2, .3)
    assert r.pixels(1000, 500) == (100, 100, 200, 150)
    assert r.crop(np.zeros((500, 1000, 3), dtype=np.uint8)).shape == (150, 200, 3)


def test_matching_multiscale():
    rng = np.random.default_rng(42)
    template = rng.integers(0, 2, (30, 20), dtype=np.uint8)*255
    image = np.zeros((60, 60), dtype=np.uint8)
    image[10:43, 12:34] = cv2.resize(template, (22, 33), interpolation=cv2.INTER_NEAREST)
    score, rect = match_score(image, template)
    assert score > .99
    assert rect == (12, 10, 22, 33)


def test_hsv_four_colors():
    for bgr, idx in [((0, 0, 255), 0), ((255, 0, 0), 1), ((0, 255, 0), 2), ((0, 0, 0), 3)]:
        image = np.full((30, 30, 3), bgr, dtype=np.uint8)
        assert color_profile(image)[idx] == 1


def test_bank_and_card(tmp_path):
    folder = tmp_path/'card'/'Ah'
    folder.mkdir(parents=True)
    image = np.full((100, 70, 3), 255, np.uint8)
    cv2.putText(image, 'A', (5, 32), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 200), 2)
    cv2.circle(image, (20, 50), 8, (0, 0, 200), -1)
    assert cv2.imwrite(str(folder/'sample.png'), image)
    bank = TemplateBank(tmp_path)
    result = Recognizer({}, bank).symbol(image, ('card', 'empty'))
    assert result.value == 'Ah'
    assert result.confidence >= .84


def test_uniform_empty(tmp_path):
    folder = tmp_path/'empty'/'empty'
    folder.mkdir(parents=True)
    image = np.full((100, 70, 3), (35, 90, 35), np.uint8)
    cv2.imwrite(str(folder/'sample.png'), image)
    result = Recognizer({}, TemplateBank(tmp_path)).symbol(image, ('card', 'empty'))
    assert result.status == 'empty'


def test_missing_templates_not_zero(tmp_path):
    r = Recognizer({}, TemplateBank(tmp_path))
    image = np.zeros((40, 100, 3), dtype=np.uint8)
    assert r.number(image).status == 'unknown'
    assert r.symbol(image, ('card',)).status == 'unknown'


def test_glyph_nms(tmp_path):
    # Equal line height in glyph crops preserves punctuation geometry.
    glyphs = []
    for label in '12K':
        image = np.zeros((40, 30, 3), np.uint8)
        cv2.putText(image, label, (2, 31), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        folder = tmp_path/'glyph'/label
        folder.mkdir(parents=True)
        cv2.imwrite(str(folder/'sample.png'), image)
        glyphs.append(image)
    roi = np.concatenate(glyphs, axis=1)
    result = Recognizer({'confidence': .80, 'margin': .01}, TemplateBank(tmp_path)).number(roi)
    assert result.status == 'known'
    assert result.value == 12000


def mocked_recognizer(tmp_path, monkeypatch, cards, numbers=(1000, 10000, 100), opps=1):
    names = ['hero1', 'hero2', *[f'board{i}' for i in range(1, 6)], 'pot', 'stack', 'call']
    config = {'rois': {n: [0, 0, 1, 1] for n in names}}
    for i in range(opps):
        config['rois'][f'opp{i+1}'] = [0, 0, 1, 1]
    recognizer = Recognizer(config, TemplateBank(tmp_path))
    card_iter = iter(cards+[Reading('back', .99, 'known')]*opps)
    number_iter = iter(Reading(n, .99, 'known') for n in numbers)
    monkeypatch.setattr(recognizer, 'symbol', lambda *args: next(card_iter))
    monkeypatch.setattr(recognizer, 'number', lambda *args: next(number_iter))
    return recognizer


def known(value):
    return Reading(value, .99, 'known')


def empty():
    return Reading(None, .99, 'empty')


def test_full_table_assembly(tmp_path, monkeypatch):
    cards = list(map(known, ['Ah', 'Kd', '2c', '3c', '4s']))+[empty(), empty()]
    r = mocked_recognizer(tmp_path, monkeypatch, cards, opps=2)
    state, readings, error = r.read(np.zeros((100, 100, 3), np.uint8))
    assert not error
    assert state.hero == ('Ah', 'Kd')
    assert state.board == ('2c', '3c', '4s')
    assert state.opponents == 2
    assert not state.effective_known
    assert state.effective_stack == 10000


@pytest.mark.parametrize('cards', [
    [known('Ah'), known('Ah')]+[empty()]*5,
    [known('Ah'), known('Kd'), known('2c')]+[empty()]*4,
    [known('Ah'), known('Kd'), empty(), known('2c'), known('3c'), known('4c'), empty()],
    [known('Ah'), Reading()]+[empty()]*5,
])
def test_invalid_table_rejected(tmp_path, monkeypatch, cards):
    r = mocked_recognizer(tmp_path, monkeypatch, cards)
    state, readings, error = r.read(np.zeros((100, 100, 3), np.uint8))
    assert state is None
    assert error


def test_manual_opponents_without_rois(tmp_path, monkeypatch):
    cards = [known('Ah'), known('Kd')]+[empty()]*5
    r = mocked_recognizer(tmp_path, monkeypatch, cards, opps=0)
    state, _, error = r.read(np.zeros((100, 100, 3), np.uint8), override=4)
    assert not error
    assert state.opponents == 4


def test_unknown_white_card_not_empty(tmp_path):
    folder = tmp_path/'empty'/'empty'
    folder.mkdir(parents=True)
    background = np.full((100, 70, 3), 255, np.uint8)
    cv2.imwrite(str(folder/'sample.png'), background)
    card = background.copy()
    cv2.putText(card, 'Q', (5, 32), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    result = Recognizer({}, TemplateBank(tmp_path)).symbol(card, ('card', 'empty'))
    assert result.status == 'unknown'
