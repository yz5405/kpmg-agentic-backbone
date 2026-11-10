# Verification record

Verified 2026-11-10 with Python 3.12 on Windows.

- 4 integration test groups passed through FastAPI TestClient.
- Both HTML routes and health endpoint returned successfully.
- RAG returned extractive evidence and citations, preserving caller trace IDs.
- Graph-only and combined tool routing completed.
- Off-topic and missing-company requests were handled explicitly.
- Unsupported company returned no evidence.
- Blank queries, boolean top_k and out-of-range top_k returned HTTP 422.

This is a fixture-backed demonstration, not a live retrieval deployment. Browser visual QA and Docker execution have not been performed. No online deployment URL exists yet. GitHub write attempts were rejected with HTTP 403; Render account connection is pending.
