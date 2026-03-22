"""
LLM prompt templates and output parsers for the two nodes that require
a language model call: generate_queries and score_result.

Calls use the Groq API (see GROQ_API_KEY and GROQ_MODEL in backend/.env).

Design principles:
  - Numbered list output for queries (reliable across models)
  - Score-then-reason format for scoring (trivially parseable, no JSON)
  - Concise system messages
  - case_facts is always the grounding context — never omitted
"""

from groq_llm import generate_text


# ---------------------------------------------------------------------------
# Generate queries
# ---------------------------------------------------------------------------

def generate_queries_prompt(
    case_facts: str,
    queries_run: list[str],
    n: int = 3,
) -> list[dict]:
    """
    Build the message list for the generate-queries LLM call.

    Args:
        case_facts:   raw text describing the legal situation
        queries_run:  queries already executed (LLM must avoid repeating these)
        n:            number of novel queries to generate

    Returns:
        List of Ollama message dicts (role + content).
    """
    prior = "\n".join(f"- {q}" for q in queries_run) if queries_run else "None"

    return [
        {
            "role": "system",
            "content": (
                "You are a legal research assistant. Your job is to generate "
                "precise search queries for CourtListener, a database of US court "
                "opinions. Queries should use specific legal terms and concepts — "
                "not full sentences. Each query should explore a different legal "
                "angle of the case."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Case facts:\n{case_facts}\n\n"
                f"Queries already run (do not repeat these):\n{prior}\n\n"
                f"Generate {n} novel search queries that cover unexplored legal "
                f"angles of this case. Output only a numbered list, one query per "
                f"line, no explanations.\n\n"
                f"Example format:\n"
                f"1. negligence per se highway safety\n"
                f"2. duty of care motor vehicle operator\n"
                f"3. reasonable person standard traffic violation"
            ),
        },
    ]


def parse_queries(response_text: str) -> list[str]:
    """
    Parse the numbered list output from generate_queries into a clean list.

    Handles:
      "1. query text"  →  "query text"
      "1) query text"  →  "query text"
      "query text"     →  "query text"  (unnumbered fallback)
    """
    queries = []
    for line in response_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading number + delimiter ("1." or "1)")
        if line[0].isdigit():
            line = line.lstrip("0123456789").lstrip(".").lstrip(")").strip()
        if line:
            queries.append(line)
    return queries


def run_generate_queries(
    case_facts: str,
    queries_run: list[str],
    n: int = 3,
) -> list[str]:
    """
    Call Groq and return a parsed list of search queries.
    This is the function the router calls directly.
    """
    messages = generate_queries_prompt(case_facts, queries_run, n)
    raw = generate_text(messages[0]["content"], messages[1]["content"], temperature=0.3)
    return parse_queries(raw)


# ---------------------------------------------------------------------------
# Score result
# ---------------------------------------------------------------------------

def score_result_prompt(case_facts: str, result: dict) -> list[dict]:
    """
    Build the message list for the score-result LLM call.

    Args:
        case_facts: raw text describing the legal situation
        result:     normalized result dict from courtlistener.py

    Returns:
        List of Ollama message dicts.
    """
    case_name = result.get("case_name", "Unknown")
    citation = result.get("citation", "")
    snippet = result.get("snippet", "")
    source_type = result.get("source_type", "search")

    header = f"{case_name}"
    if citation:
        header += f" ({citation})"

    return [
        {
            "role": "system",
            "content": (
                "You are a legal relevance assessor. Given a legal case and a "
                "search result from CourtListener, rate how relevant the result "
                "is to the case. Output your score on the first line as a decimal "
                "between 0.0 and 1.0. On the second line, write one sentence "
                "explaining why. No other output."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Case facts:\n{case_facts}\n\n"
                f"Search result ({source_type}):\n"
                f"Case: {header}\n"
                f"Excerpt: {snippet}\n\n"
                f"How relevant is this result to the case facts?\n"
                f"Line 1: score (0.0 to 1.0)\n"
                f"Line 2: one-sentence reason"
            ),
        },
    ]


def parse_score(response_text: str) -> tuple[float, str]:
    """
    Parse the score-then-reason output from score_result.

    Returns:
        (score, reason) where score is clamped to [0.0, 1.0].
        Falls back to (0.0, raw_text) if parsing fails.
    """
    lines = [l.strip() for l in response_text.strip().splitlines() if l.strip()]
    if not lines:
        return 0.0, "No response"

    try:
        score = float(lines[0])
        score = max(0.0, min(1.0, score))  # clamp to valid range
    except ValueError:
        return 0.0, response_text

    reason = lines[1] if len(lines) > 1 else ""
    return score, reason


def run_score_result(case_facts: str, result: dict) -> tuple[float, str]:
    """
    Call Groq and return (score, reason) for a single result.
    This is the function the router calls directly.
    """
    messages = score_result_prompt(case_facts, result)
    raw = generate_text(messages[0]["content"], messages[1]["content"], temperature=0.0)
    return parse_score(raw)
