"""Log the last observed decision per hand, not every video frame."""
import csv
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ['Дата', 'Карты', 'Борд', 'Банк', 'Колл', 'Эквити', 'EV',
          'Рекомендация', 'Оппоненты', 'Источник', 'Причина завершения']


class HandLogger:
    def __init__(self, path='hands_log.csv'):
        self.path = Path(path)
        self.pending = None
        self.hand_id = 0
        self.logged = False

    def observe(self, state, result, source='screen'):
        if self.pending:
            old, _, old_source = self.pending
            if old.hero != state.hero or len(state.board) < len(old.board) or source != old_source or not set(old.board) <= set(state.board):
                self.flush('новая раздача / смена источника')
                self.pending = None
        if self.pending is None:
            self.hand_id += 1
            self.logged = False
        self.pending = state, result, source

    def flush(self, reason='завершение сессии'):
        if not self.pending or self.logged:
            return
        state, result, source = self.pending
        self.path.parent.mkdir(parents=True, exist_ok=True)
        header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open('a', encoding='utf-8-sig', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            if header:
                writer.writeheader()
            writer.writerow(dict(zip(FIELDS, [datetime.now(timezone.utc).isoformat(),
                ' '.join(state.hero), ' '.join(state.board), state.pot, state.call,
                round(result.equity.equity*100, 3), round(result.ev, 3),
                result.recommendation, state.opponents, source, reason])))
        self.logged = True

    def end(self, reason='карты героя исчезли'):
        self.flush(reason)
        self.pending = None
