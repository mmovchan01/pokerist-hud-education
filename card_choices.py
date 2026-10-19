"""Card-picker labels and standard two-colour deck presentation (no GUI)."""
from screenshot_album import CARD_LABELS

SYMBOLS = {'s': '♠', 'h': '♥', 'd': '♦', 'c': '♣'}
EMPTY_CHOICE = 'Пусто'
# Known cards stay in the picker by default: hiding them made it impossible to add
# another photo of, for example, 3♥ once one sample existed.
MISSING_ONLY_DEFAULT = False
CARD_CHOICES = {EMPTY_CHOICE: 'empty', **{
    f'{card[0]}{SYMBOLS[card[1]]}  ({card})': card for card in CARD_LABELS}}


# Dark-theme friendly: red suits stay red, black suits become light text.
RED_SUIT, BLACK_SUIT, NEUTRAL = '#ff6b6b', '#e8f3f7', '#8fa9b8'


def choice_color(display):
    card = CARD_CHOICES.get(display)
    if card in CARD_LABELS:
        return RED_SUIT if card[1] in 'hd' else BLACK_SUIT
    return NEUTRAL


def display_choice(label):
    return next((text for text, code in CARD_CHOICES.items() if code == label), '')


def resolve_choice(kind, display):
    if kind == 'card':
        label = CARD_CHOICES.get(display, display)
        return ('empty', 'empty') if label == 'empty' else ('card', label)
    return kind, display


def filtered_choices(known, missing_only=False, keep_label=None):
    """Never hide empty or a current suggestion/correction, even in missing mode."""
    return [text for text, label in CARD_CHOICES.items()
            if label == 'empty' or not missing_only or label not in known or label == keep_label]
