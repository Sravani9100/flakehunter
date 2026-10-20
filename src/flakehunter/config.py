from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLAKEHUNTER_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./flakehunter.db"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Bearer token CI jobs use to upload JUnit reports. Uploads are disabled when unset.
    upload_token: str | None = None

    # GitHub App credentials, needed only for webhook-driven ingestion and pull requests.
    github_app_id: str | None = None
    github_private_key_path: Path | None = None
    github_webhook_secret: str | None = None
    github_api_url: str = "https://api.github.com"
    # Artifacts whose name matches this regex are treated as JUnit reports.
    artifact_name_pattern: str = r"junit|test-results"

    flake_window_days: int = 14

    # AI diagnosis and fixing. Read from ANTHROPIC_API_KEY (no prefix), including in .env.
    # When unset, the SDK falls back to its own credential discovery.
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    ai_enabled: bool = True
    anthropic_model: str = "claude-opus-5-5"
    ai_effort: str = "high"
    # Server-side refusal fallback; supported on Claude Opus 5.5 and other current models.
    ai_fallbacks: bool = True
    agent_max_turns: int = 40

    # Test reruns. "subprocess" runs locally (trusted code only); "docker" isolates each batch.
    sandbox: str = "subprocess"
    sandbox_image: str = "flakehunter-sandbox"
    sandbox_workers: int = 8
    baseline_runs: int = 20
    verify_runs: int = 100

    # Dev and evals only: lets a repository point at a local directory instead of GitHub.
    allow_local_repos: bool = False

    evals_results_path: Path = Path("evals/results/latest.json")


@lru_cache
def get_settings() -> Settings:
    return Settings()
