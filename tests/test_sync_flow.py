import itertools
import time

from helpcenter_sync.report import RunReport
from helpcenter_sync.sync import apply_sync, plan_sync, prepare_articles
from helpcenter_sync.vector_store import IndexedArticle
from helpcenter_sync.zendesk import Article


class FakeGateway:
    """In-memory vector store that rebuilds state from file attributes, like the real one."""

    def __init__(self):
        self.files: dict[str, dict] = {}
        self.fail_slugs: tuple[str, ...] = ()
        self.uploads = 0
        self._ids = itertools.count(1)

    def indexed_articles(self) -> dict[str, IndexedArticle]:
        indexed: dict[str, IndexedArticle] = {}
        for file_id, attrs in self.files.items():
            entry = indexed.setdefault(attrs["article_id"], IndexedArticle(attrs["content_hash"]))
            entry.file_ids.append(file_id)
        return indexed

    def upload_file(self, filename: str, text: str, attributes: dict) -> str:
        if self.fail_slugs and filename.startswith(self.fail_slugs):
            raise RuntimeError("embedding failed")
        file_id = f"file-{next(self._ids)}"
        self.files[file_id] = {**attributes, "filename": filename}
        self.uploads += 1
        return file_id

    def delete_files(self, file_ids: list[str]) -> None:
        for file_id in file_ids:
            self.files.pop(file_id, None)


def _article(i: int, body: str = "<p>Body</p>") -> Article:
    return Article(id=i, title=f"Article {i}", html_url=f"https://support.optisigns.com/hc/en-us/articles/{i}-Article-{i}",
                   body_html=body, updated_at="2026-01-01T00:00:00Z")


def _sync(tmp_path, gateway, articles, allow_removals=True) -> RunReport:
    prepared = prepare_articles(articles, str(tmp_path))
    report = RunReport(started_at=time.time(), fetched=len(prepared))
    return apply_sync(prepared, gateway, report, allow_removals=allow_removals, concurrency=2)


def _files_of(gateway: FakeGateway, article_id: int) -> list[dict]:
    return [a for a in gateway.files.values() if a["article_id"] == str(article_id)]


def test_first_run_uploads_one_markdown_file_per_article(tmp_path):
    gateway = FakeGateway()
    report = _sync(tmp_path, gateway, [_article(1), _article(2)])

    assert (report.added, report.updated, report.skipped, report.failed) == (2, 0, 0, 0)
    assert report.files_uploaded == 2 and report.chunks_embedded == 2
    assert sorted(a["filename"] for a in gateway.files.values()) == ["article-1.md", "article-2.md"]
    assert (tmp_path / "articles" / "article-1.md").exists()


def test_unchanged_run_skips_and_uploads_nothing(tmp_path):
    gateway = FakeGateway()
    _sync(tmp_path, gateway, [_article(1), _article(2)])
    report = _sync(tmp_path, gateway, [_article(1), _article(2)])

    assert (report.added, report.updated, report.skipped, report.files_uploaded) == (0, 0, 2, 0)
    assert gateway.uploads == 2


def test_changed_article_replaces_its_file(tmp_path):
    gateway = FakeGateway()
    _sync(tmp_path, gateway, [_article(1), _article(2)])
    old_hash = _files_of(gateway, 2)[0]["content_hash"]

    report = _sync(tmp_path, gateway, [_article(1), _article(2, "<p>New body</p>")])
    assert (report.updated, report.skipped) == (1, 1)
    files = _files_of(gateway, 2)
    assert len(files) == 1 and files[0]["content_hash"] != old_hash


def test_deleted_article_is_removed(tmp_path):
    gateway = FakeGateway()
    _sync(tmp_path, gateway, [_article(i) for i in range(1, 6)])
    report = _sync(tmp_path, gateway, [_article(i) for i in range(1, 5)])
    assert report.removed == 1 and _files_of(gateway, 5) == []


def test_mass_removal_is_blocked(tmp_path):
    gateway = FakeGateway()
    _sync(tmp_path, gateway, [_article(i) for i in range(1, 11)])
    report = _sync(tmp_path, gateway, [_article(1), _article(2)])
    assert report.removed == 0 and len(gateway.indexed_articles()) == 10


def test_partial_fetch_never_removes(tmp_path):
    gateway = FakeGateway()
    _sync(tmp_path, gateway, [_article(1), _article(2)])
    report = _sync(tmp_path, gateway, [_article(1)], allow_removals=False)
    assert report.removed == 0 and len(gateway.indexed_articles()) == 2


def test_file_that_failed_embedding_is_uploaded_again():
    indexed = {"1": IndexedArticle("h1", ["f1"], healthy=False)}
    assert plan_sync({"1": "h1"}, indexed, allow_removals=True).update == ["1"]


def test_failed_update_keeps_the_old_version_live(tmp_path):
    gateway = FakeGateway()
    _sync(tmp_path, gateway, [_article(1), _article(2)])
    gateway.fail_slugs = ("article-2",)

    report = _sync(tmp_path, gateway, [_article(1, "<p>v2</p>"), _article(2, "<p>v2</p>")])
    assert (report.updated, report.failed) == (1, 1)
    assert report.failures[0]["slug"] == "article-2"
    assert len(_files_of(gateway, 2)) == 1
