---
name: edit-cv
description: '# Edit CV'
metadata:
  user-invocable: true
  disable-model-invocation: true
---

# Edit CV

Use the Editing Flow contract and escaped JSON examples in `langflow_flows/editing_flow.md`. Call the native MCP tool `editing_flow` with `{input_value: JSON.stringify(payload)}` and optional `session_id` beside `input_value`.

Agent instructions:

- For a new document from an uploaded `.tex` file, send payload `operation: "create"` with the exact returned `file_id`. Omit `source_latex`.
- If creating from text, compose complete non-empty LaTeX from supplied facts, then send `operation: "create"` with `source_latex`. Omit `file_id`. `document_name` defaults to `cv.tex`.
- After creation, keep the returned `document_id` and `latest_version_id`.
- For edits, send `operation: "edit"`, a known `document_id`, and non-empty `instruction` or complete replacement `source_latex`. Include `base_version_id` when known; otherwise the agent resolves the current version with `get_context`.
- For validation, send `operation: "check"` with known `document_id` and `version_id`.
- The Editing Agent uses `get_context`, `check_latex`, `edit_latex`, and `write_latex`. It retrieves context before turning instructions into complete replacement source. `write_latex` accepts `document_name`, mapped to backend `name`, and supports `file_id`.
- Every replacement `source_latex` must be the complete raw `.tex` source, not a
  diff or fragment. Preserve the existing preamble unless the edit requires it,
  keep `\documentclass`, `\begin{document}`, and `\end{document}`, and ensure
  XeLaTeX compatibility.
- Do not wrap replacement source in Markdown fences or explanatory text. Escape
  user-provided LaTeX special characters, keep URLs in `\url{...}`, and do not
  add shell-escape, `\write18`, external commands, absolute paths, or
  unsupplied file references.
- After producing a replacement, call `check_latex` or rely on the edit result's
  compile status before reporting success. If compilation fails, inspect the
  returned error and correct the complete source rather than submitting a
  fragment.
- Never invent IDs, use a `file_...` ID as a `doc_...` ID, call an endpoint with an empty ID, or retry an edit using a stale base version. Retrieve fresh context and reconcile a conflict first.
- File access uses `upload_file`, `list_files`, and `download_file`; decode downloaded `content_base64` when inspecting source. There is no `read_file` tool or separate generation flow.

Show the returned document/version IDs, complete source, compile status, warnings, and available artifact URLs. For stale saved nodes, follow the sync instructions in `README.md`; restarting Langflow alone does not update them.
