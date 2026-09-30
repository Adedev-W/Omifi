"""Langflow 1.12-compatible CV editing component."""

import json
import os
from typing import Any

import httpx
from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output, StrInput


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for attribute in ("text", "content", "value"):
        candidate = getattr(value, attribute, None)
        if isinstance(candidate, str):
            return candidate
    return str(value)


class _BackendClient:
    """Self-contained HTTP adapter for Langflow's isolated component loader."""

    def __init__(self) -> None:
        self.base_url = os.getenv("LATEX_BACKEND_URL", "http://localhost:8080").rstrip("/")
        self.api_key = os.getenv("LATEX_BACKEND_API_KEY", "")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        with httpx.Client(timeout=60) as client:
            response = client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        payload = response.json()
        if not response.is_success:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            details = error.get("details", {})
            suffix = f" details={details}" if details else ""
            raise RuntimeError(f"{error.get('message', response.text)}{suffix}")
        return payload

    def check_latex(self, document_id: str, version_id: str) -> Any:
        return self._request("POST", f"/v1/documents/{document_id}/check-latex", json={"version_id": version_id})

    def edit_latex(
        self,
        document_id: str,
        base_version_id: str,
        source_latex: str,
        change_summary: str,
        job_description: str = "",
    ) -> Any:
        return self._request(
            "POST",
            f"/v1/documents/{document_id}/versions",
            json={
                "base_version_id": base_version_id,
                "source_latex": source_latex,
                "change_summary": change_summary,
                "job_description": job_description or None,
            },
        )

    def write_latex(self, name: str, source_latex: str, change_summary: str, file_id: str = "") -> Any:
        if bool(file_id.strip()) == bool(source_latex.strip()):
            raise ValueError("Exactly one of file_id or source_latex is required")
        payload: dict[str, Any] = {"name": name, "change_summary": change_summary}
        if file_id.strip():
            payload["file_id"] = file_id.strip()
        else:
            payload["source_latex"] = source_latex
        return self._request(
            "POST",
            "/v1/documents",
            json=payload,
        )


class EditingComponent(Component):
    display_name = "CV Editing Backend Tools"
    description = (
        "CV document tools. Use write_latex exactly once to create a document "
        "from either a non-empty full source_latex or a file_id returned by the upload tool. "
        "Use edit_latex only with the returned document_id and current base_version_id. "
        "Use check_latex only with non-empty document_id and version_id; never invent or omit IDs."
    )
    name = "EditingComponent"

    inputs = [
        StrInput(name="operation", display_name="Operation", value="check_latex", tool_mode=True),
        StrInput(name="document_id", display_name="Document ID", value="", tool_mode=True, info="Required for check_latex and edit_latex. Use the exact returned ID."),
        StrInput(name="version_id", display_name="Version ID", value="", tool_mode=True, info="Required for check_latex and edit_latex. Use the exact returned version ID."),
        StrInput(name="base_version_id", display_name="Base Version ID", value="", tool_mode=True, info="Required for edit_latex. Use the latest returned version ID."),
        StrInput(name="name", display_name="Document Name", value="cv.tex", tool_mode=True, info="Filename such as cv.tex; do not use the component name."),
        StrInput(name="file_id", display_name="Uploaded File ID", value="", tool_mode=True, info="For write_latex, use this OR source_latex, never both."),
        MessageTextInput(name="source_latex", display_name="Full Source LaTeX", value="", tool_mode=True, info="For write_latex/edit_latex, send the complete non-empty LaTeX source."),
        MessageTextInput(name="job_description", display_name="Job Description", value="", tool_mode=True),
        StrInput(name="change_summary", display_name="Change Summary", value="", tool_mode=True),
    ]
    outputs = [
        Output(name="check_latex_tool", display_name="Check LaTeX", method="check_latex", group_outputs=True),
        Output(name="edit_latex_tool", display_name="Edit LaTeX", method="edit_latex", group_outputs=True),
        Output(name="write_latex_tool", display_name="Write LaTeX", method="write_latex", group_outputs=True),
        Output(name="result", display_name="Result", method="run", group_outputs=True),
    ]

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.client = _BackendClient()

    def check_latex(self, document_id: str | None = None, version_id: str | None = None) -> dict[str, Any]:
        document_id = document_id or getattr(self, "document_id", "")
        version_id = version_id or getattr(self, "version_id", "")
        if not document_id.strip() or not version_id.strip():
            raise ValueError("check_latex requires non-empty document_id and version_id")
        return self.client.check_latex(document_id, version_id)

    def edit_latex(
        self,
        document_id: str | None = None,
        base_version_id: str | None = None,
        source_latex: str | None = None,
        change_summary: str | None = None,
        job_description: str | None = None,
    ) -> dict[str, Any]:
        document_id = document_id or getattr(self, "document_id", "")
        base_version_id = base_version_id or getattr(self, "base_version_id", "")
        source_latex = source_latex if source_latex is not None else getattr(self, "source_latex", "")
        change_summary = change_summary if change_summary is not None else getattr(self, "change_summary", "")
        job_description = job_description if job_description is not None else getattr(self, "job_description", "")
        if not document_id.strip() or not base_version_id.strip() or not source_latex.strip():
            raise ValueError("edit_latex requires non-empty document_id, base_version_id, and source_latex")
        return self.client.edit_latex(document_id, base_version_id, source_latex, change_summary, job_description)

    def write_latex(
        self,
        name: str | None = None,
        source_latex: str | None = None,
        change_summary: str | None = None,
        file_id: str | None = None,
        operation: str | None = None,
    ) -> dict[str, Any]:
        if operation:
            try:
                payload = json.loads(operation)
            except json.JSONDecodeError as exc:
                if operation != "write_latex":
                    raise ValueError("write_latex operation must be write_latex or a JSON payload") from exc
            else:
                if not isinstance(payload, dict):
                    raise ValueError("write_latex operation JSON must be an object")
                name = name or payload.get("name") or payload.get("document_name")
                source_latex = source_latex or payload.get("source_latex")
                change_summary = change_summary or payload.get("change_summary")
                file_id = file_id or payload.get("file_id")
        name = _text_value(name) or "cv.tex"
        source_latex = _text_value(source_latex if source_latex is not None else getattr(self, "source_latex", ""))
        change_summary = _text_value(change_summary if change_summary is not None else getattr(self, "change_summary", "")) or "Initial source"
        file_id = _text_value(file_id if file_id is not None else getattr(self, "file_id", ""))
        if bool(file_id.strip()) == bool(source_latex.strip()):
            raise ValueError("write_latex requires exactly one of non-empty file_id or source_latex")
        return self.client.write_latex(name, source_latex, change_summary or "Initial source", file_id)

    def run(
        self,
        operation: str = "check_latex",
        document_id: str = "",
        version_id: str = "",
        base_version_id: str = "",
        name: str = "cv.tex",
        file_id: str = "",
        source_latex: str = "",
        job_description: str = "",
        change_summary: str = "",
    ) -> str:
        if operation == "check_latex":
            result = self.check_latex(document_id, version_id)
        elif operation == "edit_latex":
            result = self.edit_latex(document_id, base_version_id, source_latex, change_summary, job_description)
        elif operation == "write_latex":
            result = self.write_latex(name, source_latex, change_summary or "Initial source", file_id)
        else:
            raise ValueError("operation must be check_latex, edit_latex, or write_latex")
        return json.dumps(result, ensure_ascii=False)
