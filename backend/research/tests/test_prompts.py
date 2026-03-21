"""
Tests for research/prompts.py

Strategy:
  - Prompts are strings/templates, so tests are purely about rendering:
    do all required variables get substituted, is the output non-empty,
    are the instructions clear enough to parse in downstream tests?
  - No LLM calls here — that belongs in integration tests on the router.
"""

import pytest


# ---------------------------------------------------------------------------
# GENERATE_QUERIES_PROMPT
# ---------------------------------------------------------------------------

# TODO: test that rendering with case_facts, queries_already_run, n=3
#       produces a string with no unresolved template placeholders
# TODO: test that queries_already_run list is present in the rendered output
#       so the LLM actually sees what to avoid
# TODO: test that n is reflected in the prompt (e.g. "generate 3 queries")


# ---------------------------------------------------------------------------
# SCORE_RESULT_PROMPT
# ---------------------------------------------------------------------------

# TODO: test that rendering with case_facts + a result dict produces a
#       non-empty string with no unresolved placeholders
# TODO: test that case_name and snippet from the result appear in the output
#       (LLM needs to see the actual content to score it)
