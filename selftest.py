"""Self-checks for brain.py. Run: python brain.py selftest"""
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
    config = _load_config_from({"assistants": "oops"})
    assert config["assistants"] == [], config["assistants"]


def test_load_config_falls_back_for_non_dict_policy():
    config = _load_config_from({"policy": "oops"})
    assert config["policy"]["mastery_level"] == 5, config["policy"]
    assert config["policy"]["daily_items"] == 3, config["policy"]


def test_load_config_partial_config_merges_over_defaults():
    config = _load_config_from({"policy": {"daily_items": 7}})
    assert config["policy"]["daily_items"] == 7, "override must apply"
    assert config["policy"]["mastery_level"] == 5, "omitted key must keep default"


def test_load_config_rejects_absolute_path():
    config = _load_config_from({"paths": {"notes": "/etc/passwd"}})
    assert config["paths"]["notes"] == "data/notes", config["paths"]


def test_load_config_rejects_path_traversal():
    config = _load_config_from({"paths": {"notes": "../../escape"}})
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
    config = _load_config_from({"paths": {"notes": "data"}})
    assert config["paths"]["notes"] == "data/notes", config["paths"]


def test_load_config_keeps_paths_under_a_renamed_data_root():
    config = _load_config_from(
        {"paths": {"data": "brain-data", "notes": "brain-data/notes"}})
    assert config["paths"]["data"] == "brain-data", config["paths"]
    assert config["paths"]["notes"] == "brain-data/notes", config["paths"]


def test_load_config_rejects_path_outside_a_renamed_data_root():
    # notes' value happens to equal its own default ("data/notes"), so a plain
    # value check can't tell "left untouched" from "rejected and fell back to
    # the same string" - assert the containment check actually fired instead.
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        config = _load_config_from(
            {"paths": {"data": "brain-data", "notes": "data/notes"}})
    assert config["paths"]["data"] == "brain-data", config["paths"]
    assert config["paths"]["notes"] == "data/notes", \
        "notes must fall back to its default - it no longer sits under the renamed data root"
    assert "not inside paths.data" in buf.getvalue(), \
        "containment check must fire even though the fallback string is unchanged: " + buf.getvalue()


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


def _silent(fn, *args, **kwargs):
    """Call a cmd_* function with stdout captured, so selftest output stays pristine."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _tmp_root():
    """A temp dir containing a copy of config.json, cleaned up by the caller."""
    root = Path(tempfile.mkdtemp(prefix="brain-test-"))
    shutil.copy(str(brain.ROOT / "config.json"), str(root / "config.json"))
    return root


def _write_skill(root, slug, level, next_review, target_level=3):
    path = root / "data" / "skills" / (slug + ".md")
    path.write_text(
        "---\nslug: %s\nlevel: %d\ntarget_level: %d\n"
        "last_reviewed: 2026-01-01\nnext_review: %s\ninterval_days: 1\nevidence: []\n"
        "---\n\n## Level rationale\nseeded\n" % (slug, level, target_level, next_review),
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
        assert state["bootstrapped"] == [], state
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
        skills = brain.read_skills(config, root)
        assert [s["slug"] for s in skills] == ["good"], skills
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
            '{"schema": 1, "in_flight": "oops", "bootstrapped": []}', encoding="utf-8")
        assert _silent(brain.cmd_due, config, root) == 0
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
        adj, nodes = brain.build_graph(config, root)
        assert nodes["x"] == "skill", nodes
        orphans = [n for n, kind in nodes.items() if kind == "note" and not adj.get(n)]
        assert "x" not in orphans, orphans
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_load_config_falls_back_for_non_int_graph_min_notes():
    config = _load_config_from({"policy": {"graph_min_notes": "30"}})
    assert config["policy"]["graph_min_notes"] == 30, config["policy"]
    root = _tmp_root()
    try:
        assert _silent(brain.cmd_init, config, root) == 0
        assert _silent(brain.cmd_graph, config, root) == 0
    finally:
        shutil.rmtree(str(root), ignore_errors=True)


def test_due_survives_non_int_daily_items():
    config = _load_config_from({"policy": {"daily_items": "3"}})
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
