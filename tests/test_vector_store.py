from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from helpcenter_sync.vector_store import MAX_CHUNK_TOKENS, VectorStoreGateway, count_chunks


def _gateway():
    client = MagicMock()
    client.files.create.return_value = SimpleNamespace(id="f1")
    return VectorStoreGateway(client, "vs_1"), client


def test_upload_attaches_file_with_attributes_and_static_chunking():
    gateway, client = _gateway()
    client.vector_stores.files.create_and_poll.return_value = SimpleNamespace(status="completed")

    assert gateway.upload_file("guide.md", "# Guide", {"article_id": "1"}) == "f1"
    kwargs = client.vector_stores.files.create_and_poll.call_args.kwargs
    assert kwargs["attributes"] == {"article_id": "1"}
    assert kwargs["chunking_strategy"]["static"]["max_chunk_size_tokens"] == MAX_CHUNK_TOKENS
    assert client.files.create.call_args.kwargs["file"][0] == "guide.md"


def test_failed_embedding_deletes_the_uploaded_file():
    gateway, client = _gateway()
    client.vector_stores.files.create_and_poll.return_value = SimpleNamespace(status="failed", last_error="boom")

    with pytest.raises(RuntimeError):
        gateway.upload_file("guide.md", "# Guide", {"article_id": "1"})
    client.files.delete.assert_called_once_with("f1")


def test_indexed_articles_groups_by_article_and_flags_unhealthy_files():
    gateway, client = _gateway()
    client.vector_stores.files.list.return_value = [
        SimpleNamespace(id="f1", status="completed", attributes={"article_id": "1", "content_hash": "h"}),
        SimpleNamespace(id="f2", status="failed", attributes={"article_id": "1", "content_hash": "h"}),
        SimpleNamespace(id="f3", status="completed", attributes={"article_id": "2", "content_hash": "x"}),
        SimpleNamespace(id="f4", status="completed", attributes={}),
    ]
    indexed = gateway.indexed_articles()
    assert indexed["1"].file_ids == ["f1", "f2"] and not indexed["1"].healthy
    assert indexed["2"].healthy and set(indexed) == {"1", "2"}


def test_chunk_count_follows_the_static_strategy():
    assert count_chunks("short article") == 1
    assert count_chunks("word " * 5000) == 2
    assert count_chunks("word " * 9000) == 3
