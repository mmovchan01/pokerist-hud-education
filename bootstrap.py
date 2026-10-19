"""First-run installer: standard library only, always uses the project venv."""
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 10):
        print('Python 3.10 or newer is required. Install Python with Tcl/Tk.')
        return 1
    if importlib.util.find_spec('tkinter') is None:
        print('Tcl/Tk is missing. Windows: modify Python installation, enable Tcl/Tk.\n'
              'Ubuntu/Debian: install python3-tk and python3-venv. macOS: use Python with Tk.')
        return 1
    python = ROOT/'.venv'/('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT/'.venv')], check=True)
    requirements = ROOT/'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = ROOT/'.venv'/'hud-requirements.sha256'
    if '--repair' in sys.argv or not stamp.exists() or stamp.read_text().strip() != fingerprint:
        print('Installing dependencies into .venv (first start requires internet)...', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
        stamp.write_text(fingerprint, encoding='ascii')
    return subprocess.call([str(python), str(ROOT/'desktop_launcher.py')], cwd=ROOT)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f'Startup failed: {exc}\nCheck Python installation and internet access.')
        raise SystemExit(1) from exc
