from unittest.mock import MagicMock

from helpcenter_sync import publish


def test_run_log_and_report_overwrite_the_gist(monkeypatch):
    patch = MagicMock()
    monkeypatch.setattr(publish.requests, "patch", patch)

    publish.publish_to_gist("abc", "tok", "log lines", '{"added": 1}')

    url = patch.call_args.args[0]
    files = patch.call_args.kwargs["json"]["files"]
    assert url == "https://api.github.com/gists/abc"
    assert files == {"last-run.log": {"content": "log lines"}, "last-run.json": {"content": '{"added": 1}'}}
    assert patch.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"
