from __future__ import annotations

import time

import httpx

from occupational_health.core.errors import ApiError


class EmbeddingClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
        query_timeout: float | None = None,
        query_max_retries: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        # 在线检索必须尽快失败，文档批处理可以慢慢重试。
        self.query_timeout = query_timeout if query_timeout is not None else timeout
        self.query_max_retries = (
            query_max_retries if query_max_retries is not None else max_retries
        )
        self._client = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    def __enter__(self) -> EmbeddingClient:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        timeout = self.query_timeout if query else self.timeout
        max_retries = self.query_max_retries if query else self.max_retries
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = self._client.post(
                    f"{self.base_url}/embed",
                    json={"texts": texts, "query": query},
                    timeout=timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if len(payload["vectors"]) != len(texts):
                    raise ApiError(503, "MODEL_UNAVAILABLE", "向量服务返回数量不一致")
                return payload["vectors"]
            except httpx.TimeoutException as exc:
                last_exc = exc
                if not self._should_retry(attempt, max_retries):
                    raise ApiError(
                        503, "MODEL_LOADING", "向量服务响应超时，可能仍在加载模型"
                    ) from exc
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # 4xx means the request itself is invalid; only 5xx is worth retrying.
                if exc.response.status_code < 500:
                    raise ApiError(400, "EMBEDDING_ERROR", "向量服务请求失败") from exc
                if not self._should_retry(attempt, max_retries):
                    raise ApiError(
                        503, "MODEL_UNAVAILABLE", "向量服务暂时不可用"
                    ) from exc
            except httpx.HTTPError as exc:
                last_exc = exc
                if not self._should_retry(attempt, max_retries):
                    raise ApiError(
                        503, "MODEL_UNAVAILABLE", "向量服务不可用，请稍后重试"
                    ) from exc
            self._backoff(attempt)
        raise ApiError(503, "MODEL_UNAVAILABLE", "向量服务不可用") from last_exc

    def wait_until_ready(self, timeout: float) -> None:
        """Block until the embedding service answers its health check."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                response = self._client.get(f"{self.base_url}/health", timeout=2)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
        raise ApiError(503, "MODEL_LOADING", "向量服务未在限定时间内就绪")

    def _should_retry(self, attempt: int, max_retries: int) -> bool:
        return attempt < max_retries

    def _backoff(self, attempt: int) -> None:
        time.sleep(self.retry_backoff * (2**attempt))
