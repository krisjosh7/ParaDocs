"""Unit tests for workflow.research_gate confidence-weighted sufficiency."""

from __future__ import annotations

from workflow import initial_case_state
from workflow.research_gate import (
    MIN_RESEARCH_CONFIDENCE_MASS,
    research_context_confidence_score,
    sufficient_context_for_research,
)


def test_confidence_score_two_low_confidence_events_passes() -> None:
    state = initial_case_state("c", "x", "upload")
    state["events"] = [
        {"event": "A", "confidence": 0.0},
        {"event": "B", "confidence": 0.0},
    ]
    state["structured"] = []
    s = research_context_confidence_score(state)
    assert s >= MIN_RESEARCH_CONFIDENCE_MASS
    assert sufficient_context_for_research(state) is True


def test_confidence_score_single_event_fails_without_extras() -> None:
    state = initial_case_state("c", "x", "upload")
    state["events"] = [{"event": "Only one", "confidence": 0.0}]
    state["structured"] = []
    assert research_context_confidence_score(state) < MIN_RESEARCH_CONFIDENCE_MASS
    assert sufficient_context_for_research(state) is False


def test_confidence_score_single_high_confidence_event_passes() -> None:
    state = initial_case_state("c", "x", "upload")
    state["events"] = [{"event": "Strong", "confidence": 1.0}]
    state["structured"] = []
    assert sufficient_context_for_research(state) is True


def test_confidence_score_structured_summary_complements_events() -> None:
    state = initial_case_state("c", "x", "upload")
    state["events"] = [{"event": "One", "confidence": 0.0}]
    state["structured"] = [
        {
            "summary": {"text": "Case overview", "confidence": 0.0},
            "claims": [],
            "parties": [],
            "jurisdiction": {"value": "", "confidence": 0.0},
            "damages": [],
        },
    ]
    assert sufficient_context_for_research(state) is True
