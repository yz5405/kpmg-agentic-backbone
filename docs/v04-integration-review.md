# Agent v0.4 verification and reproduction

[PR #14](https://github.com/yz5405/kpmg-agentic-backbone/pull/14) integrates capability-aware routing, capped fallback, and SEC citation provenance. The validation below covers the integration at commit `a191833`.

## Verified in v0.4

| Area | Result |
| --- | --- |
| Automated regression | [73 tests passed](v04-regression-summary.md) |
| Local retrieval | Frozen Chroma and DuckDB verified through FastAPI |
| Neo4j | [Automatic routing to the real read-only graph backend verified](v04-neo4j-verification.md) |
| Financial Explorer v2 | [Real retrieval and SEC citation rendering verified](v04-ui-acceptance.md) |

## Reproduce locally

1. Follow the [repository setup instructions](../README.md#local-environment). Use team-approved instances and artifacts. Load credentials from your local environment.
2. Enable real Chroma and GraphRAG. Set `KPMG_TOOL_SELECTION=auto` to exercise question-aware routing. Keep both LLM flags off for retrieval-only verification.
3. Run the [regression command](v04-regression-summary.md), then use the [Neo4j](v04-neo4j-verification.md) and [UI](v04-ui-acceptance.md) checks.
4. Use the repository validation scripts with approved local inputs for additional team evaluation.

## Scope and open checks

RAG-first remains available. Automatic routing selects Vector for narrative retrieval, Structured for supported financial lookups, and Graph for explicit claim keyword searches. One alternate retrieval attempt is allowed. SEC source validation and evidence evaluation run before answer generation. Cross-company ranking, financial calculations that require complete coverage, and graph traversal remain unsupported.

The remaining end-to-end check is a real model-generated answer with citations in Financial Explorer. The retrieval traces, rule-based extraction records, and generated HTML are kept outside this public documentation update.
