# Phase 2 — Documents Module (Ingestion Half of RAG)

## Goal

Let clients manage unstructured business content (policies, FAQs, etc.) with
a draft/publish lifecycle, and turn published documents into searchable
embeddings.

## Prerequisites

Phase 0 (tenancy/auth).

## Data model

### `documents`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk | |
| title | text | |
| content_source | enum(`upload`,`paste`,`url`) | |
| source_ref | text nullable | original filename or source URL, for reference |
| draft_content | text | latest edited text (post-extraction, pre-publish) |
| tags | text[] | flat tags |
| status | enum(`draft`,`processing`,`active`,`failed`,`inactive`) | |
| last_published_at | timestamptz nullable | |
| created_at / updated_at | timestamptz | |

### `document_chunks`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| document_id | UUID fk | |
| tenant_id | UUID | denormalized for direct tenant-scoped queries without a join |
| chunk_index | int | |
| content | text | |
| embedding | vector(1536) | pgvector column, dimension matches chosen OpenAI embedding model |
| token_count | int | |
| is_active | bool | see "safe publish" below |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/tenant/documents` | Create (paste text or metadata for upload/url) |
| POST | `/tenant/documents/{id}/upload` | Multipart file upload (PDF/DOCX/TXT) → extracts text into `draft_content` |
| POST | `/tenant/documents/import-url` | Fetch + strip HTML → `draft_content` |
| GET | `/tenant/documents` | List, filter by tag/status |
| GET | `/tenant/documents/{id}` | Detail |
| PATCH | `/tenant/documents/{id}` | Edit title/tags/draft_content → stays/returns to `draft` |
| POST | `/tenant/documents/{id}/publish` | Chunk + embed → `processing` → `active`/`failed` |
| POST | `/tenant/documents/{id}/retry` | Re-attempt publish after `failed` |
| PATCH | `/tenant/documents/{id}/deactivate` | → `inactive` (excluded from retrieval, not deleted) |
| DELETE | `/tenant/documents/{id}` | Hard delete (document + chunks) |

## File parsing

- PDF → `pypdf` (`PdfReader`, concatenate page text)
- DOCX → `python-docx` (concatenate paragraph text)
- TXT → decode as UTF-8 directly
- URL import → `httpx.get` + `BeautifulSoup` (strip script/style/nav, extract
  main textual content — simple heuristic is fine for MVP, no need for
  readability-style extraction initially)
- Enforce a max file size (e.g. 10MB) and max extracted character count to
  bound embedding cost and prevent abuse

## "Safe publish" pattern

Publishing must never leave a previously-searchable document suddenly
unsearchable just because a new edit failed to embed:

1. On publish, set `status=processing`.
2. Chunk `draft_content`, call OpenAI embeddings in batches.
3. Insert new `document_chunks` rows with `is_active=false`.
4. On full success: flip new chunks to `is_active=true`, delete/flip old
   chunks to `is_active=false` (or delete them), set `status=active`,
   `last_published_at=now()`.
5. On any failure: leave old `is_active=true` chunks untouched, set
   `status=failed`, discard the partial new chunk rows.

Retrieval queries always filter `document_chunks.is_active = true` and join to
`documents.status = 'active'`.

## Chunking strategy

- Simple recursive splitter: target ~500 tokens per chunk, ~50 token overlap,
  split on paragraph/sentence boundaries first, hard-wrap only if a single
  paragraph exceeds the target size
- No heavyweight framework dependency — this is straightforward enough to
  implement directly (a few dozen lines), keeping the dependency list
  (already fixed in `pyproject.toml`) unchanged

## Embedding

- OpenAI embeddings endpoint (e.g. `text-embedding-3-small`, 1536 dims —
  confirm dimension matches the `vector(N)` column before the first migration)
- Batch chunks per document into groups (e.g. 100 per API call) to reduce
  request overhead

## Task checklist

1. Models + migration (incl. pgvector index — `ivfflat` or `hnsw` on `embedding`)
2. Upload/parse endpoints for PDF/DOCX/TXT
3. URL import endpoint
4. Chunking function (pure function, easily unit-testable)
5. Embedding client wrapper (batches, retries with backoff)
6. Publish pipeline implementing the safe-publish swap above
7. CRUD + list/filter endpoints

## Test plan

- Unit: chunker produces expected chunk count/overlap for known input sizes
- Unit: PDF/DOCX/TXT fixtures extract expected text
- Integration: publish a document → chunks exist with `is_active=true`,
  `documents.status=active`
- Integration: force an embedding failure (mock) → `status=failed`, old
  active chunks (from a prior successful publish) remain queryable
- Integration: similarity search for a known question returns the chunk
  containing the answer, ranked first
- Integration: `inactive` document's chunks excluded from retrieval

## Out of scope

- OCR for scanned/image-only PDFs
- Per-language chunking tuning
- Automatic re-crawl of imported URLs on a schedule
