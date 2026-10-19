"""Persistent screenshot inbox and reversible, explicitly human-labelled exports."""
import copy
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from screen import Rect
from template_labels import label_folder

CARD_LABELS = [rank+suit for suit in 'shdc' for rank in 'AKQJT98765432']


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.album-', delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def image_bytes(image):
    ok, data = cv2.imencode('.png', image)
    if not ok:
        raise ValueError('Не удалось закодировать PNG')
    return data.tobytes()


def read_image(path):
    image = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'Не удалось прочитать снимок: {path}')
    return image


def validate_rect(rect):
    if not isinstance(rect, (list, tuple)) or len(rect) != 4 or any(not isinstance(v, (int, float)) or not np.isfinite(v) for v in rect):
        raise ValueError('Некорректная область')
    x, y, w, h = rect
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.00001 or y+h > 1.00001:
        raise ValueError('Выделение выходит за границы снимка')


def valid_label(kind, label):
    return ((kind == 'card' and label in CARD_LABELS) or
            (kind == 'empty' and label == 'empty') or
            (kind == 'back' and label == 'back') or
            (kind == 'glyph' and label in tuple('0123456789.,KMB')))


class Album:
    def __init__(self, folder='captures/inbox', templates='templates'):
        self.folder, self.templates = Path(folder), Path(templates)
        self.folder.mkdir(parents=True, exist_ok=True)

    def _path(self, identifier):
        if not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('Некорректный ID снимка')
        return self.folder/f'{identifier}.json'

    def add(self, image, rois, source, suggested=False):
        if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 20:
            raise ValueError('Некорректное изображение')
        items = {}
        for name, rect in rois.items():
            if not re.fullmatch('[A-Za-z0-9_-]+', name):
                raise ValueError('Некорректное имя области')
            validate_rect(rect)
            kind = 'glyph' if name in ('pot', 'stack', 'call') or name.startswith('oppstack') else ('back' if name.startswith('opp') else 'card')
            items[name] = dict(rect=list(rect), kind=kind, label=None, status='pending', export=None)
        identifier = uuid.uuid4().hex
        record = dict(version=1, id=identifier, revision=0, created_at=datetime.now(timezone.utc).isoformat(),
                      image=f'{identifier}.png', size=[image.shape[1], image.shape[0]],
                      source=copy.deepcopy(source), suggested_rois=suggested, items=items)
        path = self.folder/record['image']
        atomic_write(path, image_bytes(image))
        try:
            atomic_write(self._path(identifier), json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8'))
        except OSError:
            path.unlink(missing_ok=True)
            raise
        return record

    def load(self, identifier):
        record = json.loads(self._path(identifier).read_text(encoding='utf-8'))
        if not isinstance(record, dict):
            raise ValueError('Повреждены метаданные снимка')
        if record.get('version') != 1 or record.get('id') != identifier or record.get('image') != f'{identifier}.png':
            raise ValueError('Повреждены метаданные снимка')
        if not isinstance(record.get('revision'), int) or record['revision'] < 0 or not isinstance(record.get('created_at'), str) or not isinstance(record.get('items'), dict):
            raise ValueError('Повреждена структура альбома')
        for name, item in record['items'].items():
            if not re.fullmatch('[A-Za-z0-9_-]+', name) or not isinstance(item, dict):
                raise ValueError('Некорректная область в альбоме')
            validate_rect(item.get('rect', []))
            if item.get('status') not in ('pending', 'exported', 'skipped', 'reused') or item.get('kind') not in ('card', 'glyph', 'back', 'empty'):
                raise ValueError('Некорректный статус области')
            if item['status'] in ('exported', 'reused') and not valid_label(item['kind'], item.get('label')):
                raise ValueError('Некорректная сохранённая метка')
        return record

    def records(self):
        records, errors = [], []
        for path in self.folder.glob('*.json'):
            try:
                record = self.load(path.stem)
                if not (self.folder/record['image']).exists():
                    raise ValueError('Нет PNG для снимка')
                records.append(record)
            except (OSError, ValueError, KeyError) as exc:
                errors.append(f'{path.name}: {exc}')
        return sorted(records, key=lambda r: r['created_at']), errors

    def image(self, record):
        # Never trust a sidecar-supplied path to point outside the album.
        return read_image(self.folder/f'{record["id"]}.png')

    def _commit(self, record):
        record['revision'] += 1
        atomic_write(self._path(record['id']), json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8'))

    def _managed_export(self, record, item_id, item):
        export = item.get('export')
        if not export:
            return None
        path = self.templates/export
        expected = f'album_{record["id"]}_{item_id}.png'
        if path.name != expected or not path.resolve().is_relative_to(self.templates.resolve()):
            raise ValueError('Недопустимый путь экспортированного шаблона')
        return path

    def annotate(self, identifier, item_id, kind, label, rect=None, skip=False, revision=None):
        if not re.fullmatch('[A-Za-z0-9_-]+', item_id):
            raise ValueError('Некорректный ID области')
        record = self.load(identifier)
        if revision is not None and revision != record['revision']:
            raise ValueError('Снимок изменён другим редактором. Нажмите «Обновить список».')
        item = record['items'][item_id]
        coordinates = list(rect if rect is not None else item['rect'])
        validate_rect(coordinates)
        if not skip and not valid_label(kind, label):
            raise ValueError('Выберите карту/символ из списка')
        old_export = self._managed_export(record, item_id, item)
        new_export = None
        if not skip:
            crop = Rect(*coordinates).crop(self.image(record))
            if not crop.size:
                raise ValueError('Пустое выделение')
            relative = Path(kind)/label_folder(label)/f'album_{identifier}_{item_id}.png'
            new_export = self.templates/relative
            atomic_write(new_export, image_bytes(crop))
            item['export'] = relative.as_posix()
        else:
            item['export'] = None
        item.pop('recognition', None)
        item.update(rect=coordinates, kind=kind, label=None if skip else label,
                    status='skipped' if skip else 'exported')
        self._commit(record)
        if old_export and old_export != new_export:
            old_export.unlink(missing_ok=True)
        return record

    def accept_known(self, identifier, item_id, kind, label, confidence, method, revision, automatic=True, rect=None):
        """Mark a pending crop as already known, without writing ANY template."""
        record = self.load(identifier)
        if record['revision'] != revision:
            raise ValueError('Снимок изменился во время распознавания')
        item = record['items'][item_id]
        if item['status'] != 'pending' or item.get('export'):
            raise ValueError('Автоподпись разрешена только для новой области')
        if kind not in ('card', 'empty') or not valid_label(kind, label) or not np.isfinite(confidence) or not .94 <= confidence <= 1.000001:
            raise ValueError('Недостаточная уверенность или неверная метка')
        coordinates = list(rect if rect is not None else item['rect'])
        validate_rect(coordinates)
        item.update(rect=coordinates, kind=kind, label=label, status='reused', export=None,
                    recognition={'confidence': float(confidence), 'method': method, 'automatic': bool(automatic)})
        self._commit(record)
        return record

    def add_region(self, identifier, rect):
        validate_rect(rect)
        record = self.load(identifier)
        item_id = 'crop_'+uuid.uuid4().hex[:12]
        record['items'][item_id] = dict(rect=list(rect), kind='glyph', label=None,
                                       status='pending', export=None)
        self._commit(record)
        return record, item_id
