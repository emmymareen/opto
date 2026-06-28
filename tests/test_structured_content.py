import json

from opto.config import Config
from opto.pipeline import Pipeline


def _pipe(tmp_path):
    cfg = Config(
        cache_dir=tmp_path / "c",
        audit_log_path=tmp_path / "a.jsonl",
        telemetry_db=tmp_path / "t.db",
        min_tokens_to_compress=10,
    )
    cfg.ensure_dirs()
    return Pipeline(config=cfg)


def test_anthropic_structured_content_preserved(tmp_path):
    """Compress text blocks in place; never drop tool_use/image/cache_control."""
    big = json.dumps([{"id": i, "v": "x" * 10} for i in range(300)])
    msgs = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Summarize:\n" + big, "cache_control": {"type": "ephemeral"}},
            {"type": "tool_use", "id": "t1", "name": "run", "input": {"cmd": "ls"}},
            {"type": "image", "source": {"type": "base64", "data": "AAAA"}},
        ],
    }]
    out = _pipe(tmp_path).run([dict(m) for m in msgs])
    c = out.messages[0]["content"]
    assert isinstance(c, list) and len(c) == 3
    assert len(c[0]["text"]) < len(big)                       # text compressed
    assert c[0]["cache_control"] == {"type": "ephemeral"}     # metadata kept
    assert c[1]["type"] == "tool_use" and c[1]["name"] == "run"
    assert c[2]["type"] == "image" and c[2]["source"]["data"] == "AAAA"
    assert out.report.saved_fraction > 0.5


def test_non_text_only_message_untouched(tmp_path):
    msgs = [{"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}]
    out = _pipe(tmp_path).run([dict(m) for m in msgs])
    assert out.messages[0]["content"] == msgs[0]["content"]
