"""Self-checks for brain.py. Run: python brain.py selftest"""
import datetime
import shutil
import tempfile
import traceback
from pathlib import Path

import brain


def test_frontmatter_parses_scalars_and_lists():
    meta, body = brain.parse_frontmatter(
        "---\nslug: python-async\nlevel: 2\nevidence: [a, b]\n---\n\n# Body\n"
    )
    assert meta == {"slug": "python-async", "level": 2, "evidence": ["a", "b"]}, meta
    assert body == "# Body\n", repr(body)


def test_frontmatter_empty_list_is_empty_not_blank_string():
    meta, _ = brain.parse_frontmatter("---\nevidence: []\n---\nx\n")
    assert meta["evidence"] == [], meta


def test_frontmatter_keeps_later_dashes_in_body():
    _, body = brain.parse_frontmatter("---\na: 1\n---\nintro\n\n---\n\nmore\n")
    assert "---" in body, repr(body)


def test_frontmatter_missing_block_raises():
    try:
        brain.parse_frontmatter("# no frontmatter here\n")
    except brain.FrontmatterError:
        return
    raise AssertionError("expected FrontmatterError")


def test_frontmatter_unterminated_block_raises():
    try:
        brain.parse_frontmatter("---\na: 1\nstill going\n")
    except brain.FrontmatterError:
        return
    raise AssertionError("expected FrontmatterError")


def test_frontmatter_line_without_colon_raises():
    try:
        brain.parse_frontmatter("---\na: 1\nbroken line\n---\nx\n")
    except brain.FrontmatterError:
        return
    raise AssertionError("expected FrontmatterError")


def test_next_interval_advances_clamps_and_resets():
    iv = [1, 3, 7, 16, 35]
    assert brain.next_interval(1, iv, True) == 3
    assert brain.next_interval(16, iv, True) == 35
    assert brain.next_interval(35, iv, True) == 35, "must clamp at the top"
    assert brain.next_interval(7, iv, False) == 3
    assert brain.next_interval(1, iv, False) == 1, "must floor at the bottom"
    assert brain.next_interval(99, iv, True) == 1, "unknown interval restarts"


def test_parse_date_returns_none_on_garbage():
    assert brain.parse_date("2026-09-19") == datetime.date(2026, 9, 19)
    assert brain.parse_date("not-a-date") is None
    assert brain.parse_date(None) is None
    assert brain.parse_date("", fallback="X") == "X"


def test_load_config_merges_defaults():
    config = brain.load_config()
    assert config["policy"]["intervals_days"] == [1, 3, 7, 16, 35], config["policy"]
    assert config["paths"]["notes"] == "data/notes", config["paths"]


def _tmp_root():
    """A temp dir containing a copy of config.json, cleaned up by the caller."""
    root = Path(tempfile.mkdtemp(prefix="brain-test-"))
    shutil.copy(str(brain.ROOT / "config.json"), str(root / "config.json"))
    return root


def test_init_creates_tree_and_is_idempotent():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert brain.cmd_init(config, root) == 0
        data = root / "data"
        for sub in ("notes", "skills", "log", "local"):
            assert (data / sub).is_dir(), "missing " + sub
        assert (data / "target.md").is_file()
        assert (data / "state.json").is_file()
        assert (data / "questions.md").is_file()
        assert (data / ".gitignore").read_text(encoding="utf-8").strip() == "local/"

        (data / "target.md").write_text("EDITED", encoding="utf-8")
        assert brain.cmd_init(config, root) == 0, "second run must succeed"
        assert (data / "target.md").read_text(encoding="utf-8") == "EDITED", \
            "init must never overwrite existing content"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_init_data_repo_has_no_remote():
    root = _tmp_root()
    try:
        brain.cmd_init(brain.load_config(), root)
        data = root / "data"
        assert data.is_dir(), "init must create data/ whether or not git exists"
        if (data / ".git").exists():
            assert brain.has_remote(data) is False, "data/ must never have a remote"
        else:
            # git unavailable here; has_remote must still answer False, not raise
            assert brain.has_remote(data) is False
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_init_writes_valid_state_json():
    root = _tmp_root()
    try:
        brain.cmd_init(brain.load_config(), root)
        import json as _json
        state = _json.loads((root / "data" / "state.json").read_text(encoding="utf-8"))
        assert state["in_flight"] is None, state
        assert state["schema"] == 1, state
        assert state["bootstrapped"] == [], state
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def run():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print("ok   " + name)
        except Exception:
            failed.append(name)
            print("FAIL " + name)
            traceback.print_exc()
    print("\n%d passed, %d failed" % (len(tests) - len(failed), len(failed)))
    return 1 if failed else 0
