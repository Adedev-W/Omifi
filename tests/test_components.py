import json
from pathlib import Path

import pytest

from langflow_components.editing_component import EditingComponent
from langflow_components.judges_component import JudgesComponent


class FakeEditingClient:
    def check_latex(self, document_id, version_id):
        return {"document_id": document_id, "version_id": version_id, "valid": True}

    def edit_latex(self, *args):
        return {"edited": True}

    def write_latex(self, *args):
        return {"written": True, "args": args}


class FakeJudgesClient:
    def get_document(self, document_id):
        return {"document_id": document_id}

    def save_report(self, document_id, report):
        return {"document_id": document_id, "report": report}


class MessageValue:
    def __init__(self, text):
        self.text = text


def test_editing_component_rejects_invalid_tool_name():
    component = EditingComponent()
    component.client = FakeEditingClient()
    try:
        component.run(operation="invalid")
    except ValueError as error:
        assert "check_latex" in str(error)
    else:
        raise AssertionError("invalid operation should fail")


def test_components_expose_langflow_tool_mode():
    operation_input = EditingComponent.inputs[0]
    judges_operation_input = JudgesComponent.inputs[0]
    assert getattr(operation_input, "kwargs", {}).get("tool_mode", True) is True
    assert getattr(judges_operation_input, "kwargs", {}).get("tool_mode", True) is True
    editing_inputs = {
        item.kwargs["name"]: item
        for item in EditingComponent.inputs
        if "name" in getattr(item, "kwargs", {})
    }
    for name in ("name", "file_id", "source_latex", "change_summary"):
        assert editing_inputs[name].kwargs.get("tool_mode") is True
    judges_inputs = {
        item.kwargs["name"]: item
        for item in JudgesComponent.inputs
        if "name" in getattr(item, "kwargs", {})
    }
    for name in ("document_id", "version_id", "job_description", "query", "report_json"):
        assert judges_inputs[name].kwargs.get("tool_mode") is True


def test_langflow_bundle_uses_canonical_component_sources():
    bundle_dir = Path(__file__).parents[1] / "langflow_components" / "cv_automation"

    assert (bundle_dir / "__init__.py").is_file()
    for filename, class_name in (
        ("editing_component.py", "EditingComponent"),
        ("judges_component.py", "JudgesComponent"),
    ):
        source = (bundle_dir / filename).read_text(encoding="utf-8")
        assert "from lfx.custom.custom_component.component import Component" in source
        assert f"class {class_name}(Component):" in source


def test_editing_component_calls_backend_tool():
    component = EditingComponent()
    component.client = FakeEditingClient()
    result = json.loads(component.run(operation="check_latex", document_id="doc_1", version_id="ver_1"))
    assert result["valid"] is True


def test_editing_component_rejects_incomplete_backend_inputs():
    component = EditingComponent()
    component.client = FakeEditingClient()

    with pytest.raises(ValueError, match="non-empty document_id and version_id"):
        component.check_latex("", "")
    with pytest.raises(ValueError, match="exactly one"):
        component.write_latex(name="cv.tex", source_latex="", file_id="")


def test_editing_component_can_create_document_from_uploaded_file():
    component = EditingComponent()
    component.client = FakeEditingClient()

    result = component.write_latex(name="uploaded.tex", file_id="file_123")

    assert result["written"] is True
    assert result["args"] == ("uploaded.tex", "", "Initial source", "file_123")


def test_editing_component_accepts_nested_tool_mode_write_payload():
    component = EditingComponent()
    component.client = FakeEditingClient()

    result = component.write_latex(
        operation=json.dumps(
            {
                "operation": "write_latex",
                "name": "cv.tex",
                "source_latex": r"\documentclass{article}\begin{document}Hello\end{document}",
                "change_summary": "Create CV",
            }
        )
    )

    assert result["args"] == (
        "cv.tex",
        r"\documentclass{article}\begin{document}Hello\end{document}",
        "Create CV",
        "",
    )


def test_editing_component_accepts_langflow_message_source():
    component = EditingComponent()
    component.client = FakeEditingClient()

    result = component.write_latex(
        source_latex=MessageValue(r"\documentclass{article}\begin{document}Hello\end{document}"),
    )

    assert result["args"] == (
        "cv.tex",
        r"\documentclass{article}\begin{document}Hello\end{document}",
        "Initial source",
        "",
    )


def test_judges_component_falls_back_without_tavily(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    result = JudgesComponent().search_web("python")
    assert result["results"] == []
    assert result["warnings"]


def test_judges_component_saves_report():
    component = JudgesComponent()
    component.client = FakeJudgesClient()
    result = json.loads(component.run(operation="save_report", document_id="doc_1", report_json='{"version_id":"ver_1"}'))
    assert result["report"]["version_id"] == "ver_1"
