"""Validated, atomic config save with a recoverable copy of the previous setup."""
import json
import os
import shutil
import tempfile
from pathlib import Path


def save_config(path, data):
    from screen import load_config
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.hud-config-', suffix='.json', delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        load_config(temporary)
        if path.exists():
            shutil.copy2(path, path.with_name(path.name+'.bak'))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
