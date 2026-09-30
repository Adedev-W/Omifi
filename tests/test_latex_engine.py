from pathlib import Path

from app.config import Settings
from app.latex_engine import compile_source, normalize_source, validate_source


VALID_SOURCE = r"\documentclass{article}\begin{document}Hello\end{document}"


def test_normalize_source_removes_markdown_fence_and_normalizes_file_text():
    source = "\ufeff```latex\r\n\\documentclass{article}\r\n\\begin{document}Hello\\end{document}\r\n```\r\n"
    assert normalize_source(source) == "\\documentclass{article}\n\\begin{document}Hello\\end{document}"


def test_validate_source_rejects_missing_document_markers():
    result = validate_source("plain text", 1000)
    assert not result.valid
    assert any("documentclass" in error for error in result.errors)


def test_validate_source_enforces_source_limit():
    result = validate_source(VALID_SOURCE, 4)
    assert not result.valid
    assert any("limit" in error for error in result.errors)


def test_compile_reports_missing_engine(tmp_path: Path):
    settings = Settings(latex_engine="definitely-not-installed", artifact_dir=tmp_path)
    result = compile_source(settings, VALID_SOURCE, tmp_path / "work")
    assert result.status == "unavailable"
    assert result.warning


def test_compile_success_keeps_shell_escape_disabled(monkeypatch, tmp_path: Path):
    import app.latex_engine as engine

    seen: list[str] = []

    monkeypatch.setattr(engine.shutil, "which", lambda _: "/usr/bin/fake-xelatex")

    def fake_run(command, workdir, settings):
        seen.extend(command)
        output_dir = Path(command[command.index("-output-directory") + 1])
        (output_dir / "source.pdf").write_bytes(b"%PDF-test")
        return 0, b"ok", False

    monkeypatch.setattr(engine, "_run_with_bounded_output", fake_run)
    result = compile_source(Settings(latex_engine="xelatex", artifact_dir=tmp_path), VALID_SOURCE, tmp_path / "work")
    assert result.status == "success"
    assert result.pdf_path and result.pdf_path.is_file()
    assert "-no-shell-escape" in seen
    assert "--shell-escape" not in seen


def test_compile_failure_and_timeout_are_structured(monkeypatch, tmp_path: Path):
    import subprocess
    import app.latex_engine as engine

    monkeypatch.setattr(engine.shutil, "which", lambda _: "/usr/bin/fake-xelatex")
    monkeypatch.setattr(engine, "_run_with_bounded_output", lambda *args, **kwargs: (1, b"fatal latex error", False))
    failed = engine.compile_source(Settings(latex_engine="xelatex", artifact_dir=tmp_path), VALID_SOURCE, tmp_path / "failed")
    assert failed.status == "failed"
    assert "fatal latex error" in failed.log

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(kwargs.get("args", args[0] if args else "xelatex"), 1, output=b"timed out")

    monkeypatch.setattr(engine, "_run_with_bounded_output", timeout)
    timed_out = engine.compile_source(Settings(latex_engine="xelatex", artifact_dir=tmp_path), VALID_SOURCE, tmp_path / "timeout")
    assert timed_out.status == "timeout"


def test_compiler_log_is_bounded(monkeypatch, tmp_path: Path):
    import app.latex_engine as engine

    monkeypatch.setattr(engine.shutil, "which", lambda _: "/usr/bin/fake-xelatex")
    monkeypatch.setattr(engine, "_run_with_bounded_output", lambda *args, **kwargs: (1, b"x" * 1000, False))
    result = engine.compile_source(
        Settings(latex_engine="xelatex", artifact_dir=tmp_path, max_log_bytes=32),
        VALID_SOURCE,
        tmp_path / "bounded",
    )
    assert len(result.log.encode()) <= 32


def test_compile_runs_isolated_engine_process(tmp_path: Path):
    script = tmp_path / "fake-latex"
    script.write_text(
        "#!/bin/sh\n"
        "out=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = \"-output-directory\" ]; then shift; out=$1; fi\n"
        "  shift\n"
        "done\n"
        "printf 'fake compiler log'\n"
        "printf '%%PDF-test' > \"$out/source.pdf\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    result = compile_source(
        Settings(latex_engine=str(script), artifact_dir=tmp_path),
        VALID_SOURCE,
        tmp_path / "real-process",
    )
    assert result.status == "success"
    assert result.pdf_path and result.pdf_path.read_bytes() == b"%PDF-test"
