"""
Shared fixtures and configuration for the research test suite.

Loads .env from the repo root automatically — no manual export needed.
Just run from the backend/ directory:
    pytest research/tests/test_courtlistener.py -v
"""

import os
from pathlib import Path
import pytest
from dotenv import load_dotenv

# .env is two levels up: backend/research/tests/ -> backend/ -> ParaDocs/
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ENV_PATH)

# Confirmed valid citation from the CourtListener citation-lookup API docs.
KNOWN_CITATION_TEXT = "Obergefell v. Hodges (576 U.S. 644) established the right to marriage"

# Simple legal query guaranteed to return results.
KNOWN_SEARCH_QUERY = "negligence per se"

# Well-known SCOTUS cases — high cite counts, stable opinion IDs.
# Miranda v. Arizona (1966): cluster 103604, opinion ID varies by document.
# Used for citation chasing tests instead of a hardcoded ID from docs examples.
KNOWN_CASE_SEARCH = "Miranda v. Arizona"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that make real HTTP calls to CourtListener "
        "(requires COURTLISTENER_TOKEN env var — skipped if token is absent)",
    )


@pytest.fixture(autouse=True)
def skip_integration_without_token(request):
    """Auto-skip integration tests when no token is set."""
    if request.node.get_closest_marker("integration"):
        if not os.environ.get("COURTLISTENER_TOKEN"):
            pytest.skip("COURTLISTENER_TOKEN not set — skipping integration test")
