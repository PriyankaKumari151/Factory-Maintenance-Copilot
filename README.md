# Factory Maintenance Copilot — two-day interview lab

All factory records, SOPs, inventory, and ticket APIs are synthetic. This is a local prototype, not a deployed industrial control system. The application never controls equipment.

## 1. What you are building

An operator can (a) retrieve SOP evidence, (b) view SQL downtime rankings and fault totals, or (c) combine SQL results, matching SOP evidence, and a REST inventory lookup. The operator reviews and submits a maintenance ticket to a separate mock service.

The UI explicitly selects the workflow, dates, and machine. It does NOT infer arbitrary SQL operations from natural language. The question helps document retrieval and answer generation. Combined mode investigates the fault with the most recorded downtime for the highest-downtime machine in the selected window. It does not establish root cause.

Data path: CSV -> Pandas ETL -> SQLite -> parameterised SQL.
Document path: Markdown sections -> metadata -> TF-IDF or semantic embeddings -> cosine ranking -> evidence -> optional Gemini response.
Integration path: workflow -> requests -> separate FastAPI platform -> inventory JSON / persistent ticket SQLite.

## 2. Windows setup (Command Prompt)

Install Python 3.11 (64-bit) if you do not already have it. Extract the ZIP into a short path, for example `C:\Projects\factory-copilot`. Open that folder in VS Code. Choose Command Prompt as the terminal profile for these commands.

```bat
cd C:\Projects\factory-copilot
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
python seed_data.py
python ingestion.py
python -m pytest -q
```

If your extracted files are in a nested `factory-copilot` folder, `cd` into that folder first. If `py -3.11` is unavailable but `python --version` shows Python 3.11, use `python -m venv .venv`. Run commands where `requirements.txt` exists.

The sample generation prints 93 raw rows. ETL prints 90 accepted and 3 rejected. Re-running ETL replaces operational tables; it does not delete tickets in `data/platform.db`.

First use the supplied offline configuration: `RETRIEVAL_BACKEND=tfidf`, blank Gemini key/model. This confirms plumbing before adding external dependencies.

## 3. Start three terminals

In EACH terminal change to the project folder and activate `.venv`.

Terminal 1: simulated enterprise platform:

```bat
python -m uvicorn mock_platform:app --host 127.0.0.1 --port 8001
```

Terminal 2: copilot API:

```bat
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Terminal 3: UI:

```bat
python -m streamlit run app.py
```

Open http://localhost:8501. Inspect the API at http://127.0.0.1:8000/docs and mock platform at http://127.0.0.1:8001/docs. Leave all three terminals running. Stop a process with Ctrl+C.

Try combined mode, all machines, October 1–7, 2026:

> Which machine had the highest downtime? Show its main recorded fault, relevant SOP, and spare-part availability.

You should see SQL results, SOP source sections, inventory, and a workflow trace. Offline mode explicitly states that no LLM answer was generated. Check the UI's generation and retrieval labels rather than assuming which mode is active.

## 4. Learn the code in this order

### A. `seed_data.py` and `ingestion.py` — 60–90 minutes

Read the three machines and six faults. Understand the random seed. Inspect `data/downtime.csv` and locate duplicate, missing-time, and negative-duration records. Read `clean_events()` line by line, then inspect `data/rejected_downtime.csv`.

Learn: DataFrames, type conversion, boolean masks, vectorised datetime subtraction, `.loc`, deduplication, rejection reports, SQLite connections.

Exercise: add an unknown machine record, rerun ingestion, and explain why rejection is preferable to assigning a guessed machine. Recreate original data with `python seed_data.py` then `python ingestion.py`.

### B. `database.py` — 60 minutes

Read `downtime_summary()` and `fault_summary()`. The SQL is handwritten; question text is never inserted into SQL. Placeholders bind values, not SQL syntax. The database is opened read-only for analytics.

Learn: JOIN, GROUP BY, SUM, COUNT, ORDER BY, parameters, half-open timestamp windows, indexes.

Important convention: dates are UTC; the inclusive end date becomes the next day's exclusive midnight. Events are assigned by START timestamp and their entire duration is counted. This is not overlap-clipped calendar downtime. Raw overlapping events could double-count time; real deployment needs event normalisation and an agreed business definition.

Exercise: explain why `2026-10-08T00:00:00Z` is excluded from October 1–7. Then write a query to count events by fault code without copying the existing query.

### C. `retrieval.py` — 90 minutes

Each SOP has metadata and two heading sections. We preserve the heading section as a chunk. `SOPRetriever` loads and indexes once per API process; changing documents requires restarting the API. This small demo does not persist its embedding matrix to disk.

Learn: chunking, source metadata, TF-IDF versus learned dense embeddings, matrix dimensions, normalisation, cosine similarity, top-k, metadata filtering.

The dot product `scores = self.matrix @ vector` equals cosine similarity for the normalised representations used here. A similarity score is NOT a probability or calibrated confidence score. The zero-score filter is a minimal baseline, not a reliable semantic abstention strategy.

Exercise: SOP workflow -> machine M002 -> fault SEAL_FAIL -> ask about seal inspection. Inspect retrieved chunks. Try UNKNOWN_FAULT and confirm no evidence is returned. Notice that a broad query with no filters can produce irrelevant matches: explain how evaluation and better filters would help.

### D. `platform_client.py` and `mock_platform.py` — 60–90 minutes

Learn: HTTP GET/POST, headers, request timeouts, bounded retries, status codes, request schemas, idempotency keys, SQLite transactions.

Stop terminal 1 and rerun combined mode. Inventory should be explicitly unavailable. Restart it. Submit a reviewed ticket, then submit identical content again. The same request key returns the same ticket; changed content with the same key yields 409. A new investigation creates a new request key.

### E. `workflow.py` and `api.py` — 60–90 minutes

Learn: TypedDict state, graph nodes, conditional edges, `compile()`, `invoke()`, Pydantic validation, response models, component caching, logging.

Trace the three routes. `sop` retrieves documents; `analytics` queries SQL; `combined` queries SQL then SOPs then inventory. Mode selection is explicit. This is a deterministic LangGraph workflow, not autonomous multi-agent orchestration. Explain how a future structured LLM router could choose allowed operations after schema validation.

### F. `llm_client.py` and `app.py` — 60 minutes

Learn: REST model requests, system instructions, evidence serialization, token/output limits, error paths, frontend/backend separation, session state. Documents are treated as data in the prompt, but prompt wording alone does not guarantee injection resistance or factual correctness.

## 5. Enable semantic retrieval

Do this once the baseline runs:

```bat
python -m pip install -r requirements-semantic.txt
```

Change `.env`:

```ini
RETRIEVAL_BACKEND=semantic
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Restart terminal 2. First use downloads model weights from Hugging Face; allow time and internet access. CPU is sufficient for this tiny dataset. This installs PyTorch dependencies and may take several minutes. On model download/import failure, inspect the terminal, or deliberately switch back to `tfidf` and restart. The application does not silently fall back and mislabel retrieval.

For this symmetric MiniLM model, `.encode()` is sufficient. Models with query/document-specific prompts should use the appropriate query and document encoding methods.

## 6. Enable actual LLM answers

Create a Gemini API key in https://aistudio.google.com/apikey. Check available models and quota in your account; do not assume any model name or free quota is guaranteed. Set `.env`:

```ini
GEMINI_API_KEY=your_actual_key
GEMINI_MODEL=your_available_generateContent_model_id
```

Use a plain model ID without `models/`. Restart terminal 2. The provider request uses the native `generateContent` REST endpoint and the `x-goog-api-key` header. Offline mode should change to `gemini` on a successful call. An HTTP error produces `llm_error`, preserving evidence. 401/403 often indicate credentials/access; 404 may indicate an unavailable model; 429 indicates a quota/rate issue. Inspect provider documentation rather than repeatedly guessing model names.

Keep `.env` private; `.gitignore` and `.dockerignore` exclude it. Only synthetic evidence is included. Live model calls can consume provider quota or incur charges.

## 7. Evaluate

With API and mock platform running, open a fourth activated terminal:

```bat
python -m pytest -q
python evaluate.py
```

There are 12 unit/integration tests and 20 live deterministic checks. `evaluation_results.json` contains individual results and wall-clock latency. SQL evaluation independently aggregates the clean CSV. Retrieval checks are intentionally small and often metadata-filtered, so passing is not evidence of broad semantic quality. The checks do not measure generated-answer correctness, groundedness, or citation entailment. Manually review five generated answers and verify every number and cited claim against evidence. Compare keyword and semantic modes using paraphrased questions without fault filters as a stretch task.

Live evaluation issues up to 18 generation requests when LLM mode is enabled. Leave key/model blank for deterministic offline evaluation if you want to avoid those calls.

## 8. Git and handoff

```bat
git init
git add .
git commit -m "Build synthetic factory maintenance copilot"
```

Learn the differences between tracked files, ignored secrets, commits, and branches. `requirements.txt` uses compatibility ranges, not a fully locked environment. After successful installation you can record your exact versions with `python -m pip freeze > requirements-lock.txt` and reproduce with that file.

Optional Docker: the included Dockerfile builds the backend only, not the full three-service system. It is a packaging exercise; full deployment needs service networking, environment configuration, persistent volumes, and a UI container. For two days, run locally first.

## 9. Interview talking points and limits

- Problem: operators need operational records and the relevant approved procedure in one place.
- Business validation: shadow an operator, ask where time is lost, observe existing escalation, then agree acceptance criteria.
- User story: as an operator, see the selected machine's fault records and cited procedure so I can escalate with evidence.
- Acceptance criteria: correct date/machine scope, exact SQL totals, visible source versions, explicit unavailable stock, ticket review before submission.
- Tradeoffs: SQLite for setup speed; NumPy search for tiny corpus; fixed SQL for testability; explicit routing for clarity; bounded network calls for graceful failure.
- Not implemented: arbitrary text-to-SQL, real Poka/Weaver connectors, autonomous agents, telemetry anomaly detection, scanned-PDF OCR, production access control, cloud deployment, automatic citation validation, comprehensive retrieval evaluation, document version lifecycle.
- Future production work: identity and authorisation, per-site data isolation, document lifecycle, audited source validation, database migration, monitoring, load testing, cloud secrets/storage/model endpoint.

Day 1: setup -> ETL -> SQL -> retrieval -> offline UI.
Day 2: HTTP integration -> graph -> semantic/LLM modes -> tests -> five-minute demo practice.
Keep time for sleep and explaining the implementation in your own words.

Official references:
- https://fastapi.tiangolo.com/tutorial/
- https://docs.langchain.com/oss/python/langgraph/graph-api
- https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html
- https://ai.google.dev/api/generate-content
