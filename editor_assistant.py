"""Editor-only template assistance; automatic labels NEVER become training data."""
import hashlib
from dataclasses import dataclass
from pathlib import Path

from screenshot_album import CARD_LABELS
from vision import Recognizer, TemplateBank, load_template


def pixel_key(image):
    return (image.shape, hashlib.sha256(image.tobytes()).digest())


@dataclass(frozen=True)
class Suggestion:
    kind: str
    label: str
    confidence: float
    automatic: bool
    method: str


class EditorAssistant:
    """Use only from the editor's single background worker."""
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

    def analyze(self, image):
        self.reload()
        exact = self.exact.get(pixel_key(image), set())
        if len(exact) > 1:
            # Conflicting human labels for identical pixels: do not choose one.
            return None, set(self.known_cards)
        if len(exact) == 1:
            kind, label = next(iter(exact))
            return Suggestion(kind, label, 1., True, 'exact pixels'), set(self.known_cards)
        strict = Recognizer({'confidence': .94, 'margin': .08}, self.bank).symbol(image, ('card', 'empty'))
        if strict.status in ('known', 'empty'):
            kind = 'empty' if strict.status == 'empty' else 'card'
            if kind == 'empty' or strict.value in CARD_LABELS:
                return Suggestion(kind, 'empty' if kind == 'empty' else strict.value,
                                  float(strict.confidence), True, 'template matching'), set(self.known_cards)
        relaxed = Recognizer({'confidence': .84, 'margin': .04}, self.bank).symbol(image, ('card', 'empty'))
        if relaxed.status in ('known', 'empty'):
            kind = 'empty' if relaxed.status == 'empty' else 'card'
            if kind == 'empty' or relaxed.value in CARD_LABELS:
                return Suggestion(kind, 'empty' if kind == 'empty' else relaxed.value,
                                  float(relaxed.confidence), False, 'suggestion'), set(self.known_cards)
        return None, set(self.known_cards)


def has_card_template(root, label):
    if label not in CARD_LABELS:
        return False
    return any(load_template(path) is not None for path in (Path(root)/'card'/label).glob('*.png'))
