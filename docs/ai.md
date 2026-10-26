# The AI module

Members ask questions about their workspace's documents and get streamed answers that cite the passages they come from. Every model call is costed, and each workspace has a monthly spending cap.

| File (`backend/src/app/ai/`) | What it does |
| --- | --- |
| `providers.py` | Claude, any OpenAI-compatible server, or a fake. The rest of the app never imports an SDK. |
| `ask.py` | `POST /workspaces/{id}/ask`: search, call the model, stream the answer, check the citations, record the cost. |
| `documents.py` | Upload, list and delete documents; search a workspace's passages with pgvector. |
| `usage.py` | The usage ledger, the monthly cap, and `GET /workspaces/{id}/usage`. |
| `pricing.py` | Prices per million tokens. |
| `parsing.py`, `chunking.py`, `embeddings.py` | PDF, Word, Markdown and text in; passages and vectors out. |

## Choosing a model

| `AI_PROVIDER` | Settings | Notes |
| --- | --- | --- |
| `anthropic` (default) | `ANTHROPIC_API_KEY`, `AI_MODEL=claude-opus-5-5`, `AI_EFFORT=low` | Native citations: Claude returns the exact sentences it used, and `ask.py` checks each one is in the passage it names. With `AI_FALLBACKS=true` (the default), a request Claude's safety classifiers decline is re-run on Anthropic's recommended fallback model instead of failing. |
| `openai` | `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `AI_MODEL` | Works with OpenAI, Ollama (`http://localhost:11434/v1`), vLLM and LM Studio. The model is asked to write `[1]` after each claim; the numbers become citations. Weaker than native citations, because the model can cite the wrong passage. |
| `fake` | none | Quotes the best passage. For tests, and for trying the app without a key. |

For a model missing from `pricing.py`, set `AI_PRICE_INPUT_PER_MTOK` and `AI_PRICE_OUTPUT_PER_MTOK` (both `0` for a model you host). Otherwise unknown models are costed at the highest price in the table, so the cap stops early rather than late.

## What the answer stream looks like

`POST /workspaces/{id}/ask` with `{"question": "…", "history": [{"role": "user", "text": "…"}, …]}` returns server-sent events:

- `sources`: the passages the model was given, numbered from 1.
- `delta`: text as it is written. Show it, then replace it with `done`.
- `done`: `answer` as parts with the source numbers each cites, `grounded` (at least one citation survived checking), `refused`, `truncated`, tokens and `cost_usd`.
- `error`: the model call failed.

Before the stream starts, the API answers `429` when the workspace's budget is spent and `409` when it has no documents.

## Spending caps

`AI_MONTHLY_BUDGET_USD` applies to every workspace; set `workspaces.ai_monthly_budget_usd` to give one workspace its own cap (part 3 sets it from the Stripe plan). Customers can see their spending but not change the cap.

Two known gaps, both written down in the code: the cap is checked before a call and the cost recorded after, so concurrent calls can overshoot by the calls in flight; and a call abandoned by a closed browser tab goes unrecorded. Reserve an estimate before each call if either matters to you.

## Search quality

`scripts/eval_retrieval.py` embeds the documents in `eval/documents/` and checks that, for each question in `eval/questions.yaml`, a passage containing its evidence phrase is among the top results. CI runs it with the real model and fails below 90% recall@3.

The first run on CI, with `paraphrase-multilingual-mpnet-base-v2`: recall@1 and recall@3 were both 27/27, including 5 Turkish and 5 Arabic questions about English documents. The word-matching test embedder scored 6/27 and 15/27 on the same set. A perfect score means this set is too easy to tell good changes from bad ones; replace it with questions from your own users and documents.

Search scans one workspace's chunks exactly. It stays fast to roughly 100,000 chunks per workspace; past that, add an HNSW index with pgvector's iterative scans turned on, so the workspace filter can't starve the results.

## Changing the embedding model

The `chunks.embedding` column is 768 dimensions, to match the default model. A model with another size needs `EMBEDDING_DIM` in `models.py`, a migration, and a re-upload of every document. With a mismatched model, uploads and questions fail with a message saying so, rather than storing vectors that cannot be compared.
