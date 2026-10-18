"""Install a screenshot-derived ROI preset without guessing desktop position."""
import json
import shutil
from pathlib import Path

BUILTIN = Path(__file__).resolve().parent/'profiles'/'pokerist_3d_1280x719'


def load_profile(folder=BUILTIN):
    data = json.loads((Path(folder)/'profile.json').read_text(encoding='utf-8'))
    width, height = data['reference_size']
    if min(width, height) <= 0 or not data['rois']:
        raise ValueError('Invalid profile')
    return data


def check_aspect(width, height, reference_size):
    expected = reference_size[0]/reference_size[1]
    if height <= 0 or abs(width/height/expected-1) > .025:
        raise ValueError('Выделите только изображение игры целиком, включая верхнее меню и нижние кнопки, без рамки браузера. Ожидается примерно 16:9 (1280×719).')


def seed_templates(destination, folder=BUILTIN):
    """Add namespaced samples; never remove or overwrite manual templates."""
    count = 0
    source = Path(folder)/'templates'
    for kind in ('card', 'glyph', 'back', 'empty'):
        for path in sorted((source/kind).glob('*/*.png')):
            target = Path(destination)/kind/path.parent.name/('pokerist3d_'+path.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(path, target)
                count += 1
    return count
