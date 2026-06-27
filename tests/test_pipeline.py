import json


from opto.config import Config
from opto.pipeline import Pipeline
from opto.router import classify
from opto.types import ContentKind
from opto.compressors import get_compressor
from opto.relevance import score_chunks, apply_drop
from opto.types import Chunk


def make_config(tmp_path, **overrides):
    overrides.setdefault("min_tokens_to_compress", 10)
    cfg = Config(
        cache_dir=tmp_path / "cache",
        audit_log_path=tmp_path / "audit.jsonl",
        telemetry_db=tmp_path / "tel.sqlite",
        **overrides,
    )
    cfg.ensure_dirs()
    return cfg


def test_classify_json():
    assert classify('{"a": [1,2,3], "b": "x"}') == ContentKind.JSON


def test_classify_code():
    src = "def foo(x):\n    return x + 1\n\nclass Bar:\n    pass\n"
    assert classify(src) == ContentKind.CODE


def test_classify_log():
    log = "\n".join(f"2025-01-01 12:00:0{i} INFO starting {i}" for i in range(6))
    assert classify(log) == ContentKind.LOG


def test_json_crusher_reduces_long_arrays():
    big = json.dumps([{"i": i, "v": "x" * 5} for i in range(200)])
    out = get_compressor(ContentKind.JSON).compress(big, 0.6)
    assert len(out) < len(big)
    assert "elided" in out


def test_code_compressor_strips_comments():
    code = "# a comment\ndef f():\n    return 1  \n\n\n\n# another\nx = 2\n"
    out = get_compressor(ContentKind.CODE).compress(code, 0.5)
    assert "a comment" not in out
    assert "def f()" in out


def test_relevance_drops_irrelevant():
    chunks = [
        Chunk(text="completely unrelated banana smoothie recipe steps"),
        Chunk(text="the authentication token refresh logic in auth module"),
    ]
    score_chunks(chunks, "fix the authentication token refresh bug")
    apply_drop(chunks, threshold=0.5)
    # the auth chunk must survive
    assert not chunks[1].dropped


def test_pipeline_compresses_and_reports(tmp_path):
    cfg = make_config(tmp_path)
    pipe = Pipeline(config=cfg)
    big_json = json.dumps([{"id": i, "name": f"item{i}", "blob": "y" * 20} for i in range(300)])
    messages = [
        {"role": "system", "content": "You are a helpful coding assistant."},
        {"role": "user", "content": "Summarize this tool output:\n" + big_json},
    ]
    out = pipe.run(messages)
    assert out.report.original_tokens > out.report.compressed_tokens
    assert out.report.saved_fraction > 0


def test_pipeline_skips_small_requests(tmp_path):
    cfg = make_config(tmp_path, min_tokens_to_compress=100000)
    pipe = Pipeline(config=cfg)
    messages = [{"role": "user", "content": "hi"}]
    out = pipe.run(messages)
    assert out.report.compressed is False
    assert out.messages == messages


def test_quality_gate_holdout_passes_through(tmp_path):
    cfg = make_config(tmp_path, holdout_fraction=0.5)
    pipe = Pipeline(config=cfg)
    big = json.dumps([{"id": i, "v": "z" * 10} for i in range(300)])
    messages = [{"role": "user", "content": big}]
    # run several; at least one should be held out as control given 50% rate
    held = 0
    for _ in range(20):
        out = pipe.run([dict(m) for m in messages])
        if out.report.held_out:
            held += 1
    assert held > 0


def test_reversible_cache_roundtrip(tmp_path):
    cfg = make_config(tmp_path)
    pipe = Pipeline(config=cfg)
    original = "def secret():\n    # important\n    return 42\n" * 20
    messages = [{"role": "user", "content": original}]
    pipe.run(messages)
    # at least one original should be retrievable from the cache
    files = list((tmp_path / "cache").glob("*.json"))
    assert files, "expected reversible cache to store originals"
