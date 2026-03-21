# CourtListener API client — all HTTP calls to CourtListener live here.
# Nothing else in the research module imports requests/httpx directly;
# they go through these functions.
#
# Responsibilities:
#   - Authenticate with the CourtListener API (token from env)
#   - search_opinions(query: str) -> list[dict]
#       Hits /api/rest/v3/search/ with type=o (opinions)
#       Returns a normalized list of dicts:
#         { id, case_name, citation, court, date_filed, snippet, url }
#   - Normalize raw API responses into a consistent shape so the rest of
#     the subgraph never has to know about CourtListener's field names
#
# Future (stretch):
#   - lookup_citations(opinion_id) — fetch what a case cites / is cited by
#   - search_dockets(query) — docket-level search if needed
