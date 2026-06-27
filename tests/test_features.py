
from opto.compressors.code import CodeCompressor
from opto.compressors.prose import extractive_summary, compress_prose, set_prose_model
from opto.cachealign import preserved_indices
from opto.evals import EvalHarness, load_sample_tasks


def test_ast_compresses_python_and_keeps_signatures():
    src = (
        "import os\n\n"
        "def add(a, b):\n"
        "    # internal\n"
        "    total = a + b\n"
        "    for i in range(100):\n"
        "        total += i\n"
        "    return total\n\n"
        "class Service:\n"
        "    def start(self, port):\n"
        "        do_a_lot_of_things()\n"
        "        return port\n"
    )
    out = CodeCompressor().compress(src, aggressiveness=0.6)
    assert "def add(a, b):" in out
    assert "class Service:" in out
    assert "def start(self, port):" in out
    assert "body elided" in out
    assert len(out) < len(src)
    # the noisy loop body should be gone
    assert "total += i" not in out


def test_ast_falls_back_on_non_python():
    js = "function foo() {\n  // c\n  return 1;\n}\n" * 5
    out = CodeCompressor().compress(js, aggressiveness=0.6)
    assert "function foo()" in out  # regex path keeps it, just trims


def test_extractive_summary_shortens_long_prose():
    text = (
        "The system has many parts. " * 10
        + "The critical detail is that the timeout is 30 seconds. "
        + "Background information continues for a while. " * 10
    )
    out = extractive_summary(text, keep_ratio=0.3)
    assert len(out) < len(text)
    assert "elided" in out


def test_prose_model_hook_used_then_reset():
    set_prose_model(lambda t, r: "MODEL_OUTPUT")
    try:
        assert compress_prose("x" * 500, 0.5) == "MODEL_OUTPUT"
    finally:
        set_prose_model(None)
    assert compress_prose("x" * 500, 0.5) != "MODEL_OUTPUT"


def test_cache_alignment_preserves_system():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ]
    assert preserved_indices(msgs, preserve_system=True, pin_prefix=0) == {0}
    assert preserved_indices(msgs, preserve_system=True, pin_prefix=1) == {0, 1}
    assert preserved_indices(msgs, preserve_system=False, pin_prefix=0) == set()


def test_eval_dry_run_reports_savings():
    res = EvalHarness().dry_run(load_sample_tasks())
    assert res.n == 3
    assert res.saved_fraction > 0
