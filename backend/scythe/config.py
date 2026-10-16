from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCYTHE_", env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://scythe:scythe@localhost:5544/scythe"
    spacy_model: str = "en_core_web_sm"
    models_dir: Path = ROOT / "models"
    # Where browsers reach this API. The GitHub App's callback URL is {api_url}/api/auth/callback.
    api_url: str = "http://localhost:8000"
    # Origins allowed to use the API (CORS) and to receive sign-in redirects: the Vite dev server,
    # `vite preview`, and the GitHub Pages site (e.g. https://<user>.github.io).
    frontend_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]
    # GitHub App credentials (Settings -> Developer settings -> GitHub Apps).
    github_client_id: str = ""
    github_client_secret: str = ""
    github_app_slug: str = ""  # for the "install on a repo" link
    # Use an in-memory/on-disk fake GitHub instead of api.github.com (tests, offline dev).
    github_fake: bool = False
    github_fake_path: Path | None = ROOT / ".fake-github.json"
    # Fernet key for encrypting GitHub tokens at rest; generated into .scythe-secret if unset.
    secret_key: str = ""
    session_days: int = 14


settings = Settings()
