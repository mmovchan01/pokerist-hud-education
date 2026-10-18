"""Presentation-independent review labels, progress and library inventory."""
from collections import Counter

from screenshot_album import CARD_LABELS
from vision import TemplateBank

STATUS_LABELS = {'pending': 'Нужно разобрать', 'exported': 'Образец сохранён',
                 'reused': 'Уже в базе', 'skipped': 'Пропущено'}
KIND_LABELS = {'Карта': 'card', 'Пустое место': 'empty', 'Рубашка': 'back', 'Цифра / символ': 'glyph'}


def region_title(name):
    if name.startswith('hero'):
        return 'Ваша карта '+name[4:]
    if name.startswith('board'):
        return 'Борд · карта '+name[5:]
    if name.startswith('oppstack'):
        return 'Стек соперника '+name[8:]
    if name.startswith('opp'):
        return 'Карты соперника '+name[3:]
    return {'pot': 'Банк', 'stack': 'Ваш стек', 'call': 'Сумма колла'}.get(name, 'Дополнительная вырезка')


def eligible_items(record, cards_only=True):
    return [name for name, item in record['items'].items()
            if not cards_only or name.startswith(('hero', 'board')) or item['kind'] == 'card']


def progress(record, cards_only=True):
    items = eligible_items(record, cards_only)
    return sum(record['items'][name]['status'] != 'pending' for name in items), len(items)


def template_inventory(folder):
    bank = TemplateBank(folder)
    counts = Counter(label for kind, label, _ in bank.samples if kind == 'card' and label in CARD_LABELS)
    paths = {label: [] for label in CARD_LABELS}
    for kind, label, image in bank.samples:
        if kind == 'card' and label in paths:
            paths[label].append(bank.sample_paths[id(image)])
    return counts, paths
