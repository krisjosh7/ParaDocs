# LLM prompt templates for the two nodes that require a language model call.
# Keeping prompts here (separate from router logic) makes them easy to iterate
# on without touching control flow.
#
# Templates (to be defined as f-strings or LangChain PromptTemplate objects):
#
#   GENERATE_QUERIES_PROMPT
#     Input:  case_facts, queries_already_run, n (number of queries to produce)
#     Output: a numbered list of novel, specific legal search queries
#     Goal:   maximize coverage of unexplored angles; avoid repeating prior queries
#
#   SCORE_RESULT_PROMPT
#     Input:  case_facts, result (case_name, citation, snippet)
#     Output: relevance score 0.0–1.0 + one-sentence justification
#     Goal:   filter noise from CourtListener results before passing to RAG store
