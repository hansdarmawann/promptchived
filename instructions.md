# Promptchived v1 specification

Promptchived is a single-user web application that runs on `127.0.0.1`. It archives ChatGPT and Gemini exports in PostgreSQL 18 while preserving messages, alternative branches, source metadata, revisions, and attachment references.

## Core behavior

1. A source folder is registered as either `chatgpt` or `gemini`.
2. The **Scan again** button creates a `pending` job. `promptchived worker` claims jobs through a `SKIP LOCKED` row lock.
3. Every file receives a SHA-256 hash. An `imported` file with the same hash is not processed again.
4. Conversations and messages are upserted using provider IDs, with stable fingerprints as a fallback. When content changes, the previous content is retained as a revision.
5. Text is immediately split into chunks and indexed as `tsvector`, making full-text search available before embedding generation finishes.
6. The worker downloads `intfloat/multilingual-e5-small` into a local cache and stores normalized 384-dimensional embeddings.

## Source parsers

- The ChatGPT parser reads `conversations*.json` shards, `mapping`, `parent` relationships, `current_node`, text and multimodal parts, and asset filename mappings. It stores every branch and marks the path from `current_node` to the root as active.
- The Gemini parser reads each `div.outer-cell` in `MyActivity*.html`, then separates the prompt, answer, and timestamp. An `/app/{id}` link supplies the conversation ID; an entry without an ID becomes a standalone conversation.
- Relative media links are resolved against the export file and must remain inside the registered source root.

## Search

- Full text: `pg_catalog.simple`, a GIN index, `websearch_to_tsquery`, and `ts_rank_cd`, with titles weighted A and bodies weighted B.
- Semantic: E5 `query:` and `passage:` prefixes with exact cosine distance over `vector(384)`.
- Hybrid: up to 100 candidates from each retrieval path are combined per message using Reciprocal Rank Fusion with `k=60`.
- Source, provider, role, and date filters are applied before ranking.
- Long messages are split at approximately 400 tokens with a 50-token overlap while preserving the complete original text.

## Security and limitations

- Rendered HTML and Markdown are sanitized, and scripts from exports are never executed.
- The attachment endpoint only serves paths located under a registered source folder.
- Version 1 does not provide OCR, new transcription, document content extraction, ZIP upload, login, automatic synchronization, or generative answers.
- Timestamps are displayed in `Asia/Jakarta` and stored as UTC `timestamptz` values.

## Code structure

- `src/promptchived/importers`: export format normalization.
- `src/promptchived/services/import_jobs.py`: queueing, deduplication, upserts, and embedding generation.
- `src/promptchived/services/search.py`: full-text, semantic, and RRF retrieval.
- `src/promptchived/main.py`: Jinja pages and the FastAPI API.
- `migrations`: the PostgreSQL schema and pgvector extension.
- `tests`: anonymized fixtures and important behavior regressions.
- `Dockerfile` and `compose.yml`: container image and the local web, worker, migration, PostgreSQL 18, and pgvector stack.
