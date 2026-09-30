# Generate Cover Letter

Follow `.bob/skills/generate-cover-letter/SKILL.md`. Gather the user's experience, target role/company, and job description, then compose complete cover-letter LaTeX in Bob. Use the known file gateway tools `upload_file`, `list_files`, and `download_file` when needed; decode downloaded `content_base64` to inspect facts.

Call native MCP `editing_flow` with `{input_value: JSON.stringify(payload)}` and optional outer `session_id`. The payload is `operation: "create"`, `document_name: "cover-letter.tex"`, and complete `source_latex`; omit `file_id`. See `langflow_flows/editing_flow.md` for exact escaped JSON. There is no separate cover-letter generation flow. Never invent candidate facts or IDs, or use a file ID as a document ID. Preserve returned document/version IDs and show source, compile status, warnings, and available artifact URLs.
