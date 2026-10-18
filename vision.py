"""Conservative multi-scale recognition. Unknown != absent != zero."""
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

import cv2
import numpy as np

from screen import Rect, preprocess
from template_labels import folder_label


def load_template(path):
    """OpenCV fopen is not Unicode-safe on every Windows build."""
    try:
        data = np.frombuffer(Path(path).read_bytes(), np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    except (OSError, cv2.error):
        return None


def parse_amount(text):
    """Poker UI notation: 1,5K / 1.5K, 1,234 / 1.234, 1,234.50.

    A single separator followed by three digits means grouping (1.234=1234).
    Ambiguous decimal conventions must be fixed in the game, not guessed by EV.
    """
    value = text.strip().upper().replace(' ', '').replace('\u00a0', '')
    if not re.fullmatch(r'\d+(?:[.,]\d+)*[KMB]?', value):
        raise ValueError(f'Некорректное число: {text!r}')
    multiplier = {'K': 1000, 'M': 1000000, 'B': 1000000000}.get(value[-1], 1)
    if value[-1] in 'KMB':
        value = value[:-1]
    if '.' in value and ',' in value:
        decimal = max(value.rfind('.'), value.rfind(','))
        whole, fraction = value[:decimal], value[decimal+1:]
        groups = re.split('[.,]', whole)
        if not 1 <= len(groups[0]) <= 3 or any(len(g) != 3 for g in groups[1:]):
            raise ValueError('Invalid grouping')
        value = ''.join(groups)+'.'+fraction
    elif '.' in value or ',' in value:
        parts = re.split('[.,]', value)
        if len(parts) == 2 and len(parts[1]) != 3:
            value = '.'.join(parts)
        elif all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3:
            value = ''.join(parts)
        else:
            raise ValueError('Ambiguous number format')
    try:
        return float(Decimal(value)*multiplier)
    except InvalidOperation as exc:
        raise ValueError(text) from exc


def match_score(image, template):
    """Return best shape match across 0.9 / 1.0 / 1.1 template scale."""
    best = (-1.0, (0, 0, 0, 0))
    for scale in (0.9, 1.0, 1.1):
        w, h = max(2, round(template.shape[1]*scale)), max(2, round(template.shape[0]*scale))
        if w > image.shape[1] or h > image.shape[0]:
            continue
        resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_NEAREST)
        if np.std(resized) < 1:
            continue
        result = cv2.matchTemplate(image, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, pos = cv2.minMaxLoc(result)
        if score > best[0]:
            best = score, (*pos, w, h)
    return best


def color_profile(image):
    """Ink distribution supports red/blue diamonds, green/black clubs.

    Compare to the *labelled* template rather than equating all red shapes with
    hearts. Shape matching still decides rank and suit together.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, sat, val = cv2.split(hsv)
    masks = [(sat > 75) & ((hue < 12) | (hue > 165)),
             (sat > 75) & (hue >= 90) & (hue <= 135),
             (sat > 75) & (hue >= 30) & (hue < 90),
             (sat < 90) & (val < 110)]
    counts = np.array([np.count_nonzero(m) for m in masks], dtype=float)
    return counts / max(1, counts.sum())


@dataclass
class Reading:
    value: object = None
    confidence: float = 0.0
    # status: known, empty or unknown
    status: str = 'unknown'


@dataclass
class TableState:
    hero: tuple
    board: tuple
    pot: float
    stack: float
    call: float
    opponents: int
    effective_stack: float
    readings: dict = field(default_factory=dict)
    captured_at: float = field(default_factory=time.time)
    effective_known: bool = False

    def signature(self):
        return (self.hero, self.board, self.pot, self.stack, self.call,
                self.opponents, self.effective_stack, self.effective_known)


class TemplateBank:
    def __init__(self, root):
        self.root = Path(root)
        self.samples = []
        self.reload()

    def reload(self):
        samples = []
        self.sample_paths = {}
        for kind in ('card', 'glyph', 'back', 'empty'):
            for path in sorted((self.root/kind).glob('*/*.png')):
                image = load_template(path)
                if image is not None:
                    samples.append((kind, folder_label(path.parent.name), image))
                    self.sample_paths[id(image)] = str(path)
        # Earlier collectors accidentally wrote '.' samples into glyph/ itself.
        for path in sorted((self.root/'glyph').glob('*.png')):
            image = load_template(path)
            if image is not None:
                samples.append(('glyph', '.', image))
                self.sample_paths[id(image)] = str(path)
        self.samples = samples

    def candidates(self, kind):
        return [(label, image) for k, label, image in self.samples if k == kind]


class Recognizer:
    def __init__(self, config, bank):
        self.config, self.bank = config, bank
        self.threshold = config.get('confidence', .84)
        self.margin = config.get('margin', .04)

    def rank_symbols(self, roi, kinds):
        """One ranked result per semantic label, with the matching sample path.

        Normalize query and template identically BEFORE preprocessing. Previously
        the query used height 110 and templates 100, which depressed even near-
        identical matches and made the editor's .94 threshold hard to reach.
        """
        if roi is None or not roi.size:
            return []
        height = 100
        image = cv2.resize(roi, (max(2, round(roi.shape[1]*height/roi.shape[0])), height))
        binary = cv2.copyMakeBorder(preprocess(image), 8, 8, 8, 8, cv2.BORDER_REPLICATE)
        padded = cv2.copyMakeBorder(image, 8, 8, 8, 8, cv2.BORDER_REPLICATE)
        scores = {}
        for kind in kinds:
            for label, raw in self.bank.candidates(kind):
                template = cv2.resize(raw, (max(2, round(raw.shape[1]*height/raw.shape[0])), height))
                score, (x, y, w, h) = match_score(binary, preprocess(template))
                if kind == 'empty':
                    aligned = cv2.resize(raw, (image.shape[1], image.shape[0]))
                    aspect = (raw.shape[1]/raw.shape[0])/(roi.shape[1]/roi.shape[0])
                    diff = cv2.absdiff(image, aligned)
                    appearance = 1-float(np.mean(diff))/255
                    changed = float(np.mean(np.max(diff, axis=2) > 35))
                    score = appearance if (.8 <= aspect <= 1.25 and appearance >= .97 and changed <= .015) else -1
                elif score > 0:
                    patch = padded[y:y+h, x:x+w]
                    score -= .20*float(np.abs(color_profile(patch)-color_profile(template)).sum()/2)
                key = (kind, label)
                candidate = dict(kind=kind, label=label, score=float(max(-1, min(1, score))),
                                 path=getattr(self.bank, 'sample_paths', {}).get(id(raw)))
                if key not in scores or score > scores[key]['score']:
                    scores[key] = candidate
        return sorted(scores.values(), key=lambda item: item['score'], reverse=True)

    def symbol(self, roi, kinds):
        ranked = self.rank_symbols(roi, kinds)
        if not ranked:
            return Reading()
        best = ranked[0]
        runner = ranked[1]['score'] if len(ranked) > 1 else -1
        if best['score'] < self.threshold or best['score']-runner < self.margin:
            return Reading(confidence=max(0, best['score']))
        empty = best['kind'] == 'empty'
        return Reading(None if empty else best['label'], best['score'], 'empty' if empty else 'known')

    def number(self, roi):
        if self.config.get('number_method') == 'segmented':
            from numeric_vision import recognize_number
            text, confidence = recognize_number(roi, self.bank.candidates('glyph'))
            if text is None:
                return Reading(confidence=confidence)
            try:
                return Reading(parse_amount(text), confidence, 'known')
            except ValueError:
                return Reading(confidence=confidence)
        # All glyph templates are normalized to a common character height;
        # labels with alternative samples compete in global X-axis NMS.
        normalized = cv2.resize(roi, (max(2, round(roi.shape[1]*40/roi.shape[0])), 40))
        image = preprocess(normalized)
        hits = []
        for label, raw in self.bank.candidates('glyph'):
            # Preserve punctuation's baseline/size by using full text-height crops.
            template = preprocess(cv2.resize(raw, (max(2, round(raw.shape[1]*36/raw.shape[0])), 36)))
            for scale in (.9, 1., 1.1):
                w, h = round(template.shape[1]*scale), round(template.shape[0]*scale)
                if min(w, h) < 2 or w > image.shape[1] or h > image.shape[0]:
                    continue
                templ = cv2.resize(template, (w, h), interpolation=cv2.INTER_NEAREST)
                if np.std(templ) < 1:
                    continue
                response = cv2.matchTemplate(image, templ, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(response >= self.threshold)
                hits.extend((float(response[y, x]), int(x), w, label) for y, x in zip(ys, xs))
        kept = []
        for hit in sorted(hits, reverse=True):
            score, x, w, label = hit
            conflicts = [other for other in kept if max(0, min(x+w, other[1]+other[2])-max(x, other[1])) / min(w, other[2]) > .35]
            if conflicts:
                # Close scores for different labels are ambiguous, not reliable digits.
                if any(other[3] != label and other[0]-score < self.margin for other in conflicts):
                    return Reading(confidence=score)
                continue
            kept.append(hit)
        if not kept:
            return Reading()
        ordered = sorted(kept, key=lambda h: h[1])
        # Reject unexplained horizontal gaps in the recognized text.
        if any(b[1]-(a[1]+a[2]) > 1.5*max(a[2], b[2]) for a, b in zip(ordered, ordered[1:])):
            return Reading()
        # Tight text ROIs only. Refuse partial strings if foreground ink lies
        # outside every recognized glyph (e.g. an unknown trailing K).
        foreground = image < 128 if np.mean(image) > 127 else image > 128
        coverage = np.zeros(image.shape[1], dtype=bool)
        for _, x, w, _ in ordered:
            coverage[max(0, x-1):min(len(coverage), x+w+1)] = True
        ink = foreground.sum(axis=0)
        if ink[~coverage].sum() > max(2, ink.sum()*.03):
            return Reading()
        try:
            return Reading(parse_amount(''.join(h[3] for h in ordered)), min(h[0] for h in kept), 'known')
        except ValueError:
            return Reading()

    def read(self, frame, override=None):
        readings = {}
        for name, rect in self.config['rois'].items():
            roi = Rect(*rect).crop(frame)
            if roi.size == 0:
                readings[name] = Reading()
            elif name in ('pot', 'stack', 'call') or name.startswith('oppstack'):
                readings[name] = self.number(roi)
            else:
                readings[name] = self.symbol(roi, ('back', 'empty') if name.startswith('opp') else ('card', 'empty'))
        required = ['hero1', 'hero2', *[f'board{i}' for i in range(1, 6)], 'pot', 'stack', 'call']
        if any(readings[n].status == 'unknown' for n in required):
            return None, readings, 'Не распознаны обязательные зоны: '+', '.join(n for n in required if readings[n].status == 'unknown')
        if any(readings[n].status != 'known' for n in ('hero1', 'hero2', 'pot', 'stack', 'call')):
            return None, readings, 'Ожидается рука героя и числовые значения'
        hero = tuple(readings[n].value for n in ('hero1', 'hero2'))
        board_values = [readings[f'board{i}'].value for i in range(1, 6)]
        board = tuple(c for c in board_values if c)
        if len(board) not in (0, 3, 4, 5) or board_values != list(board)+[None]*(5-len(board)):
            return None, readings, 'Неполный борд / анимация'
        if len(set(hero+board)) != len(hero+board):
            return None, readings, 'Дубликат карты; проверьте шаблоны'
        opp_names = [n for n in readings if re.fullmatch(r'opp[1-8]', n)]
        if override is None and (not opp_names or any(readings[n].status == 'unknown' for n in opp_names)):
            return None, readings, 'Укажите оппонентов вручную или обучите рубашки и пустые места'
        active = [n for n in opp_names if readings[n].status == 'known']
        opponents = override if override is not None else len(active)
        if not 1 <= opponents <= 8:
            return None, readings, 'Нет активных оппонентов'
        stack = readings['stack'].value
        other_stacks = [readings.get('oppstack'+n[3:], Reading()).value for n in active]
        effective_known = override is None and bool(other_stacks) and all(s is not None for s in other_stacks)
        effective = min(stack, max(other_stacks)) if effective_known else stack
        state = TableState(hero, board, readings['pot'].value, stack, readings['call'].value,
                           opponents, effective, readings, effective_known=effective_known)
        return state, readings, ''


class Stabilizer:
    """Two identical full states sampled at least 250ms apart; reset on unknown."""
    def __init__(self):
        self.previous = None
        self.time = 0

    def update(self, state, now=None):
        now = time.monotonic() if now is None else now
        if state is None:
            self.previous = None
            self.time = now
            return None
        sig = state.signature()
        if sig != self.previous:
            self.previous, self.time = sig, now
            return None
        return state if now-self.time >= .250 else None
