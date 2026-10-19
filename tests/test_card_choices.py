from card_choices import (CARD_CHOICES, EMPTY_CHOICE, choice_color,
                          display_choice, filtered_choices, resolve_choice)
from screenshot_album import Album
import numpy as np


def test_empty_first_and_all_cards_present():
    assert next(iter(CARD_CHOICES)) == EMPTY_CHOICE
    assert len(CARD_CHOICES) == 53
    assert len(set(CARD_CHOICES.values())) == 53
    assert resolve_choice('card', EMPTY_CHOICE) == ('empty', 'empty')
    assert display_choice('empty') == EMPTY_CHOICE


def test_standard_suit_colours_and_selection_mapping():
    for code in ('Ah', 'Kd', 'Qs', 'Jc'):
        display = display_choice(code)
        assert resolve_choice('card', display) == ('card', code)
        assert choice_color(display) == ('#ff6b6b' if code[1] in 'hd' else '#e8f3f7')
    assert choice_color(EMPTY_CHOICE) == '#8fa9b8'
    assert resolve_choice('glyph', '.') == ('glyph', '.')
    assert resolve_choice('back', 'back') == ('back', 'back')


def test_empty_choice_exports_as_empty_not_card(tmp_path):
    album = Album(tmp_path/'inbox', tmp_path/'templates')
    record = album.add(np.full((60, 80, 3), 120, np.uint8),
                       {'hero1': [0, 0, .5, .5]}, {})
    kind, label = resolve_choice('card', EMPTY_CHOICE)
    record = album.annotate(record['id'], 'hero1', kind, label)
    assert record['items']['hero1']['kind'] == 'empty'
    assert record['items']['hero1']['export'].startswith('empty/empty/')
    assert not (album.templates/'card').exists()


def test_known_cards_hidden_by_default_but_always_reachable():
    """Known cards are recognized automatically; the full list must remain available when needed."""
    from card_choices import MISSING_ONLY_DEFAULT
    assert MISSING_ONLY_DEFAULT is True
    known = {'3h'}
    assert display_choice('3h') not in filtered_choices(known, MISSING_ONLY_DEFAULT)
    assert display_choice('3h') in filtered_choices(known, False)
    assert display_choice('Ah') in filtered_choices(known, MISSING_ONLY_DEFAULT)
