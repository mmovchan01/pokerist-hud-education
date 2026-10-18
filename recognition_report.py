"""Plain-language report: which cards the recognizer knows and how well it does on its own samples.

The accuracy check is leave-one-out: each sample is recognized against all the
OTHER samples. It is optimistic (same screenshots, same lighting) and says
nothing about new frames. Kept free of tkinter so it is unit-tested headless.
"""
from dataclasses import dataclass, field
from pathlib import Path

from poker_coach import DECK
from ui_text import card_text
from vision import Recognizer, TemplateBank

GLYPHS_NEEDED = ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'K', 'M', 'B', '.', ',')
GLYPH_TITLES = {'.': 'точка', ',': 'запятая'}


@dataclass
class Report:
    cards_known: dict = field(default_factory=dict)    # card code -> number of samples
    cards_missing: list = field(default_factory=list)
    glyphs_known: dict = field(default_factory=dict)
    glyphs_missing: list = field(default_factory=list)
    correct: int = 0
    wrong: int = 0
    unsure: int = 0
    untested: int = 0       # cards with a single sample cannot be checked
    wrong_cards: list = field(default_factory=list)


class _Without:
    """Bank view that hides one sample; mirrors the TemplateBank API used by Recognizer."""

    def __init__(self, bank, skip):
        self.bank, self.skip = bank, skip
        self.sample_paths = bank.sample_paths

    def candidates(self, kind):
        return [(label, image) for index, (k, label, image) in enumerate(self.bank.samples)
                if k == kind and index != self.skip]


def build_report(templates_root):
    bank = TemplateBank(Path(templates_root))
    report = Report()
    counts = {}
    for kind, label, _ in bank.samples:
        if kind == 'card':
            counts[label] = counts.get(label, 0)+1
    report.cards_known = {code: counts[code] for code in DECK if code in counts}
    report.cards_missing = [code for code in DECK if code not in counts]
    glyph_counts = {}
    for kind, label, _ in bank.samples:
        if kind == 'glyph':
            glyph_counts[label] = glyph_counts.get(label, 0)+1
    report.glyphs_known = {g: glyph_counts[g] for g in GLYPHS_NEEDED if g in glyph_counts}
    report.glyphs_missing = [g for g in GLYPHS_NEEDED if g not in glyph_counts]

    recognizer_config = {}
    for index, (kind, label, image) in enumerate(bank.samples):
        if kind != 'card':
            continue
        if counts.get(label, 0) < 2:
            report.untested += 1
            continue
        reading = Recognizer(recognizer_config, _Without(bank, index)).symbol(image, ('card', 'empty'))
        if reading.value == label:
            report.correct += 1
        elif reading.value is None and reading.status == 'unknown':
            report.unsure += 1
        else:
            report.wrong += 1
            report.wrong_cards.append(label)
    return report


def _cards(codes):
    return ' '.join(card_text(code) for code in codes)


def _glyphs(labels):
    return ', '.join(GLYPH_TITLES.get(g, g) for g in labels)


def format_report(report):
    """Short plain-language text for a non-specialist; no metric names."""
    known, total = len(report.cards_known), len(DECK)
    lines = [f'Карты: программа узнаёт {known} из {total} видов.']
    if report.cards_missing:
        lines.append(f'Пока не знает: {_cards(report.cards_missing)}.')
    else:
        lines.append('Все 52 карты есть в базе образцов.')
    if report.glyphs_missing:
        lines.append(f'Цифры: не хватает {_glyphs(report.glyphs_missing)}. '
                     'Без них банк и стек могут не читаться.')
    else:
        lines.append('Цифры и знаки: все нужные есть.')

    checked = report.correct+report.wrong+report.unsure
    if checked == 0:
        lines.append('Проверка точности пока невозможна: нужно минимум по два образца одной карты.')
    else:
        lines.append(f'Проверка на ваших образцах: узнано верно {report.correct} из {checked}, '
                     f'ошибок {report.wrong}, программа не уверена в {report.unsure}.')
        lines.append('Проверка сделана на тех же снимках, на которых программа училась, поэтому '
                     'на новых кадрах точность будет ниже.')
    if report.wrong_cards:
        lines.append(f'Чаще путает: {_cards(sorted(set(report.wrong_cards)))}. '
                     'Добавьте примеры этих карт при других бликах и перекрытиях.')
    if report.untested:
        lines.append(f'Карт с одним образцом: {report.untested}. Для них проверка невозможна — '
                     'добавьте второй пример.')

    lines.append('')
    lines.append('Что сделать дальше:')
    if report.cards_missing:
        lines.append('1. Откройте «Редактор снимков» и добавьте по 2–3 примера для недостающих карт.')
    if report.glyphs_missing:
        lines.append('2. Для цифр выделите и подпишите банк и стек на снимках, где видны недостающие цифры.')
    if not report.cards_missing and not report.glyphs_missing and not report.wrong_cards:
        lines.append('База полная. Проверьте один кадр на шаге «Проверить один кадр».')
    return '\n'.join(lines)
