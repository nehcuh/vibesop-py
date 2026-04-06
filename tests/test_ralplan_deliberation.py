"""Tests for ralplan deliberation engine."""

import pytest
from vibesop.core.plan.deliberation import RalplanDR
from vibesop.core.plan.architect import ArchitectReview
from vibesop.core.plan.critic import CriticEvaluation
from vibesop.core.plan.gate import ExecutionGate


def test_ralplan_add_option():
    dr = RalplanDR()
    dr.add_option("Option A", "Do it fast", ["quick", "cheap"], ["risky"])
    assert len(dr.viable_options) == 1
    assert dr.viable_options[0]["name"] == "Option A"


def test_ralplan_select_favored():
    dr = RalplanDR()
    dr.add_option("Option A", "Do it fast", ["quick"], ["risky"])
    dr.add_option("Option B", "Do it right", ["safe"], ["slow"])
    dr.select_favored("Option B", "Safety first")
    assert dr.favored_option == "Option B"
    assert dr.rationale == "Safety first"


def test_ralplan_select_nonexistent_option():
    dr = RalplanDR()
    dr.add_option("Option A", "Test", [], [])
    dr.select_favored("Option Z", "Should not work")
    assert dr.favored_option is None


def test_ralplan_to_dict():
    dr = RalplanDR(principles=["YAGNI", "DRY"])
    d = dr.to_dict()
    assert d["principles"] == ["YAGNI", "DRY"]
    assert d["favored_option"] is None


def test_architect_review():
    review = ArchitectReview(
        antithesis="Option A is too risky",
        risks=["data loss", "downtime"],
        recommendations=["add backup plan"],
    )
    d = review.to_dict()
    assert d["antithesis"] == "Option A is too risky"
    assert len(d["risks"]) == 2


def test_critic_evaluation_passes():
    ev = CriticEvaluation(principle_consistent=True, violations=[])
    assert ev.passes is True


def test_critic_evaluation_fails():
    ev = CriticEvaluation(principle_consistent=True, violations=["violates YAGNI"])
    assert ev.passes is False


def test_execution_gate_ready():
    gate = ExecutionGate(
        passed=True,
        plan_name="Test Plan",
        plan_path="/path/to/plan",
        review_iterations=3,
        architect_approved=True,
        critic_passed=True,
        user_approved=True,
    )
    assert gate.is_ready is True


def test_execution_gate_not_ready():
    gate = ExecutionGate(
        passed=True,
        plan_name="Test Plan",
        plan_path="/path/to/plan",
        review_iterations=3,
        architect_approved=True,
        critic_passed=True,
        user_approved=False,
    )
    assert gate.is_ready is False
