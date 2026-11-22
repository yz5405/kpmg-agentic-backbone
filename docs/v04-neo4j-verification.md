# v0.4 Neo4j automatic routing verification

A November 22, 2026 read-only smoke test on `a191833` sent a Microsoft competition claims question through Agent FastAPI. The Agent automatically selected and used Graph. Neo4j returned three accepted results with SEC filing links and section provenance. The API returned `SUCCESS` with zero fallback attempts.

A separate test with Neo4j intentionally unconfigured recorded `backend_unavailable` and successfully used its single Chroma fallback. The graph case validates lexical claim search. LLM answer generation was disabled, and graph traversal is outside this verification.

## Reproduce

Load the team-approved Neo4j configuration using the [local environment setup](v04-agent-setup.md#local-environment), enable automatic routing, and leave generated Cypher disabled. Submit “Find Microsoft claims about competition” to `/query` with `top_k=3`. Check that `selected_tool` and `used_tool` are both `graph`, each citation has SEC section provenance, and `fallback_attempts` is zero.
