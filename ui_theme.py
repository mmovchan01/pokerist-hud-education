"""One visual language for every Tk window: calm dark slate, mint accent.

The 'clam' ttk theme is used on every platform on purpose: native Windows
themes ignore button and checkbox colours, which left bright grey strips on
the dark HUD. Only standard Tk/ttk options are used.
"""
import sys

PALETTE = {
    'bg': '#0e1a25',          # window background
    'surface': '#172b3d',     # cards and panels
    'surface_alt': '#20394d', # buttons, badges
    'field': '#10222f',       # entries, lists, text areas
    'border': '#2b4a60',
    'select': '#2a5873',
    'text': '#e8f3f7',
    'muted': '#8fa9b8',
    'accent': '#5ee8ba',
    'accent_hover': '#86f2cc',
    'accent_text': '#05261c',
    'good': '#4ade80',
    'bad': '#f87171',
    'warn': '#fbbf24',
    'info': '#7dd3fc',
    'card_face': '#f5f9fb',
}

SUIT_COLORS = {
    's': '#1f2933',  # black on the light card face
    'h': '#d93a4f',
    'd': '#2b6fd6',
    'c': '#1b8a52',
}

TONE_KEYS = {'good', 'bad', 'warn', 'info', 'muted', 'text'}

FAMILY = 'Segoe UI' if sys.platform == 'win32' else 'Arial'


def font(size=10, weight='normal'):
    return (FAMILY, size, weight)


def tone_color(tone):
    if tone not in TONE_KEYS:
        tone = 'text'
    return PALETTE[tone]


def apply_theme(root):
    """Configure ttk styles and option database once per Tk root."""
    from tkinter import ttk

    p = PALETTE
    style = ttk.Style(root)
    if 'clam' in style.theme_names():
        style.theme_use('clam')
    root.configure(background=p['bg'])

    style.configure('.', background=p['bg'], foreground=p['text'], font=font(10),
                    bordercolor=p['border'], lightcolor=p['border'], darkcolor=p['border'],
                    troughcolor=p['field'], focuscolor=p['accent'],
                    selectbackground=p['select'], selectforeground=p['text'],
                    fieldbackground=p['field'], insertcolor=p['text'])

    style.configure('TFrame', background=p['bg'])
    style.configure('Card.TFrame', background=p['surface'])
    style.configure('TLabel', background=p['bg'], foreground=p['text'])
    style.configure('Muted.TLabel', background=p['bg'], foreground=p['muted'])
    style.configure('Title.TLabel', background=p['bg'], foreground=p['accent'], font=font(20, 'bold'))
    style.configure('Card.TLabel', background=p['surface'], foreground=p['text'])
    style.configure('CardMuted.TLabel', background=p['surface'], foreground=p['muted'])
    style.configure('CardHead.TLabel', background=p['surface'], foreground=p['accent'], font=font(9, 'bold'))
    style.configure('CardValue.TLabel', background=p['surface'], foreground=p['text'], font=font(17, 'bold'))
    style.configure('Status.TLabel', background=p['surface_alt'], foreground=p['text'], padding=(10, 6))

    style.configure('TButton', background=p['surface_alt'], foreground=p['text'],
                    bordercolor=p['surface_alt'], lightcolor=p['surface_alt'], darkcolor=p['surface_alt'],
                    focusthickness=0, padding=(12, 7), relief='flat')
    style.map('TButton',
              background=[('disabled', p['surface']), ('pressed', p['border']), ('active', p['border'])],
              foreground=[('disabled', p['muted'])])
    style.configure('Accent.TButton', background=p['accent'], foreground=p['accent_text'],
                    bordercolor=p['accent'], lightcolor=p['accent'], darkcolor=p['accent'],
                    font=font(10, 'bold'))
    style.map('Accent.TButton',
              background=[('disabled', p['surface_alt']), ('pressed', p['accent']), ('active', p['accent_hover'])],
              foreground=[('disabled', p['muted'])])
    style.configure('Card.TButton', background=p['surface_alt'], bordercolor=p['surface_alt'],
                    lightcolor=p['surface_alt'], darkcolor=p['surface_alt'])
    style.map('Card.TButton', background=[('active', p['border']), ('disabled', p['surface'])])

    style.configure('TCheckbutton', background=p['bg'], foreground=p['text'], focuscolor=p['bg'])
    style.map('TCheckbutton', background=[('active', p['bg'])])
    style.configure('Card.TCheckbutton', background=p['surface'], foreground=p['text'], focuscolor=p['surface'])
    style.map('Card.TCheckbutton', background=[('active', p['surface'])])

    style.configure('TEntry', fieldbackground=p['field'], foreground=p['text'],
                    bordercolor=p['border'], lightcolor=p['border'], darkcolor=p['border'],
                    insertcolor=p['text'], padding=6)
    style.map('TEntry', fieldbackground=[('disabled', p['surface']), ('readonly', p['surface'])],
              bordercolor=[('focus', p['accent'])])

    style.configure('TCombobox', fieldbackground=p['field'], foreground=p['text'],
                    background=p['surface_alt'], arrowcolor=p['text'], bordercolor=p['border'],
                    lightcolor=p['border'], darkcolor=p['border'], padding=4)
    style.map('TCombobox', fieldbackground=[('readonly', p['field']), ('disabled', p['surface'])],
              foreground=[('readonly', p['text']), ('disabled', p['muted'])],
              selectbackground=[('readonly', p['field'])], selectforeground=[('readonly', p['text'])],
              bordercolor=[('focus', p['accent'])])

    style.configure('TScrollbar', background=p['surface_alt'], troughcolor=p['bg'],
                    bordercolor=p['bg'], arrowcolor=p['muted'], lightcolor=p['surface_alt'],
                    darkcolor=p['surface_alt'])
    style.configure('TPanedwindow', background=p['bg'])
    style.configure('Treeview', background=p['surface'], fieldbackground=p['surface'],
                    foreground=p['text'], bordercolor=p['border'], rowheight=26)
    style.map('Treeview', background=[('selected', p['select'])], foreground=[('selected', p['text'])])
    style.configure('Treeview.Heading', background=p['surface_alt'], foreground=p['text'],
                    bordercolor=p['surface_alt'], relief='flat', font=font(10, 'bold'))
    style.configure('TLabelframe', background=p['bg'], bordercolor=p['border'])
    style.configure('TLabelframe.Label', background=p['bg'], foreground=p['muted'])

    # Plain Tk widgets (Listbox, the dropdown popup) read the option database.
    root.option_add('*Listbox.background', p['field'])
    root.option_add('*Listbox.foreground', p['text'])
    root.option_add('*Listbox.selectBackground', p['select'])
    root.option_add('*Listbox.selectForeground', p['text'])
    root.option_add('*Listbox.highlightThickness', 0)
    root.option_add('*Listbox.borderWidth', 0)
    root.option_add('*TCombobox*Listbox.background', p['field'])
    root.option_add('*TCombobox*Listbox.foreground', p['text'])
    root.option_add('*TCombobox*Listbox.selectBackground', p['select'])
    root.option_add('*TCombobox*Listbox.selectForeground', p['text'])
    return style


def card(parent, padding=(14, 12)):
    """A raised dark panel. Put ttk widgets inside with the 'Card.*' styles."""
    import tkinter as tk

    return tk.Frame(parent, bg=PALETTE['surface'], highlightthickness=1,
                    highlightbackground=PALETTE['border'], highlightcolor=PALETTE['border'],
                    padx=padding[0], pady=padding[1])
