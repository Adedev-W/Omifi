---
name: judge-cv
description: '# Judge CV'
metadata:
  user-invocable: true
  disable-model-invocation: true
---

# Judge CV

Use the Judges Flow contract and escaped JSON example in `langflow_flows/judges_flow.md`.

1. Require non-empty `document_id`, `version_id`, and the user's `job_description`. Use IDs returned by the backend. If only an uploaded `.tex` file exists, first call `editing_flow` with `operation: "create"` and its exact `file_id`, then retain the returned document/version IDs. Never use a `file_...` ID as a `doc_...` ID or invent IDs.
2. Call native MCP `judges_flow` with `{input_value: JSON.stringify(payload)}` containing those three fields. Optional `session_id` belongs beside `input_value`.
3. The Judges Agent uses `get_context`, optional `search_web`, and `save_report`. Confirm the selected version belongs to the document and evaluate that source against the supplied job description.
4. Persist a report containing `version_id`, `scores: {ats, requirements, quality}` with integer values from 0–100, `rubric_version`, `evidence`, `gaps`, `recommendations`, and `warnings`. Keep scores nested under `scores`. Missing search credentials or search failures become warnings and do not prevent saving.
5. Preserve the returned report/version IDs and summarize the scores, supporting evidence, gaps, recommendations, warnings, and citations. Claim persistence only after `save_report` succeeds.

If file inspection is needed, use `list_files` and `download_file` and decode `content_base64`; uploads use `upload_file`. The file gateway has no `read_file`. For stale saved nodes, follow the sync instructions in `README.md`; restarting Langflow alone does not update them.
