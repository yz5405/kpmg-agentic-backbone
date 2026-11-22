# v0.4 integration review

## Decisions and contract draft

- Keep RAG-first available and make auto routing opt-in for the sprint. GraphRAG
  revision `de637a8` applies ticker and form filters and translates fiscal labels
  into reporting windows. Graph refuses unsupported filters. Structured accepts
  some upstream keys it does not apply, such as section and is_table. The Agent
  adapter only offers ticker, form, fiscal year and fiscal period and explicitly
  rejects other keys. A quarter requires a fiscal year. A ticker list scopes
  allowed companies without guaranteeing coverage for each company.
- Put the coverage check after query understanding and before tool selection.
  Check the requested capabilities, fiscal interval and number of companies.
  After retrieval, verify SEC provenance and evidence sufficiency before
  sending evidence to the answer model. A candidate count or Chroma status is
  insufficient to establish that a calculation is answerable.
- Keep the frozen `final_v2` retriever as the reproducible reference. Keep the
  Agent's citation ID validation and answer policy. Defer a Terra versus Luna
  recommendation until paired live comparisons of supported answers, truthful
  abstention, citation correctness, latency and tokens are available.
- Proposed Retrieval Contract §19 change for team review. Report selected and
  accepted tool, attempted tool and outcome, sanitized failure category,
  fallback count, latency, trace ID and provenance. Distinguish no match,
  insufficient evidence and backend failure. Define ranking as a separate
  capability requiring common units, complete per-company time coverage and
  deterministic arithmetic. This draft has not been posted to GitHub.

## Known limitations

EV2-040 uses the latest filing for each company in a specific snapshot.
EV2-042 additionally requires verified net income and revenue for the same
company and interval. EV2-043 additionally requires comparable prior-year
revenue. The current bounded retriever does not prove completeness for these
operations. The ranking and Microsoft–Apple comparison tests assert safe
abstention with available candidate evidence.

The local browser check covers live retrieval and SEC citation rendering.
Live model output and the new Neo4j routing pass require usable, approved
credential configuration. Historical backend tests from PR #14 are recorded
separately from this sprint's reruns.
