# Editing Flow Contract

## Native MCP input

Bob calls the native Langflow MCP tool `editing_flow` with `{input_value: JSON.stringify(payload)}`. `input_value` must be a JSON string containing the payload below. An optional `session_id` belongs beside `input_value` in the outer arguments; reuse a known session when needed, or omit it.

| Payload `operation` | Required payload fields | Optional payload fields |
| --- | --- | --- |
| `create` | Exactly one non-empty `file_id` or complete `source_latex` | `document_name` (default `cv.tex`), `change_summary` |
| `edit` | Non-empty `document_id` and at least one non-empty `instruction` or complete replacement `source_latex` | `base_version_id`, `job_description`, `change_summary` |
| `check` | Non-empty `document_id` and `version_id` | None |

For `create`, omit the unused source field. A `file_id` must refer to uploaded LaTeX; profile notes or a job description must first be used to compose complete LaTeX from the supplied facts. Bob can generate CV or cover-letter source and then submit `operation: "create"`; there is no separate generation flow.

## Exact JSON examples

These are the outer MCP arguments for `editing_flow`. Angle-bracket values are placeholders: replace them only with actual returned IDs before calling a tool. The source example demonstrates escaping; replace its body with the user's supplied content.

Create from an uploaded `.tex` file:

```json
{
  "input_value": "{\"operation\":\"create\",\"document_name\":\"cv.tex\",\"file_id\":\"<returned-file-id>\"}"
}
```

Create from complete source, with JSON escaping at both levels:

```json
{
  "input_value": "{\"operation\":\"create\",\"document_name\":\"cv.tex\",\"source_latex\":\"\\\\documentclass{article}\\n\\\\begin{document}\\nUser-supplied CV content.\\n\\\\end{document}\\n\"}"
}
```

Edit by instruction, optionally supplying the last known version as the base:

```json
{
  "input_value": "{\"operation\":\"edit\",\"document_id\":\"<returned-document-id>\",\"base_version_id\":\"<returned-version-id>\",\"instruction\":\"Shorten the summary while preserving all supplied facts.\"}"
}
```

Check a selected version:

```json
{
  "input_value": "{\"operation\":\"check\",\"document_id\":\"<returned-document-id>\",\"version_id\":\"<returned-version-id>\"}"
}
```

## Agent tools and ID handling

Load the component from `langflow_components/cv_automation/` with Langflow Tool Mode enabled and connect its Toolset output to the Editing Agent Tools input. The agent's tool names are:

- `get_context`: retrieve the document and source for a known `document_id`, selecting a known `version_id` when provided. Resolve the current version here when `base_version_id` is omitted from an edit payload.
- `check_latex`: validate a known `document_id` and `version_id`.
- `edit_latex`: persist complete replacement `source_latex` for a known `document_id` and resolved `base_version_id`, with `change_summary` and optional `job_description`. For an instruction, retrieve context and produce the complete updated source before calling this tool.
- `write_latex`: create a document with `document_name` (default `cv.tex`), `change_summary`, and exactly one of `file_id` or complete `source_latex`. The adapter maps `document_name` to the backend request field `name`.

The flow payload uses `create`, `edit`, or `check`; these are distinct from the component tool names. After creation or editing, preserve the returned `document_id`, `latest_version_id` and version/artifact metadata. Use that returned version ID for `version_id` or the next edit's `base_version_id` as appropriate.

Never use a `file_...` ID as a `doc_...` ID, change an ID's prefix, invent IDs, or call document tools with empty IDs. File upload alone does not create a document. Use the known file gateway tools `upload_file`, `list_files`, and `download_file`; inspect downloaded content by decoding `content_base64`. The gateway has no `read_file` tool.

Preserve supplied facts and LaTeX intent. Explain compile warnings or conflicts and return available source and artifact URLs. If a base version is stale, retrieve fresh context and reconcile the requested edit before submitting again.

## Updating saved flows

Restarting Langflow loads component files but does not update code or tool definitions embedded in saved flow nodes. Apply the approved repair with `uv run python scripts/sync_langflow.py --apply`, using `CV_LANGFLOW_URL`, `CV_LANGFLOW_API_KEY`, and `CV_LANGFLOW_PROJECT_ID` from `.env` or the existing Langflow configuration in `.bob/mcp.json`. Reconnect Bob's Langflow MCP connection to refresh tool discovery. See the [README repair instructions](../README.md#langflow-and-mcp).
