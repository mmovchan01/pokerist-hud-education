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
    from ui_theme import PALETTE as P, apply_theme, font

    root = tk.Tk()
    apply_theme(root)
    root.title('Pokerist — проверка одного кадра')
    root.geometry('1100x860')
    root.minsize(700, 620)
    root.configure(background=P['bg'])
    verdict = 'Кадр распознан. Это ещё не проверка стабилизации: сверьте карты и числа глазами.' if state else f'Кадр не распознан: {error}'
    tk.Label(root, text='Проверка одного кадра', bg=P['bg'], fg=P['accent'], font=font(16, 'bold'), anchor='w').pack(fill='x', padx=14, pady=(14, 0))
    tk.Label(root, text=verdict, bg=P['bg'], fg=P['good'] if state else P['bad'], font=font(11, 'bold'),
             wraplength=1050, justify='left', anchor='w').pack(fill='x', padx=14, pady=(4, 6))
    legend = tk.Frame(root, bg=P['bg'])
    legend.pack(fill='x', padx=14)
    for color, text in ((P['good'], 'зелёный — распознано'), (P['info'], 'синий — пустое место'), (P['bad'], 'красный — неизвестно')):
        tk.Label(legend, text='■ ', bg=P['bg'], fg=color, font=font(12)).pack(side='left')
        tk.Label(legend, text=text + '     ', bg=P['bg'], fg=P['muted'], font=font(9)).pack(side='left')
    tk.Label(root, text='Confidence — похожесть на образец, а не вероятность правильного ответа.',
             bg=P['bg'], fg=P['muted'], font=font(9), anchor='w').pack(fill='x', padx=14, pady=(2, 8))
    image = cv2.imread(str(annotated_path))
    scale = min(1, 1050/image.shape[1], 400/image.shape[0])
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    photo = ImageTk.PhotoImage(Image.fromarray(rgb).resize((round(image.shape[1]*scale), round(image.shape[0]*scale))))
    tk.Label(root, image=photo, bg=P['bg'], bd=0).pack(pady=4)
    tree = ttk.Treeview(root, columns=('roi', 'value', 'status', 'confidence'), show='headings', height=8)
    for column, title in [('roi', 'Зона'), ('value', 'Значение'), ('status', 'Статус'), ('confidence', 'Похожесть')]:
        tree.heading(column, text=title)
        tree.column(column, width=200, anchor='w')
    for name, reading in readings.items():
        tree.insert('', 'end', values=(name, '—' if reading.value is None else reading.value,
                                      reading.status, f'{reading.confidence:.1%}'))
    tree.pack(fill='both', expand=True, padx=14, pady=6)
    tk.Label(root, text=f'Сохранены исходный снимок, разметка и JSON:\n{report_path.resolve()}\nМожно прислать эти файлы для настройки. Перед отправкой проверьте личные данные.',
             bg=P['bg'], fg=P['muted'], font=font(9), wraplength=1050, justify='left').pack(fill='x', padx=14, pady=6)
    ttk.Button(root, text='Закрыть', style='Accent.TButton', command=root.destroy).pack(pady=(4, 14))
    root.mainloop()
