import logging
from dataclasses import dataclass
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Article:
    id: int
    title: str
    html_url: str
    body_html: str
    updated_at: str


def _session() -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "helpcenter-sync/1.0"
    return session


def fetch_articles(base_url: str, locale: str, limit: int = 0) -> Iterator[Article]:
    session = _session()
    url = f"{base_url}/api/v2/help_center/{locale}/articles.json?per_page=100&sort_by=position"
    count = 0
    while url:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for raw in payload["articles"]:
            if raw.get("draft") or not raw.get("body"):
                continue
            yield Article(
                id=raw["id"],
                title=raw["title"].strip(),
                html_url=raw["html_url"],
                body_html=raw["body"],
                updated_at=raw["updated_at"],
            )
            count += 1
            if limit and count >= limit:
                return
        url = payload.get("next_page")
    log.info("Fetched %d articles from %s", count, base_url)
