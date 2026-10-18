from review_helpers import eligible_items, progress, region_title, template_inventory
from profile_support import BUILTIN


def test_progress_and_scopes_include_reused_and_empty():
    record = {'items': {
        'hero1': {'kind': 'card', 'status': 'exported'},
        'board1': {'kind': 'empty', 'status': 'reused'},
        'board2': {'kind': 'card', 'status': 'pending'},
        'pot': {'kind': 'glyph', 'status': 'pending'}}}
    assert eligible_items(record) == ['hero1', 'board1', 'board2']
    assert progress(record) == (2, 3)
    assert progress(record, False) == (2, 4)


def test_readable_region_names():
    assert region_title('hero2') == 'Ваша карта 2'
    assert region_title('board4') == 'Борд · карта 4'
    assert region_title('oppstack3') == 'Стек соперника 3'
    assert region_title('pot') == 'Банк'


def test_library_contains_readable_samples_only(tmp_path):
    counts, paths = template_inventory(BUILTIN/'templates')
    assert len(counts) == 13
    assert paths['Ks']
    counts, paths = template_inventory(tmp_path)
    assert not counts
    assert len(paths) == 52
