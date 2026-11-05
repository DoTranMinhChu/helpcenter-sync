import io
import logging
import math
from dataclasses import dataclass, field

import tiktoken
from openai import NotFoundError, OpenAI

log = logging.getLogger(__name__)

# Median article is ~1.1k tokens; at 4096 tokens 97% of articles embed as one chunk, so the chunk
# that answers a question almost always also contains the article's "Article URL:" line.
MAX_CHUNK_TOKENS = 4096
CHUNK_OVERLAP_TOKENS = 400
CHUNKING_STRATEGY = {
    "type": "static",
    "static": {"max_chunk_size_tokens": MAX_CHUNK_TOKENS, "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS},
}

_encoding = tiktoken.get_encoding("cl100k_base")


def count_chunks(text: str) -> int:
    """Chunks the static strategy above produces for this text (the API doesn't report it)."""
    tokens = len(_encoding.encode(text))
    if tokens <= MAX_CHUNK_TOKENS:
        return 1
    return 1 + math.ceil((tokens - MAX_CHUNK_TOKENS) / (MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS))


@dataclass
class IndexedArticle:
    content_hash: str
    file_ids: list[str] = field(default_factory=list)
    healthy: bool = True


def resolve_vector_store(client: OpenAI, vector_store_id: str, name: str) -> str:
    if vector_store_id:
        return client.vector_stores.retrieve(vector_store_id).id
    for store in client.vector_stores.list(limit=100):
        if store.name == name:
            log.info("Using existing vector store %s (%s)", name, store.id)
            return store.id
    store = client.vector_stores.create(name=name)
    log.info("Created vector store %s (%s)", name, store.id)
    return store.id


class VectorStoreGateway:
    def __init__(self, client: OpenAI, vector_store_id: str):
        self.client = client
        self.vector_store_id = vector_store_id

    def indexed_articles(self) -> dict[str, IndexedArticle]:
        """Rebuild sync state from file attributes, so the job keeps no local state between runs."""
        indexed: dict[str, IndexedArticle] = {}
        for vs_file in self.client.vector_stores.files.list(vector_store_id=self.vector_store_id, limit=100):
            attrs = vs_file.attributes or {}
            article_id = str(attrs.get("article_id", ""))
            if not article_id:
                continue
            entry = indexed.setdefault(article_id, IndexedArticle(content_hash=str(attrs.get("content_hash", ""))))
            entry.file_ids.append(vs_file.id)
            if vs_file.status != "completed" or entry.content_hash != attrs.get("content_hash"):
                entry.healthy = False
        return indexed

    def upload_file(self, filename: str, text: str, attributes: dict) -> str:
        uploaded = self.client.files.create(
            file=(filename, io.BytesIO(text.encode("utf-8")), "text/markdown"),
            purpose="assistants",
        )
        vs_file = self.client.vector_stores.files.create_and_poll(
            vector_store_id=self.vector_store_id,
            file_id=uploaded.id,
            attributes=attributes,
            chunking_strategy=CHUNKING_STRATEGY,
        )
        if vs_file.status != "completed":
            self.delete_files([uploaded.id])
            raise RuntimeError(f"embedding failed: {vs_file.last_error}")
        return uploaded.id

    def delete_files(self, file_ids: list[str]) -> None:
        for file_id in file_ids:
            try:
                self.client.vector_stores.files.delete(file_id=file_id, vector_store_id=self.vector_store_id)
            except NotFoundError:
                pass
            try:
                self.client.files.delete(file_id)
            except NotFoundError:
                pass
