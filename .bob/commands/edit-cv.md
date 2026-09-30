# Edit CV

Follow `.bob/skills/edit-cv/SKILL.md` and `langflow_flows/editing_flow.md`. Call native MCP `editing_flow` with `{input_value: JSON.stringify(payload)}` and optional outer `session_id`.

- Create: payload `operation: "create"`, optional `document_name` (default `cv.tex`), and exactly one of an uploaded `.tex` file's returned `file_id` or complete `source_latex` composed from supplied facts.
- Edit: payload `operation: "edit"`, known `document_id`, and non-empty `instruction` or complete replacement `source_latex`, with optional known `base_version_id`.
- Check: payload `operation: "check"`, known `document_id`, and `version_id`.

Keep returned document/version IDs; never invent IDs, use a `file_...` ID as a `doc_...` ID, or retry with a stale base. The agent uses `get_context`, `check_latex`, `edit_latex`, and `write_latex`; `document_name` maps to backend `name`. File access uses `upload_file`, `list_files`, and `download_file`, with downloaded `content_base64` decoded for inspection. Show the source, new version, compile status, warnings, and available artifact URLs.
