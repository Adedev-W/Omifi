# Omifi PRD: System Design and Implementation

**Status:** Implementable MVP  
**Scope:** Editing Flow and Judges Flow  
**Database:** SQLite  
**Language:** American English  
**Architecture diagram:** [`omifi-architecture.png`](assets/omifi-architecture.png)

## 1. Summary

Omifi helps users adapt a LaTeX resume to a job description, generate a PDF,
and evaluate resume quality. IBM Bob Shell provides the user interface,
Langflow orchestrates editing and judging, and the backend remains the source
of truth for documents, versions, reports, and artifacts.

The backend and MCP server run in their own environment. The existing
Langflow environment remains separate and communicates with Omifi over HTTP.

## 2. Goals

- Accept `.tex` files or plain text and a job description.
- Create immutable full-source LaTeX versions.
- Validate and compile source into PDF safely.
- Store version history and generated artifacts.
- Produce ATS, requirements, and quality scores with evidence.
- Expose file operations through MCP without installing Langflow in the
  backend environment.

## 3. Out of scope

- Generating a resume from scratch.
- Separate cover-letter or research flows.
- User login, multi-tenant identity, and per-user permissions.
- Cloud or Kubernetes deployment.
- Databases other than SQLite.
- Replacing the existing Langflow environment.

## 4. Actors and use cases

| Actor | Responsibility |
| --- | --- |
| User | Submits a resume, job description, editing instructions, and evaluation requests. |
| IBM Bob Shell | Provides the chat interface and runs project MCP servers. |
| Langflow Editing Agent | Orchestrates edits and selects LaTeX tools. |
| Langflow Judges Agent | Evaluates a resume and optionally searches the web. |
| Backend Server | Owns documents, versions, reports, artifacts, and compiler results. |
| Backend MCP Server | Provides file operations to Bob Shell and Langflow. |

Primary flow:

1. The user uploads a LaTeX resume.
2. The user supplies a job description and edit request.
3. The editing agent asks the backend to validate or store complete source.
4. The backend creates a version, validates it, compiles it, and returns
   metadata and artifact URLs.
5. The user requests an evaluation.
6. The judges agent gathers context, optionally uses Tavily, and saves a
   report.
7. The user lists or downloads source files and PDF artifacts.

## 5. Target architecture

```text
User / LaTeX file
        │
        ▼
IBM Bob Shell
        ├──────────────────────────────┐
        ▼                              ▼
Langflow MCP tools               Backend MCP server
        │                              │
        ├───────────────┐              ├── Upload files
        ▼               ▼              ├── List files
  Editing Flow      Judges Flow        └── Download files
        │               │                       │
        ▼               ▼                       ▼
 Editing Agent     Judges Agent          Backend HTTP API
        │               │                       │
        ▼               ▼                       ▼
Editing Component  Judges Component   SQLite + local storage
        │               │
        ├── Check, edit, and write LaTeX
        └── Optional Tavily web search

Langflow components ── HTTP JSON + X-API-Key ──► Backend
```

### Environment boundaries

**Backend and MCP environment**

- FastAPI and Uvicorn.
- SQLAlchemy, aiosqlite, and SQLite.
- FastMCP and the internal HTTP client.
- LaTeX compiler and artifact filesystem.
- No Langflow imports or Langflow installation.

**Existing Langflow environment**

- Langflow runtime and saved flows.
- Custom components.
- Tavily integration.
- HTTP-only access to the backend.

### Default local processes

| Process | Default | Environment |
| --- | --- | --- |
| Backend API | `8000` or configured port | Backend and MCP |
| Langflow | `7860` | Existing Langflow |
| MCP server | stdio | Backend and MCP |

All URLs and ports must be configurable through `.env`.

## 6. Functional requirements

### FR-1: File ingestion

- Accept `.tex` and plain-text files treated as LaTeX source.
- Return a `file_id`, filename, media type, size, checksum, and relative
  location.
- Keep uploaded files below the configured workspace root.
- Never let user-provided paths choose a filesystem location.
- Enforce a configurable upload-size limit.

### FR-2: Documents and versions

- Each document has one or more immutable versions.
- Each version stores complete source, checksum, base version, change summary,
  and compile status.
- Creating a new version never changes an earlier version.
- Require `base_version_id` for conflict detection.
- Return HTTP `409` without creating a version when a conflict is detected.

### FR-3: Editing Flow

The Editing Flow accepts a document or file reference, a job description, an
editing instruction, and an optional version ID.

The editing agent can use:

- **Check LaTeX** for source validation.
- **Edit LaTeX** for a complete replacement on an existing document.
- **Write LaTeX** to create a document and version from complete source.

The agent may determine the new source, but the backend owns validation,
versioning, compilation, artifact creation, and error handling.

### FR-4: LaTeX validation and compilation

- Use an isolated artifact directory for each document and version.
- Disable `--shell-escape`.
- Enforce compiler timeouts, bounded logs, and artifact-size limits.
- Create PDF metadata only after a successful compilation.
- Preserve the source and return structured errors when compilation fails.
- Return a clear warning when the configured compiler is unavailable.

### FR-5: Judges Flow

The Judges Flow accepts a document, version, and job description. It may use
Tavily for relevant external context.

Every report must include:

- ATS or keyword-coverage score.
- Job-requirement matching score.
- Structure and quality score.
- Evidence from the resume and job description.
- Gaps, risks, recommendations, and warnings.

Tavily credentials remain in Langflow. The backend does not require the Tavily
SDK or credential.

### FR-6: MCP file operations

The backend MCP server provides:

- `upload_file`
- `list_files`
- `download_file`

The MCP server forwards file operations to the backend and does not maintain
separate business state.

### FR-7: Artifact access

- Preview and download artifacts through opaque artifact IDs.
- Build URLs from `CV_PUBLIC_BASE_URL` or equivalent configuration.
- Never accept arbitrary filesystem paths at artifact endpoints.
- Store artifact status, checksum, MIME type, size, and creation time.

## 7. HTTP API contract

Internal endpoints require:

```http
X-API-Key: <shared-internal-api-key>
Content-Type: application/json
```

The health endpoint may be public for local monitoring.

### File API

`POST /v1/files` uploads a file and returns:

```json
{
  "file_id": "file_01...",
  "filename": "resume.tex",
  "media_type": "text/x-tex",
  "size_bytes": 1234,
  "sha256": "..."
}
```

`GET /v1/files` lists files. `GET /v1/files/{file_id}/download` downloads a
file. Both endpoints must use opaque IDs and reject path traversal.

### Document API

- `POST /v1/documents` creates a document and initial version.
- `GET /v1/documents/{document_id}` returns the document and version history.
- `POST /v1/documents/{document_id}/versions` creates a new full-source version.
- `POST /v1/documents/{document_id}/check-latex` validates a version.
- `POST /v1/documents/{document_id}/render` renders a PDF artifact.
- `POST /v1/documents/{document_id}/reports` stores a judge report.

### Error envelope

All errors use:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {}
  }
}
```

## 8. Configuration

Keep secrets in `.env` and never commit them. Important settings include:

- `CV_INTERNAL_API_KEY`
- `CV_PUBLIC_BASE_URL`
- `CV_LATEX_ENGINE`
- `CV_LATEX_TIMEOUT_SECONDS`
- `CV_MAX_UPLOAD_BYTES`
- `CV_LANGFLOW_URL`
- `CV_LANGFLOW_API_KEY`
- `CV_LANGFLOW_PROJECT_ID`

Do not hardcode flow IDs, API keys, or filesystem paths.

## 9. Reliability and security

- Normalize UTF-8 BOMs, Windows line endings, and Markdown LaTeX fences before
  validation and compilation.
- Preserve immutable source versions after compiler failures.
- Use short database transactions and a busy timeout for SQLite.
- Keep large binary artifacts out of SQLite.
- Clean up artifacts only when they are not referenced.
- Return warnings instead of silently hiding unavailable external tools.
- Test custom components against the installed Langflow version.

## 10. Acceptance checklist

The MVP is complete when:

- Backend tests pass without Langflow installed.
- Custom components run in the existing Langflow environment.
- File upload, listing, and download work through MCP.
- Creating and editing a document preserves immutable versions.
- Invalid LaTeX returns structured validation errors.
- XeLaTeX compilation produces a downloadable PDF when available.
- Missing compilers produce an actionable warning.
- Judges reports persist scores, evidence, gaps, recommendations, and warnings.
- The complete flow succeeds:

```text
Upload resume → Create document → Edit full source
→ Validate and compile → Store version and PDF
→ Run judges → Store report → Download artifact
```
