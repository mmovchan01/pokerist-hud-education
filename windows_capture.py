"""Win32 client-only rendering. Never substitutes a desktop screenshot."""
import sys

import numpy as np


def _api():
    if sys.platform != 'win32':
        raise RuntimeError('Захват окна Texas Poker доступен в Windows 10/11.')
    import ctypes as ct
    from ctypes import wintypes as wt
    user, gdi = ct.windll.user32, ct.windll.gdi32
    signatures = {
        'IsWindowVisible': ([wt.HWND], wt.BOOL),
        'IsIconic': ([wt.HWND], wt.BOOL),
        'GetWindowTextLengthW': ([wt.HWND], ct.c_int),
        'GetWindowTextW': ([wt.HWND, wt.LPWSTR, ct.c_int], ct.c_int),
        'GetWindowThreadProcessId': ([wt.HWND, ct.POINTER(wt.DWORD)], wt.DWORD),
        'GetClientRect': ([wt.HWND, ct.POINTER(wt.RECT)], wt.BOOL),
        'ClientToScreen': ([wt.HWND, ct.POINTER(wt.POINT)], wt.BOOL),
        'GetDC': ([wt.HWND], wt.HDC),
        'ReleaseDC': ([wt.HWND, wt.HDC], ct.c_int),
        'PrintWindow': ([wt.HWND, wt.HDC, wt.UINT], wt.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(user, name)
        function.argtypes, function.restype = args, result
    for name, args, result in [
        ('CreateCompatibleDC', [wt.HDC], wt.HDC),
        ('CreateCompatibleBitmap', [wt.HDC, ct.c_int, ct.c_int], wt.HBITMAP),
        ('SelectObject', [wt.HDC, wt.HGDIOBJ], wt.HGDIOBJ),
        ('DeleteObject', [wt.HGDIOBJ], wt.BOOL),
        ('DeleteDC', [wt.HDC], wt.BOOL),
        ('GetDIBits', [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ct.c_void_p, ct.c_void_p, wt.UINT], ct.c_int),
    ]:
        function = getattr(gdi, name)
        function.argtypes, function.restype = args, result
    return ct, wt, user, gdi


def find_window(title):
    import os
    if not title.strip():
        raise ValueError('Укажите заголовок окна, например Texas Poker')
    ct, wt, user, _ = _api()
    callback_type = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    matches = []

    @callback_type
    def visit(hwnd, _):
        process = wt.DWORD()
        user.GetWindowThreadProcessId(hwnd, ct.byref(process))
        if process.value != os.getpid() and user.IsWindowVisible(hwnd):
            length = user.GetWindowTextLengthW(hwnd)
            buffer = ct.create_unicode_buffer(length+1)
            user.GetWindowTextW(hwnd, buffer, length+1)
            if title.casefold() in buffer.value.casefold():
                matches.append((hwnd, buffer.value))
        return True

    user.EnumWindows.argtypes = [callback_type, wt.LPARAM]
    user.EnumWindows.restype = wt.BOOL
    if not user.EnumWindows(visit, 0):
        raise RuntimeError('Windows не смогла перечислить окна')
    if len(matches) != 1:
        raise RuntimeError(f'«{title}»: найдено окон {len(matches)}. Откройте игру или уточните заголовок.')
    hwnd, actual_title = matches[0]
    if user.IsIconic(hwnd):
        raise RuntimeError('Окно Texas Poker свёрнуто — разверните его перед снимком.')
    rect, origin = wt.RECT(), wt.POINT(0, 0)
    if not user.GetClientRect(hwnd, ct.byref(rect)) or not user.ClientToScreen(hwnd, ct.byref(origin)):
        raise RuntimeError('Не удалось определить клиентскую область игры')
    region = dict(left=origin.x, top=origin.y, width=rect.right, height=rect.bottom)
    if min(region['width'], region['height']) < 20:
        raise RuntimeError('Клиентская область игры слишком мала')
    return hwnd, actual_title, region


def validate_render(image):
    if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 20:
        raise RuntimeError('Некорректный размер снимка окна')
    if float(image.mean()) < 5 and float(image.std()) < 2:
        raise RuntimeError('Игра вернула чёрный кадр. Попробуйте оконный/безрамочный режим вместо эксклюзивного fullscreen. Снимок не сохранён.')


def capture_window(title='Texas Poker'):
    hwnd, actual_title, region = find_window(title)
    ct, wt, user, gdi = _api()

    class BitmapHeader(ct.Structure):
        _fields_ = [('size', wt.DWORD), ('width', wt.LONG), ('height', wt.LONG),
                    ('planes', wt.WORD), ('bits', wt.WORD), ('compression', wt.DWORD),
                    ('image_size', wt.DWORD), ('xppm', wt.LONG), ('yppm', wt.LONG),
                    ('colors', wt.DWORD), ('important', wt.DWORD)]

    width, height = region['width'], region['height']
    source = user.GetDC(hwnd)
    memory = bitmap = previous = None
    try:
        if not source:
            raise RuntimeError('GetDC: нет доступа к окну игры')
        memory = gdi.CreateCompatibleDC(source)
        bitmap = gdi.CreateCompatibleBitmap(source, width, height)
        if not memory or not bitmap:
            raise RuntimeError('Не удалось выделить буфер снимка')
        previous = gdi.SelectObject(memory, bitmap)
        # PW_CLIENTONLY | PW_RENDERFULLCONTENT: no other windows or taskbar.
        if not user.PrintWindow(hwnd, memory, 0x1 | 0x2):
            raise RuntimeError('PrintWindow не поддерживается игрой. Попробуйте оконный режим. Рабочий стол не захватывается.')
        # GetDIBits requires the bitmap not to be selected into a DC.
        gdi.SelectObject(memory, previous)
        previous = None
        header = BitmapHeader()
        header.size = ct.sizeof(BitmapHeader)
        header.width, header.height = width, -height  # top-down BGRA
        header.planes, header.bits = 1, 32
        buffer = (ct.c_ubyte*(width*height*4))()
        if gdi.GetDIBits(memory, bitmap, 0, height, buffer, ct.byref(header), 0) != height:
            raise RuntimeError('Не удалось прочитать пиксели окна')
        image = np.frombuffer(buffer, np.uint8).reshape(height, width, 4)[:, :, :3].copy()
        validate_render(image)
        return image, dict(window_title=actual_title, capture=region, method='PrintWindow/client')
    finally:
        if previous and memory:
            gdi.SelectObject(memory, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if memory:
            gdi.DeleteDC(memory)
        if source:
            user.ReleaseDC(hwnd, source)
