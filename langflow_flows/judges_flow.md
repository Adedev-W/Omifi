# Judges Flow Contract

## Native MCP input

Bob calls the native Langflow MCP tool `judges_flow` with `{input_value: JSON.stringify(payload)}`. `input_value` is a JSON string whose payload contains non-empty `document_id`, `version_id`, and `job_description`. An optional `session_id` belongs beside `input_value` in the outer arguments; reuse a known session when needed, or omit it.

Use actual backend document/version IDs from creation, editing, or retrieved context. Never use a `file_...` ID as a `doc_...` ID, change prefixes, invent IDs, or submit empty IDs. If only an uploaded `.tex` file is available, first call `editing_flow` with `operation: "create"` and its exact `file_id`, then retain the returned document/version IDs. Obtain the user's job description before judging.

Exact outer MCP arguments for `judges_flow` (replace placeholders with returned IDs and the user's full job description before calling):

```json
{
  "input_value": "{\"document_id\":\"<returned-document-id>\",\"version_id\":\"<returned-version-id>\",\"job_description\":\"<user-supplied-job-description>\"}"
}
```

## Agent tools and report

Load the component from `langflow_components/cv_automation/` with Tool Mode enabled and connect its Toolset output to the Judges Agent Tools input. Its tool names are:

- `get_context`: retrieve the known document and selected version; confirm the version belongs to that document and evaluate its source against the supplied job description.
- `search_web`: optionally gather relevant job/company evidence and retain citations. External information must not be used to invent candidate facts.
- `save_report`: persist the report for the same `document_id`, passing the report as `report_json` with the selected `version_id` inside it.

The report has this shape. Scores below are illustrative; calculate integer scores from 0–100 for the actual evaluation and fill the arrays with supporting findings.

```json
{
  "version_id": "<returned-version-id>",
  "scores": {
    "ats": 80,
    "requirements": 75,
    "quality": 90
  },
  "rubric_version": "mvp-v1",
  "evidence": [],
  "gaps": [],
  "recommendations": [],
  "warnings": []
}
```

Keep scores nested under `scores`. Persist through `save_report` before claiming the report was saved, and preserve the returned report/version identifiers. Missing Tavily credentials or search failures become entries in `warnings` and do not prevent report persistence. Summarize ATS, requirements, quality, evidence, gaps, recommendations, warnings, and available citations for the user.

## Updating saved flows

Restarting Langflow does not update code or tool definitions embedded in saved nodes. Apply the approved repair with `uv run python scripts/sync_langflow.py --apply`, using `CV_LANGFLOW_URL`, `CV_LANGFLOW_API_KEY`, and `CV_LANGFLOW_PROJECT_ID` from `.env` or the existing Langflow configuration in `.bob/mcp.json`. Reconnect Bob's Langflow MCP connection to refresh tool discovery. See the [README repair instructions](../README.md#langflow-and-mcp).
