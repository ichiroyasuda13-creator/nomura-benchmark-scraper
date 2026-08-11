from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from app.config import LOG_DIR, REQUEST_DELAY_SEC, USER_AGENT


class HttpClient:
    def __init__(self, delay_sec: float = REQUEST_DELAY_SEC) -> None:
        self.delay_sec = delay_sec
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request_at = 0.0

    def _sleep_if_needed(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay_sec:
            time.sleep(self.delay_sec - elapsed)

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float = 60,
        stream: bool = False,
    ) -> requests.Response:
        self._sleep_if_needed()
        response = self.session.get(url, params=params, timeout=timeout, stream=stream)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response

    def head(self, url: str, *, timeout: float = 30) -> requests.Response:
        self._sleep_if_needed()
        response = self.session.head(url, timeout=timeout, allow_redirects=True)
        self._last_request_at = time.monotonic()
        return response


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        LOG_DIR / "nomura_benchmark.log",
        rotation="10 MB",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
    )
    logger.add(lambda msg: print(msg, end=""), colorize=False)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
