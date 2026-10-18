"""Small, testable helpers shared by desktop setup tools."""
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def selection_bounds(coords, scale, width, height):
    """Clip either drag direction to the original screenshot, not its preview."""
    if scale <= 0:
        raise ValueError('Invalid display scale')
    xa, ya, xb, yb = coords
    x1, x2 = sorted((round(xa/scale), round(xb/scale)))
    y1, y2 = sorted((round(ya/scale), round(yb/scale)))
    return (max(0, min(width, x1)), max(0, min(height, y1)),
            max(0, min(width, x2)), max(0, min(height, y2)))


def preview_scale(width, height, screen_width, screen_height):
    if min(width, height) <= 0:
        raise ValueError('Screenshot must not be empty')
    return min(1., min(1200, max(200, screen_width-80))/width,
               min(720, max(150, screen_height-240))/height)


def launcher_command(python, mode, window_title=''):
    modes = {'profile': '--profile', 'calibrate': '--calibrate', 'collect': '--collect',
             'check': '--check', 'run': '--run', 'demo': '--demo'}
    if mode not in modes:
        raise ValueError('Unknown launch mode')
    command = [str(python), str(ROOT/'main.py'), modes[mode]]
    if mode in ('profile', 'calibrate', 'collect', 'check'):
        command.extend(['--delay', '4'])
    if mode == 'calibrate' and window_title.strip():
        command.extend(['--window-title', window_title.strip()])
    return command
