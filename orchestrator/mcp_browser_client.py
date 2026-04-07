"""
Async HTTP client for Chrome DevTools MCP server (chrome-devtools-mcp via mcp-proxy).

Setup:
  1. Start Chrome with remote debugging:
       chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\ChromeDebug"
  2. Run chrome-devtools-mcp via mcp-proxy (StreamableHTTP transport):
       npx mcp-proxy --transport streamablehttp --port 3200 -- node
         "C:\\...\\chrome-devtools-mcp\\build\\src\\bin\\chrome-devtools-mcp.js"
         --browser-url=http://127.0.0.1:9222
  3. Set MCP_DEVTOOLS_URL=http://localhost:3200 in .env

Protocol (MCP StreamableHTTP):
  - Requires Accept: application/json, text/event-stream on every request
  - Responses are SSE-formatted (even non-streaming ones): "data: {...}\n"
  - Requires initialize handshake → session ID returned in Mcp-Session-Id header
  - All subsequent requests include Mcp-Session-Id header
"""
from __future__ import annotations

import json
import logging

import httpx

log = logging.getLogger("getcontact")

_CONNECT_TIMEOUT = 5.0
_CALL_TIMEOUT = 30.0
_MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPBrowserError(Exception):
    """Raised when MCP server returns an error response."""
    pass


class MCPBrowserClient:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._available: bool | None = None  # Cache: None=unknown, True/False
        self._id_counter: int = 0
        self._session_id: str | None = None  # Set after initialize handshake

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _parse_response(self, resp: httpx.Response) -> dict:
        """Parse response — handles both JSON and SSE (text/event-stream) formats."""
        content_type = resp.headers.get("content-type", "")
        text = resp.text.strip()
        if "text/event-stream" in content_type:
            # SSE format: one or more "data: {...}" lines
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("data:"):
                    try:
                        return json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        pass
            return {"raw": text}
        try:
            return resp.json()
        except Exception:
            return {"raw": text}

    # ── Initialization handshake ──────────────────────────────────────────────

    async def _ensure_initialized(self) -> None:
        """Initialize MCP session if not already done (required before any tool call)."""
        if self._session_id is not None:
            return
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "getcontact-mcp-client", "version": "1.0.0"},
            },
        }
        base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as c:
            resp = await c.post(f"{self.base_url}/mcp", json=payload, headers=base_headers)
            resp.raise_for_status()

            # Extract session ID from response header (case-insensitive)
            session_id = (
                resp.headers.get("mcp-session-id")
                or resp.headers.get("Mcp-Session-Id", "")
            )
            if session_id:
                self._session_id = session_id
                log.debug("[MCPBrowser] Session initialized: %s", session_id[:8])

            # Send notifications/initialized (required by MCP spec)
            notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            await c.post(f"{self.base_url}/mcp", json=notif, headers=self._headers())

    # ── Availability ─────────────────────────────────────────────────────────

    async def is_available(self) -> bool:
        """Check if MCP server is reachable by doing initialize handshake."""
        if self._available is False:
            return False
        try:
            await self._ensure_initialized()
            self._available = True
            return True
        except Exception as e:
            log.debug("[MCPBrowser] Availability check failed: %s", e)
            self._available = False
            return False

    def reset_availability(self) -> None:
        """Reset cache + session so next call re-initializes."""
        self._available = None
        self._session_id = None

    # ── Browser Tools ─────────────────────────────────────────────────────────

    async def navigate(self, url: str) -> dict:
        return await self._call("browser_navigate", {"url": url})

    async def evaluate(self, script: str) -> dict:
        """Execute script in browser context.
        Script is wrapped as an IIFE so return statements work:
          (function() { <script> })()
        browser_evaluate treats the function param as () => (<expr>),
        so IIFE ensures the return value is propagated correctly.
        """
        iife = f"(function() {{ {script} }})()"
        return await self._call("browser_evaluate", {"function": iife})

    async def get_current_url(self) -> str:
        """Get current page URL. Parses '- Page URL:' from any browser_ tool response."""
        result = await self.evaluate("return window.location.href;")
        return self._extract_page_url(result) or ""

    @staticmethod
    def _extract_page_url(result: dict) -> str:
        """Extract page URL from browser_ tool markdown response text."""
        raw = result.get("raw", "")
        # Format: "- Page URL: https://..."
        for line in raw.split("\n"):
            line = line.strip()
            if "Page URL:" in line:
                url = line.split("Page URL:")[-1].strip()
                if url.startswith("http"):
                    return url
        # Fallback: ### Result section
        in_result = False
        for line in raw.split("\n"):
            line = line.strip()
            if line == "### Result":
                in_result = True
                continue
            if in_result and line.startswith("http"):
                return line
            if in_result and line.startswith("#"):
                break
        return ""

    async def snapshot(self) -> dict:
        return await self._call("browser_snapshot", {})

    async def screenshot(self) -> dict:
        return await self._call("browser_take_screenshot", {})

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _call(self, tool_name: str, args: dict) -> dict:
        await self._ensure_initialized()
        try:
            data = await self._do_call(tool_name, args)

            # Session expired → reinitialize and retry once
            if "error" in data:
                err_msg = str(data["error"]).lower()
                if "session" in err_msg or "not initialized" in err_msg:
                    log.debug("[MCPBrowser] Session expired, reinitializing...")
                    self._session_id = None
                    await self._ensure_initialized()
                    data = await self._do_call(tool_name, args)

            if "error" in data:
                raise MCPBrowserError(f"MCP JSON-RPC error: {data['error']}")

            result = data.get("result", {})
            if result.get("isError"):
                raise MCPBrowserError(f"MCP tool error: {result}")

            content = result.get("content", [])
            text = next((item["text"] for item in content if item.get("type") == "text"), "")
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"raw": text}

        except MCPBrowserError:
            raise
        except httpx.TimeoutException:
            self._available = None
            raise MCPBrowserError(f"MCP server timeout calling {tool_name}")
        except httpx.HTTPStatusError as e:
            raise MCPBrowserError(f"MCP HTTP error {e.response.status_code}: {tool_name}")
        except Exception as e:
            self._available = None
            raise MCPBrowserError(f"MCP call failed: {tool_name}: {e}")

    async def _do_call(self, tool_name: str, args: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        }
        async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as c:
            resp = await c.post(f"{self.base_url}/mcp", json=payload, headers=self._headers())
            resp.raise_for_status()
            return self._parse_response(resp)


# Singleton per URL
_clients: dict[str, MCPBrowserClient] = {}


def get_mcp_browser(url: str | None = None) -> MCPBrowserClient | None:
    from orchestrator.config import cfg
    target_url = url or cfg.get("MCP_DEVTOOLS_URL", "")
    if not target_url:
        return None
    if target_url not in _clients:
        _clients[target_url] = MCPBrowserClient(target_url)
    return _clients[target_url]
