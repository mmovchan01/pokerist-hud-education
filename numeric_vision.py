"""Conservative white-text glyph segmentation for tiny Pokerist 3D numerals.

Unlike sliding matches, segmentation must account for every nonempty character
column, including an unknown suffix or a chip icon. Never parses a substring.
"""
import cv2
import numpy as np


def ink(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if int(gray.max())-int(gray.min()) < 45:
        return None
    _, mask = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)
    if not .005 < np.mean(mask > 0) < .48:
        return None
    return mask


def strips(mask):
    occupied = np.any(mask > 0, axis=0)
    intervals, start = [], None
    for x, value in enumerate([*occupied, False]):
        if value and start is None:
            start = x
        elif not value and start is not None:
            intervals.append((start, x))
            start = None
    return intervals


def canonical(mask):
    columns = np.flatnonzero(np.any(mask > 0, axis=0))
    if not len(columns):
        return None
    mask = mask[:, columns[0]:columns[-1]+1]
    width = max(1, round(mask.shape[1]*40/mask.shape[0]))
    if width > 44:
        return None
    resized = cv2.resize(mask, (width, 40), interpolation=cv2.INTER_NEAREST)
    canvas = np.zeros((48, 48), np.uint8)
    left = (48-width)//2
    canvas[4:44, left:left+width] = resized
    return canvas


def recognize_number(image, samples, threshold=.90, margin=.06):
    """Returns (text, minimum score); ambiguity returns (None, best score)."""
    mask = ink(image)
    if mask is None:
        return None, 0.
    templates = []
    for label, sample in samples:
        binary = ink(sample)
        pattern = canonical(binary) if binary is not None else None
        if pattern is not None:
            templates.append((label, pattern))
    chars, confidence = [], 1.
    intervals = strips(mask)
    if not intervals or len(intervals) > 16:
        return None, 0.
    for left, right in intervals:
        pattern = canonical(mask[:, left:right])
        if pattern is None:
            return None, 0.
        scores = {}
        for label, template in templates:
            # Translational tolerance, with an all-zero border on both sides.
            padded = cv2.copyMakeBorder(pattern, 2, 2, 2, 2, cv2.BORDER_CONSTANT)
            score = float(cv2.minMaxLoc(cv2.matchTemplate(padded, template, cv2.TM_CCOEFF_NORMED))[1])
            scores[label] = max(score, scores.get(label, -1))
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ranked:
            return None, 0.
        label, best = ranked[0]
        runner = ranked[1][1] if len(ranked) > 1 else -1
        if best < threshold or best-runner < margin:
            return None, max(0., best)
        confidence = min(confidence, best)
        chars.append(label)
    return ''.join(chars), confidence
