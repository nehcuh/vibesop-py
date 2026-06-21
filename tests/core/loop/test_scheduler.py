"""Tests for ``CronExpr`` parser and ``CronDaemon`` poller.

Covers:
    - ``_parse_field``: wildcard, fixed, step, range+step, list, out-of-range,
      garbage input.
    - ``CronExpr``: 5-field validation, empty-field rejection, weekday mapping,
      next_run_after for sparse expressions, should_run second-agnosticism.
    - ``CronDaemon.run_once``: trigger filtering, invalid-cron skip, empty input,
      LoopSpec construction edge cases.
    - POSIX compatibility: ``0`` and ``7`` both = Sunday.
    - P0 regression: ``1-10/3`` gives ``{1,4,7,10}`` (not full range spread).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from vibesop.core.loop.models import LoopSpec
from vibesop.core.loop.scheduler import CronDaemon, CronExpr, _parse_field

# ──────────────────────────────────────────────────────────────────
# _parse_field
# ──────────────────────────────────────────────────────────────────


class TestParseField:
    def test_wildcard_returns_full_range(self):
        assert _parse_field("*", 0, 59) == set(range(0, 60))

    def test_fixed_value(self):
        assert _parse_field("30", 0, 59) == {30}

    def test_step_from_min(self):
        assert _parse_field("*/15", 0, 59) == {0, 15, 30, 45}

    def test_step_with_range_base_does_not_spread(self):
        """P0 regression: ``1-10/3`` must yield {1,4,7,10}, not the
        legacy bug that spread it to {1,4,7,...,58}."""
        result = _parse_field("1-10/3", 0, 59)
        assert result == {1, 4, 7, 10}

    def test_step_with_range_base_within_larger_field(self):
        """Same P0 fix, in hour field where max=23."""
        assert _parse_field("9-17/2", 0, 23) == {9, 11, 13, 15, 17}

    def test_step_from_fixed_base(self):
        """Non-standard but supported: ``30/10`` = {30, 40, 50}."""
        assert _parse_field("30/10", 0, 59) == {30, 40, 50}

    def test_step_zero_is_ignored(self):
        assert _parse_field("*/0", 0, 59) == set()

    def test_list(self):
        assert _parse_field("1,15,30", 0, 59) == {1, 15, 30}

    def test_range(self):
        assert _parse_field("9-17", 0, 23) == set(range(9, 18))

    def test_out_of_range_ignored(self):
        assert _parse_field("99", 0, 59) == set()

    def test_empty_part_ignored(self):
        assert _parse_field("5,,10", 0, 59) == {5, 10}

    def test_garbage_part_ignored(self):
        assert _parse_field("5,abc,10", 0, 59) == {5, 10}

    def test_combined_list_of_ranges_and_steps(self):
        assert _parse_field("0,15-30/15,45", 0, 59) == {0, 15, 30, 45}


# ──────────────────────────────────────────────────────────────────
# CronExpr — construction
# ──────────────────────────────────────────────────────────────────


class TestCronExprInit:
    def test_valid_5_field(self):
        c = CronExpr("*/15 * * * *")
        assert c.minutes == {0, 15, 30, 45}

    def test_invalid_4_field(self):
        with pytest.raises(ValueError, match="5 段"):
            CronExpr("* * * *")

    def test_invalid_6_field(self):
        with pytest.raises(ValueError, match="5 段"):
            CronExpr("* * * * * *")

    def test_empty_field_set_raises(self):
        """``99 * * * *`` → minute field empty → ValueError naming minute."""
        with pytest.raises(ValueError, match="minute"):
            CronExpr("99 * * * *")

    def test_posix_7_equals_sunday(self):
        """POSIX: dow 0 and 7 both mean Sunday."""
        c = CronExpr("0 0 * * 7")
        # 7 should be normalised to 0
        assert 7 not in c.dow
        assert 0 in c.dow


# ──────────────────────────────────────────────────────────────────
# CronExpr — next_run_after & should_run
# ──────────────────────────────────────────────────────────────────


class TestEveryFifteenMinutes:
    def setup_method(self):
        self.c = CronExpr("*/15 * * * *")

    def test_next_after_exact_match(self):
        dt = datetime(2026, 6, 19, 10, 0, tzinfo=UTC)
        n = self.c.next_run_after(dt)
        # 10:00:00 is the after-baseline; next is 10:15
        assert (n.hour, n.minute, n.day) == (10, 15, 19)

    def test_next_after_offset(self):
        dt = datetime(2026, 6, 19, 10, 10, tzinfo=UTC)
        n = self.c.next_run_after(dt)
        assert (n.hour, n.minute) == (10, 15)

    def test_next_after_last_quarter_rolls_to_next_hour(self):
        dt = datetime(2026, 6, 19, 10, 45, tzinfo=UTC)
        n = self.c.next_run_after(dt)
        assert (n.hour, n.minute) == (11, 0)

    def test_should_run_at_quarter(self):
        assert self.c.should_run(datetime(2026, 6, 19, 10, 0, tzinfo=UTC)) is True

    def test_should_not_run_between_quarters(self):
        assert self.c.should_run(datetime(2026, 6, 19, 10, 7, tzinfo=UTC)) is False

    def test_should_run_is_second_agnostic(self):
        """Within minute 10:00, seconds 00 / 30 / 59 all match."""
        for sec in (0, 30, 59):
            assert self.c.should_run(datetime(2026, 6, 19, 10, 0, sec, tzinfo=UTC)) is True


class TestDailyAt2230:
    def setup_method(self):
        self.c = CronExpr("30 22 * * *")

    def test_next_before_target(self):
        dt = datetime(2026, 6, 19, 22, 0, tzinfo=UTC)
        n = self.c.next_run_after(dt)
        assert (n.day, n.hour, n.minute) == (19, 22, 30)

    def test_next_at_target_rolls_to_tomorrow(self):
        dt = datetime(2026, 6, 19, 22, 30, tzinfo=UTC)
        n = self.c.next_run_after(dt)
        assert (n.day, n.hour, n.minute) == (20, 22, 30)

    def test_should_run_at_target(self):
        assert self.c.should_run(datetime(2026, 6, 19, 22, 30, tzinfo=UTC)) is True

    def test_should_not_run_at_wrong_minute(self):
        assert self.c.should_run(datetime(2026, 6, 19, 22, 31, tzinfo=UTC)) is False


class TestWeekday9AM:
    """``0 9 * * 1-5`` → business-day 9am. Validates P1 weekday mapping fix."""

    def setup_method(self):
        self.c = CronExpr("0 9 * * 1-5")

    @pytest.mark.parametrize(
        "date,expected",
        [
            ("2026-06-22", True),  # Monday
            ("2026-06-23", True),  # Tuesday
            ("2026-06-24", True),  # Wednesday
            ("2026-06-25", True),  # Thursday
            ("2026-06-26", True),  # Friday
            ("2026-06-27", False),  # Saturday
            ("2026-06-28", False),  # Sunday
        ],
    )
    def test_should_run_by_weekday(self, date: str, expected: bool):
        y, m, d = (int(x) for x in date.split("-"))
        dt = datetime(y, m, d, 9, 0, tzinfo=UTC)
        assert self.c.should_run(dt) is expected

    def test_next_after_friday_morning_is_monday(self):
        """Friday 9:05 → next Monday 9:00."""
        dt = datetime(2026, 6, 26, 9, 5, tzinfo=UTC)  # Friday
        n = self.c.next_run_after(dt)
        assert n.weekday() == 0  # Monday
        assert (n.hour, n.minute) == (9, 0)


class TestYearlySparse:
    """``0 0 1 1 *`` → Jan 1 each year. Exercises next_run_after for sparse expr."""

    def test_next_from_june_is_next_year(self):
        c = CronExpr("0 0 1 1 *")
        dt = datetime(2026, 6, 19, 0, 0, tzinfo=UTC)
        n = c.next_run_after(dt)
        assert (n.year, n.month, n.day) == (2027, 1, 1)

    def test_next_from_january_first_late_is_next_year(self):
        c = CronExpr("0 0 1 1 *")
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        n = c.next_run_after(dt)
        assert (n.year, n.month, n.day) == (2027, 1, 1)


class TestRapidFireWeekday:
    """``*/5 * * * 1-5`` → every 5 min on weekdays."""

    def test_next_minute_same_hour(self):
        c = CronExpr("*/5 * * * 1-5")
        dt = datetime(2026, 6, 22, 9, 3, tzinfo=UTC)  # Monday 09:03
        n = c.next_run_after(dt)
        assert (n.hour, n.minute) == (9, 5)
        assert n.weekday() == 0


class TestSundayDow:
    """``0 0 * * 0`` and ``0 0 * * 7`` are equivalent (POSIX Sunday)."""

    def test_zero_and_seven_match_same_sunday(self):
        c_zero = CronExpr("0 0 * * 0")
        c_seven = CronExpr("0 0 * * 7")
        # Sunday 2026-06-28
        sunday = datetime(2026, 6, 28, 0, 0, tzinfo=UTC)
        assert c_zero.should_run(sunday)
        assert c_seven.should_run(sunday)
        # Saturday 2026-06-27
        saturday = datetime(2026, 6, 27, 0, 0, tzinfo=UTC)
        assert not c_zero.should_run(saturday)
        assert not c_seven.should_run(saturday)


# ──────────────────────────────────────────────────────────────────
# CronDaemon
# ──────────────────────────────────────────────────────────────────


def _spec(name: str, schedule: str, **overrides) -> LoopSpec:
    base = {
        "name": name,
        "description": f"loop {name}",
        "schedule": schedule,
        "query": f"check {name}",
    }
    base.update(overrides)
    return LoopSpec(**base)


class TestCronDaemonRunOnce:
    def test_empty_specs_returns_empty(self):
        daemon = CronDaemon()
        assert daemon.run_once([]) == []

    def test_every_minute_loop_is_triggered(self):
        """``* * * * *`` always matches current minute."""
        daemon = CronDaemon()
        spec = _spec("every-min", "* * * * *")
        triggered = daemon.run_once([spec])
        assert spec in triggered

    def test_filter_mixed_specs_preserves_order(self):
        """Daemon returns triggered subset preserving input order.

        ``far_future`` is ``0 0 1 1 *`` (Jan 1). On non-Jan-1 days it won't
        fire; on Jan 1 it will. We don't assert either way — instead we
        verify the two every-minute specs are both returned in input order.
        """
        daemon = CronDaemon()
        every_min = _spec("a-every-min", "* * * * *")
        far_future = _spec("b-far", "0 0 1 1 *")
        every_min_2 = _spec("c-every-min", "* * * * *")
        triggered = daemon.run_once([every_min, far_future, every_min_2])
        assert every_min in triggered
        assert every_min_2 in triggered
        assert triggered.index(every_min) < triggered.index(every_min_2)

    def test_invalid_cron_is_skipped_silently(self, caplog):
        """A spec with an invalid cron schedule (that bypassed LoopSpec
        validation) should be skipped with a warning, not raise."""
        import logging

        daemon = CronDaemon()
        spec = _spec("bad-cron", "* * * * *")  # construct validly first
        # Bypass LoopSpec validation to inject invalid schedule
        object.__setattr__(spec, "schedule", "not a cron")
        with caplog.at_level(logging.WARNING, logger="vibesop.core.loop.scheduler"):
            triggered = daemon.run_once([spec])
        assert triggered == []
        assert any("invalid cron" in rec.message.lower() for rec in caplog.records)

    def test_non_cron_trigger_is_skipped(self):
        """Specs whose trigger != 'cron' must be skipped. We can't directly
        construct one (LoopTrigger only has CRON in v1), so we use a duck-typed
        stub to verify the daemon's guard clause."""
        daemon = CronDaemon()

        class WebhookStub:
            name = "webhook-loop"
            schedule = "* * * * *"
            trigger = "webhook"  # not 'cron'

        triggered = daemon.run_once([WebhookStub()])  # type: ignore[arg-type]
        assert triggered == []

    def test_daemon_is_stateless_across_calls(self):
        """Two consecutive run_once calls behave identically (no sticky state)."""
        daemon = CronDaemon()
        spec = _spec("stateless", "* * * * *")
        first = daemon.run_once([spec])
        second = daemon.run_once([spec])
        assert first == second
