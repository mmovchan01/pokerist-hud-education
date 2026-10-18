import json
from pathlib import Path

import cv2
import pytest

from profile_support import BUILTIN, check_aspect, load_profile, seed_templates
from template_labels import folder_label, label_folder
from vision import Recognizer, TemplateBank

CASES = json.loads((BUILTIN/'verification_cases.json').read_text())


@pytest.fixture(scope='module')
def recognizer():
    return Recognizer(load_profile(), TemplateBank(BUILTIN/'templates'))


@pytest.mark.parametrize('case', CASES, ids=lambda c: Path(c['file']).stem)
def test_reference_crops(recognizer, case):
    image = cv2.imread(str(BUILTIN/case['file']))
    reading = recognizer.number(image) if case['numeric'] else recognizer.symbol(image, ('card', 'empty'))
    assert reading.status == case['expected_status']
    if reading.status == 'known':
        assert reading.value == case['ground_truth']
    else:
        assert reading.value is None


def test_install_idempotent_and_non_destructive(tmp_path):
    first = seed_templates(tmp_path)
    assert first > 0
    assert seed_templates(tmp_path) == 0
    manual = tmp_path/'card'/'Ah'/'manual.png'
    manual.parent.mkdir(exist_ok=True)
    manual.write_bytes(b'manual data')
    assert seed_templates(tmp_path) == 0
    assert manual.read_bytes() == b'manual data'
    bank = TemplateBank(tmp_path)
    assert '.' in {label for label, _ in bank.candidates('glyph')}


def test_profile_aspect():
    check_aspect(1280, 719, (1280, 719))
    check_aspect(1920, 1080, (1280, 719))
    with pytest.raises(ValueError):
        check_aspect(1000, 1000, (1280, 719))


@pytest.mark.parametrize('label', ['.', ',', 'A', '7', 'K'])
def test_portable_template_labels(label):
    assert folder_label(label_folder(label)) == label
    if label == '.':
        assert label_folder(label) != '.'


def test_missing_suffix_is_not_silently_dropped(recognizer):
    from numeric_vision import recognize_number
    image = cv2.imread(str(BUILTIN/'verification_crops/photo6_call.png'))
    samples = [(label, sample) for label, sample in recognizer.bank.candidates('glyph') if label != 'K']
    text, _ = recognize_number(image, samples)
    assert text is None


def test_legacy_decimal_samples_are_loaded(tmp_path):
    # Older code interpreted glyph/'.' as glyph/ and wrote files there.
    folder = tmp_path/'glyph'
    folder.mkdir()
    source = next((BUILTIN/'templates/glyph/dot').glob('*.png'))
    (folder/'legacy.png').write_bytes(source.read_bytes())
    assert [label for label, _ in TemplateBank(tmp_path).candidates('glyph')] == ['.']


@pytest.mark.parametrize('number', range(1, 7))
def test_complete_uploaded_screenshot(recognizer, number):
    # These are still training/reference images, not an accuracy holdout.
    path = BUILTIN.parents[1]/'photo example'/f'photo_{number}_2026-10-18_20-58-33.jpg'
    if not path.exists():
        pytest.skip('Original uploads not included in this distribution')
    frame = cv2.imread(str(path))
    state, readings, error = recognizer.read(frame, override=2)
    # 2 is a manual test input, NOT an inferred or annotated opponent count.
    if number == 6:
        assert not error
        assert state.hero == ('Ks', '8d')
        assert state.board == ('6c', 'Qs', '7s', '5h')
        assert (state.pot, state.call, state.stack) == (11900, 5500, 13950)
    else:
        assert state is None
        assert error
