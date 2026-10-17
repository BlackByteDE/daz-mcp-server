"""_wait_for_async_result must not report a still-running request as a
successful call that returned None."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import respx
from fastmcp.exceptions import ToolError

from vangard_daz_mcp._client import set_http_client
from vangard_daz_mcp._mcp import _wait_for_async_result

BASE_URL = "http://localhost:18811"


@pytest_asyncio.fixture(autouse=True)
async def http_client():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        set_http_client(client)
        yield client
    set_http_client(None)


@pytest.mark.parametrize("status", ["running", "queued"])
async def test_timeout_while_running_raises(status):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/requests/script-1/result").mock(
            return_value=httpx.Response(200, json={"status": status, "result": None}))
        with pytest.raises(ToolError, match=status):
            await _wait_for_async_result("script-1", timeout_seconds=1)


async def test_completed_returns_result():
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/requests/script-1/result").mock(
            return_value=httpx.Response(200, json={"status": "completed", "result": {"ok": 1}}))
        assert await _wait_for_async_result("script-1") == {"ok": 1}
