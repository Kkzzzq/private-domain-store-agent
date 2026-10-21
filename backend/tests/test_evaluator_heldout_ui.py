from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"


def test_heldout_reveal_uses_inline_reason_form_instead_of_prompt():
    """内嵌浏览器/沙箱 iframe 会禁用 prompt()，揭示理由必须用页面内输入框。"""
    script = (WEB / "op-agent-quality.js").read_text(encoding="utf-8")
    assert "window.prompt" not in script
    assert "prompt('" not in script and 'prompt("' not in script
    assert "aq-heldout-form" in script and "提交揭示" in script
    style = (WEB / "op-agent-quality.css").read_text(encoding="utf-8")
    assert ".aq-heldout-form[hidden]{display:none}" in style
