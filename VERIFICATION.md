# Verification of this starter

Executed in the build environment:

- Generated 93 synthetic operational rows; accepted 90 and rejected 3.
- 12 pytest tests passed: data cleaning, date boundaries, parameter binding, metadata filters, out-of-vocabulary retrieval, combined graph execution, no-events handling, API validation, ticket idempotency, inventory failure, and model timeout handling.
- 20/20 deterministic HTTP evaluation checks passed with the actual FastAPI and mock-platform processes running together, using TF-IDF and offline extract mode.
- Streamlit AppTest loaded the interface, ran an investigation, displayed three evidence tables, and successfully submitted a reviewed ticket with no UI exceptions.

Not verified: live Gemini generation, external model authentication/quotas, sentence-transformer model download or semantic-mode execution, Docker build, Windows runtime. Instructions for those steps are in README.md. Model response correctness and citation support require human review; the 20 checks do not establish answer accuracy.

Re-run the checks in your own environment. Timing depends on hardware and whether LLM generation is enabled.
