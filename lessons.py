"""Short quiz lessons. Every correct answer is computed by the same math the HUD uses.

Pure Python: no tkinter, no screen. Progress lives in a small JSON file next to
the project (ignored by git). A lesson is passed with at least PASS_MARK correct
answers out of QUESTIONS_PER_LESSON.
"""
import json
import random
from dataclasses import dataclass
from pathlib import Path

from treys import Evaluator

from poker_coach import DECK, ENCODED, chen_score, draws, monte_carlo, preflop
from ui_text import card_text

QUESTIONS_PER_LESSON = 5
PASS_MARK = 4
SIMULATIONS = 2000          # lessons use the minimum allowed precision to stay fast
MIN_GAP_PERCENT = 8         # equity vs pot odds must differ this much, so the answer is clear

HAND_NAMES = {1: 'Стрит-флеш', 2: 'Каре', 3: 'Фулл-хаус', 4: 'Флеш', 5: 'Стрит',
              6: 'Тройка', 7: 'Две пары', 8: 'Пара', 9: 'Старшая карта'}
HAND_HINTS = {
    'Стрит-флеш': 'пять карт по порядку одной масти.',
    'Каре': 'четыре карты одного ранга.',
    'Фулл-хаус': 'тройка и пара одновременно.',
    'Флеш': 'пять карт одной масти, не по порядку.',
    'Стрит': 'пять карт по порядку, масти разные.',
    'Тройка': 'три карты одного ранга.',
    'Две пары': 'две разные пары.',
    'Пара': 'две карты одного ранга.',
    'Старшая карта': 'ни одной пары; побеждает самая высокая карта.',
}


@dataclass(frozen=True)
class Question:
    prompt: str
    hero: tuple
    board: tuple
    options: tuple
    correct: int
    explanation: str


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    intro: str


LESSONS = (
    Lesson('start', 'Сила стартовой руки',
           'До открытия стола у вас только две карты. Программа оценивает их баллом по шкале Чена: '
           'пары, высокие карты и карты одной масти повышают балл. Выберите руку, которая сильнее.'),
    Lesson('names', 'Названия комбинаций',
           'По семи картам (ваши две и пять на столе) собирается лучшая пятикарточная комбинация. '
           'Назовите её. Если сомневаетесь, сравните с подсказками в вариантах.'),
    Lesson('odds', 'Колл: шанс против цены',
           'Колл окупается, если ваш шанс выиграть банк не меньше доли, которую стоит колл: '
           'колл ÷ (банк + колл). Посчитайте, выгоден ли колл.'),
    Lesson('outs', 'Аутсы: сколько карт помогут',
           'Аут — карта, которая улучшает руку. Флеш-дро на флопе даёт 9 аутов, стрит-дро с дыркой — 4, '
           'двустороннее стрит-дро — 8. Одна карта считается один раз, даже если подходит под два дро.'),
)


def hand_text(cards):
    return ' '.join(card_text(c) for c in cards)


def _shuffled(rng, correct_value, others):
    options = [correct_value, *others]
    rng.shuffle(options)
    return options


def _start_question(rng):
    while True:
        first, second = rng.sample(DECK, 2), rng.sample(DECK, 2)
        if set(first) & set(second):
            continue
        a, b = chen_score(first), chen_score(second)
        if abs(a-b) >= 2:
            break
    stronger = first if a > b else second
    options = [hand_text(first), hand_text(second)]
    rng.shuffle(options)
    explanation = (f'{hand_text(first)}: балл {a}, {preflop(first, 1).split(";")[0].lower()}. '
                   f'{hand_text(second)}: балл {b}, {preflop(second, 1).split(";")[0].lower()}. '
                   f'Сильнее {hand_text(stronger)}: чем выше балл, тем лучше рука.')
    return Question('Какая стартовая рука сильнее?', (), (), tuple(options),
                    options.index(hand_text(stronger)), explanation)


def _names_question(rng):
    evaluator = Evaluator()
    hero_pool = rng.sample(DECK, 7)
    hero, board = tuple(hero_pool[:2]), tuple(hero_pool[2:])
    score = evaluator.evaluate([ENCODED[c] for c in board], [ENCODED[c] for c in hero])
    name = HAND_NAMES[evaluator.get_rank_class(score)]
    wrong = [n for n in HAND_NAMES.values() if n != name]
    others = rng.sample(wrong, 3)
    options = _shuffled(rng, name, others)
    explanation = (f'Лучшая комбинация: {name.lower()} — {HAND_HINTS[name]} '
                   'Проверьте по семи картам: сначала ищите одинаковые ранги и масти, потом порядок.')
    return Question('Какая комбинация у героя на этом столе?', hero, board,
                    tuple(options), options.index(name), explanation)


def _odds_question(rng):
    while True:
        cards = rng.sample(DECK, 2+rng.choice([3, 4]))
        hero, board = tuple(cards[:2]), tuple(cards[2:])
        pot = rng.choice([100, 150, 200, 300, 400])
        call = rng.choice([50, 100, 150])
        need = call/(pot+call)*100
        equity = monte_carlo(hero, board, 1, SIMULATIONS, rng.randint(0, 10**9)).equity*100
        if abs(equity-need) >= MIN_GAP_PERCENT:
            break
    good = equity > need
    verdict = 'Колл' if good else 'Пас'
    options = _shuffled(rng, 'Колл', ['Пас'])
    explanation = (f'Нужный шанс = колл ÷ (банк + колл) = {call} ÷ ({pot} + {call}) ≈ {need:.0f}%. '
                   f'Ваш шанс примерно {equity:.0f}%. '
                   + ('Ваш шанс выше — колл окупается.' if good else
                      'Ваш шанс ниже — колл не окупается, лучше пас.'))
    return Question(f'Банк {pot}, колл {call}. Играть колл или пас?', hero, board,
                    tuple(options), options.index(verdict), explanation)


def _outs_question(rng):
    for _ in range(2000):
        cards = rng.sample(DECK, 5)
        hero, board = tuple(cards[:2]), tuple(cards[2:])
        result = draws(hero, board)
        if 'Оверкарты (условные ауты на пару)' in result.groups or not result.groups:
            continue
        correct = len(result.outs)
        if correct < 4:
            continue
        pool = [v for v in (correct-2, correct-1, correct+1, correct+2, correct+4) if v > 0 and v != correct]
        others = rng.sample(pool, 3)
        options = _shuffled(rng, str(correct), [str(v) for v in others])
        explanation = (f'{result.description}. Всего уникальных аутов: {correct}. '
                       'Карту, которая подходит под два дро, считайте один раз.')
        return Question('Сколько карт из колоды улучшат руку на следующей улице?', hero, board,
                        tuple(options), options.index(str(correct)), explanation)
    raise RuntimeError('не удалось подобрать вопрос')


def make_question(lesson_id, rng):
    """Build one question for a lesson. Deterministic for a given rng state."""
    if lesson_id == 'start':
        return _start_question(rng)
    if lesson_id == 'names':
        return _names_question(rng)
    if lesson_id == 'odds':
        return _odds_question(rng)
    if lesson_id == 'outs':
        return _outs_question(rng)
    raise KeyError(lesson_id)


def make_session(lesson_id, seed=None):
    rng = random.Random(seed)
    return [make_question(lesson_id, rng) for _ in range(QUESTIONS_PER_LESSON)]


class Progress:
    """Best result per lesson, stored as JSON. A missing or broken file means nothing passed yet."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def best(self, lesson_id):
        return self.data.get(lesson_id, {}).get('best', 0)

    def passed(self, lesson_id):
        return self.best(lesson_id) >= PASS_MARK

    def record(self, lesson_id, correct):
        entry = self.data.setdefault(lesson_id, {'best': 0, 'attempts': 0})
        entry['best'] = max(entry['best'], correct)
        entry['attempts'] = entry.get('attempts', 0)+1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
