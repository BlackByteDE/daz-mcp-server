"""Map dazpy and httpx exceptions to FastMCP ToolError."""
from __future__ import annotations

import os

import httpx
from fastmcp.exceptions import ToolError

import dazpy.exceptions as daz_exc

from ._client import DAZ_TIMEOUT, TOKEN_FILE


def handle_dazpy_error(exc: Exception) -> None:
    """Re-raise a dazpy exception as a ToolError with a helpful message.

    Call this inside an except block:  handle_dazpy_error(exc)
    The function always raises; it never returns normally.
    """
    if isinstance(exc, daz_exc.ConnectionError):
        raise ToolError(
            "Cannot connect to DAZ Studio. Ensure DAZ Studio is running with "
            "the DazScriptServer plugin active."
        ) from exc
    if isinstance(exc, daz_exc.TimeoutError):
        raise ToolError(
            f"Request timed out after {DAZ_TIMEOUT}s. "
            "Increase the timeout by setting the DAZ_TIMEOUT environment variable."
        ) from exc
    if isinstance(exc, daz_exc.AuthenticationError):
        source = "DAZ_API_TOKEN environment variable" if os.environ.get("DAZ_API_TOKEN") else TOKEN_FILE
        raise ToolError(
            f"Authentication failed. Verify the API token in: {source}"
        ) from exc
    if isinstance(exc, daz_exc.NodeNotFoundError):
        raise ToolError(str(exc)) from exc
    if isinstance(exc, (daz_exc.ScriptRuntimeError, daz_exc.ScriptSyntaxError)):
        raise ToolError(exc.diagnostic) from exc
    raise exc


# ---------------------------------------------------------------------------
# Legacy helpers for existing httpx-based code paths in server.py
# ---------------------------------------------------------------------------

def handle_network_error(exc: Exception) -> None:
    """Re-raise httpx network errors as ToolError."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        raise ToolError(
            "Cannot connect to DAZ Studio. Ensure DAZ Studio is running with "
            "the DazScriptServer plugin active."
        ) from exc
    if isinstance(exc, httpx.TimeoutException):
        raise ToolError(
            f"Request timed out after {DAZ_TIMEOUT}s. "
            "Increase the timeout by setting the DAZ_TIMEOUT environment variable."
        ) from exc
    raise exc


def check_response(response: httpx.Response) -> None:
    """Raise ToolError for known HTTP error statuses."""
    if response.status_code == 401:
        source = "DAZ_API_TOKEN environment variable" if os.environ.get("DAZ_API_TOKEN") else TOKEN_FILE
        raise ToolError(
            f"Authentication failed (HTTP 401). Verify the API token in: {source}"
        )
    response.raise_for_status()
