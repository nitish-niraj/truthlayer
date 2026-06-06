# stress/

Synthetic inputs used by the stress test suite (`tests/test_stress.py`).
These are generated programmatically — no hand-authored fixtures — and
exercise the pipeline at the boundaries:

- Large PDFs (50+ claims after extraction)
- Many concurrent image verifications
- Vision timeouts (the LLM takes longer than the budget)
- Search timeouts (Tavily stalls)
- Mixed batches (some PDFs, some images, in the same test run)

Files in this directory are typically `.txt` or `.pdf` blobs produced by
the test fixture builder. They are git-ignored to keep the repository
small.
