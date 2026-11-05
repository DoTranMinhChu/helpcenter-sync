import logging

import requests

log = logging.getLogger(__name__)


def publish_to_gist(gist_id: str, token: str, log_text: str, report_json: str) -> None:
    """Overwrite a public gist with the latest run; the gist's revision history keeps earlier runs."""
    response = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"files": {"last-run.log": {"content": log_text}, "last-run.json": {"content": report_json}}},
        timeout=30,
    )
    response.raise_for_status()
    log.info("Published run log to https://gist.github.com/%s", gist_id)
