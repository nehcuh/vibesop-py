"""Malformed structured output must not be reinterpreted as a task list."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from vibesop.core.orchestration.task_decomposer import (
    TaskDecomposer,
    _LLMDecompositionResult,
    _LLMTaskItem,
)


def _serialized_tasks():
    return _LLMDecompositionResult(
        tasks=[
            _LLMTaskItem(
                intent="Review", query="Review the current project", skill_id="builtin/review"
            ),
            _LLMTaskItem(intent="Improve", query="Improve the presentation", skill_id=None),
        ]
    ).model_dump_json(indent=2)


@pytest.mark.parametrize("wrap", [False, True])
def test_truncated_model_payload_has_no_synthetic_tasks(wrap):
    payload = _serialized_tasks()[:-20]
    if wrap:
        payload = "```json\n" + payload
    llm = SimpleNamespace(call=Mock(return_value=SimpleNamespace(content=payload)))
    assert TaskDecomposer(llm).decompose("Review project and improve presentation") == []


def test_valid_model_payload_preserves_queries_and_skill_ids():
    llm = SimpleNamespace(call=Mock(return_value=SimpleNamespace(content=_serialized_tasks())))
    tasks = TaskDecomposer(llm).decompose("Review project and improve presentation")
    assert [(t.intent, t.query, t.skill_id) for t in tasks] == [
        ("Review", "Review the current project", "builtin/review"),
        ("Improve", "Improve the presentation", None),
    ]


@pytest.mark.parametrize("prefix", ["1.", "1)", "-", "*", "+"])
def test_explicit_prose_lists_remain_supported(prefix):
    llm = SimpleNamespace(
        call=Mock(
            return_value=SimpleNamespace(content=f"{prefix} Review: Review the current project")
        )
    )
    tasks = TaskDecomposer(llm).decompose("Review the current project")
    assert len(tasks) == 1
    assert tasks[0].intent == "Review"
    assert tasks[0].query == "Review the current project"


def test_unstructured_metadata_is_not_a_task_list():
    assert TaskDecomposer()._parse_regex_response('"intent": "Review the current project",') == []


def test_prefixed_truncated_json_cannot_smuggle_a_prose_list():
    payload = "Here is the result: " + _serialized_tasks()[:-20]
    payload += "\n1. Review: This line is still part of the broken response"
    llm = SimpleNamespace(call=Mock(return_value=SimpleNamespace(content=payload)))
    assert TaskDecomposer(llm).decompose("Review project and improve presentation") == []
