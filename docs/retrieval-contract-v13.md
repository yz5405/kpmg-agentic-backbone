# Retrieval contract v1.3 integration

The checklist uses frozen Chroma `7a7ad9801f86`. The demo target is the
Full233 index `3abed1490b13` with 233 filings and 37,957 persisted
chunks. Use upstream RAG main at `6a7b001` or later for paged loading.

In the demo process set `KPMG_RAG_BACKEND=real`, `KPMG_COVERAGE_PRECHECK=1`,
`RAG_BACKEND=chroma` and `RAG_CHROMA_DIR` to the selected index.
Unset `RAG_INDEX_DIR` and `RAG_COVERAGE_MANIFEST` so coverage reads from
the same retriever. Check persistence with the upstream
`scripts/repersist_chroma.py <chroma_dir> --check` before serving requests.

The joint path defaults to 15 results and selects the single-filing or
multi-target API according to the coverage result. With GraphRAG auto
routing enabled, a resolved supported ticker can use one GraphRAG tool
on a RAG coverage miss. Filing coverage for GOOGL, AMZN, WMT, INTC, CAH
and WDC still requires backend confirmation.

The calculator covers quarterly consolidated revenue difference and
YoY growth from verified SEC tables. It keeps each filing date and
declines conflicting or noncomparable inputs. Ranking, Exhibit 21
counts, general financial arithmetic and live model acceptance remain
outside this verification.
