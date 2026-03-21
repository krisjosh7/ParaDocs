"""
Tests for research/prompts.py

Unit tests:        no Ollama needed — test prompt structure and output parsers
Integration tests: real Ollama call — verify the model is running and producing
                   coherent, parseable, contextually relevant output
"""

import pytest
import httpx

from research.prompts import (
    generate_queries_prompt,
    parse_queries,
    score_result_prompt,
    parse_score,
    run_generate_queries,
    run_score_result,
    MODEL,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_CASE_FACTS = (
    "A driver ran a red light at 45mph in a school zone, striking a pedestrian "
    "in the crosswalk. The pedestrian suffered a broken leg and lost wages. "
    "The driver claims the light was malfunctioning. We are pursuing a negligence "
    "claim and need to establish duty of care and the standard for traffic violations."
)

SAMPLE_RESULT_RELEVANT = {
    "case_name": "Rodriguez v. City of Los Angeles",
    "citation": "123 F.3d 456",
    "snippet": (
        "The court held that a driver's violation of a traffic ordinance "
        "constitutes negligence per se, establishing duty and breach simultaneously "
        "when the plaintiff falls within the class of persons the statute was "
        "designed to protect."
    ),
    "source_type": "search",
}

SAMPLE_RESULT_IRRELEVANT = {
    "case_name": "In re Estate of Johnson",
    "citation": "78 B.R. 112",
    "snippet": (
        "The bankruptcy trustee argued that the decedent's estate failed to "
        "properly disclose assets in the Chapter 7 filing, and that the "
        "homestead exemption did not apply to the disputed property."
    ),
    "source_type": "search",
}

PRIOR_QUERIES = ["negligence per se traffic", "duty of care pedestrian crosswalk"]


# ---------------------------------------------------------------------------
# Unit: generate_queries_prompt structure
# ---------------------------------------------------------------------------

def test_generate_queries_prompt_returns_two_messages():
    messages = generate_queries_prompt(SAMPLE_CASE_FACTS, PRIOR_QUERIES, n=3)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_generate_queries_prompt_case_facts_in_user_message():
    messages = generate_queries_prompt(SAMPLE_CASE_FACTS, PRIOR_QUERIES, n=3)
    assert SAMPLE_CASE_FACTS in messages[1]["content"]


def test_generate_queries_prompt_prior_queries_in_user_message():
    messages = generate_queries_prompt(SAMPLE_CASE_FACTS, PRIOR_QUERIES, n=3)
    user_content = messages[1]["content"]
    for q in PRIOR_QUERIES:
        assert q in user_content, f"Prior query missing from prompt: {q!r}"


def test_generate_queries_prompt_n_reflected_in_user_message():
    for n in (2, 3, 5):
        messages = generate_queries_prompt(SAMPLE_CASE_FACTS, PRIOR_QUERIES, n=n)
        assert str(n) in messages[1]["content"]


def test_generate_queries_prompt_empty_prior_queries():
    # "None" should appear when no prior queries exist
    messages = generate_queries_prompt(SAMPLE_CASE_FACTS, [], n=3)
    assert "None" in messages[1]["content"]


def test_generate_queries_prompt_messages_nonempty():
    messages = generate_queries_prompt(SAMPLE_CASE_FACTS, PRIOR_QUERIES, n=3)
    for m in messages:
        assert m["content"].strip() != ""


# ---------------------------------------------------------------------------
# Unit: parse_queries
# ---------------------------------------------------------------------------

def test_parse_queries_numbered_dot():
    raw = "1. negligence per se\n2. duty of care pedestrian\n3. traffic violation standard"
    result = parse_queries(raw)
    assert result == ["negligence per se", "duty of care pedestrian", "traffic violation standard"]


def test_parse_queries_numbered_paren():
    raw = "1) negligence per se\n2) duty of care"
    result = parse_queries(raw)
    assert result == ["negligence per se", "duty of care"]


def test_parse_queries_unnumbered_fallback():
    raw = "negligence per se\nduty of care"
    result = parse_queries(raw)
    assert result == ["negligence per se", "duty of care"]


def test_parse_queries_strips_blank_lines():
    raw = "\n1. negligence per se\n\n2. duty of care\n"
    result = parse_queries(raw)
    assert len(result) == 2


def test_parse_queries_empty_string():
    assert parse_queries("") == []


def test_parse_queries_no_empty_strings_in_output():
    raw = "1. negligence per se\n2.   \n3. duty of care"
    result = parse_queries(raw)
    assert all(q.strip() != "" for q in result)


# ---------------------------------------------------------------------------
# Unit: score_result_prompt structure
# ---------------------------------------------------------------------------

def test_score_result_prompt_returns_two_messages():
    messages = score_result_prompt(SAMPLE_CASE_FACTS, SAMPLE_RESULT_RELEVANT)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_score_result_prompt_case_facts_in_user_message():
    messages = score_result_prompt(SAMPLE_CASE_FACTS, SAMPLE_RESULT_RELEVANT)
    assert SAMPLE_CASE_FACTS in messages[1]["content"]


def test_score_result_prompt_case_name_in_user_message():
    messages = score_result_prompt(SAMPLE_CASE_FACTS, SAMPLE_RESULT_RELEVANT)
    assert SAMPLE_RESULT_RELEVANT["case_name"] in messages[1]["content"]


def test_score_result_prompt_snippet_in_user_message():
    messages = score_result_prompt(SAMPLE_CASE_FACTS, SAMPLE_RESULT_RELEVANT)
    assert SAMPLE_RESULT_RELEVANT["snippet"] in messages[1]["content"]


def test_score_result_prompt_missing_fields_dont_crash():
    # Result with minimal fields should not raise KeyError
    messages = score_result_prompt(SAMPLE_CASE_FACTS, {})
    assert len(messages) == 2


# ---------------------------------------------------------------------------
# Unit: parse_score
# ---------------------------------------------------------------------------

def test_parse_score_valid():
    score, reason = parse_score("0.85\nThis case directly addresses negligence per se.")
    assert score == pytest.approx(0.85)
    assert "negligence" in reason.lower()


def test_parse_score_clamps_above_one():
    score, _ = parse_score("1.5\nSome reason")
    assert score == 1.0


def test_parse_score_clamps_below_zero():
    score, _ = parse_score("-0.2\nSome reason")
    assert score == 0.0


def test_parse_score_integer_input():
    score, _ = parse_score("1\nHighly relevant")
    assert score == pytest.approx(1.0)


def test_parse_score_invalid_first_line_returns_zero():
    score, _ = parse_score("not a number\nsome text")
    assert score == 0.0


def test_parse_score_empty_string_returns_zero():
    score, reason = parse_score("")
    assert score == 0.0


def test_parse_score_no_reason_line():
    score, reason = parse_score("0.7")
    assert score == pytest.approx(0.7)
    assert reason == ""


# ---------------------------------------------------------------------------
# Integration: Ollama connection
# ---------------------------------------------------------------------------

def _ollama_running() -> bool:
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def _model_available() -> bool:
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        models = [m["name"] for m in r.json().get("models", [])]
        return any(MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False


ollama_required = pytest.mark.skipif(
    not _ollama_running(),
    reason="Ollama is not running — start with: ollama serve",
)

model_required = pytest.mark.skipif(
    not _model_available(),
    reason=f"Model {MODEL} not available — run: ollama pull {MODEL}",
)


@ollama_required
def test_ollama_is_reachable():
    r = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
    assert r.status_code == 200


@ollama_required
@model_required
def test_ollama_model_is_listed():
    r = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
    models = [m["name"] for m in r.json().get("models", [])]
    assert any(MODEL.split(":")[0] in m for m in models), \
        f"{MODEL} not found in {models}"


# ---------------------------------------------------------------------------
# Integration: run_generate_queries quality
# ---------------------------------------------------------------------------

@ollama_required
@model_required
def test_run_generate_queries_returns_list():
    result = run_generate_queries(SAMPLE_CASE_FACTS, [], n=3)
    assert isinstance(result, list)
    assert len(result) > 0


@ollama_required
@model_required
def test_run_generate_queries_returns_correct_count():
    result = run_generate_queries(SAMPLE_CASE_FACTS, [], n=3)
    # Allow ±1 — models sometimes produce 2 or 4 despite being asked for 3
    assert 2 <= len(result) <= 4


@ollama_required
@model_required
def test_run_generate_queries_no_empty_strings():
    result = run_generate_queries(SAMPLE_CASE_FACTS, [], n=3)
    assert all(q.strip() != "" for q in result)


@ollama_required
@model_required
def test_run_generate_queries_look_like_search_terms():
    """Queries should be concise phrases, not full sentences or paragraphs."""
    result = run_generate_queries(SAMPLE_CASE_FACTS, [], n=3)
    for q in result:
        word_count = len(q.split())
        assert word_count <= 15, f"Query too long to be a search term: {q!r}"


@ollama_required
@model_required
def test_run_generate_queries_avoids_prior_queries():
    """Queries should not repeat what's already been run."""
    result = run_generate_queries(SAMPLE_CASE_FACTS, PRIOR_QUERIES, n=3)
    for q in result:
        for prior in PRIOR_QUERIES:
            assert q.lower() != prior.lower(), \
                f"Model repeated a prior query: {q!r}"


# ---------------------------------------------------------------------------
# Integration: run_score_result quality
# ---------------------------------------------------------------------------

@ollama_required
@model_required
def test_run_score_result_returns_float_and_string():
    score, reason = run_score_result(SAMPLE_CASE_FACTS, SAMPLE_RESULT_RELEVANT)
    assert isinstance(score, float)
    assert isinstance(reason, str)


@ollama_required
@model_required
def test_run_score_result_score_in_valid_range():
    score, _ = run_score_result(SAMPLE_CASE_FACTS, SAMPLE_RESULT_RELEVANT)
    assert 0.0 <= score <= 1.0


@ollama_required
@model_required
def test_run_score_result_reason_nonempty():
    _, reason = run_score_result(SAMPLE_CASE_FACTS, SAMPLE_RESULT_RELEVANT)
    assert len(reason.strip()) > 0


@ollama_required
@model_required
def test_run_score_result_relevant_scores_higher_than_irrelevant():
    """
    The core competence test. A result directly about traffic negligence
    should score meaningfully higher than a bankruptcy estate case.
    A delta of 0.2 is a loose threshold — catches clearly broken scoring
    without being brittle to model variance.
    """
    relevant_score, _ = run_score_result(SAMPLE_CASE_FACTS, SAMPLE_RESULT_RELEVANT)
    irrelevant_score, _ = run_score_result(SAMPLE_CASE_FACTS, SAMPLE_RESULT_IRRELEVANT)
    assert relevant_score > irrelevant_score, (
        f"Relevant result ({relevant_score:.2f}) should score higher than "
        f"irrelevant result ({irrelevant_score:.2f})"
    )
    assert (relevant_score - irrelevant_score) >= 0.2, (
        f"Expected score gap ≥ 0.2, got {relevant_score - irrelevant_score:.2f}"
    )
