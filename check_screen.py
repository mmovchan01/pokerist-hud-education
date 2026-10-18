"""Single-frame diagnostics: annotated screenshot, readings and JSON report.

A successful read of one screenshot is NOT a temporally stabilized live state.
"""
import json
import time
from pathlib import Path

import cv2

from screen import Rect, enable_dpi, grab, load_config
from vision import Recognizer, TemplateBank


def write_report(frame, config, readings, state, error, output_dir='captures'):
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stem = f'check_{time.time_ns()}'
    raw_path = folder/f'{stem}_raw.png'
    annotated_path = folder/f'{stem}_annotated.png'
    report_path = folder/f'{stem}.json'
    annotated = frame.copy()
    for name, values in config['rois'].items():
        reading = readings[name]
        color = {'known': (70, 220, 80), 'empty': (230, 180, 50)}.get(reading.status, (40, 70, 240))
        x, y, w, h = Rect(*values).pixels(frame.shape[1], frame.shape[0])
        cv2.rectangle(annotated, (x, y), (x+w, y+h), color, 2)
        cv2.putText(annotated, f'{name}: {reading.value if reading.value is not None else reading.status} {reading.confidence:.0%}',
                    (x, max(12, y-4)), cv2.FONT_HERSHEY_SIMPLEX, .4, color, 1)
    for path, image in ((raw_path, frame), (annotated_path, annotated)):
        if not cv2.imwrite(str(path), image):
            raise OSError(f'Cannot save {path}')
    report = {
        'single_frame_valid': state is not None,
        'temporal_stabilization_checked': False,
        'error': error,
        'raw_image': raw_path.name,
        'annotated_image': annotated_path.name,
        'readings': {n: {'value': r.value, 'status': r.status, 'confidence': r.confidence}
                     for n, r in readings.items()}}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report_path, annotated_path


def check(config_path, template_dir):
    import mss
    import tkinter as tk
    from tkinter import ttk
    from PIL import Image, ImageTk

    enable_dpi()
    config = load_config(config_path)
    with mss.mss() as sct:
        frame = grab(sct, config)
    state, readings, error = Recognizer(config, TemplateBank(template_dir)).read(frame)
    report_path, annotated_path = write_report(frame, config, readings, state, error)
    root = tk.Tk()
    root.title('Pokerist — проверка одного кадра')
    root.geometry('1100x800')
    root.minsize(700, 600)
    ttk.Label(root, text='Один кадр распознан; это ещё не проверка стабилизации.' if state else error,
              wraplength=1050, font=('Arial', 12, 'bold')).pack(fill='x', padx=10, pady=8)
    ttk.Label(root, text='Зелёный: распознано; синий: пустой слот; красный: неизвестно.\nСверьте каждую карту и число глазами. Confidence — похожесть, не вероятность.', wraplength=1050).pack(fill='x', padx=10)
    image = cv2.imread(str(annotated_path))
    scale = min(1, 1050/image.shape[1], 400/image.shape[0])
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    photo = ImageTk.PhotoImage(Image.fromarray(rgb).resize((round(image.shape[1]*scale), round(image.shape[0]*scale))))
    ttk.Label(root, image=photo).pack(pady=5)
    tree = ttk.Treeview(root, columns=('roi', 'value', 'status', 'confidence'), show='headings', height=8)
    for column, title in [('roi', 'Зона'), ('value', 'Значение'), ('status', 'Статус'), ('confidence', 'Похожесть')]:
        tree.heading(column, text=title)
        tree.column(column, width=200)
    for name, reading in readings.items():
        tree.insert('', 'end', values=(name, '—' if reading.value is None else reading.value,
                                      reading.status, f'{reading.confidence:.1%}'))
    tree.pack(fill='both', expand=True, padx=10)
    ttk.Label(root, text=f'Сохранены исходный снимок, разметка и JSON: {report_path.resolve()}\nМожно прислать эти файлы для настройки. Перед отправкой проверьте личные данные.', wraplength=1050).pack(padx=10, pady=8)
    ttk.Button(root, text='Закрыть', command=root.destroy).pack(pady=5)
    root.mainloop()
