"""W5.2 Task 3.3 — SKILL.md warning header + frontmatter (permissive policy).

Verifies ``_render_skill_md``:

- Cross-project candidates get the warning header block.
- Single-project candidates have NO warning header.
- Cross-project frontmatter gains ``project_distribution`` (basenames
  only — privacy P-5) + ``scope_recommended: global``.
- Absolute filesystem paths NEVER appear in the SKILL.md body.
- Permissive policy: all queries preserved even for cross-project.
"""

from __future__ import annotations

from datetime import UTC, datetime

from vibesop.core.observability.skill_promote import (
    ClusterCandidate,
    _format_cross_project_warning,
    _project_id_to_basename,
    _render_skill_md,
    _sanitize_body_text,
    dedupe_project_distribution,
)


def _make_candidate(
    *,
    cluster_id: str = "c1",
    queries: list[str] | None = None,
    project_distribution: dict[str, int] | None = None,
    span_count: int = 5,
) -> ClusterCandidate:
    return ClusterCandidate(
        cluster_id=cluster_id,
        task_ids=["t1", "t2"],
        queries=queries or ["example query one", "example query two"],
        span_count=span_count,
        gold_rate=0.8,
        gold_task_ids=["t1"],
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        project_distribution=project_distribution or {},
    )


class TestProjectIdToBasename:
    def test_basename_resolves_absolute_path(self) -> None:
        assert _project_id_to_basename("/Users/jane.doe/Projects/foo") == "foo"

    def test_basename_handles_short_id(self) -> None:
        # Defensive: project_id that's not a real path
        result = _project_id_to_basename("shortid")
        assert isinstance(result, str)
        assert len(result) > 0


class TestWarningBlock:
    def test_warning_block_lists_all_projects_by_basename(self) -> None:
        """Warning names source projects + their span counts."""
        block = _format_cross_project_warning({"/Users/jane/proj-a": 7, "/Users/jane/proj-b": 3})
        assert "Cross-project cluster" in block
        assert "`proj-a` (7 spans)" in block
        assert "`proj-b` (3 spans)" in block
        # Sorted by count desc → proj-a appears first.
        assert block.index("proj-a") < block.index("proj-b")

    def test_warning_block_empty_for_empty_distribution(self) -> None:
        """No distribution → no warning."""
        assert _format_cross_project_warning({}) == ""

    def test_warning_block_never_emits_absolute_paths(self) -> None:
        """Privacy P-5: absolute filesystem paths must not appear."""
        block = _format_cross_project_warning({"/Users/jane.doe/super/secret/path/proj-x": 5})
        assert "/Users/" not in block
        assert "jane.doe" not in block
        assert "secret" not in block
        assert "`proj-x`" in block


class TestRenderCrossProject:
    def test_render_cross_project_adds_warning_header(self) -> None:
        """SKILL.md body contains the warning header for heterogeneous clusters."""
        c = _make_candidate(
            project_distribution={"/users/me/a": 4, "/users/me/b": 2},
        )
        content = _render_skill_md(c, "custom/test-xp")
        assert "Cross-project cluster" in content
        assert "handle with care" in content.lower()

    def test_warning_header_appears_before_overview(self) -> None:
        """Pi re-review H2: warning must be the FIRST thing the user sees
        after the frontmatter close — positioned above ``## Overview``,
        not buried as the second paragraph inside Overview.
        """
        c = _make_candidate(
            project_distribution={"/users/me/a": 4, "/users/me/b": 2},
        )
        content = _render_skill_md(c, "custom/test-warn-pos")
        # Split frontmatter from body.
        body = content.split("---\n", 2)[2]
        overview_idx = body.find("## Overview")
        warning_idx = body.find("Cross-project cluster")
        assert overview_idx != -1 and warning_idx != -1, "missing required markers"
        assert warning_idx < overview_idx, (
            f"warning must precede ## Overview; got warning@{warning_idx} "
            f"vs overview@{overview_idx}"
        )
        # And the very first non-empty line of the body should be the
        # warning quote (``>``), not ``## Overview``.
        first_nonblank = next(
            (ln for ln in body.splitlines() if ln.strip()),
            "",
        )
        assert first_nonblank.startswith(">"), (
            f"first body line should be the warning quote; got: {first_nonblank!r}"
        )

    def test_render_single_project_has_no_warning_header(self) -> None:
        """SKILL.md for a single-project cluster has NO warning header."""
        c = _make_candidate(
            project_distribution={"/users/me/a": 5},
        )
        content = _render_skill_md(c, "custom/test-single")
        assert "Cross-project cluster" not in content
        assert "handle with care" not in content.lower()

    def test_render_cross_project_frontmatter_has_project_distribution(self) -> None:
        """Frontmatter gains project_distribution + scope_recommended."""
        c = _make_candidate(
            project_distribution={"/users/me/alpha": 7, "/users/me/beta": 3},
        )
        content = _render_skill_md(c, "custom/test-fm")
        # Split frontmatter from body.
        frontmatter = content.split("---\n", 2)[1]
        assert "project_distribution:" in frontmatter
        assert "alpha: 7" in frontmatter
        assert "beta: 3" in frontmatter
        assert "scope_recommended: global" in frontmatter

    def test_render_never_emits_absolute_paths(self) -> None:
        """Privacy P-5 regression: no absolute paths anywhere in body."""
        c = _make_candidate(
            project_distribution={
                "/Users/jane.doe/secret/proj-x": 4,
                "/Users/jane.doe/other/proj-y": 2,
            },
            queries=["q1", "q2"],
        )
        content = _render_skill_md(c, "custom/test-priv")
        assert "/Users/" not in content
        assert "jane.doe" not in content
        assert "secret" not in content
        # Basenames DO appear.
        assert "proj-x" in content
        assert "proj-y" in content

    def test_render_keeps_all_queries_when_cross_project(self) -> None:
        """Permissive policy: 5 queries preserved even when cross-project."""
        c = _make_candidate(
            queries=[f"query number {i}" for i in range(5)],
            project_distribution={"/users/me/a": 4, "/users/me/b": 2},
        )
        content = _render_skill_md(c, "custom/test-permissive")
        for i in range(5):
            assert f"query number {i}" in content


class TestDedupBasenames:
    """omx-code-review CRITICAL #1 — same-basename pool projects.

    Two pool members may share a directory basename (multiple checkouts
    of the same repo). Naive ``{basename: count}`` produces duplicate
    YAML keys → ``ruamel.yaml`` raises ``DuplicateKeyError`` on load →
    drafted SKILL.md silently fails to parse.
    """

    def test_dedupe_returns_distinct_keys_for_same_basename(self) -> None:
        out = dedupe_project_distribution({"/users/a/work/foo": 3, "/users/b/home/foo": 5})
        assert len(out) == 2
        # Both basenames preserved, but second is suffixed.
        assert "foo" in out
        assert "foo-2" in out

    def test_dedupe_preserves_counts_without_summing(self) -> None:
        """Counts are NOT merged — suffix signals multiple sources."""
        out = dedupe_project_distribution({"/users/a/work/foo": 3, "/users/b/home/foo": 5})
        # First-seen wins the bare name.
        assert out["foo"] == 3
        assert out["foo-2"] == 5

    def test_dedupe_three_collisions(self) -> None:
        out = dedupe_project_distribution({"/p/foo": 1, "/q/foo": 2, "/r/foo": 3})
        assert set(out.keys()) == {"foo", "foo-2", "foo-3"}

    def test_dedupe_does_not_collide_with_real_basename_hyphen_n(self) -> None:
        """Grok re-review CRITICAL: synthetic suffix must not collide with
        a real path whose basename already ends in ``-N``.

        Regression test for the silent-overwrite bug:
            {"/p/foo": 1, "/q/foo": 3, "/q/foo-2": 4}
        Pre-fix: ``{foo: 1, foo-2: 4}`` (third entry clobbers second synthetic).
        Post-fix: ``{foo: 1, foo-2: 3, foo-2-2: 4}`` (synthetic keeps incrementing).
        """
        out = dedupe_project_distribution({"/p/foo": 1, "/q/foo": 3, "/q/foo-2": 4})
        # All three counts preserved (no silent overwrite).
        assert sorted(out.values()) == [1, 3, 4], f"counts lost: {out}"
        # No duplicate keys (the whole point).
        assert len(out) == 3

    def test_dedupe_multiple_real_hyphen_paths(self) -> None:
        """Stress: multiple real paths with ``-N`` suffixes + collisions."""
        out = dedupe_project_distribution(
            {"/p/foo": 1, "/q/foo": 2, "/r/foo-2": 3, "/s/foo-2": 4, "/t/foo-3": 5}
        )
        # All 5 entries preserved.
        assert len(out) == 5
        assert sorted(out.values()) == [1, 2, 3, 4, 5]

    def test_dedupe_no_collision_when_basenames_differ(self) -> None:
        out = dedupe_project_distribution({"/users/a/alpha": 4, "/users/b/beta": 2})
        assert out == {"alpha": 4, "beta": 2}

    def test_render_with_duplicate_basenames_yields_parseable_yaml(self) -> None:
        """End-to-end: the rendered frontmatter must parse without error."""
        from ruamel.yaml import YAML

        c = _make_candidate(
            project_distribution={"/users/a/work/vibesop": 3, "/users/b/home/vibesop": 5},
        )
        content = _render_skill_md(c, "custom/dup-basename")
        frontmatter = content.split("---\n", 2)[1]
        # Must NOT raise DuplicateKeyError.
        parsed = YAML().load(frontmatter)
        assert parsed is not None
        assert parsed["project_distribution"]["vibesop"] == 3
        assert parsed["project_distribution"]["vibesop-2"] == 5

    def test_warning_block_handles_duplicate_basenames(self) -> None:
        """Warning prose must also dedupe so it stays readable."""
        block = _format_cross_project_warning({"/users/a/work/foo": 4, "/users/b/home/foo": 2})
        assert "`foo` (4 spans)" in block
        assert "`foo-2` (2 spans)" in block


class TestRenderScopeFooter:
    """omx-code-review HIGH #3 — footer activate path must match --scope.

    Prior version hardcoded ``.vibe/skills/{id}`` regardless of scope,
    contradicting the CLI's stdout hint for ``--scope global`` promotes
    within the same run.
    """

    def test_default_scope_footer_points_to_local_skills_dir(self) -> None:
        c = _make_candidate(queries=["q1"])
        content = _render_skill_md(c, "custom/foo")  # default scope=project
        assert ".vibe/skills/custom/foo" in content
        assert "~/.vibe/skills/" not in content

    def test_global_scope_footer_points_to_home_skills_dir(self) -> None:
        c = _make_candidate(queries=["q1"])
        content = _render_skill_md(c, "custom/foo", scope="global")
        assert "~/.vibe/skills/custom/foo" in content
        # Local path should NOT appear for global scope (the literal
        # activate command must point at home, not cwd).
        # Use the activate-instruction substring to avoid matching the
        # global path ~/.vibe/... which contains ".vibe/" as a substring.
        assert "skill add .vibe/skills/custom/foo" not in content

    def test_scope_does_not_affect_drafts_root(self) -> None:
        """Scope only varies the footer hint — drafts_root is the source
        of truth for where the file actually lands. Verified at CLI level
        in test_skill_promote_scope_cli.py."""
        # Render-only check: the function signature accepts scope without
        # error and produces parseable output.
        c = _make_candidate(queries=["q1"])
        for s in ("project", "global"):
            content = _render_skill_md(c, "custom/foo", scope=s)  # type: ignore[arg-type]
            assert "## Overview" in content


class TestDraftName:
    """M7 F3 — name is a neutral draft slug, NOT derived from queries.

    Adjudicated design: ``name`` is the strongest routing-match magnet
    (+0.4 containment bonus), so a raw query there makes an unedited
    draft over-match once injected. ``description`` stays provenance-only
    on purpose. These tests pin the decision so nobody "optimizes" it
    back.
    """

    def test_name_is_draft_cluster_slug(self) -> None:
        c = _make_candidate(cluster_id="abc123def456", queries=["do the thing"])
        content = _render_skill_md(c, "custom/test-name")
        frontmatter = content.split("---\n", 2)[1]
        assert "name: draft-abc123de" in frontmatter
        # The raw query must NOT appear in the name field.
        name_line = next(ln for ln in frontmatter.splitlines() if ln.startswith("name:"))
        assert "do the thing" not in name_line

    def test_name_does_not_leak_query_even_when_hostile(self) -> None:
        c = _make_candidate(queries=["setup: config\nthen deploy"])
        content = _render_skill_md(c, "custom/test-hostile-name")
        frontmatter = content.split("---\n", 2)[1]
        name_line = next(ln for ln in frontmatter.splitlines() if ln.startswith("name:"))
        assert "setup" not in name_line
        assert "\n" not in name_line

    def test_description_keeps_provenance(self) -> None:
        c = _make_candidate(cluster_id="abc123def456", span_count=7)
        content = _render_skill_md(c, "custom/test-desc")
        frontmatter = content.split("---\n", 2)[1]
        assert "Auto-drafted from cluster abc123def456" in frontmatter
        assert "7 spans" in frontmatter


class TestSanitizeBodyText:
    """M7 F6 — queries embedded in the body are single-line + truncated."""

    def test_collapses_newlines_and_whitespace_runs(self) -> None:
        q = "first line\n\nsecond   paragraph\twith\ttabs"
        assert _sanitize_body_text(q) == "first line second paragraph with tabs"

    def test_truncates_long_queries_with_ellipsis(self) -> None:
        q = "x" * 700
        out = _sanitize_body_text(q)
        assert out.endswith("…")
        assert len(out) <= 201

    def test_render_queries_block_is_single_line_per_query(self) -> None:
        c = _make_candidate(queries=["line one\n\nline two", "short"])
        content = _render_skill_md(c, "custom/test-body-sanitize")
        assert "- line one line two" in content
        # No raw multi-line query survives into the body.
        assert "line one\n\nline two" not in content

    def test_render_truncates_700_char_query(self) -> None:
        long_q = "word " * 200  # 1000 chars
        c = _make_candidate(queries=[long_q])
        content = _render_skill_md(c, "custom/test-body-truncate")
        body = content.split("---\n", 2)[2]
        query_lines = [ln for ln in body.splitlines() if ln.startswith("- word")]
        assert len(query_lines) == 1
        assert query_lines[0].endswith("…")
        assert len(query_lines[0]) < 250


class TestGlobalPrivacyBoundary:
    """M12 M5 — global drafts carry NO example queries / project identifiers.

    Design v3 §隐私边界: 全局草稿不含示例 query 与项目标识. Project scope
    keeps the permissive rendering (covered by the classes above).
    """

    def test_global_draft_omits_example_queries(self) -> None:
        c = _make_candidate(queries=["my secret refactor query", "another private query"])
        content = _render_skill_md(c, "custom/foo", scope="global")
        assert "my secret refactor query" not in content
        assert "another private query" not in content
        assert "example queries omitted" in content

    def test_project_draft_keeps_example_queries(self) -> None:
        c = _make_candidate(queries=["visible project query"])
        content = _render_skill_md(c, "custom/foo", scope="project")
        assert "visible project query" in content

    def test_global_cross_project_omits_project_identifiers(self) -> None:
        c = _make_candidate(
            project_distribution={"/home/user/alpha": 3, "/home/user/beta": 2},
        )
        content = _render_skill_md(c, "custom/foo", scope="global")
        assert "project_distribution" not in content
        assert "alpha" not in content
        assert "beta" not in content
        # The cross-project warning survives, but names nothing.
        assert "Cross-project cluster" in content
        assert "project names omitted" in content

    def test_project_cross_project_keeps_distribution(self) -> None:
        """Sanity: project scope keeps the W5.2 permissive rendering."""
        c = _make_candidate(project_distribution={"/home/user/alpha": 3, "/home/user/beta": 2})
        content = _render_skill_md(c, "custom/foo", scope="project")
        assert "project_distribution" in content
        assert "alpha" in content

    def test_global_single_project_has_no_warning(self) -> None:
        c = _make_candidate()
        content = _render_skill_md(c, "custom/foo", scope="global")
        assert "Cross-project cluster" not in content


class TestMaterializeFreshFlag:
    """gate18 pi NIT-2 — freshness is decided inside materialize_candidate.

    The first call writes and reports ``fresh=True``; a second call over
    an existing (possibly edited) draft reports ``fresh=False`` and does
    not clobber. Callers key the edit-guard baseline hash off this flag.
    """

    def test_first_write_fresh_second_not(self, tmp_path) -> None:
        from vibesop.core.observability.skill_promote import materialize_candidate

        candidate = _make_candidate()
        first = materialize_candidate(candidate, "custom/foo", drafts_root=tmp_path)
        assert first.fresh is True
        assert first.path.exists()

        # Simulate a human edit between promotes.
        first.path.write_text("edited by human", encoding="utf-8")
        second = materialize_candidate(candidate, "custom/foo", drafts_root=tmp_path)
        assert second.fresh is False
        assert second.path == first.path
        assert second.path.read_text(encoding="utf-8") == "edited by human"


class TestGate31Skeleton:
    """gate31: the draft body grew a fill-in skeleton (When-NOT-to-Apply /
    Acceptance Checklist / Anti-patterns) and the empty-core-steps case
    renders a guided TODO instead of a bare parenthetical."""

    def test_skeleton_sections_present(self) -> None:
        content = _render_skill_md(_make_candidate(), "custom/x-c1")
        assert "## When NOT to Apply" in content
        assert "## Acceptance Checklist" in content
        assert "## Anti-patterns" in content
        # Section order: boundaries right after When-to-Apply, checklist
        # and anti-patterns after Steps, provenance last.
        assert content.index("## When to Apply") < content.index("## When NOT to Apply")
        assert content.index("## Steps") < content.index("## Acceptance Checklist")
        assert content.index("## Acceptance Checklist") < content.index("## Anti-patterns")
        assert content.index("## Anti-patterns") < content.index("## Metrics")

    def test_empty_core_steps_render_guided_todo(self) -> None:
        candidate = _make_candidate()
        assert candidate.core_steps == []
        content = _render_skill_md(candidate, "custom/x-c1")
        assert "TODO: reconstruct the procedure" in content
        assert "no core steps identified" not in content

    def test_core_steps_still_render_when_present(self) -> None:
        candidate = _make_candidate()
        candidate.core_steps = ["route:query", "tool:edit"]
        content = _render_skill_md(candidate, "custom/x-c1")
        assert "1. route:query" in content
        assert "2. tool:edit" in content
        assert "TODO: reconstruct the procedure" not in content

    def test_global_scope_also_gets_skeleton(self) -> None:
        """The M12 privacy boundary only masks example queries; the
        editing skeleton applies to global drafts too."""
        candidate = _make_candidate(project_distribution={"p/a": 2, "p/b": 3})
        content = _render_skill_md(candidate, "custom/x-c1", scope="global")
        assert "## Acceptance Checklist" in content
        assert "example queries omitted" in content


class TestGate32TriggersPrefill:
    """gate32 A1: the renderer prefills frontmatter ``triggers:`` from
    hygiene-filtered cluster queries (project scope only) so an activated
    skill can catch the pattern that produced it."""

    def test_project_scope_prefills_sanitized_triggers(self) -> None:
        candidate = _make_candidate(queries=["帮我合并到 main 吧", "提交: 全部", "推上去吧"])
        content = _render_skill_md(candidate, "custom/x-c1")
        line = next(ln for ln in content.splitlines() if ln.startswith("triggers:"))
        assert "帮我合并到 main 吧" in line
        assert "推上去吧" in line
        # Colon-bearing query must be quoted so the YAML stays parseable.
        assert '"提交: 全部"' in line

    def test_agent_prompt_shapes_and_low_info_filtered(self) -> None:
        candidate = _make_candidate(
            queries=[
                "帮我合并到 main 吧",
                "You are an adversarial SKEPTIC. Your job is to REFUTE",
                "<system-reminder> background task done",
                "继续",
                "x" * 200,
            ]
        )
        content = _render_skill_md(candidate, "custom/x-c1")
        line = next(ln for ln in content.splitlines() if ln.startswith("triggers:"))
        assert "帮我合并到 main 吧" in line
        assert "SKEPTIC" not in line
        assert "system-reminder" not in line
        assert "继续" not in line

    def test_all_filtered_yields_todo_placeholder(self) -> None:
        candidate = _make_candidate(queries=["继续", "You are a reviewer"])
        content = _render_skill_md(candidate, "custom/x-c1")
        # No ACTIVE triggers key — only the commented TODO placeholder.
        assert not any(ln.startswith("triggers:") for ln in content.splitlines())
        assert "# triggers: TODO" in content

    def test_global_scope_never_prefills_raw_queries(self) -> None:
        """M12 privacy boundary: global drafts get a TODO placeholder,
        never raw cluster queries (gate32 claude MAJOR-2)."""
        candidate = _make_candidate(
            queries=["帮我合并到 main 吧"],
            project_distribution={"p/a": 2, "p/b": 3},
        )
        content = _render_skill_md(candidate, "custom/x-c1", scope="global")
        assert "帮我合并到 main 吧" not in content
        assert "# triggers: TODO" in content

    def test_is_agent_prompt_shape_predicate(self) -> None:
        from vibesop.core.observability.skill_promote import _is_agent_prompt_shape

        assert _is_agent_prompt_shape("You are an independent reviewer")
        assert _is_agent_prompt_shape("ou are a senior engineer")  # truncated echo
        assert _is_agent_prompt_shape("<system-reminder> hook fired")
        assert _is_agent_prompt_shape('[ { "type": "text", "text": "x" } ]')
        assert _is_agent_prompt_shape("x" * 200)
        assert not _is_agent_prompt_shape("帮我合并到 main 吧")
        assert not _is_agent_prompt_shape("you are")  # no trailing space → not a role prompt


class TestAgentPromptPrefixPredicate:
    """gate35 D2 (修订 C): display-layer prefix-only predicate.

    ``_is_agent_prompt_shape`` is FROZEN (replay baseline imports it);
    ``_has_agent_prompt_prefix`` shares the prefix blacklist but drops the
    150-char rule so pasted tracebacks / long legit specs are not tagged
    ``shape: agent-echo`` and sunk.
    """

    def test_prefix_hits(self) -> None:
        from vibesop.core.observability.skill_promote import _has_agent_prompt_prefix

        assert _has_agent_prompt_prefix("You are an adversarial SKEPTIC. REFUTE this plan")
        assert _has_agent_prompt_prefix("ou are a senior engineer")  # truncated echo
        assert _has_agent_prompt_prefix("<system-reminder> hook fired")
        assert _has_agent_prompt_prefix("system-reminder without bracket")
        assert _has_agent_prompt_prefix("<command-name> /vibe-help")
        assert _has_agent_prompt_prefix('[ { "type": "text", "text": "x" } ]')
        assert _has_agent_prompt_prefix('[{"type": "text"}]')
        assert _has_agent_prompt_prefix("background task finished: xyz")
        # Normalization: case + whitespace collapse (same as frozen predicate).
        assert _has_agent_prompt_prefix("  YOU   ARE  a reviewer\n")

    def test_must_not_catch_long_legit_or_traceback(self) -> None:
        """must-NOT-catch 反例: 长合法 query / 粘贴 traceback 不得命中。

        The frozen ``_is_agent_prompt_shape`` returns True for these via
        the 150-char rule — the display predicate must NOT (修订 C).
        """
        from vibesop.core.observability.skill_promote import (
            _has_agent_prompt_prefix,
            _is_agent_prompt_shape,
        )

        long_legit = "请帮我重构这个模块，要求保持现有 API 兼容，并且" * 10  # >150 chars
        traceback = "Traceback (most recent call last):\n" + '  File "x.py", line 1\n' * 10
        for query in (long_legit, traceback, "x" * 200):
            assert not _has_agent_prompt_prefix(query)
            # 对照: 冻结谓词的 150 字符规则仍在（一字不动）。
            assert _is_agent_prompt_shape(query)

    def test_must_not_catch_normal_or_empty(self) -> None:
        from vibesop.core.observability.skill_promote import _has_agent_prompt_prefix

        assert not _has_agent_prompt_prefix("帮我合并到 main 吧")
        assert not _has_agent_prompt_prefix("how do I run the tests")
        assert not _has_agent_prompt_prefix("you are")  # no trailing space
        # Empty text is NOT an echo here (unlike the frozen predicate):
        # the tag marks machine wrappers, not missing data.
        assert not _has_agent_prompt_prefix("")
        assert not _has_agent_prompt_prefix("   ")
