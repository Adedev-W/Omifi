import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .storage import bounded_text


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


@dataclass
class CompileResult:
    status: str
    log: str = ""
    warning: str | None = None
    pdf_path: Path | None = None


def normalize_source(source: str) -> str:
    """Normalize text received from APIs into a compilable .tex document."""
    normalized = source.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = normalized.splitlines()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        normalized = "\n".join(lines[1:-1]).strip()
    return normalized


def _run_with_bounded_output(command: list[str], workdir: Path, settings: Settings) -> tuple[int, bytes, bool]:
    """Run a compiler while draining stdout and retaining only bounded output."""
    process = subprocess.Popen(
        command,
        cwd=workdir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "TEXMFOUTPUT": str(workdir)},
    )
    output = bytearray()

    def consume() -> None:
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(8192)
            if not chunk:
                return
            remaining = settings.max_log_bytes - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])

    reader = threading.Thread(target=consume, name="latex-output-reader", daemon=True)
    reader.start()
    timed_out = False
    try:
        process.wait(timeout=settings.latex_timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    reader.join(timeout=2)
    return process.returncode or 0, bytes(output), timed_out


def validate_source(source: str, max_bytes: int) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not source.strip():
        errors.append("LaTeX source must not be empty")
    if len(source.encode("utf-8")) > max_bytes:
        errors.append(f"LaTeX source exceeds the {max_bytes}-byte limit")
    if "\\documentclass" not in source:
        errors.append("LaTeX source must contain \\documentclass")
    if "\\begin{document}" not in source:
        errors.append("LaTeX source must contain \\begin{document}")
    if "\\end{document}" not in source:
        errors.append("LaTeX source must contain \\end{document}")
    if "\\usepackage{shellesc}" in source or "\\write18" in source:
        warnings.append("Source contains shell-related LaTeX commands; shell escape remains disabled")
    return ValidationResult(not errors, errors, warnings)


def compile_source(settings: Settings, source: str, workdir: Path) -> CompileResult:
    executable = shutil.which(settings.latex_engine)
    if executable is None:
        return CompileResult(
            status="unavailable",
            warning=f"LaTeX compiler '{settings.latex_engine}' is not installed",
        )

    workdir.mkdir(parents=True, exist_ok=True)
    source_path = workdir / "source.tex"
    source_path.write_text(source, encoding="utf-8")
    command = [
        executable,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-no-shell-escape",
        "-output-directory",
        str(workdir),
        str(source_path),
    ]
    try:
        returncode, output, timed_out = _run_with_bounded_output(command, workdir, settings)
    except subprocess.TimeoutExpired:
        return CompileResult(status="timeout")
    except (FileNotFoundError, PermissionError) as exc:
        return CompileResult(status="unavailable", warning=f"Unable to execute LaTeX compiler: {type(exc).__name__}")

    log = bounded_text(output, settings.max_log_bytes)
    if timed_out:
        return CompileResult(status="timeout", log=log)
    pdf_path = workdir / "source.pdf"
    if returncode != 0:
        return CompileResult(status="failed", log=log)
    if not pdf_path.is_file():
        return CompileResult(status="failed", log=log, warning="Compiler exited successfully but produced no PDF")
    if pdf_path.stat().st_size > settings.max_artifact_bytes:
        return CompileResult(status="failed", log=log, warning="Generated PDF exceeds the artifact size limit")
    return CompileResult(status="success", log=log, pdf_path=pdf_path)
