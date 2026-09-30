---
name: cv-editor
description: Use Bob Shell with Langflow workflows and the MCP file gateway to manage CVs and cover letters.
---

# CV Editor Skill

Use this skill when the user asks to create, tailor, judge, improve, or edit a CV or cover letter.

## Workflow

1. Collect the supplied profile facts, requested changes, and job description when needed. Reuse known document/version IDs and existing project configuration.
2. Use the file gateway's `upload_file`, `list_files`, and `download_file`. Upload content as `content_base64`; inspect downloaded content by decoding `content_base64`.
3. For an uploaded `.tex` file, call `editing_flow` with payload `operation: "create"` and the exact returned `file_id`. For a new CV or cover letter, compose complete LaTeX from supplied facts first, then create with `source_latex`. Pass exactly one source field. `document_name` defaults to `cv.tex`; use `cover-letter.tex` for a cover letter.
4. Preserve the returned `document_id` and `latest_version_id`. Edit through `editing_flow` with `operation: "edit"`, a known `document_id`, and `instruction` or complete replacement `source_latex`; `base_version_id` is optional and, when supplied, must be a known current version. Check with `operation: "check"`, `document_id`, and `version_id`.
5. Judge through `judges_flow` with non-empty `document_id`, `version_id`, and the user's `job_description`. The agent retrieves context and persists a report using `save_report`.
6. Present the explanation, saved score/report when requested, citations, LaTeX source, and available PDF preview/download URLs.

Both native Langflow MCP tools accept `{input_value: JSON.stringify(payload)}` with optional `session_id` beside `input_value`. Follow `langflow_flows/editing_flow.md` and `langflow_flows/judges_flow.md` for exact escaped JSON examples, component tools, and report fields.

## Rules

- Do not invent employment history, metrics, skills, education, or other personal facts.
- Use only returned or retrieved IDs. Never pass a `file_...` ID as a `doc_...` ID or derive one by changing the prefix. File upload alone does not create a document.
- Preserve user-provided LaTeX intent unless the user requests a structural change.
- Use job/company research only to improve targeting; preserve citations in the result.
- Explain compile failures clearly and provide the LaTeX source even when PDF generation fails.
- The file gateway only exposes `upload_file`, `list_files`, and `download_file`; it has no `read_file`. The separate native Langflow MCP connection exposes `editing_flow` and `judges_flow`.
- Generate source in Bob before calling `editing_flow`; do not call a nonexistent CV or cover-letter generation flow.
- Judges reports include `version_id`, nested `scores` with `ats`, `requirements`, and `quality`, plus `rubric_version`, `evidence`, `gaps`, `recommendations`, and `warnings`.
- Never execute arbitrary shell commands to modify CV data.

## Saved-flow repair

Restarting Langflow does not update saved component nodes. Follow the repair instructions in `README.md`: use `uv run python scripts/sync_langflow.py --apply` with `CV_LANGFLOW_URL`, `CV_LANGFLOW_API_KEY`, and `CV_LANGFLOW_PROJECT_ID` from `.env` or existing `.bob/mcp.json` configuration, then reconnect Bob's Langflow MCP connection. Keep credentials out of prompts and documentation.
