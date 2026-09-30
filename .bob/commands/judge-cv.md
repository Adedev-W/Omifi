# Judge CV

Follow `.bob/skills/judge-cv/SKILL.md` and `langflow_flows/judges_flow.md`. Require non-empty backend `document_id`, `version_id`, and the user's `job_description`, then call native MCP `judges_flow` with `{input_value: JSON.stringify(payload)}` containing those fields and optional outer `session_id`.

If only an uploaded `.tex` file exists, create it through `editing_flow` first and preserve its returned document/version IDs. Never invent IDs or use a `file_...` ID as a `doc_...` ID. The Judges Agent uses `get_context`, optional `search_web`, and `save_report`. Persist `{version_id, scores: {ats, requirements, quality}, rubric_version, evidence, gaps, recommendations, warnings}` with integer scores from 0–100. Search failures become warnings and do not prevent saving. Show the saved report ID, selected version, scores, findings, warnings, and citations.
