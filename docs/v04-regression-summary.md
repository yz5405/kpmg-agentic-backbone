# v0.4 regression verification

The November 22, 2026 local full-suite run for the changes published as `a191833` recorded **73 passed, 0 failed**. Pytest also reported 13 LangSmith deprecation warnings. The suite includes routing, bounded fallback, fiscal scope, and citation handling.

The result comes from the historical terminal output. A standalone raw pytest log or JUnit XML report was not retained for this run. This summary was prepared without rerunning the suite.

## Reproduce

From the Agent checkout with dependencies installed in the local virtual environment, run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q
```

At `a191833`, expect 73 passing tests. This automated run is reported separately from the live backend and browser checks.
