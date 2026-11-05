import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import ClassVar


@dataclass
class RunReport:
    started_at: float
    dry_run: bool = False
    vector_store_id: str = ""
    fetched: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    failed: int = 0
    files_uploaded: int = 0
    chunks_embedded: int = 0
    duration_s: float = 0.0
    failures: list[dict] = field(default_factory=list)
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def record_success(self, updated: bool, chunks: int) -> None:
        with self._lock:
            if updated:
                self.updated += 1
            else:
                self.added += 1
            self.files_uploaded += 1
            self.chunks_embedded += chunks

    def record_failure(self, article_id: str, slug: str, error: str) -> None:
        with self._lock:
            self.failed += 1
            self.failures.append({"article_id": article_id, "slug": slug, "error": error[:500]})

    def finish(self) -> "RunReport":
        self.duration_s = round(time.time() - self.started_at, 1)
        return self

    def to_json(self) -> str:
        data = asdict(self)
        data["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_at))
        return json.dumps(data, indent=2)

    def summary_line(self) -> str:
        return (f"fetched={self.fetched} added={self.added} updated={self.updated} "
                f"skipped={self.skipped} removed={self.removed} failed={self.failed} "
                f"files_uploaded={self.files_uploaded} chunks_embedded={self.chunks_embedded} "
                f"duration={self.duration_s}s" + (" (dry run)" if self.dry_run else ""))

    def write(self, output_dir: str) -> None:
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "run-report.json"), "w", encoding="utf-8") as f:
            f.write(self.to_json())
