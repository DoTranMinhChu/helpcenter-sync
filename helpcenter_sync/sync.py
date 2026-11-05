import hashlib
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from openai import OpenAI

from helpcenter_sync.config import Settings
from helpcenter_sync.markdown import article_slug, article_to_markdown
from helpcenter_sync.report import RunReport
from helpcenter_sync.vector_store import IndexedArticle, VectorStoreGateway, count_chunks, resolve_vector_store
from helpcenter_sync.zendesk import Article, fetch_articles

log = logging.getLogger(__name__)

# Bump when conversion changes, so every article is re-uploaded once.
PIPELINE_VERSION = "1"

# Refuse to delete more than this share of the index in one run (protects against a bad fetch).
MAX_REMOVAL_RATIO = 0.25


class Gateway(Protocol):
    def indexed_articles(self) -> dict[str, IndexedArticle]: ...
    def upload_file(self, filename: str, text: str, attributes: dict) -> str: ...
    def delete_files(self, file_ids: list[str]) -> None: ...


@dataclass
class PreparedArticle:
    article: Article
    slug: str
    markdown: str
    content_hash: str


@dataclass
class SyncPlan:
    add: list[str] = field(default_factory=list)
    update: list[str] = field(default_factory=list)
    skip: list[str] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)


def content_hash(markdown: str) -> str:
    return hashlib.sha256(f"{PIPELINE_VERSION}\n{markdown}".encode("utf-8")).hexdigest()


def plan_sync(current: dict[str, str], indexed: dict[str, IndexedArticle], allow_removals: bool) -> SyncPlan:
    plan = SyncPlan()
    for article_id, digest in current.items():
        existing = indexed.get(article_id)
        if existing is None:
            plan.add.append(article_id)
        elif existing.content_hash != digest or not existing.healthy:
            plan.update.append(article_id)
        else:
            plan.skip.append(article_id)
    if allow_removals:
        plan.remove = [article_id for article_id in indexed if article_id not in current]
    return plan


def prepare_articles(articles: list[Article], output_dir: str) -> list[PreparedArticle]:
    articles_dir = os.path.join(output_dir, "articles")
    shutil.rmtree(articles_dir, ignore_errors=True)
    os.makedirs(articles_dir)

    prepared, used_slugs = [], set()
    for article in articles:
        slug = article_slug(article)
        if slug in used_slugs:
            slug = f"{slug}-{article.id}"
        used_slugs.add(slug)
        markdown = article_to_markdown(article)
        with open(os.path.join(articles_dir, f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(markdown)
        prepared.append(PreparedArticle(article, slug, markdown, content_hash(markdown)))
    return prepared


def apply_sync(prepared: list[PreparedArticle], gateway: Gateway, report: RunReport,
               allow_removals: bool, dry_run: bool = False, concurrency: int = 8) -> RunReport:
    by_id = {str(p.article.id): p for p in prepared}
    indexed = gateway.indexed_articles()
    plan = plan_sync({k: p.content_hash for k, p in by_id.items()}, indexed, allow_removals)
    if indexed and len(plan.remove) > MAX_REMOVAL_RATIO * len(indexed):
        log.warning("Plan removes %d of %d indexed articles; skipping removals as a safety guard",
                    len(plan.remove), len(indexed))
        plan.remove = []

    report.skipped = len(plan.skip)
    log.info("Plan: add=%d update=%d skip=%d remove=%d",
             len(plan.add), len(plan.update), len(plan.skip), len(plan.remove))
    if dry_run:
        report.added, report.updated, report.removed = len(plan.add), len(plan.update), len(plan.remove)
        return report

    def upsert(article_id: str) -> None:
        item = by_id[article_id]
        is_update = article_id in indexed
        try:
            gateway.upload_file(f"{item.slug}.md", item.markdown, {
                "article_id": article_id,
                "content_hash": item.content_hash,
                "url": item.article.html_url,
                "updated_at": item.article.updated_at,
            })
        except Exception as exc:
            log.error("FAILED %s (%s): %s", item.slug, article_id, exc)
            report.record_failure(article_id, item.slug, str(exc))
            return
        # The old file is removed only after the new one is live, so the article never disappears.
        if is_update:
            gateway.delete_files(indexed[article_id].file_ids)
        chunks = count_chunks(item.markdown)
        report.record_success(updated=is_update, chunks=chunks)
        log.info("%s %s.md (%d chunk%s)", "UPDATED" if is_update else "ADDED", item.slug,
                 chunks, "" if chunks == 1 else "s")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(upsert, plan.add + plan.update))

    for article_id in plan.remove:
        gateway.delete_files(indexed[article_id].file_ids)
        report.removed += 1
        log.info("REMOVED article %s", article_id)
    return report


def run_sync(settings: Settings) -> RunReport:
    report = RunReport(started_at=time.time(), dry_run=settings.dry_run)

    articles = list(fetch_articles(settings.zendesk_base_url, settings.zendesk_locale, settings.max_articles))
    if not articles:
        raise RuntimeError("Fetched 0 articles; refusing to sync an empty set")
    prepared = prepare_articles(articles, settings.output_dir)
    report.fetched = len(prepared)

    if settings.dry_run and not settings.openai_api_key:
        log.info("Dry run without an API key: scraped %d articles, vector store not contacted", len(prepared))
        return report.finish()

    client = OpenAI(api_key=settings.openai_api_key, max_retries=5)
    report.vector_store_id = resolve_vector_store(client, settings.vector_store_id, settings.vector_store_name)
    apply_sync(prepared, VectorStoreGateway(client, report.vector_store_id), report,
               allow_removals=settings.max_articles == 0,
               dry_run=settings.dry_run,
               concurrency=settings.upload_concurrency)
    return report.finish()
