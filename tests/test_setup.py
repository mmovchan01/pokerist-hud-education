import json
import subprocess
import sys

import numpy as np
import pytest

import bootstrap
from check_screen import write_report
from config_io import save_config
from setup_support import ROOT, launcher_command, selection_bounds
from vision import Reading


@pytest.mark.parametrize('coords,expected', [
    ((10, 20, 30, 40), (20, 40, 60, 80)),
    ((30, 40, 10, 20), (20, 40, 60, 80)),
    ((-20, -10, 300, 400), (0, 0, 100, 80)),
    ((-30, -40, -10, -20), (0, 0, 0, 0)),
    ((80, 70, 300, 400), (100, 80, 100, 80)),
])
def test_selection_clipping(coords, expected):
    assert selection_bounds(coords, .5, 100, 80) == expected


def test_launch_argument_boundaries():
    title = 'Pokerist & "browser"'
    cmd = launcher_command('C:/Python with space/python.exe', 'calibrate', title)
    assert cmd[0] == 'C:/Python with space/python.exe'
    assert cmd[1] == str(ROOT/'main.py')
    assert cmd[-2:] == ['--window-title', title]
    assert '--delay' in cmd
    assert '--window-title' not in launcher_command(sys.executable, 'collect', title)
    assert '--delay' not in launcher_command(sys.executable, 'demo')
    with pytest.raises(ValueError):
        launcher_command(sys.executable, 'shell_command')


def config():
    names = ['hero1', 'hero2', 'pot', 'stack', 'call']+[f'board{i}' for i in range(1, 6)]
    return dict(version=1, capture=dict(left=0, top=0, width=800, height=600),
                window_title='', rois={n: [.1, .1, .1, .1] for n in names})


def test_safe_save_and_backup(tmp_path):
    path = tmp_path/'config.json'
    first = config()
    save_config(path, first)
    assert not path.with_name('config.json.bak').exists()
    second = config()
    second['window_title'] = 'Pokerist'
    save_config(path, second)
    assert json.loads(path.read_text()) == second
    assert json.loads(path.with_name('config.json.bak').read_text()) == first
    assert not list(tmp_path.glob('.hud-config-*'))


def test_invalid_save_preserves_existing_config(tmp_path):
    path = tmp_path/'config.json'
    save_config(path, config())
    before = path.read_bytes()
    invalid = config()
    invalid['rois']['hero1'] = [0, 0, -1, 1]
    with pytest.raises(ValueError):
        save_config(path, invalid)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('.hud-config-*'))


def test_diagnostic_report(tmp_path):
    c = {'rois': {'hero1': [.1, .1, .2, .2], 'board1': [.4, .1, .2, .2]}}
    readings = {'hero1': Reading('Ah', .95, 'known'), 'board1': Reading()}
    path, annotated = write_report(np.zeros((200, 300, 3), np.uint8), c, readings,
                                   None, 'unknown board', tmp_path)
    data = json.loads(path.read_text())
    assert not data['single_frame_valid']
    assert not data['temporal_stabilization_checked']
    assert data['readings']['hero1']['value'] == 'Ah'
    assert data['readings']['board1']['value'] is None
    assert annotated.exists()
    assert (tmp_path/data['raw_image']).exists()


@pytest.mark.parametrize('args', [ ['--delay', '-1'], ['--delay', '31'],
                                   ['--label', '--window-title', 'Pokerist'],
                                   ['--iterations', '100'], ['--check', '--run'] ])
def test_cli_validation_without_tk(args):
    result = subprocess.run([sys.executable, str(ROOT/'main.py'), *args], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'error:' in result.stderr


def test_bootstrap_missing_tk(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap.importlib.util, 'find_spec', lambda name: None)
    assert bootstrap.main() == 1
    assert 'Tcl/Tk' in capsys.readouterr().out


def test_bootstrap_install_and_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, 'ROOT', tmp_path)
    monkeypatch.setattr(bootstrap.importlib.util, 'find_spec', lambda name: object())
    monkeypatch.setattr(sys, 'argv', ['bootstrap.py'])
    (tmp_path/'requirements.txt').write_text('treys==0.1.8\n')
    python = tmp_path/'.venv'/('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if 'venv' in command:
            python.parent.mkdir(parents=True)
            python.touch()

    monkeypatch.setattr(bootstrap.subprocess, 'run', run)
    monkeypatch.setattr(bootstrap.subprocess, 'call', lambda command, **kwargs: 0)
    assert bootstrap.main() == 0
    assert len(calls) == 2
    assert calls[1][1:4] == ['-m', 'pip', 'install']
    calls.clear()
    assert bootstrap.main() == 0
    assert calls == []
    monkeypatch.setattr(sys, 'argv', ['bootstrap.py', '--repair'])
    assert bootstrap.main() == 0
    assert len(calls) == 1


def test_preview_fits_small_desktop():
    from setup_support import preview_scale
    scale = preview_scale(1920, 1080, 1366, 768)
    assert 1920*scale <= 1286
    assert 1080*scale <= 528
    assert preview_scale(600, 400, 1920, 1080) == 1


def test_launcher_record_label_and_target_window():
    assert '--record' in launcher_command(sys.executable, 'record', 'Texas Poker')
    assert launcher_command(sys.executable, 'record', 'Texas Poker')[-2:] == ['--window-title', 'Texas Poker']
    assert '--label' in launcher_command(sys.executable, 'label')
    assert '--delay' not in launcher_command(sys.executable, 'record')
    assert launcher_command(sys.executable, 'run', 'Texas Poker')[-2:] == ['--window-title', 'Texas Poker']
