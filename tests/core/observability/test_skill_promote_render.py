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
        block = _format_cross_project_warning(
            {"/Users/jane/proj-a": 7, "/Users/jane/proj-b": 3}
        )
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
        block = _format_cross_project_warning(
            {"/Users/jane.doe/super/secret/path/proj-x": 5}
        )
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
            project_distribution={"/Users/jane.doe/secret/proj-x": 4, "/Users/jane.doe/other/proj-y": 2},
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
        out = dedupe_project_distribution(
            {"/users/a/work/foo": 3, "/users/b/home/foo": 5}
        )
        assert len(out) == 2
        # Both basenames preserved, but second is suffixed.
        assert "foo" in out
        assert "foo-2" in out

    def test_dedupe_preserves_counts_without_summing(self) -> None:
        """Counts are NOT merged — suffix signals multiple sources."""
        out = dedupe_project_distribution(
            {"/users/a/work/foo": 3, "/users/b/home/foo": 5}
        )
        # First-seen wins the bare name.
        assert out["foo"] == 3
        assert out["foo-2"] == 5

    def test_dedupe_three_collisions(self) -> None:
        out = dedupe_project_distribution(
            {"/p/foo": 1, "/q/foo": 2, "/r/foo": 3}
        )
        assert set(out.keys()) == {"foo", "foo-2", "foo-3"}

    def test_dedupe_does_not_collide_with_real_basename_hyphen_n(self) -> None:
        """Grok re-review CRITICAL: synthetic suffix must not collide with
        a real path whose basename already ends in ``-N``.

        Regression test for the silent-overwrite bug:
            {"/p/foo": 1, "/q/foo": 3, "/q/foo-2": 4}
        Pre-fix: ``{foo: 1, foo-2: 4}`` (third entry clobbers second synthetic).
        Post-fix: ``{foo: 1, foo-2: 3, foo-2-2: 4}`` (synthetic keeps incrementing).
        """
        out = dedupe_project_distribution(
            {"/p/foo": 1, "/q/foo": 3, "/q/foo-2": 4}
        )
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
        out = dedupe_project_distribution(
            {"/users/a/alpha": 4, "/users/b/beta": 2}
        )
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
        block = _format_cross_project_warning(
            {"/users/a/work/foo": 4, "/users/b/home/foo": 2}
        )
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
