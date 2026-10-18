"""Observable local template recognition. No cloud AI and no automatic training."""
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from screenshot_album import CARD_LABELS
from vision import Recognizer, TemplateBank, load_template


def pixel_key(image):
    return image.shape, hashlib.sha256(image.tobytes()).digest()


@dataclass(frozen=True)
class Suggestion:
    kind: str
    label: str
    confidence: float
    automatic: bool
    method: str


@dataclass(frozen=True)
class AnalysisReport:
    state: str
    title: str
    reason: str
    suggestion: Suggestion | None
    candidates: tuple
    known_cards: frozenset
    template_count: int
    elapsed_ms: float


class EditorAssistant:
    """Use from one worker. Reports include refusal reasons and nearest samples."""
    def __init__(self, template_dir):
        self.root = Path(template_dir)
        self.fingerprint = None
        self.bank = None
        self.known_cards = set()
        self.exact = {}

    def reload(self):
        files = []
        for path in sorted(self.root.glob('*/*/*.png')):
            try:
                stat = path.stat()
                files.append((str(path), stat.st_size, stat.st_mtime_ns))
            except OSError:
                continue
        fingerprint = tuple(files)
        if fingerprint == self.fingerprint:
            return
        self.fingerprint = fingerprint
        self.bank = TemplateBank(self.root)
        self.known_cards = {label for kind, label, _ in self.bank.samples if kind == 'card' and label in CARD_LABELS}
        self.exact = {}
        for kind, label, image in self.bank.samples:
            if (kind == 'card' and label in CARD_LABELS) or kind == 'empty':
                self.exact.setdefault(pixel_key(image), set()).add((kind, 'empty' if kind == 'empty' else label))

    def inspect(self, image):
        started = time.perf_counter()
        self.reload()
        count = sum(kind in ('card', 'empty') for kind, _, _ in self.bank.samples)

        def report(state, title, reason, suggestion=None, candidates=()):
            return AnalysisReport(state, title, reason, suggestion, tuple(candidates),
                                  frozenset(self.known_cards), count, (time.perf_counter()-started)*1000)

        if image is None or not image.size:
            return report('unknown', 'Пустая вырезка', 'Поправьте рамку карты на снимке.')
        if not count:
            return report('no_templates', 'Нет образцов для сравнения',
                          'Выберите карту и сохраните первый образец, либо установите стартовые примеры. Подключение к интернету не требуется.')
        exact = self.exact.get(pixel_key(image), set())
        if len(exact) > 1:
            return report('conflict', 'Противоречие в базе',
                          'Одни и те же пиксели подписаны по-разному. Автовыбор остановлен; проверьте базу шаблонов.')
        ranked = [candidate for candidate in Recognizer({}, self.bank).rank_symbols(image, ('card', 'empty'))
                  if candidate['kind'] == 'empty' or candidate['label'] in CARD_LABELS]
        if len(exact) == 1:
            kind, label = next(iter(exact))
            suggestion = Suggestion(kind, label, 1., True, 'exact pixels')
            return report('recognized', 'Знакомый образец', 'Пиксели полностью совпадают с сохранённым шаблоном. Повторный файл не нужен.', suggestion, ranked[:3])
        if not ranked:
            return report('unknown', 'Нет подходящих образцов', 'Выберите карту вручную; проверьте её положение в рамке.')
        best = ranked[0]
        score = best['score']
        runner = ranked[1]['score'] if len(ranked) > 1 else -1
        gap = score-runner
        kind, label = best['kind'], 'empty' if best['kind'] == 'empty' else best['label']
        if score >= .94 and gap >= .08:
            return report('recognized', 'Карта распознана',
                          f'Совпадение {score:.1%}; отрыв от другой метки {gap:.1%}. Пороги: 94% и 8 п.п. Это похожесть, не вероятность.',
                          Suggestion(kind, label, score, True, 'template matching'), ranked[:3])
        if score >= .84 and gap >= .04:
            return report('suggestion', 'Нужно ваше подтверждение',
                          f'Совпадение {score:.1%}; отрыв {gap:.1%}. Для автоматического принятия требуется 94% и отрыв 8 п.п.',
                          Suggestion(kind, label, score, False, 'suggestion'), ranked[:3])
        reason = (f'Две метки слишком похожи (отрыв {gap:.1%}).' if score >= .84 else f'Лучшее совпадение только {max(0, score):.1%}.')
        return report('unknown', 'Не удалось определить карту', reason+' Проверьте рамку и выберите карту вручную. Для нового освещения сохраните дополнительный образец.', candidates=ranked[:3])

    def analyze(self, image):
        """Compatibility for existing callers; UI uses the full inspect report."""
        report = self.inspect(image)
        return report.suggestion, set(report.known_cards)


def has_card_template(root, label):
    if label not in CARD_LABELS:
        return False
    return any(load_template(path) is not None for path in (Path(root)/'card'/label).glob('*.png'))
