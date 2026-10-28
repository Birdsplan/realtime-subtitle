import json
import threading
import time
from pathlib import Path


class TranscriptLogger:
    """Persist final subtitle segments as both JSONL events and a readable text log."""

    def __init__(self, log_dir="logs", session_id=None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or time.strftime("%Y%m%d_%H%M%S")
        self.jsonl_path = self.log_dir / f"transcript_{self.session_id}.jsonl"
        self.text_path = self.log_dir / f"transcript_{self.session_id}.txt"
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.records = {}
        self._lock = threading.Lock()
        self._rewrite_text_log()

    def record(self, chunk_id, original=None, translated=None, status="updated", error=None):
        """Record or update a final subtitle segment."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            record = self.records.setdefault(
                int(chunk_id),
                {
                    "chunk_id": int(chunk_id),
                    "first_seen": timestamp,
                    "original": "",
                    "translated": "",
                    "status": "",
                    "error": "",
                },
            )
            record["updated_at"] = timestamp
            record["status"] = status
            if original is not None:
                record["original"] = original
            if translated is not None:
                record["translated"] = translated
            if error is not None:
                record["error"] = str(error)

            event = dict(record)
            event["event_at"] = timestamp
            self._append_jsonl(event)
            self._rewrite_text_log()
            return dict(record)

    def _append_jsonl(self, event):
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _rewrite_text_log(self):
        with self.text_path.open("w", encoding="utf-8") as f:
            f.write(f"Transcript session: {self.session_id}\n")
            f.write(f"Started at: {self.started_at}\n")
            f.write("=" * 60 + "\n\n")

            for chunk_id in sorted(self.records):
                record = self.records[chunk_id]
                f.write(f"[{record.get('first_seen', '')}] #{chunk_id} {record.get('status', '')}\n")
                f.write(f"Original: {record.get('original', '')}\n")
                f.write(f"Translation: {record.get('translated', '')}\n")
                if record.get("error"):
                    f.write(f"Error: {record['error']}\n")
                f.write("-" * 40 + "\n")
