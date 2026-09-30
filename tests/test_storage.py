from pathlib import Path

import pytest

from app.config import Settings
from app.errors import AppError
from app.storage import safe_filename, safe_relative_path, write_workspace_file


def test_filename_is_sanitized():
    assert safe_filename("../../cv final.tex") == "cv_final.tex"


def test_relative_path_rejects_traversal(tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    with pytest.raises(AppError) as error:
        safe_relative_path(settings, "../../outside.txt")
    assert error.value.code == "VALIDATION_ERROR"


def test_workspace_file_is_written_under_generated_directory(tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    relative = write_workspace_file(settings, "file_test", "cv.tex", b"hello")
    assert relative == "data/uploads/file_test/cv.tex"
    assert (tmp_path / relative).read_bytes() == b"hello"

