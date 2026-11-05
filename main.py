import io
import logging
import sys

from helpcenter_sync.config import Settings
from helpcenter_sync.publish import publish_to_gist
from helpcenter_sync.sync import run_sync


def main() -> int:
    captured = io.StringIO()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%dT%H:%M:%S")
    handlers = [logging.StreamHandler(sys.stdout), logging.StreamHandler(captured)]
    for handler in handlers:
        handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=handlers)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    log = logging.getLogger("main")

    settings = Settings.from_env()
    if not settings.openai_api_key and not settings.dry_run:
        log.error("OPENAI_API_KEY (or API_KEY) is not set")
        return 2

    try:
        report = run_sync(settings)
    except Exception:
        log.exception("Sync aborted")
        return 1

    report.write(settings.output_dir)
    log.info("SYNC COMPLETE %s", report.summary_line())

    if settings.log_gist_id and settings.github_token:
        try:
            publish_to_gist(settings.log_gist_id, settings.github_token, captured.getvalue(), report.to_json())
        except Exception as exc:
            log.warning("Could not publish run log: %s", exc)

    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
