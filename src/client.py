"""Resilient async HTTP client with proxy support and retry logic."""

import logging
import os

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

PROXY_URL = os.getenv("PROXY_URL")  # e.g. http://user:pass@proxy:port


def build_client() -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with optional proxy."""
    kwargs: dict = {
        "timeout": httpx.Timeout(30.0, connect=10.0),
        "follow_redirects": True,
        "http2": True,
    }
    if PROXY_URL:
        kwargs["proxy"] = PROXY_URL
    return httpx.AsyncClient(**kwargs)


# Retry on timeouts, 429 and 5xx – exponential backoff (2s, 4s, 8s)
@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def fetch(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """Perform a GET request with automatic retry."""
    response = await client.get(url, **kwargs)
    if response.status_code == 429 or response.status_code >= 500:
        response.raise_for_status()
    return response


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def post(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """Perform a POST request with automatic retry."""
    response = await client.post(url, **kwargs)
    if response.status_code == 429 or response.status_code >= 500:
        response.raise_for_status()
    return response
