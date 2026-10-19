"""Plain-language labels and tiny pure helpers for the Tk interface.

Kept free of tkinter imports so the wording and colour rules are unit-tested
on any machine, including headless CI.
"""

SUIT_SYMBOLS = {'s': '♠', 'h': '♥', 'd': '♦', 'c': '♣'}

# Each ROI key stays the same (docs and config.json depend on it); the
# dropdown only adds a human explanation after the key.
ROI_TITLES = {
    'hero1': 'Ваша карта 1',
    'hero2': 'Ваша карта 2',
    **{f'board{i}': f'Карта борда {i}' for i in range(1, 6)},
    'pot': 'Банк',
    'stack': 'Ваш стек',
    'call': 'Сумма колла',
    **{f'opp{i}': f'Рубашка соперника {i}' for i in range(1, 9)},
    **{f'oppstack{i}': f'Стек соперника {i} (необязательно)' for i in range(1, 9)},
}

KIND_TITLES = {
    'card': 'карта',
    'glyph': 'цифра или знак',
    'back': 'рубашка',
    'empty': 'пустое место',
}


def roi_choice(name, titles=ROI_TITLES):
    """Dropdown text such as 'hero1 — Ваша карта 1'."""
    title = titles.get(name)
    return f'{name} — {title}' if title else name


def roi_from_choice(choice):
    return choice.split(' — ', 1)[0]


def kind_choice(kind):
    """Dropdown text such as 'card · карта'."""
    return f'{kind} · {KIND_TITLES[kind]}' if kind in KIND_TITLES else kind


def kind_from_choice(choice):
    return choice.split(' · ', 1)[0]


def short_name(name):
    """Compact names for the live confidence line."""
    if name.startswith('hero'):
        return f'карта {name[4:]}'
    if name.startswith('board'):
        return f'борд {name[5:]}'
    return name


def card_text(card):
    """'Ah' -> 'A♠'-style label with a 10 instead of T for readability."""
    rank = '10' if card[0] == 'T' else card[0]
    return rank + SUIT_SYMBOLS.get(card[1], '?')


def recommendation_tone(text):
    """Map the coach's recommendation sentence to a colour role."""
    if text.startswith('Колл +EV'):
        return 'good'
    if text.startswith('Колл −EV'):
        return 'bad'
    if text.startswith('Погранично'):
        return 'warn'
    if text.startswith('Бесплатный'):
        return 'info'
    return 'muted'


def ev_tone(ev):
    if ev > 0:
        return 'good'
    if ev < 0:
        return 'bad'
    return 'muted'


def signed_money(value, formatter):
    """'+1.20K' / '−850.00' using a typographic minus, formatter is fmt()."""
    sign = '+' if value >= 0 else '−'
    return sign + formatter(abs(value))
