"""Hold'em mathematics: share-of-pot equity, structural outs and honest caveats.

All opponent hands are sampled uniformly WITHOUT replacement. This is not an
opponent-range solver, betting strategy or an EV model for a future raise.
"""
import math
import random
from dataclasses import dataclass

from treys import Card, Evaluator

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
DECK = tuple(r+s for r in RANKS for s in SUITS)
ENCODED = {c: Card.new(c) for c in DECK}
STRAIGHTS = [set(range(v, v+5)) for v in range(2, 11)] + [{14, 2, 3, 4, 5}]


def rank(card):
    return RANKS.index(card[0])+2


def validate_cards(hero, board):
    if len(hero) != 2 or len(board) not in (0, 3, 4, 5):
        raise ValueError('Требуется 2 карты героя и 0/3/4/5 карт борда')
    if any(c not in ENCODED for c in (*hero, *board)):
        raise ValueError('Формат карты: Ah, Td, 2c')
    if len(set((*hero, *board))) != len(hero)+len(board):
        raise ValueError('Карты не могут повторяться')


def chen_score(hero):
    a, b = sorted(map(rank, hero), reverse=True)
    base = {14: 10, 13: 8, 12: 7, 11: 6}.get(a, a/2)
    if a == b:
        return math.ceil(max(5, 2*base))
    if hero[0][1] == hero[1][1]:
        base += 2
    gap = a-b-1
    base -= 0 if gap <= 0 else {1: 1, 2: 2, 3: 4}.get(gap, 5)
    if gap <= 1 and a < 12:
        base += 1
    return math.ceil(base)


def preflop(hero, opponents):
    score = chen_score(hero)
    a, b = sorted(map(rank, hero), reverse=True)
    if score >= 10:
        category = 'Премиум'
    elif score >= 8:
        category = 'Сильная'
    elif (a == b or (hero[0][1] == hero[1][1] and a-b <= 3)):
        category = 'Спекулятивная / коннекторы'
    else:
        category = 'Слабая / мусорная'
    note = ('Мультивей: растёт ценность натсового потенциала; одна пара чаще проигрывает.'
            if opponents > 1 else 'Хедз-ап: высокие карты чаще сохраняют ценность на вскрытии.')
    return f'{category}; Чен {score}. {note} Чен не учитывает позицию и размер открытия.'


def made_hand(hero, board, evaluator=None):
    if not board:
        return 'Стартовая рука'
    evaluator = evaluator or Evaluator()
    score = evaluator.evaluate([ENCODED[c] for c in board], [ENCODED[c] for c in hero])
    cls = evaluator.get_rank_class(score)
    names = {1: 'Стрит-флеш', 2: 'Каре', 3: 'Фулл-хаус', 4: 'Флеш',
             5: 'Стрит', 6: 'Тройка', 7: 'Две пары', 8: 'Пара', 9: 'Старшая карта'}
    result = names[cls]
    hr, br = list(map(rank, hero)), list(map(rank, board))
    if cls == 6:
        result = 'Сет' if hr[0] == hr[1] and hr[0] in br else 'Трипс (возможна тройка на борде)'
    if cls == 8 and max(br) in hr and br.count(max(br)) == 1:
        kicker = hr[1] if hr[0] == max(br) else hr[0]
        best_kicker = max(r for r in range(2, 15) if r != max(br))
        result = 'Топ-пара' + (' с топ-кикером' if kicker == best_kicker else '')
    elif cls == 8 and hr[0] == hr[1] and hr[0] > max(br):
        result = 'Оверпара'
    return result


@dataclass
class DrawReport:
    groups: dict
    outs: tuple
    rule_percent: float
    hit_percent: float
    description: str


def draws(hero, board):
    """Exact enumeration of *structural* draw-completing cards, not clean outs.

    A flush/straight completion must involve a hero rank/suit not just improve
    the common board. Overcards are explicitly speculative. Flushes/straights
    already made are excluded from corresponding draw sets.
    """
    if len(board) not in (3, 4):
        return DrawReport({}, (), 0, 0, 'Дро считаются на флопе и терне.')
    known = set(hero+board)
    unseen = set(DECK)-known
    all_cards = hero+board
    all_ranks = set(map(rank, all_cards))
    board_ranks = set(map(rank, board))
    evaluator = Evaluator()
    current_class = evaluator.get_rank_class(evaluator.evaluate(
        [ENCODED[c] for c in board], [ENCODED[c] for c in hero]))
    groups = {}
    flush = set()
    for suit in SUITS:
        if current_class > 4 and sum(c[1] == suit for c in all_cards) == 4 and any(c[1] == suit for c in hero):
            flush |= {c for c in unseen if c[1] == suit}
    if flush:
        groups['Флеш-дро'] = flush
    straight = set()
    missing_ranks = set()
    if current_class > 5 and not any(run <= all_ranks for run in STRAIGHTS):
        for run in STRAIGHTS:
            missing = run-all_ranks
            # Require a private rank to contribute to the eventual straight.
            if len(missing) == 1 and (run & (set(map(rank, hero))-board_ranks)):
                missing_ranks |= missing
        straight = {c for c in unseen if rank(c) in missing_ranks}
    if straight:
        # Open-ended requires a contiguous four-card core with two endpoints.
        oesd = any(set(range(v, v+4)) <= all_ranks and
                   {v-1, v+4} <= missing_ranks for v in range(3, 11))
        label = 'OESD (двустороннее стрит-дро)' if oesd else ('Двойной гатшот' if len(missing_ranks) >= 2 else 'Гатшот')
        groups[label] = straight
    over = {c for c in unseen if rank(c) in {rank(h) for h in hero if rank(h) > max(board_ranks)}
            and sum(rank(k) == rank(c) for k in all_cards) == 1}
    if over and current_class == 9:
        groups['Оверкарты (условные ауты на пару)'] = over
    union = set().union(*groups.values()) if groups else set()
    n, remaining, streets = len(union), len(unseen), 5-len(board)
    # Exact probability of seeing one of THESE currently enumerated cards;
    # does not include runner-runner routes that create new outs later.
    hit = 1-math.comb(remaining-n, streets)/math.comb(remaining, streets)
    rule = min(100., n*(4 if len(board) == 3 else 2))
    description = ('; '.join(f'{label}: {len(cards)}' for label, cards in groups.items()) or 'Нет указанных дро')
    return DrawReport(groups, tuple(c for c in DECK if c in union), rule, hit*100, description)


@dataclass
class EquityResult:
    equity: float
    error95: float
    iterations: int


def monte_carlo(hero, board, opponents=1, iterations=3000, seed=None):
    validate_cards(hero, board)
    if not 1 <= opponents <= 8 or iterations < 2000:
        raise ValueError('1–8 оппонентов, не менее 2000 симуляций')
    rng, evaluator = random.Random(seed), Evaluator()
    pool = [ENCODED[c] for c in DECK if c not in hero+board]
    eh, eb = [ENCODED[c] for c in hero], [ENCODED[c] for c in board]
    missing = 5-len(board)
    total = total_sq = 0.
    for _ in range(iterations):
        sample = rng.sample(pool, missing+2*opponents)
        runout = eb+sample[:missing]
        hero_rank = evaluator.evaluate(runout, eh)
        ties, beaten = 0, False
        for i in range(opponents):
            start = missing+i*2
            other_rank = evaluator.evaluate(runout, sample[start:start+2])
            if other_rank < hero_rank:
                beaten = True
                break
            ties += other_rank == hero_rank
        share = 0. if beaten else 1/(ties+1)
        total += share
        total_sq += share*share
    mean = total/iterations
    variance = max(0, (total_sq-iterations*mean*mean)/(iterations-1))
    return EquityResult(mean, 1.96*math.sqrt(variance/iterations), iterations)


def fmt(value):
    for suffix, size in [('B', 1e9), ('M', 1e6), ('K', 1e3)]:
        if abs(value) >= size:
            return f'{value/size:.2f}{suffix}'
    return f'{value:.2f}'


@dataclass
class Coaching:
    equity: EquityResult
    draws: DrawReport
    made: str
    preflop: str
    pot_odds: float | None
    ev: float | None
    ev_pot_percent: float | None
    spr: float | None
    recommendation: str
    explanation: str


class Coach:
    def __init__(self, iterations=3000, seed=None):
        self.iterations, self.seed = iterations, seed

    def analyze(self, state):
        validate_cards(state.hero, state.board)
        money = [x for x in (state.pot, state.call, state.stack, state.effective_stack) if x is not None]
        if any(not math.isfinite(x) or x < 0 for x in money):
            raise ValueError('Банк, колл и стеки должны быть неотрицательными конечными числами')
        if state.call is not None and state.stack is not None and state.call > state.stack:
            raise ValueError('Колл больше стека: нужен доступный размер all-in и банк без недоступных side pots')
        eq = monte_carlo(state.hero, state.board, state.opponents, self.iterations, self.seed)
        draw = draws(state.hero, state.board)
        made = made_hand(state.hero, state.board)
        pre = preflop(state.hero, state.opponents)
        if state.pot is None or state.call is None:
            # Cards only: equity, hand and draws still work; pot odds, EV and SPR need the amounts.
            text = (f'У вас {made}. Эквити против {state.opponents} случайных рук: '
                    f'{eq.equity*100:.1f}% (MC ±{eq.error95*100:.1f} п.п., 95%). '
                    'Банк или колл не распознаны, поэтому порог колла и EV не посчитаны. '
                    'Сравните шанс с долей колла: колл ÷ (банк + колл). ')
            if state.board and len(state.board) < 5:
                text += (f'{draw.description}. Уникальных условных аутов: {len(draw.outs)}. '
                         f'Правило 2/4: {draw.rule_percent:.1f}%; точно попасть в этот набор '
                         f'к риверу: {draw.hit_percent:.1f}%. Это не вероятность победы! ')
            text += ('Модель: без рейка, будущих ставок и side pots, все увидят вскрытие; '
                     'диапазоны оппонентов равномерные. Для рейза нужны fold equity и диапазон продолжения.')
            return Coaching(eq, draw, made, pre, None, None, None, None,
                            'Суммы не распознаны: решение по шансу', text)
        total = state.pot+state.call
        odds = state.call/total if total else 0.
        ev = eq.equity*total-state.call
        spr = state.effective_stack/state.pot if state.pot and state.effective_stack is not None else None
        ev_pct = ev/state.pot*100 if state.pot else None
        if state.call == 0:
            recommendation = 'Бесплатный чек доступен; EV ставки не оценён'
        elif eq.equity-eq.error95 > odds:
            recommendation = 'Колл +EV в модели вскрытия'
        elif eq.equity+eq.error95 < odds:
            recommendation = 'Колл −EV в модели вскрытия'
        else:
            recommendation = 'Погранично: погрешность MC перекрывает порог'
        text = (f'У вас {made}. Эквити против {state.opponents} случайных рук: '
                f'{eq.equity*100:.1f}% (MC ±{eq.error95*100:.1f} п.п., 95%). '
                f'Колл {fmt(state.call)} в текущий банк {fmt(state.pot)} требует '
                f'{odds*100:.1f}%; EV колла {fmt(ev)}. {recommendation}. ')
        if state.board and len(state.board) < 5:
            text += (f'{draw.description}. Уникальных условных аутов: {len(draw.outs)}. '
                     f'Правило 2/4: {draw.rule_percent:.1f}%; точно попасть в этот набор '
                     f'к риверу: {draw.hit_percent:.1f}%. Это не вероятность победы! ')
        if spr is not None:
            text += (f'SPR {spr:.1f}' + ('' if state.effective_known else ' (верхняя оценка по стеку героя)') + '. ')
            text += ('Глубокий стек: одной пары недостаточно для автоматической игры на стек. '
                     if spr > 6 else 'Низкий SPR уменьшает запас для манёвра, но не гарантирует прибыль с парой. ')
        text += ('Модель: без рейка, будущих ставок и side pots, все увидят вскрытие; '
                 'диапазоны оппонентов равномерные. Ауты могут быть грязными; '
                 'имплайд-оддсы не равны SPR. Для рейза нужны fold equity и диапазон продолжения.')
        return Coaching(eq, draw, made, pre, odds*100, ev, ev_pct, spr, recommendation, text)
