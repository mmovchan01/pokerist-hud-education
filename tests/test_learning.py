"""Plain-language verdicts, quiz lessons, progress and the recognition report."""
import json
import random
import re
from types import SimpleNamespace

import pytest

from lessons import LESSONS, PASS_MARK, QUESTIONS_PER_LESSON, Progress, make_question, make_session
from plain import GLOSSARY, glossary_text, make_verdict, pot_line
from recognition_report import build_report, format_report
from setup_support import ROOT

# Words the beginner-facing text must never show. They stay in the «Подробнее» panel only.
JARGON = re.compile(r'\b(EV|MC|SPR|pot odds|п\.п\.|fold|side pot|outs|OESD|Monte Carlo|Чен|равномерн)\b', re.IGNORECASE)


def fake_result(equity, error, pot_odds, made='Пара', preflop='Премиум; Чен 10. Хедз-ап.', iterations=3000):
    return SimpleNamespace(
        equity=SimpleNamespace(equity=equity/100, error95=error/100, iterations=iterations),
        pot_odds=pot_odds, made=made, preflop=preflop)


def fake_state(call=100, pot=300, board=('Qh', '7s', '2d'), stack=1000, opponents=2):
    return SimpleNamespace(call=call, pot=pot, board=board, stack=stack, opponents=opponents)


def test_verdict_call_when_equity_clearly_above_need():
    verdict = make_verdict(fake_state(), fake_result(equity=62, error=2, pot_odds=25))
    assert verdict.action == 'Колл' and verdict.tone == 'good'
    assert verdict.headline == 'Колл выгоден'


def test_verdict_fold_when_equity_clearly_below_need():
    verdict = make_verdict(fake_state(), fake_result(equity=12, error=2, pot_odds=40))
    assert verdict.action == 'Пас' and verdict.tone == 'bad'


def test_verdict_is_neutral_inside_error_band():
    verdict = make_verdict(fake_state(), fake_result(equity=33, error=4, pot_odds=33))
    assert verdict.action == 'Спорно'


def test_verdict_free_check_when_nothing_to_call():
    verdict = make_verdict(fake_state(call=0), fake_result(equity=55, error=2, pot_odds=0))
    assert verdict.action == 'Чек'
    assert all(label != 'Нужно для колла' for label, _ in verdict.facts)


def test_preflop_verdict_shows_hand_category_not_board_hand():
    verdict = make_verdict(fake_state(board=()), fake_result(equity=60, error=2, pot_odds=25, preflop='Сильная; Чен 8. Хедз-ап.'))
    assert ('Стартовая рука', 'Сильная') in verdict.facts


@pytest.mark.parametrize('equity,error,odds', [(62, 2, 25), (12, 2, 40), (33, 4, 33)])
def test_verdict_text_has_no_jargon(equity, error, odds):
    verdict = make_verdict(fake_state(), fake_result(equity=equity, error=error, pot_odds=odds))
    text = ' '.join([verdict.headline, verdict.summary, verdict.caveat, *[f'{a} {b}' for a, b in verdict.facts]])
    assert not JARGON.search(text), text


def test_glossary_terms_are_unique_and_explained():
    names = [name for name, _ in GLOSSARY]
    assert len(names) == len(set(names))
    assert all(len(text) > 20 for _, text in GLOSSARY)
    assert 'доплатить' in glossary_text('Колл (уравнять)').lower()
    with pytest.raises(KeyError):
        glossary_text('Несуществующий термин')


def test_pot_line_uses_plain_words_and_plain_numbers():
    line = pot_line(SimpleNamespace(pot=300, call=100, stack=2000, opponents=3))
    assert 'доплатить 100 ' in line and 'соперников 3' in line and 'стек 2K' in line
    assert '.00' not in line


@pytest.mark.parametrize('lesson', [item.id for item in LESSONS])
def test_every_lesson_builds_consistent_questions(lesson):
    questions = make_session(lesson, seed=11)
    assert len(questions) == QUESTIONS_PER_LESSON
    for question in questions:
        assert 2 <= len(question.options) <= 4
        assert len(set(question.options)) == len(question.options)
        assert 0 <= question.correct < len(question.options)
        assert question.explanation.strip()


def test_sessions_are_reproducible_for_a_seed():
    first = make_session('names', seed=5)
    second = make_session('names', seed=5)
    assert [(q.options, q.correct) for q in first] == [(q.options, q.correct) for q in second]


def test_names_lesson_answer_matches_explanation():
    for seed in range(20):
        question = make_question('names', random.Random(seed))
        answer = question.options[question.correct]
        assert answer.lower() in question.explanation.lower()


def test_outs_lesson_answer_is_the_count_stated_in_explanation():
    for seed in range(10):
        question = make_question('outs', random.Random(seed))
        count = question.options[question.correct]
        assert f'аутов: {count}.' in question.explanation


def test_odds_lesson_is_a_clear_call_or_fold_decision():
    for seed in range(3):
        question = make_question('odds', random.Random(seed))
        assert set(question.options) == {'Колл', 'Пас'}
        assert ('ваш шанс выше' in question.explanation.lower()) == (question.options[question.correct] == 'Колл')


def test_progress_records_best_and_survives_broken_file(tmp_path):
    path = tmp_path/'progress.json'
    progress = Progress(path)
    assert not progress.passed('odds')
    progress.record('odds', 3)
    progress.record('odds', 2)
    assert progress.best('odds') == 3 and not progress.passed('odds')
    progress.record('odds', PASS_MARK)
    assert progress.passed('odds')
    assert json.loads(path.read_text(encoding='utf-8'))['odds']['attempts'] == 3
    path.write_text('не json', encoding='utf-8')
    assert Progress(path).best('odds') == 0


def test_report_on_shipped_profile_is_honest():
    report = build_report(ROOT/'profiles'/'pokerist_3d_1280x719'/'templates')
    assert len(report.cards_known) == 13 and len(report.cards_missing) == 39
    assert set(report.glyphs_missing) == {'4', '7', 'M', 'B'}
    checked = report.correct+report.wrong+report.unsure
    assert checked + report.untested == 20
    assert report.wrong == 0
    text = format_report(report)
    assert 'узнаёт 13 из 52' in text and 'на новых кадрах точность будет ниже' in text


def test_report_on_empty_folder_explains_what_to_do(tmp_path):
    text = format_report(build_report(tmp_path))
    assert 'узнаёт 0 из 52' in text
    assert 'Проверка точности пока невозможна' in text
    assert 'Редактор снимков' in text
