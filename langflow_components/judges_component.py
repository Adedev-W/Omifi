import json
import os
from typing import Any

try:
    from .backend_client import BackendClient
except ImportError:  # Langflow may load a component file directly from its path.
    from backend_client import BackendClient

try:
    from langflow.custom import Component
    from langflow.io import MessageTextInput, Output, StrInput
except ImportError:
    class Component:  # type: ignore[no-redef]
        pass

    class _Input:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any):
            self.kwargs = kwargs

    MessageTextInput = StrInput = _Input  # type: ignore[assignment,misc]

    class Output:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any):
            self.kwargs = kwargs


class JudgesComponent(Component):
    display_name = "CV Judges Backend Tools"
    description = "HTTP report persistence and optional Tavily context for CV evaluation."
    name = "JudgesComponent"
    inputs = [
        StrInput(name="operation", display_name="Operation", value="get_context", tool_mode=True),
        StrInput(name="document_id", display_name="Document ID", value="", tool_mode=True),
        StrInput(name="version_id", display_name="Version ID", value="", tool_mode=True),
        MessageTextInput(name="job_description", display_name="Job Description", value="", tool_mode=True),
        MessageTextInput(name="query", display_name="Web Search Query", value="", tool_mode=True),
        MessageTextInput(name="report_json", display_name="Report JSON", value="{}", tool_mode=True),
    ]
    outputs = [
        Output(name="context_tool", display_name="Document Context", method="get_context", group_outputs=True),
        Output(name="search_tool", display_name="Tavily Search", method="search_web", group_outputs=True),
        Output(name="report_tool", display_name="Save Report", method="save_report", group_outputs=True),
        Output(name="result", display_name="Result", method="run", group_outputs=True),
    ]

    def __init__(self, **kwargs: Any):
        try:
            super().__init__(**kwargs)
        except TypeError:
            super().__init__()
        self.client = BackendClient()

    def get_context(self, document_id: str | None = None, version_id: str | None = None) -> dict[str, Any]:
        document_id = document_id or getattr(self, "document_id", "")
        version_id = version_id or getattr(self, "version_id", "")
        context = self.client.get_document(document_id)
        if version_id:
            selected = next((item for item in context.get("versions", []) if item.get("version_id") == version_id), None)
            context["selected_version"] = selected
        return context

    def search_web(self, query: str | None = None) -> dict[str, Any]:
        query = query or getattr(self, "query", "")
        api_key = os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            return {"results": [], "warnings": ["TAVILY_API_KEY is not configured; external evidence is unavailable"]}
        try:
            from tavily import TavilyClient

            results = TavilyClient(api_key=api_key).search(query=query, max_results=5)
            return {"results": results.get("results", []), "warnings": []}
        except Exception as exc:  # external search must never prevent report persistence
            return {"results": [], "warnings": [f"Tavily search unavailable: {type(exc).__name__}"]}

    def save_report(self, document_id: str | None = None, report_json: str | dict[str, Any] | None = None) -> dict[str, Any]:
        document_id = document_id or getattr(self, "document_id", "")
        report_json = report_json if report_json is not None else getattr(self, "report_json", "{}")
        report = json.loads(report_json) if isinstance(report_json, str) else report_json
        if not isinstance(report, dict):
            raise ValueError("report_json must decode to an object")
        report.setdefault("version_id", getattr(self, "version_id", ""))
        report.setdefault("job_description", getattr(self, "job_description", "") or None)
        return self.client.save_report(document_id, report)

    def build_tools(self) -> dict[str, Any]:
        return {"get_context": self.get_context, "search_web": self.search_web, "save_report": self.save_report}

    def run(self, operation: str = "get_context", document_id: str = "", version_id: str = "", query: str = "", report_json: str = "{}", job_description: str = "") -> str:
        self.document_id = document_id or getattr(self, "document_id", "")
        self.version_id = version_id or getattr(self, "version_id", "")
        self.job_description = job_description or getattr(self, "job_description", "")
        if operation == "get_context":
            result = self.get_context(self.document_id, self.version_id)
        elif operation == "search_web":
            result = self.search_web(query)
        elif operation == "save_report":
            result = self.save_report(self.document_id, report_json)
        else:
            raise ValueError("operation must be get_context, search_web, or save_report")
        return json.dumps(result, ensure_ascii=False)
