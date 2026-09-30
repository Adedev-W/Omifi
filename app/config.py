from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
load_dotenv()
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field("sqlite:///./data/cv_editor.db", validation_alias="CV_DATABASE_URL")
    artifact_dir: Path = Field(Path("./data/artifacts"), validation_alias="CV_ARTIFACT_DIR")
    workspace_root: Path = Field(Path("."), validation_alias="CV_WORKSPACE_ROOT")
    public_base_url: str = Field("http://localhost:8080", validation_alias="CV_PUBLIC_BASE_URL")
    backend_host: str = Field("0.0.0.0", validation_alias="CV_BACKEND_HOST")
    backend_port: int = Field(8080, validation_alias="CV_BACKEND_PORT")
    internal_api_key: str = Field("", validation_alias="CV_INTERNAL_API_KEY")
    latex_engine: str = Field("xelatex", validation_alias="CV_LATEX_ENGINE")
    latex_timeout_seconds: float = Field(30.0, validation_alias="CV_LATEX_TIMEOUT_SECONDS")
    max_upload_bytes: int = Field(5 * 1024 * 1024, validation_alias="CV_MAX_UPLOAD_BYTES")
    max_source_bytes: int = Field(1024 * 1024, validation_alias="CV_MAX_SOURCE_BYTES")
    max_log_bytes: int = Field(64 * 1024, validation_alias="CV_MAX_LOG_BYTES")
    max_artifact_bytes: int = Field(10 * 1024 * 1024, validation_alias="CV_MAX_ARTIFACT_BYTES")
    artifact_retention_days: int = Field(30, validation_alias="CV_ARTIFACT_RETENTION_DAYS")
    busy_timeout_seconds: int = Field(5, validation_alias="CV_BUSY_TIMEOUT_SECONDS")

    @property
    def database_url_async(self) -> str:
        if self.database_url.startswith("sqlite:///") and "+aiosqlite" not in self.database_url:
            return self.database_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return self.database_url

    def ensure_directories(self) -> None:
        self.workspace_root.resolve().mkdir(parents=True, exist_ok=True)
        self.artifact_dir.resolve().mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
