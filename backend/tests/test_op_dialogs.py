from pathlib import Path
import re


WEB = Path(__file__).resolve().parents[2] / 'web'


def test_op_actions_do_not_require_native_browser_dialogs():
    for name in ('op.js', 'op-management.js', 'op-complete.js', 'op-agent-observatory.js'):
        source = (WEB / name).read_text(encoding='utf-8')
        assert not re.search(r'(?<![\w.])(?:window\.)?(?:prompt|confirm|alert)\(', source), name


def test_op_dialog_dependencies_and_workspace_answer_renderer():
    source = (WEB / 'op.html').read_text(encoding='utf-8')
    assert source.index('/op-dialogs.js?') < source.index('/op-management.js?')
    assert '/op-dialogs.css?' in source
    workspace = (WEB / 'op-shop.html').read_text(encoding='utf-8')
    assert workspace.index('/assistant-presentation.js?') < workspace.index('/app.js?')


def test_reason_dialog_is_text_only_and_fail_closed():
    source = (WEB / 'op-dialogs.js').read_text(encoding='utf-8')
    assert 'innerHTML' not in source
    assert 'field.maxLength = 200' in source
    assert "op-session-ended" in source
    assert "sessionStorage.getItem('token_op') === identity" in source
    assert 'event.preventDefault(); cancelAction();' in source
