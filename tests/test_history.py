import csv
from types import SimpleNamespace

from hand_history import HandLogger
from vision import TableState


def test_history_boundaries_and_flush(tmp_path):
    path = tmp_path/'history.csv'
    logger = HandLogger(path)
    result = SimpleNamespace(equity=SimpleNamespace(equity=.5), ev=10, recommendation='test')
    first = TableState(('Ah', 'Kd'), (), 100, 1000, 10, 1, 1000)
    flop = TableState(('Ah', 'Kd'), ('2c', '3c', '4c'), 200, 1000, 20, 1, 1000)
    second = TableState(('Qs', 'Qh'), (), 100, 1000, 10, 1, 1000)
    logger.observe(first, result)
    logger.observe(first, result)
    logger.observe(flop, result)
    assert not path.exists()
    logger.observe(second, result)
    logger.end()
    logger.end()
    with path.open(encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]['Борд'] == '2c 3c 4c'
    assert rows[1]['Карты'] == 'Qs Qh'
