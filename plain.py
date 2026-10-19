"""Turn the coach's math into one decision and two plain numbers.

The technical text (EV, MC, SPR, outs) stays available behind «Подробнее»;
the default view only answers: what to do, why, and how sure we are.
Pure Python, no tkinter, so the wording rules are unit-tested.
"""
from dataclasses import dataclass


# Plain-language glossary: term -> one-to-two sentence explanation for a beginner.
GLOSSARY = (
    ('Банк', 'Все фишки, которые уже лежат в центре стола. Выигравший забирает банк.'),
    ('Колл (уравнять)', 'Доплатить столько, сколько поставил до вас последний игрок. Так вы остаётесь в раздаче.'),
    ('Пас', 'Сбросить карты и выйти из раздачи. Уже вложенные фишки теряются.'),
    ('Чек', 'Пропустить ход без ставки. Ничего не стоит, если никто не ставил.'),
    ('Стартовая рука', 'Две карты, которые вам выдали до того, как открылся борд.'),
    ('Борд', 'Общие карты стола. Открываются по этапам: флоп (3 карты), тёрн (4-я), ривер (5-я).'),
    ('Ваш шанс выиграть (эквити)', 'Примерная доля банка, которую вы в среднем получите, если раздачу доиграть до конца. '
                                   'Например, 40% — при таких картах вы в среднем получаете 40% банка.'),
    ('Нужный шанс (pot odds)', 'Минимальная доля, при которой колл окупается: сумма колла ÷ (банк + колл). '
                               'Если ваш шанс выше — колл выгоден.'),
    ('Аут', 'Карта из колоды, которая улучшит вашу руку. Например, любая из 9 карт нужной масти для флеш-дро.'),
    ('Дро', 'Незаконченная комбинация, которая может стать сильной: четыре карты одной масти (флеш-дро) '
            'или четыре карты по порядку с дыркой (стрит-дро).'),
    ('Выгода колла (EV)', 'Средний результат колла, если такие ситуации повторяются много раз. '
                          'Плюс — колл выгоден в среднем, минус — невыгоден. В одной раздаче гарантий нет.'),
    ('Погрешность ±', 'Расчёт случайный: он доигрывает раздачу тысячи раз. Погрешность — насколько '
                      'его процент может отличаться от точного. Меньше — точнее.'),
    ('Симуляция (Monte Carlo)', 'Программа много раз случайно раздаёт оставшиеся карты и считает, '
                                'в скольких случаях вы выигрываете. Так оценивается ваш шанс.'),
    ('SPR (запас стека)', 'Сколько банков помещается в ваш стек. Нужен для продвинутой игры; новичку можно не думать о нём.'),
)

VERDICT_TONES = {'Колл': 'good', 'Пас': 'bad', 'Чек': 'info', 'Спорно': 'warn'}


@dataclass(frozen=True)
class Verdict:
    action: str          # 'Колл', 'Пас', 'Чек' or 'Спорно'
    headline: str        # one line: the decision
    summary: str         # one or two sentences: why
    facts: tuple         # ((label, value), ...) at most three rows
    caveat: str          # how sure the numbers are
    tone: str


def glossary_text(term):
    for name, text in GLOSSARY:
        if name == term:
            return text
    raise KeyError(term)


def money(value):
    """Chips without noise: 300 not 300.00, 1.5K not 1500.00."""
    if abs(value) >= 1000:
        return f'{value/1000:g}K'
    return f'{value:g}'


def pot_line(state):
    return (f'Банк {money(state.pot)} · доплатить {money(state.call)} · '
            f'ваш стек {money(state.stack)} · соперников {state.opponents}')


def make_verdict(state, result):
    """One decision with the numbers that justify it. Never called with an unknown state."""
    equity = result.equity.equity*100
    error = result.equity.error95*100
    need = result.pot_odds
    runs = f'{result.equity.iterations:,}'.replace(',', '\u00a0')
    caveat = (f'Расчёт приблизительный: погрешность около ±{error:.0f}%. '
              f'Он сделан по {runs} случайным раздачам.')
    facts = [('Ваш шанс выиграть', f'около {equity:.0f}%')]
    if state.call > 0:
        facts.append(('Нужно для колла', f'от {need:.0f}%'))
    if state.board:
        facts.append(('Ваша рука', result.made))
    else:
        facts.append(('Стартовая рука', result.preflop.split(';', 1)[0]))

    if state.call == 0:
        return Verdict('Чек', 'Можно проверить бесплатно',
                       'Никто не ставит, поэтому чек ничего не стоит. Если шанс высокий, '
                       'имеет смысл поставить и увеличить банк.',
                       tuple(facts), caveat, VERDICT_TONES['Чек'])
    if equity-error > need:
        return Verdict('Колл', 'Колл выгоден',
                       f'Ваш шанс (около {equity:.0f}%) выше нужного для колла ({need:.0f}%). '
                       f'Доплатите {money(state.call)}.',
                       tuple(facts), caveat, VERDICT_TONES['Колл'])
    if equity+error < need:
        return Verdict('Пас', 'Пас: колл не окупается',
                       f'Ваш шанс около {equity:.0f}%, а для колла нужно не меньше {need:.0f}%. '
                       'Доплачивать дороже, чем вы в среднем получите.',
                       tuple(facts), caveat, VERDICT_TONES['Пас'])
    return Verdict('Спорно', 'Решение почти безразлично',
                   f'Ваш шанс ({equity:.0f}%) и нужный для колла ({need:.0f}%) очень близки. '
                   'В долгой игре разница между колом и пасом невелика.',
                   tuple(facts), caveat, VERDICT_TONES['Спорно'])
