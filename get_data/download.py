"""Bounded public downloads with cache checksums and retrieval receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def session():
    client = requests.Session()
    client.headers["User-Agent"] = "PlanIT-Control/0.1 (public environmental data ingestion)"
    client.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )))
    return client


def download(client, url, path, *, refresh=False, max_bytes=50_000_000):
    path = Path(path)
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if not refresh and path.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt["url"] != url or hashlib.sha256(path.read_bytes()).hexdigest() != receipt["sha256"]:
            raise ValueError(f"Cached source failed verification: {path.name}")
        return receipt
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        digest, size = hashlib.sha256(), 0
        with client.get(url, stream=True, timeout=(15, 90)) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError(f"Source exceeds download limit: {path.name}")
                    digest.update(chunk)
                    output.write(chunk)
        if size == 0:
            raise ValueError("Source download was empty")
        receipt = {"url": url, "sha256": digest.hexdigest(), "bytes": size,
                   "retrieved_at": datetime.now(timezone.utc).isoformat()}
        temporary.replace(path)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        return receipt
    finally:
        temporary.unlink(missing_ok=True)
