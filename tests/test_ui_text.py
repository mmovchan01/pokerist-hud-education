"""Plain-language labels and colour roles: pure functions, no display needed."""
import pytest

from poker_coach import fmt
from ui_text import (KIND_TITLES, ROI_TITLES, card_text, ev_tone, kind_choice, kind_from_choice,
                     recommendation_tone, roi_choice, roi_from_choice, short_name, signed_money)

ROI_KEYS = ['hero1', 'hero2', *[f'board{i}' for i in range(1, 6)], 'pot', 'stack', 'call',
            *[f'opp{i}' for i in range(1, 9)], *[f'oppstack{i}' for i in range(1, 9)]]


def test_every_roi_key_has_a_human_title():
    # calibrator.ROI_NAMES is the source of truth for dropdowns; titles must cover it.
    assert set(ROI_KEYS) <= set(ROI_TITLES)


@pytest.mark.parametrize('name', ROI_KEYS)
def test_roi_choice_round_trip_keeps_config_key(name):
    choice = roi_choice(name)
    assert choice.startswith(name + ' — ')
    assert roi_from_choice(choice) == name


def test_unknown_roi_still_round_trips():
    assert roi_choice('custom') == 'custom'
    assert roi_from_choice('custom') == 'custom'


@pytest.mark.parametrize('kind', list(KIND_TITLES))
def test_kind_choice_round_trip(kind):
    assert kind_from_choice(kind_choice(kind)) == kind


def test_card_text_uses_ten_and_suit_symbols():
    assert card_text('Ah') == 'A♥'
    assert card_text('Td') == '10♦'
    assert card_text('2s') == '2♠'
    assert card_text('9c') == '9♣'


@pytest.mark.parametrize('text,tone', [
    ('Колл +EV в модели вскрытия', 'good'),
    ('Колл −EV в модели вскрытия', 'bad'),
    ('Погранично: погрешность MC перекрывает порог', 'warn'),
    ('Бесплатный чек доступен; EV ставки не оценён', 'info'),
    ('Что-то другое', 'muted'),
])
def test_recommendation_tone_matches_coach_wording(text, tone):
    assert recommendation_tone(text) == tone


def test_coach_recommendations_are_all_classified():
    # Keep the colour mapping in sync with the strings poker_coach really emits.
    from poker_coach import Coach
    from vision import TableState
    state = TableState(('Ah', 'Kh'), ('Qh', 'Jh', '2c'), 30000, 100000, 10000, 2, 100000)
    result = Coach(2000, 3).analyze(state)  # a call is owed, so it is never the 'free check' text
    assert recommendation_tone(result.recommendation) in {'good', 'bad', 'warn'}


def test_ev_tone_and_signed_money():
    assert ev_tone(1.5) == 'good'
    assert ev_tone(-0.01) == 'bad'
    assert ev_tone(0) == 'muted'
    assert signed_money(1200, fmt) == '+1.20K'
    assert signed_money(-850, fmt) == '−850.00'
    assert signed_money(0, fmt) == '+0.00'


def test_short_names_for_confidence_line():
    assert short_name('hero2') == 'карта 2'
    assert short_name('board5') == 'борд 5'
    assert short_name('pot') == 'pot'
