"""Self-checks for brain.py. Run: python brain.py selftest"""
import ast
import contextlib
import datetime
import io
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


def _load_config_from(loaded):
    """load_config() as if config.json on disk held `loaded`. Never leaves brain.ROOT
    monkeypatched - restores it even if load_config() raises."""
    import json as _json
    root = Path(tempfile.mkdtemp(prefix="brain-test-"))
    original_root = brain.ROOT
    try:
        (root / "config.json").write_text(_json.dumps(loaded), encoding="utf-8")
        brain.ROOT = root
        return brain.load_config()
    finally:
        brain.ROOT = original_root
        shutil.rmtree(str(root), ignore_errors=True)


def test_load_config_falls_back_for_non_list_assistants():
    config = _silent(_load_config_from, {"assistants": "oops"})
    assert config["assistants"] == [], config["assistants"]


def test_load_config_falls_back_for_non_dict_policy():
    config = _silent(_load_config_from, {"policy": "oops"})
    assert config["policy"]["mastery_level"] == 5, config["policy"]
    assert config["policy"]["daily_items"] == 3, config["policy"]


def test_load_config_partial_config_merges_over_defaults():
    config = _load_config_from({"policy": {"daily_items": 7}})
    assert config["policy"]["daily_items"] == 7, "override must apply"
    assert config["policy"]["mastery_level"] == 5, "omitted key must keep default"


def test_load_config_rejects_absolute_path():
    config = _silent(_load_config_from, {"paths": {"notes": "/etc/passwd"}})
    assert config["paths"]["notes"] == "data/notes", config["paths"]


def test_load_config_rejects_path_traversal():
    config = _silent(_load_config_from, {"paths": {"notes": "../../escape"}})
    assert config["paths"]["notes"] == "data/notes", config["paths"]


def test_load_config_keeps_legitimate_relative_override():
    config = _load_config_from({"paths": {"notes": "data/knowledge"}})
    assert config["paths"]["notes"] == "data/knowledge", config["paths"]


def test_load_config_rejects_path_outside_data_root():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from({"paths": {"notes": "elsewhere"}})
    assert config["paths"]["notes"] == "data/notes", config["paths"]
    assert "paths.'notes'" in buf.getvalue(), "must warn: " + buf.getvalue()


def test_load_config_rejects_path_equal_to_data_root():
    config = _silent(_load_config_from, {"paths": {"notes": "data"}})
    assert config["paths"]["notes"] == "data/notes", config["paths"]


def test_load_config_pins_paths_data_to_its_default():
    # paths.data is pinned: the outer .gitignore matches the literal string
    # "data/", so a renamed data root would move the whole brain - notes and
    # local/ alike - into the pushable public repo. Renaming is refused
    # outright, not merely contained.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from(
            {"paths": {"data": "brain-data", "notes": "brain-data/notes"}})
    assert config["paths"]["data"] == "data", config["paths"]
    assert config["paths"]["notes"] == "data/notes", \
        "notes must fall back too - it no longer sits under the (rejected) renamed root"
    assert "paths.'data' is pinned" in buf.getvalue(), \
        "must warn that paths.data is pinned: " + buf.getvalue()


def test_load_config_pins_paths_local_to_its_default():
    # paths.local is pinned: data/.gitignore hardcodes "local/", so renaming
    # paths.local would silently drop that inner ignore layer.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from({"paths": {"local": "data/private"}})
    assert config["paths"]["local"] == "data/local", config["paths"]
    assert "paths.'local' is pinned" in buf.getvalue(), \
        "must warn that paths.local is pinned: " + buf.getvalue()


def test_load_config_rejects_backslash_path_outside_data_root():
    # PureWindowsPath splits on '\' as well as '/', so "data\sibling" reads as
    # in-bounds if only PureWindowsPath is consulted. The real join uses the
    # platform-native Path (PurePosixPath on Linux/macOS), which treats the
    # whole string as one opaque component - a sibling of data/, not a child.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from({"paths": {"notes": "data\\sibling"}})
    assert config["paths"]["notes"] == "data/notes", config["paths"]
    assert "not inside paths.data" in buf.getvalue(), \
        "must warn and reject the backslash escape: " + buf.getvalue()


def test_load_config_rejects_backslash_path_even_when_value_looks_safe():
    # "data\notes" falls back to "data/notes" - which is also the default -
    # so a bare value assertion would pass whether this was rejected or
    # accidentally accepted. Assert on the warning instead: the same trap a
    # value-only assertion hit in the previous review round.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from({"paths": {"notes": "data\\notes"}})
    assert config["paths"]["notes"] == "data/notes", config["paths"]
    assert "not inside paths.data" in buf.getvalue(), \
        "backslash values must be rejected even though the fallback string coincides: " \
        + buf.getvalue()


def test_load_config_accepts_deep_forward_slash_path_under_data_root():
    config = _load_config_from({"paths": {"notes": "data/notes/deep"}})
    assert config["paths"]["notes"] == "data/notes/deep", config["paths"]


PERSONAS = ["scout", "teacher", "examiner", "scribe", "critic", "archivist"]
PERSONA_SECTIONS = ["## Gets", "## Produces", "## Forbidden", "## Done when"]


def test_every_persona_exists_with_all_four_sections():
    for name in PERSONAS:
        path = brain.ROOT / "personas" / (name + ".md")
        assert path.is_file(), "missing persona: " + name
        text = path.read_text(encoding="utf-8")
        for section in PERSONA_SECTIONS:
            assert section in text, "%s is missing %r" % (name, section)


def test_agents_md_references_every_persona():
    text = (brain.ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for name in PERSONAS:
        assert "personas/" + name + ".md" in text, "AGENTS.md never points at " + name


def test_templates_parse_as_frontmatter():
    for name in ("note", "skill"):
        path = brain.ROOT / "templates" / (name + ".md")
        assert path.is_file(), "missing template: " + name
        brain.parse_frontmatter(path.read_text(encoding="utf-8"))


def test_note_template_contains_a_wikilink():
    text = (brain.ROOT / "templates" / "note.md").read_text(encoding="utf-8")
    assert "[[" in text, "note template must demonstrate a [[link]]"


def _capture(fn, *args, **kwargs):
    """Call fn with stdout and stderr captured. Returns (result, stdout_text,
    stderr_text) - for tests that must inspect what a warning or a briefing
    actually printed."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = fn(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


def _silent(fn, *args, **kwargs):
    """Call a function with stdout and stderr captured, so selftest output
    stays pristine. Returns just the function's return value."""
    return _capture(fn, *args, **kwargs)[0]


def _tmp_root():
    """A temp dir containing a copy of config.json, cleaned up by the caller."""
    root = Path(tempfile.mkdtemp(prefix="brain-test-"))
    shutil.copy(str(brain.ROOT / "config.json"), str(root / "config.json"))
    return root


def _write_skill(root, slug, level, next_review, target_level=3, interval_days=1):
    path = root / "data" / "skills" / (slug + ".md")
    path.write_text(
        "---\nslug: %s\nlevel: %d\ntarget_level: %d\n"
        "last_reviewed: 2026-01-01\nnext_review: %s\ninterval_days: %d\nevidence: []\n"
        "---\n\n## Level rationale\nseeded\n"
        % (slug, level, target_level, next_review, interval_days),
        encoding="utf-8",
    )
    return path


def test_init_creates_tree_and_is_idempotent():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        data = root / "data"
        for sub in ("notes", "skills", "log", "local"):
            assert (data / sub).is_dir(), "missing " + sub
        assert (data / "target.md").is_file()
        assert (data / "state.json").is_file()
        assert (data / "questions.md").is_file()
        assert (data / ".gitignore").read_text(encoding="utf-8").strip() == "local/"

        (data / "target.md").write_text("EDITED", encoding="utf-8")
        assert _silent(brain.cmd_init, config, root) == 0, "second run must succeed"
        assert (data / "target.md").read_text(encoding="utf-8") == "EDITED", \
            "init must never overwrite existing content"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_init_data_repo_has_no_remote():
    root = _tmp_root()
    try:
        _silent(brain.cmd_init, brain.load_config(), root)
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
        _silent(brain.cmd_init, brain.load_config(), root)
        import json as _json
        state = _json.loads((root / "data" / "state.json").read_text(encoding="utf-8"))
        assert state["in_flight"] is None, state
        assert state["schema"] == 1, state
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_read_skills_skips_malformed_without_crashing():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        _write_skill(root, "good", 2, "2020-01-01")
        (root / "data" / "skills" / "broken.md").write_text(
            "no frontmatter at all\n", encoding="utf-8")
        skills = _silent(brain.read_skills, config, root)
        assert [s["slug"] for s in skills] == ["good"], skills
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_read_skills_falls_back_to_filename_when_slug_is_a_list():
    # C1 repro: templates/skill.md's own [a, b] syntax for evidence: also
    # applies to slug:, which then becomes an unhashable dict key downstream.
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        (root / "data" / "skills" / "weird.md").write_text(
            "---\nslug: [python-async]\nlevel: 2\n---\n\nbody\n", encoding="utf-8")
        skills, _out, err = _capture(brain.read_skills, config, root)
        assert [s["slug"] for s in skills] == ["weird"], skills
        assert "weird.md" in err, "must warn naming the file: " + err
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_does_not_crash_on_non_str_slug():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        (root / "data" / "skills" / "weird.md").write_text(
            "---\nslug: [python-async]\nlevel: 2\n---\n\nbody\n", encoding="utf-8")
        assert _silent(brain.cmd_due, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_reports_overdue_and_skips_mastered():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        _write_skill(root, "overdue-one", 2, "2020-01-01")
        _write_skill(root, "future-one", 2, "2099-01-01")
        _write_skill(root, "mastered-one", 5, "2020-01-01")
        assert _silent(brain.cmd_due, config, root) == 0
        skills = brain.read_skills(config, root)
        due = brain.due_skills(skills, config, brain.today())
        names = [s["slug"] for s in due]
        assert "overdue-one" in names, names
        assert "future-one" not in names, names
        assert "mastered-one" not in names, "level 5 leaves the rotation"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_treats_a_bad_date_as_due_now():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        _write_skill(root, "garbled", 1, "not-a-date")
        due = brain.due_skills(brain.read_skills(config, root), config, brain.today())
        assert [s["slug"] for s in due] == ["garbled"], due
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_on_empty_brain_says_cold_start():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        assert _silent(brain.cmd_due, config, root) == 0, "empty brain must not error"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_without_init_does_not_crash():
    root = _tmp_root()
    try:
        assert _silent(brain.cmd_due, brain.load_config(), root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_skips_non_utf8_skill_file():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        (root / "data" / "skills" / "bad.md").write_bytes(b"---\nslug: x\n---\n\xff\n")
        assert _silent(brain.cmd_due, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_skips_non_utf8_questions_file():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        _write_skill(root, "good", 1, "2020-01-01")
        (root / "data" / "questions.md").write_bytes(b"\xff\n")
        assert _silent(brain.cmd_due, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_treats_non_dict_state_as_default():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        (root / "data" / "state.json").write_text("42", encoding="utf-8")
        assert _silent(brain.cmd_due, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_treats_non_dict_in_flight_as_none():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        (root / "data" / "state.json").write_text(
            '{"schema": 1, "in_flight": "oops"}', encoding="utf-8")
        assert _silent(brain.cmd_due, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_read_state_warns_on_corrupt_json():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        (root / "data" / "state.json").write_text("not json{", encoding="utf-8")
        state, _out, err = _capture(brain.read_state, config, root)
        assert state == {"schema": 1, "in_flight": None}, state
        assert "state.json" in err, "must warn about the corrupt state file: " + err
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_output_has_briefing_due_and_gap_lines():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        _write_skill(root, "overdue-one", 2, "2020-01-01", target_level=4)
        result, out, _err = _capture(brain.cmd_due, config, root)
        assert result == 0
        assert out.startswith("BRIEFING " + brain.today().isoformat()), out
        assert "due: overdue-one(L2, " in out, out
        assert "gap: overdue-one (L2, target L4)" in out, out
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_bootstrap_is_idempotent_and_additive():
    root = _tmp_root()
    try:
        shutil.copytree(str(brain.ROOT / "adapters"), str(root / "adapters"))
        config = brain.load_config()

        assert _silent(brain.cmd_bootstrap, "cursor", config, root) == 0
        cursor_cmd = root / ".cursor" / "commands" / "start.md"
        assert cursor_cmd.is_file(), "cursor adapter not installed"
        first = cursor_cmd.read_text(encoding="utf-8")

        assert _silent(brain.cmd_bootstrap, "cursor", config, root) == 0, "second run must succeed"
        assert cursor_cmd.read_text(encoding="utf-8") == first, "must be idempotent"

        assert _silent(brain.cmd_bootstrap, "claude", config, root) == 0
        assert (root / "CLAUDE.md").is_file(), "claude adapter not installed"
        assert cursor_cmd.is_file(), "installing claude must not remove cursor"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_bootstrap_records_assistant_in_config_once():
    root = _tmp_root()
    try:
        shutil.copytree(str(brain.ROOT / "adapters"), str(root / "adapters"))
        config = brain.load_config()
        _silent(brain.cmd_bootstrap, "cursor", config, root)
        _silent(brain.cmd_bootstrap, "cursor", config, root)
        import json as _json
        written = _json.loads((root / "config.json").read_text(encoding="utf-8"))
        assert written["assistants"] == ["cursor"], written["assistants"]
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_bootstrap_rejects_unknown_assistant():
    root = _tmp_root()
    try:
        assert _silent(brain.cmd_bootstrap, "emacs-doctor", brain.load_config(), root) == 1
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_claude_adapter_imports_agents_md():
    text = (brain.ROOT / "adapters" / "claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.lstrip().startswith("@AGENTS.md"), \
        "CLAUDE.md must import AGENTS.md on line 1, not duplicate it"


def test_extract_links_finds_wikilinks_only():
    body = "sees [[alpha]] and [[beta-two]] but not [plain](x) or [[]]"
    assert brain.extract_links(body) == ["alpha", "beta-two"], brain.extract_links(body)


def test_extract_links_does_not_span_a_newline():
    body = "broken [[a\nb]] but real [[real]]"
    assert brain.extract_links(body) == ["real"], brain.extract_links(body)


def test_articulation_point_on_a_known_graph():
    # alpha - center - beta : center is the only cut vertex
    adj = {"alpha": {"center"}, "center": {"alpha", "beta"}, "beta": {"center"}}
    assert brain.articulation_points(adj) == {"center"}, brain.articulation_points(adj)


def test_articulation_points_empty_on_a_triangle():
    adj = {"a": {"b", "c"}, "b": {"a", "c"}, "c": {"a", "b"}}
    assert brain.articulation_points(adj) == set()


def test_graph_finds_orphans_and_broken_links():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        notes = root / "data" / "notes"
        (notes / "2026-01-01-alone.md").write_text(
            "---\nid: alone\nskill: x\ncreated: 2026-01-01\n---\n\nno links here\n",
            encoding="utf-8")
        (notes / "2026-01-02-points-nowhere.md").write_text(
            "---\nid: points-nowhere\nskill: x\ncreated: 2026-01-02\n---\n\n"
            "see [[ghost]]\n", encoding="utf-8")
        adj, nodes = brain.build_graph(config, root)
        orphans = [n for n in nodes if not adj.get(n)]
        assert "2026-01-01-alone" in orphans, orphans
        assert "ghost" in adj.get("2026-01-02-points-nowhere", set()), adj
        assert nodes.get("ghost") == "broken", nodes
        assert _silent(brain.cmd_graph, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_graph_skill_classification_beats_same_named_note():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        _write_skill(root, "x", 2, "2099-01-01")
        (root / "data" / "notes" / "x.md").write_text(
            "---\nid: x\nskill: x\ncreated: 2026-01-01\n---\n\nno links here\n",
            encoding="utf-8")
        adj, nodes = _silent(brain.build_graph, config, root)
        assert nodes["x"] == "skill", nodes
        orphans = [n for n, kind in nodes.items() if kind == "note" and not adj.get(n)]
        assert "x" not in orphans, orphans
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_graph_reports_hubs_frontier_and_bridges_above_threshold():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        notes = root / "data" / "notes"
        minimum = config["policy"]["graph_min_notes"]

        (notes / "hub.md").write_text(
            "---\nid: hub\nskill: x\ncreated: 2026-01-01\n---\n\nthe hub\n",
            encoding="utf-8")
        for i in range(minimum):
            (notes / ("leaf-%02d.md" % i)).write_text(
                "---\nid: leaf-%02d\nskill: x\ncreated: 2026-01-01\n---\n\n"
                "see [[hub]]\n" % i, encoding="utf-8")
        _write_skill(root, "frontier-skill", 1, "2099-01-01")
        (notes / "frontier-note.md").write_text(
            "---\nid: frontier-note\nskill: x\ncreated: 2026-01-01\n---\n\n"
            "see [[hub]] and [[frontier-skill]]\n", encoding="utf-8")

        result, out, _err = _capture(brain.cmd_graph, config, root)
        assert result == 0
        lines = out.splitlines()
        assert not any(l.startswith("metrics: need") for l in lines), out

        hubs_line = next(l for l in lines if l.startswith("hubs:"))
        assert "hub" in hubs_line, hubs_line

        frontier_line = next(l for l in lines if l.startswith("frontier:"))
        assert "frontier-skill" in frontier_line, frontier_line

        bridges_line = next(l for l in lines if l.startswith("bridges:"))
        assert "hub" in bridges_line, bridges_line
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_load_config_falls_back_for_non_int_graph_min_notes():
    config = _silent(_load_config_from, {"policy": {"graph_min_notes": "30"}})
    assert config["policy"]["graph_min_notes"] == 30, config["policy"]
    root = _tmp_root()
    try:
        assert _silent(brain.cmd_init, config, root) == 0
        assert _silent(brain.cmd_graph, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_survives_non_int_daily_items():
    config = _silent(_load_config_from, {"policy": {"daily_items": "3"}})
    root = _tmp_root()
    try:
        assert _silent(brain.cmd_init, config, root) == 0
        _write_skill(root, "good", 2, "2020-01-01")
        assert _silent(brain.cmd_due, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_load_config_keeps_unknown_policy_key_untouched():
    config = _load_config_from({"policy": {"custom_key": "hello"}})
    assert config["policy"]["custom_key"] == "hello", config["policy"]


def test_load_config_falls_back_for_empty_intervals_days():
    # next_interval() does intervals[0] when there's no current match -
    # an empty list turns that into an IndexError instead of a warning.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from({"policy": {"intervals_days": []}})
    assert config["policy"]["intervals_days"] == [1, 3, 7, 16, 35], config["policy"]
    assert "intervals_days" in buf.getvalue(), "must warn: " + buf.getvalue()


def test_load_config_falls_back_for_non_int_intervals_days_elements():
    # The list-shape check passes (it is a list) but next_interval() compares
    # its elements to an int, so a str element raises TypeError, not a warning.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from({"policy": {"intervals_days": ["a", "b"]}})
    assert config["policy"]["intervals_days"] == [1, 3, 7, 16, 35], config["policy"]
    assert "intervals_days" in buf.getvalue(), "must warn: " + buf.getvalue()


def test_migrate_moves_folder_and_keeps_links_resolving():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        (root / "data" / "notes" / "2026-01-01-a.md").write_text(
            "---\nid: a\nskill: x\ncreated: 2026-01-01\n---\n\nsee [[2026-01-02-b]]\n",
            encoding="utf-8")
        (root / "data" / "notes" / "2026-01-02-b.md").write_text(
            "---\nid: b\nskill: x\ncreated: 2026-01-02\n---\n\nsee [[2026-01-01-a]]\n",
            encoding="utf-8")

        config["paths"]["notes"] = "data/knowledge"
        assert _silent(brain.cmd_migrate, config, root) == 0
        assert (root / "data" / "knowledge" / "2026-01-01-a.md").is_file()
        assert not (root / "data" / "notes").exists()

        _, nodes = brain.build_graph(config, root)
        assert nodes.get("2026-01-02-b") == "note", \
            "links must still resolve after the move, not become broken"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_migrate_warns_and_fails_on_target_collision():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        (root / "data" / "notes" / "keep.md").write_text("mine\n", encoding="utf-8")
        (root / "data" / "knowledge").mkdir()  # stray folder already at the target

        config["paths"]["notes"] = "data/knowledge"
        assert _silent(brain.cmd_migrate, config, root) == 1, \
            "a target collision must fail the run"
        assert (root / "data" / "notes" / "keep.md").is_file(), \
            "the original note must stay put on a collision"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_migrate_git_mv_preserves_history():
    if shutil.which("git") is None:
        print("skip: git not available in this environment - git mv history not verified")
        return
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        data = root / "data"

        brain.git(["config", "user.email", "test@example.com"], data)
        brain.git(["config", "user.name", "test"], data)
        (data / "notes" / "2026-01-01-a.md").write_text(
            "---\nid: a\nskill: x\ncreated: 2026-01-01\n---\n\nnote body\n",
            encoding="utf-8")
        code, out = brain.git(["add", "notes"], data)
        assert code == 0, out
        code, out = brain.git(["commit", "-m", "seed"], data)
        assert code == 0, out

        config["paths"]["notes"] = "data/knowledge"
        assert _silent(brain.cmd_migrate, config, root) == 0
        new_path = data / "knowledge" / "2026-01-01-a.md"
        assert new_path.is_file(), "file must exist at the new path after migrate"

        code, status_out = brain.git(["status", "--short"], data)
        assert code == 0, status_out
        assert status_out.startswith("R"), \
            "expected git mv to stage a rename, got: " + status_out

        code, out = brain.git(["commit", "-m", "migrate"], data)
        assert code == 0, out
        code, log_out = brain.git(
            ["log", "--follow", "--oneline", "--", "knowledge/2026-01-01-a.md"], data)
        assert code == 0 and log_out.strip(), \
            "git log --follow must show history at the new path: " + log_out
        assert "seed" in log_out, \
            "history must follow through the rename back to the original commit: " + log_out
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_decay_closes_expired_questions():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        (root / "data" / "questions.md").write_text(
            "# Open questions\n\n- 2020-01-01 ancient and unanswered\n"
            "- %s asked today\n" % brain.today().isoformat(), encoding="utf-8")
        actions = brain.decay_actions(config, root)
        joined = " | ".join(actions)
        assert "ancient and unanswered" in joined, joined
        assert "asked today" not in joined, joined
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_decay_flags_mastered_skills_leaving_rotation():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        _write_skill(root, "mastered-thing", 5, "2020-01-01", target_level=5)
        joined = " | ".join(brain.decay_actions(config, root))
        assert "mastered-thing" in joined, joined
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_schedule_pass_advances_interval_and_sets_dates():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        _write_skill(root, "adv", 2, "2020-01-01", interval_days=1)
        assert _silent(brain.cmd_schedule, "adv", True, config, root) == 0
        meta, _ = brain.parse_frontmatter(
            (root / "data" / "skills" / "adv.md").read_text(encoding="utf-8"))
        assert meta["interval_days"] == 3, meta
        assert meta["last_reviewed"] == brain.today().isoformat(), meta
        expected_next = (brain.today() + datetime.timedelta(days=3)).isoformat()
        assert meta["next_review"] == expected_next, meta
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_schedule_fail_steps_interval_back():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        _write_skill(root, "back", 2, "2020-01-01", interval_days=7)
        assert _silent(brain.cmd_schedule, "back", False, config, root) == 0
        meta, _ = brain.parse_frontmatter(
            (root / "data" / "skills" / "back.md").read_text(encoding="utf-8"))
        assert meta["interval_days"] == 3, meta
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_schedule_preserves_body_and_unrelated_frontmatter_keys():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        path = root / "data" / "skills" / "kept.md"
        path.write_text(
            "---\nslug: kept\nlevel: 2\ntarget_level: 3\n"
            "last_reviewed: 2020-01-01\nnext_review: 2020-01-01\ninterval_days: 1\n"
            "evidence: [a, b]\n---\n\n## Level rationale\nhand-written notes\n",
            encoding="utf-8")
        assert _silent(brain.cmd_schedule, "kept", True, config, root) == 0
        meta, body = brain.parse_frontmatter(path.read_text(encoding="utf-8"))
        assert meta["evidence"] == ["a", "b"], meta
        assert meta["level"] == 2, meta
        assert meta["target_level"] == 3, meta
        assert body == "## Level rationale\nhand-written notes\n", repr(body)
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_schedule_unknown_slug_returns_1_without_writing():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        assert _silent(brain.cmd_schedule, "ghost", True, config, root) == 1
        assert not (root / "data" / "skills" / "ghost.md").exists()
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_schedule_warns_and_returns_1_on_read_only_skill_file():
    root = _tmp_root()
    try:
        config = brain.load_config()
        assert _silent(brain.cmd_init, config, root) == 0
        path = _write_skill(root, "locked", 2, "2020-01-01", interval_days=1)
        path.chmod(0o444)
        try:
            code, _out, err = _capture(brain.cmd_schedule, "locked", True, config, root)
            assert code == 1, code
            assert "locked.md" in err, "must name the path: " + err
        finally:
            path.chmod(0o644)
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_interview_template_has_five_questions():
    text = (brain.ROOT / "templates" / "interview.md").read_text(encoding="utf-8")
    for n in range(1, 6):
        assert ("%d." % n) in text, "interview is missing question %d" % n


def _write_misses(root, entries):
    """Seed data/misses.md. entries are (days_ago, check, text)."""
    today = datetime.date.today()
    lines = ["# Misses", ""]
    for days_ago, check, text in entries:
        when = (today - datetime.timedelta(days=days_ago)).isoformat()
        lines.append("- %s %s | %s" % (when, check, text))
    (root / "data" / "misses.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def test_init_creates_checks_folder_and_miss_log():
    root = _tmp_root()
    try:
        _silent(brain.cmd_init, brain.load_config(), root)
        assert (root / "data" / "checks").is_dir(), "promoted checks need a home"
        assert (root / "data" / "misses.md").is_file()
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_misses_counts_by_check():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        _write_misses(root, [
            (1, "tests", "no failing case named"),
            (2, "tests", "empty input unhandled"),
            (3, "cost", "no smaller version considered"),
        ])
        live, promotions, expired, fired = brain.miss_summary(config, root)
        assert live == {"tests": 2, "cost": 1}, live
        assert promotions == [], promotions
        assert expired == [], expired
        assert fired == {"tests": 2, "cost": 1}, fired
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_misses_promotes_at_threshold():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        threshold = config["policy"]["promotion_threshold"]
        _write_misses(root, [(i, "rollback", "no undo path") for i in range(threshold)]
                      + [(1, "cost", "no cheaper version")])
        promotions = brain.miss_summary(config, root)[1]
        assert promotions == ["rollback"], promotions
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_misses_expired_do_not_count_toward_promotion():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        old = config["policy"]["miss_expiry_days"] + 10
        threshold = config["policy"]["promotion_threshold"]
        _write_misses(root, [(old + i, "rollback", "no undo path")
                             for i in range(threshold)])
        live, promotions, expired, fired = brain.miss_summary(config, root)
        assert live == {}, live
        assert promotions == [], "a habit fixed long ago must not promote itself"
        assert len(expired) == threshold, expired
        assert fired == {}, "an expired line is not a live firing either"
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_misses_expired_drain_through_decay():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        old = config["policy"]["miss_expiry_days"] + 1
        _write_misses(root, [(old, "tests", "stale one"), (1, "tests", "fresh one")])
        actions = brain.decay_actions(config, root)
        stale = [a for a in actions if a.startswith("expired miss")]
        assert len(stale) == 1, actions
        assert "stale one" in stale[0], stale
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_misses_ignores_prose_and_malformed_lines():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        (root / "data" / "misses.md").write_text(
            "# Misses\n\nSome note to myself about the format.\n"
            "- not-a-date tests | nope\n"
            "- 2026-13-45 tests | impossible date\n"
            "- %s tests | counted\n"
            "- %s Tests | uppercase slug is not a slug\n"
            "- %s tests |\n"
            % ((datetime.date.today().isoformat(),) * 3),
            encoding="utf-8")
        live = brain.miss_summary(config, root)[0]
        assert live == {"tests": 1}, live
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_misses_absent_file_never_raises():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        (root / "data" / "misses.md").unlink()
        assert brain.miss_summary(config, root) == ({}, [], [], {})
        result, out, err = _capture(brain.cmd_misses, config, root)
        assert result == 0, result
        assert "none logged" in out, out
        assert err == "", err
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_ok_lines_count_as_firings_not_misses():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        _write_misses(root, [
            (1, "tests", "no failing case named"),
            (2, "tests", "ok"),
            (3, "tests", "OK"),
            (4, "cost", "ok"),
        ])
        live, _, _, fired = brain.miss_summary(config, root)
        assert live == {"tests": 1}, live
        assert fired == {"tests": 3, "cost": 1}, fired
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_misses_shows_a_check_that_never_missed():
    """0 missed / 9 fired is the most informative row, so it must be printed.

    A table built from the miss counts alone would drop the row entirely and
    the gate would look like it had never run.
    """
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        _write_misses(root, [(i + 1, "operations", "ok") for i in range(3)])
        result, out, err = _capture(brain.cmd_misses, config, root)
        assert result == 0, result
        assert "operations" in out, out
        assert "0 / 3" in out, out
        assert err == "", err
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_expired_ok_lines_do_not_drain_through_decay():
    """An `ok` is not a miss, so there is nothing to report when it expires."""
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        old = config["policy"]["miss_expiry_days"] + 1
        _write_misses(root, [(old, "tests", "ok"), (old, "cost", "stale one")])
        stale = [a for a in brain.decay_actions(config, root)
                 if a.startswith("expired miss")]
        assert len(stale) == 1, stale
        assert "stale one" in stale[0], stale
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_misses_without_data_folder_points_at_init():
    root = _tmp_root()
    try:
        result, out, _ = _capture(brain.cmd_misses, brain.load_config(), root)
        assert result == 0, result
        assert "brain.py init" in out, out
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_surfaces_promotion_candidates():
    root = _tmp_root()
    try:
        config = brain.load_config()
        _silent(brain.cmd_init, config, root)
        _write_skill(root, "python-async", 2, datetime.date.today().isoformat())
        threshold = config["policy"]["promotion_threshold"]
        _write_misses(root, [(i, "rollback", "no undo path") for i in range(threshold)])
        result, out, _ = _capture(brain.cmd_due, config, root)
        assert result == 0, result
        assert "promote: rollback" in out, out
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_config_rejects_checks_path_outside_data():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from({"paths": {"checks": "elsewhere"}})
    assert config["paths"]["checks"] == "data/checks", config["paths"]
    assert "paths.'checks'" in buf.getvalue(), "must warn: " + buf.getvalue()


STDLIB_ALLOWLIST = {
    "argparse", "ast", "contextlib", "datetime", "io", "json", "pathlib", "re",
    "shutil", "subprocess", "sys", "tempfile", "traceback", "brain", "selftest",
}


def test_only_stdlib_and_local_modules_are_imported():
    # ADR-025: walk the AST, never match text - a regex anchored at line start
    # still missed a third-party name sharing a comma-separated import line
    # ("import json, requests" only ever matched "json"), and could never see
    # an import nested inside a function, such as brain.py's own
    # `import selftest` inside main(). A parsed tree has no such blind spots:
    # every Import/ImportFrom node is found regardless of where it sits.
    for name in ("brain.py", "selftest.py"):
        text = (brain.ROOT / name).read_text(encoding="utf-8")
        tree = ast.parse(text, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:  # relative import, e.g. "from . import x"
                    continue
                modules = [node.module.split(".")[0]]
            else:
                continue
            for module in modules:
                assert module in STDLIB_ALLOWLIST, \
                    "%s imports %r, not on the stdlib allow-list" % (name, module)


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
