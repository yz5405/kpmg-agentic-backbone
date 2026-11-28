# GraphRAG contract and Agent integration boundary

The current Agent uses the official Python arms. This path receives evidence
lists and cannot distinguish all decisions from the MCP search envelope.
Discover capabilities per arm with `describe_filters` and `describe_corpus`.
Keep those snapshots separate from Chroma coverage. A missing or unavailable
snapshot does not certify that a filing is absent. Use ticker routing as a
candidate signal and CIK for company identity joins.

The Python adapter preserves the evidence fields and arm metadata. Ticker
arrays stay intact. Multiple period filters use individual scalar scopes
with the same trace ID. Exact dates remain reporting-period filters.
Section slugs are for Graph. Structured has no section pointer. A Graph
claim's fixed provenance hops do not implement traversal.

A future Specialist adapter can accept question, trace ID, chosen arm,
scoped filters and top_k. Its result should carry request_id, status, reason,
results, count, arm and graphrag_commit. Keep the 19 fields and open metadata
on each result, including nullable chunk_id, fact or section provenance,
and raw data-source caveats. Treat abstain/missing_fact and clarify/ambiguous
as decisions and keep transport/tool errors separate. Compare scores only
within their originating call. Never replace validated evidence on an
empty or failed fallback.

Stdio and streamable HTTP are upstream transports. Production transport
selection and dynamic capability caching belong in a separate change.
There is no Hybrid arm or GraphRAG Specialist service in this integration.
