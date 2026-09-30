---
name: generate-cover-letter
description: '# Generate Cover Letter'
metadata:
  user-invocable: true
  disable-model-invocation: true
---

# Generate Cover Letter

Compose a complete cover-letter LaTeX source in Bob using the user's supplied experience, target role/company, and job description. Ask for missing facts needed for the letter; do not invent achievements, relationships, or employer details.

1. If facts are in uploaded files, use `list_files` and `download_file` with returned file IDs, then decode `content_base64`. The file gateway also exposes `upload_file`; it has no `read_file` tool.
2. Generate the complete non-empty LaTeX source, including the document preamble and body, grounded in the supplied facts.
3. Call native MCP `editing_flow` with `{input_value: JSON.stringify(payload)}`. Use payload `operation: "create"`, `document_name: "cover-letter.tex"`, and the complete `source_latex`; omit `file_id`. Optional `session_id` belongs beside `input_value`.
4. Preserve the returned `document_id` and `latest_version_id`, then show the source, compile status, warnings, and available PDF preview/download URLs.

## LaTeX source requirements

Write `source_latex` as the complete raw contents of a `.tex` file. Do not return
explanations, JSON, HTML, or Markdown fences around it. The source must:

- start with a document class, normally `\documentclass[11pt,a4paper]{article}`;
- include `\begin{document}` and `\end{document}`;
- use UTF-8 text and be compatible with XeLaTeX; use `fontspec` only when needed;
- escape LaTeX special characters in user data (`&`, `%`, `$`, `#`, `_`, `{`, `}`,
  `~`, `^`, and `\`) instead of inserting them unescaped;
- keep URLs in `\url{...}` and avoid shell-escape, `\write18`, external commands,
  absolute paths, or references to files that were not supplied;
- keep the preamble conservative and avoid packages or fonts that are not
  necessary for the requested document.

Before calling `editing_flow`, verify that the source is complete and that all
facts are grounded in the user's input. The API removes accidental BOM,
line-ending differences, and an outer ` ```latex ` fence, but do not rely on
that cleanup: send the raw `.tex` source directly.

Follow `langflow_flows/editing_flow.md` for the exact escaped JSON contract. Creation accepts exactly one of `file_id` or `source_latex`; an existing complete `.tex` letter may instead be uploaded and created using its returned `file_id`. Never use a file ID as a document ID or invent IDs. There is no separate cover-letter generation flow; Bob writes the source and the Editing Agent persists it through `write_latex`.
