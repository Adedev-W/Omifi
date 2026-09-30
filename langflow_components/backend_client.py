import os
from typing import Any

import httpx


class BackendClientError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


class BackendClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 60):
        self.base_url = (base_url or os.getenv("LATEX_BACKEND_URL", "http://localhost:8080")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("LATEX_BACKEND_API_KEY", "")
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key} if self.api_key else {}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, f"{self.base_url}{path}", headers=self.headers, **kwargs)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not response.is_success:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            raise BackendClientError(
                error.get("code", "BACKEND_ERROR"),
                error.get("message", response.text),
                error.get("details", {}),
            )
        return payload

    def get_document(self, document_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/documents/{document_id}")

    def check_latex(self, document_id: str, version_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/documents/{document_id}/check-latex", json={"version_id": version_id})

    def edit_latex(self, document_id: str, base_version_id: str, source_latex: str, change_summary: str, job_description: str = "") -> dict[str, Any]:
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

    def write_latex(
        self,
        name: str,
        source_latex: str = "",
        change_summary: str = "Initial source",
        file_id: str = "",
    ) -> dict[str, Any]:
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

    def save_report(self, document_id: str, report: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/v1/documents/{document_id}/reports", json=report)
