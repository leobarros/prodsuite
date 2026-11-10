from pathlib import Path

POMODORO_JS = Path(__file__).resolve().parents[1] / "static" / "js" / "pomodoro.js"


def test_pomodoro_js_keeps_required_runtime_helpers():
    source = POMODORO_JS.read_text(encoding="utf-8")
    for symbol in (
        "function serverNowMs(",
        "function start(",
        "function pause(",
        "function reset(",
        "function completeCycle(",
        "function playChime(",
        "function useMixingAudioSession(",
        'session.type = "ambient"',
    ):
        assert symbol in source, f"helper ausente no pomodoro.js: {symbol}"
