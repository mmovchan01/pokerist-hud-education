import math

import pytest

from poker_coach import (Coach, chen_score, draws, made_hand, monte_carlo,
                         validate_cards)
from vision import TableState


def state(hero=('Ah', 'Kh'), board=('Qh', 'Jh', '2c'), pot=30000, call=10000, opponents=2):
    return TableState(hero, board, pot, 100000, call, opponents, 100000)


def test_chen():
    assert chen_score(('As', 'Ah')) == 20
    assert chen_score(('Ks', 'Kh')) == 16
    assert chen_score(('7c', '7s')) == 7
    assert chen_score(('Ah', 'Kh')) == 12
    assert chen_score(('7c', '2d')) == -1


def test_combo_union():
    report = draws(('Ah', 'Kh'), ('Qh', 'Jh', '2c'))
    assert len(report.groups['Флеш-дро']) == 9
    assert len(report.groups['Гатшот']) == 4
    assert len(report.outs) == 18  # 9 + 4 + 6 - Th
    assert len(report.outs) == len(set(report.outs))
    assert report.hit_percent == pytest.approx((1-math.comb(29, 2)/math.comb(47, 2))*100)
    assert report.rule_percent == 72


def test_oesd():
    d = draws(('9s', '8s'), ('7d', '6c', 'Kh'))
    assert len(d.outs) == 8
    assert any('OESD' in label for label in d.groups)


def test_wheel_gutshot():
    d = draws(('Ah', '4h'), ('2s', '3c', 'Kd'))
    assert len(d.groups['Гатшот']) == 4
    assert {c[0] for c in d.groups['Гатшот']} == {'5'}


def test_double_gutshot_not_oesd():
    d = draws(('8h', '6c'), ('4s', '5d', 'Tc', '2d'))
    # 4568 needs 7; 2456 needs 3: two inside gaps, not open-ended.
    assert len(d.groups['Двойной гатшот']) == 8


def test_no_common_board_draw():
    d = draws(('2h', '2c'), ('6s', '7d', '8c', '9h'))
    assert not any('стрит' in name or 'Гатшот' in name for name in d.groups)


def test_no_false_improvement_of_made_flush():
    d = draws(('Ah', 'Kh'), ('Qh', 'Jh', '2h'))
    assert not d.outs


def test_made_hand():
    assert made_hand(('Ah', 'Kd'), ('Ac', '5s', '2s')) == 'Топ-пара с топ-кикером'
    assert made_hand(('5h', '5d'), ('5c', 'Ks', '2s')) == 'Сет'
    assert made_hand(('Ah', 'Ad'), ('Kc', '5s', '2s')) == 'Оверпара'


def test_ties_are_split_not_wins():
    result = monte_carlo(('2c', '3d'), ('As', 'Ks', 'Qs', 'Js', 'Ts'), 2, 2000, 4)
    assert result.equity == pytest.approx(1/3)
    assert result.error95 < 1e-6


def test_nuts_river():
    r = monte_carlo(('As', 'Ks'), ('Qs', 'Js', 'Ts', '2h', '3d'), 8, 2000, 17)
    assert r.equity == 1


def test_multiway():
    one = monte_carlo(('As', 'Ad'), (), 1, 3000, 42)
    four = monte_carlo(('As', 'Ad'), (), 4, 3000, 42)
    assert .79 < one.equity < .90
    assert .47 < four.equity < .63
    assert four.equity < one.equity


def test_ev_math():
    r = Coach(seed=42).analyze(state())
    assert r.pot_odds == 25
    assert r.ev == pytest.approx(r.equity.equity*40000-10000)
    assert r.ev_pot_percent == pytest.approx(r.ev/300)
    assert r.spr == pytest.approx(100000/30000)


def test_zero_bank_and_check():
    r = Coach(seed=42).analyze(state(pot=0, call=0))
    assert r.pot_odds == 0
    assert r.spr is None
    assert r.ev_pot_percent is None
    assert 'чек' in r.recommendation


@pytest.mark.parametrize('hero,board', [(('Ah', 'Ah'), ()), (('Ah', 'Kd'), ('Ah', '2c', '3c')), (('XX', 'Kd'), ())])
def test_invalid_cards(hero, board):
    with pytest.raises(ValueError):
        validate_cards(hero, board)


@pytest.mark.parametrize('pot,call', [(-1, 0), (100, -1), (float('nan'), 1), (100, 100001)])
def test_invalid_money(pot, call):
    with pytest.raises(ValueError):
        Coach().analyze(state(pot=pot, call=call))
