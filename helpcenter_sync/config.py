import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    vector_store_id: str
    vector_store_name: str
    zendesk_base_url: str
    zendesk_locale: str
    max_articles: int
    output_dir: str
    upload_concurrency: int
    dry_run: bool
    log_gist_id: str
    github_token: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY") or "",
            vector_store_id=os.getenv("VECTOR_STORE_ID", "").strip(),
            vector_store_name=os.getenv("VECTOR_STORE_NAME", "optibot-kb"),
            zendesk_base_url=os.getenv("ZENDESK_BASE_URL", "https://support.optisigns.com").rstrip("/"),
            zendesk_locale=os.getenv("ZENDESK_LOCALE", "en-us"),
            max_articles=int(os.getenv("MAX_ARTICLES", "0")),
            output_dir=os.getenv("OUTPUT_DIR", "out"),
            upload_concurrency=int(os.getenv("UPLOAD_CONCURRENCY", "8")),
            dry_run=_bool(os.getenv("DRY_RUN")),
            log_gist_id=os.getenv("LOG_GIST_ID", "").strip(),
            github_token=os.getenv("GITHUB_TOKEN", "").strip(),
        )
