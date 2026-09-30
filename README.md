<p align="center">
  <img src="docs/assets/omifi-logo.svg" alt="Omifi logo" width="160">
</p>

<h1 align="center">Omifi</h1>

<p align="center">
  A deterministic backend for LaTeX resumes, cover letters, versioning, PDF
  generation, and resume evaluation.
</p>

## Overview

Omifi is a resume and cover-letter workflow for people who need to revise
LaTeX documents against a job description without losing previous versions.
It accepts LaTeX source, validates and compiles it into PDF artifacts, and
stores structured evaluation reports. Langflow runs in its existing
environment and communicates with the Omifi backend over HTTP.

![Omifi system design](docs/assets/omifi-system-design.drawio.svg)

## What Omifi is and what it solves

### Problem statement

Before Omifi, a resume-editing request typically involved several disconnected
steps: a person edited a `.tex` file by hand, copied content into an AI
workflow, compiled the document locally, and kept track of PDF files and
earlier drafts manually. That process makes it easy to lose a working version,
overwrite good content, miss a LaTeX error, or submit a resume that does not
match the job description. The people affected are job seekers, career
coaches, and teams that prepare multiple tailored applications.

### The product

Omifi provides one controlled workflow for uploading a resume, creating an
immutable document version, editing the complete source, checking LaTeX,
rendering a PDF, and saving an evaluation report. The backend owns document
state and file safety; the AI workflow only requests explicit operations.

### How the solution works

1. A user gives Bob a resume file, job description, or editing request.
2. Bob sends the request to the appropriate Langflow MCP tool.
3. Langflow uses the editing or judging component to turn the request into a
   structured operation.
4. The Omifi backend validates the payload, stores the source as a new version,
   compiles it when requested, and returns IDs, status, warnings, and artifact
   URLs.
5. The judging flow can compare the resume with the job description and save
   scores, evidence, gaps, recommendations, and warnings.

### Main benefits

- **No lost drafts:** every edit creates an immutable version.
- **A reliable PDF result:** LaTeX validation and compilation happen through
  one backend contract.
- **Traceable evaluations:** scores and supporting evidence are stored with the
  document version they describe.
- **Clear tool boundaries:** Bob handles the conversation, Langflow handles
  orchestration, and Omifi handles state and file operations.
- **Safer automation:** source, IDs, compiler status, and errors are explicit
  instead of being hidden in a chat response.

![Omifi workflow overview](docs/assets/omifi-workflow-overview.png)

The workflow image shows the product path from a user's source document to an
edited version, a compiled artifact, and an evaluation report. It is the
shortest view of what Omifi does for an application document.

## Quick start

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

The API is available at `http://localhost:8080`. The health endpoint does not
require an API key. If `CV_INTERNAL_API_KEY` is configured, send it in the
`X-API-Key` header for internal endpoints.

PDF generation requires the executable configured by `CV_LATEX_ENGINE`
(`xelatex` by default). If the compiler is unavailable, Omifi still stores the
source and version with an `unavailable` compile status.

## Docker

The Docker image installs the Python dependencies and XeLaTeX:

```bash
cp .env.example .env
docker compose up --build
```

SQLite data and generated artifacts are stored in the `cv-data` Docker volume.
Stop the service with `docker compose down`. Use `docker compose down -v` only
when you also want to remove the database and artifacts.

## Langflow and MCP

### What Langflow does

Langflow hosts the editing and judging flows. The editing flow chooses whether
to retrieve context, check LaTeX, create a document, or save a complete
replacement source. The judging flow retrieves the selected version, can
search for relevant external context, and prepares a structured report.

![Langflow editing and judging flows](docs/assets/langflow-editing-flow.png)

![Langflow judging flow](docs/assets/langflow-judges-flow.png)

These flow images show the orchestration layer. Langflow does not own the
canonical document or artifact; it calls the backend tools and passes the
returned IDs and results to the next step.

### What Bob does

Bob is the user-facing entry point. It receives the user's natural-language
request, keeps the conversation context, and calls the native MCP tools
`editing_flow` or `judges_flow`. Bob also uses the file gateway when a user
uploads or downloads a file.

![Bob and the MCP file gateway](docs/assets/mcp-file-gateway.png)

The file-gateway image represents Bob's file boundary: upload, list, and
download operations are forwarded to Omifi instead of being stored as
business state inside Bob.

### How data moves between Bob, Langflow, and Omifi

Bob sends a JSON payload to Langflow through the native MCP connection.
Langflow calls Omifi's HTTP API with the selected operation and receives
structured JSON containing document IDs, version IDs, compile status, warnings,
and artifact metadata. Bob then presents the result to the user and reuses the
returned IDs for later edits, checks, renders, or evaluations. No component
should invent IDs or replace a `doc_...` ID with a file ID.

![Omifi runtime integration](docs/assets/omifi-runtime.png)

The runtime image summarizes the deployed boundaries: Bob and Langflow are
clients of the backend, while SQLite and local storage remain behind the Omifi
API.

### Final output

The integration ends with a usable application package: a persisted document
version, a compile result, an optional downloadable PDF artifact, and a judge
report tied to that exact version. If compilation or web search is unavailable,
the response still identifies the limitation through an explicit status or
warning.

Run the existing Langflow environment with the Omifi components:

```bash
LANGFLOW_COMPONENTS_PATH="$PWD/langflow_components/cv_automation" \
  .venv-langflow/bin/langflow run
```

The editing component provides `get_context`, `check_latex`, `edit_latex`, and
`write_latex`. The judges component provides `get_context`, `search_web`, and
`save_report`. Tavily credentials must remain in the Langflow environment.

Run the Bob Shell file gateway over stdio:

```bash
uv run python -m app.mcp_server
```

The gateway exposes `upload_file`, `list_files`, and `download_file`. Upload
content uses `content_base64`; download content must be decoded from
`content_base64`. There is no `read_file` tool.

The native Langflow MCP tools are `editing_flow` and `judges_flow`. Both accept
`{input_value: JSON.stringify(payload)}`. The complete contracts and examples
are available in [Editing Flow](langflow_flows/editing_flow.md) and
[Judges Flow](langflow_flows/judges_flow.md).

When creating a document, submit exactly one of `file_id` or complete
`source_latex`. For a cover letter, use `document_name: "cover-letter.tex"`.
Always preserve the returned `document_id` and `latest_version_id`; never
invent IDs or convert a `file_...` ID into a `doc_...` ID.

After changing components or flow contracts, synchronize saved flows:

```bash
uv run python scripts/sync_langflow.py --apply
```

Use `CV_LANGFLOW_URL`, `CV_LANGFLOW_API_KEY`, and `CV_LANGFLOW_PROJECT_ID` from
your local environment. Reconnect Bob's native MCP connection after syncing.

## API

- `POST /v1/files`
- `GET /v1/files` and `GET /v1/files/{file_id}/download`
- `POST /v1/documents` and `GET /v1/documents/{document_id}`
- `POST /v1/documents/{document_id}/versions`
- `POST /v1/documents/{document_id}/check-latex`
- `POST /v1/documents/{document_id}/render`
- `POST /v1/documents/{document_id}/reports`
- `GET /v1/artifacts/{artifact_id}/preview`
- `GET /v1/artifacts/{artifact_id}/download`

All errors use the envelope
`{"error": {"code": "...", "message": "...", "details": {}}}`.

## Documentation and assets

- [System design](docs/omifi-system-design-prd.md)
- [End-to-end test guide](docs/omifi-e2e.md)
- [Editing flow definition](docs/editing-flow.json)
- [Judges flow definition](docs/judges-flow.json)
- [Documentation assets](docs/assets/)

## Validation

```bash
uv run pytest -q
uv run python -m compileall -q app langflow_components langflow_flows tests
uv lock --check
```
