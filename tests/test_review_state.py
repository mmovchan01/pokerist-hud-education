from types import SimpleNamespace

import cv2

from editor_assistant import EditorAssistant
from profile_support import BUILTIN
from review_state import ReviewState


def test_manual_selection_does_not_cancel_diagnostics():
    state = ReviewState()
    ticket = state.begin('frame', 'hero1', 0)
    state.select()
    report = SimpleNamespace(suggestion=SimpleNamespace(automatic=True))
    assert state.accept(ticket, report)
    assert state.phase == 'ready'
    assert not state.can_auto_accept(enabled=True)


def test_stale_result_cannot_update_another_card():
    state = ReviewState()
    old = state.begin('frame', 'hero1', 0)
    current = state.begin('frame', 'hero2', 0)
    report = SimpleNamespace(suggestion=SimpleNamespace(automatic=True))
    assert not state.accept(old, report)
    assert state.accept(current, report)
    assert not state.can_auto_accept()  # explicit opt-in
    assert state.can_auto_accept(enabled=True)
    assert not state.can_auto_accept(enabled=True, variant=True)
    state.invalidate()
    assert not state.accept(current, report)


def test_report_explains_missing_templates(tmp_path):
    sample = cv2.imread(str(next((BUILTIN/'templates/card/Ks').glob('*.png'))))
    report = EditorAssistant(tmp_path).inspect(sample)
    assert report.state == 'no_templates'
    assert report.template_count == 0
    assert report.reason
    assert report.suggestion is None


def test_near_identical_sample_has_ranked_evidence():
    sample = cv2.imread(str(next((BUILTIN/'templates/card/Ks').glob('*.png'))))
    sample = cv2.GaussianBlur(sample, (3, 3), .35)
    report = EditorAssistant(BUILTIN/'templates').inspect(sample)
    assert report.state == 'recognized'
    assert report.suggestion.label == 'Ks'
    assert report.suggestion.method == 'template matching'
    assert report.candidates[0]['path']
    assert report.candidates[0]['score'] >= .94
    assert report.elapsed_ms >= 0
