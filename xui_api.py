import httpx
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


class XUIApi:
    """
    Version-agnostic client for 3x-ui panels.

    Supports both the legacy panel API (3x-ui <= v2.6.x, e.g. POST /panel/inbound/list,
    POST /server/status) and the newer API (3x-ui >= v2.8.x, e.g. GET
    /panel/api/inbounds/list, GET /panel/api/server/status).  The working style is
    auto-detected per panel and cached on the instance.
    """

    def __init__(self, url: str, username: str, password: str):
        self.base_url = url.rstrip('/')
        self.username = username
        self.password = password
        self.client = httpx.AsyncClient(verify=False, timeout=30)
        self.session_cookie = None
        self.cookie_name = None
        # "legacy" or "api"; None until first successful call
        self.api_style = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.aclose()

    async def aclose(self):
        await self.client.aclose()

    async def login(self) -> bool:
        login_url = f"{self.base_url}/login"
        credentials = {"username": self.username, "password": self.password}
        try:
            response = await self.client.post(login_url, data=credentials)
            if response.status_code == 200 and response.json().get("success"):
                for name in ("3x-ui", "session", "x-ui", "login"):
                    if response.cookies.get(name):
                        self.cookie_name = name
                        self.session_cookie = response.cookies.get(name)
                        break
                if not self.session_cookie and response.cookies:
                    self.cookie_name = next(iter(response.cookies))
                    self.session_cookie = response.cookies.get(self.cookie_name)
                return True
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"Error connecting to panel: {e}")
        return False

    async def _ensure_session(self) -> bool:
        if not self.session_cookie:
            return await self.login()
        return True

    def _auth(self) -> Optional[Dict[str, str]]:
        if self.session_cookie and self.cookie_name:
            return {self.cookie_name: self.session_cookie}
        return None

    async def _request(self, method: str, path: str) -> Optional[Dict[str, Any]]:
        """Perform an authenticated request; return the JSON body when success=true."""
        url = f"{self.base_url}{path}"
        try:
            if method == "GET":
                response = await self.client.get(url, cookies=self._auth())
            else:
                response = await self.client.post(url, cookies=self._auth())
            if response.status_code == 404:
                return None
            data = response.json()
            if data.get("success"):
                return data
        except (httpx.RequestError, ValueError):
            return None
        return None

    async def _call_first(self, candidates: List[Tuple[str, str, str]]) -> Optional[Dict[str, Any]]:
        """Try (style, method, path) candidates; prefer the detected style, fall back on the rest."""
        if self.api_style:
            candidates = sorted(
                candidates, key=lambda cand: 0 if cand[0] == self.api_style else 1
            )
        for style, method, path in candidates:
            data = await self._request(method, path)
            if data is not None:
                self.api_style = style
                return data
        return None

    async def get_inbounds(self) -> Optional[Dict[str, Any]]:
        if not await self._ensure_session():
            return None
        return await self._call_first([
            ("api", "GET", "/panel/api/inbounds/list"),
            ("legacy", "POST", "/panel/inbound/list"),
        ])

    async def get_all_clients(self) -> List[Dict[str, Any]]:
        """Return a flat list of all clients across all inbounds with traffic info.
        Each dict: {email, up, down, total, expiryTime, reset_day (from inbound)}
        """
        inbounds_data = await self.get_inbounds()
        if not inbounds_data or not inbounds_data.get("success"):
            return []

        clients: List[Dict[str, Any]] = []
        for inbound in inbounds_data.get("obj", []):
            for cs in inbound.get("clientStats", []):
                entry = {
                    "email": cs.get("email", ""),
                    "up": cs.get("up", 0),
                    "down": cs.get("down", 0),
                    "total": cs.get("total", 0),
                    "expiryTime": cs.get("expiryTime", 0),
                }
                clients.append(entry)
        return clients

    async def get_server_status(self) -> Optional[Dict[str, Any]]:
        if not await self._ensure_session():
            return None
        data = await self._call_first([
            ("api", "GET", "/panel/api/server/status"),
            ("legacy", "POST", "/server/status"),
        ])
        return data.get("obj") if data else None

    async def reset_all_client_traffic(self) -> bool:
        if not await self._ensure_session():
            return False
        data = await self._call_first([
            ("api", "POST", "/panel/api/inbounds/resetAllClientTraffics/-1"),
            ("legacy", "POST", "/panel/inbound/resetAllClientTraffics/-1"),
        ])
        return data is not None

    async def reset_client_traffic(self, inbound_id: str, email: str) -> bool:
        """Reset traffic for a single client by email within a specific inbound."""
        if not await self._ensure_session():
            return False
        data = await self._call_first([
            ("api", "POST", f"/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}"),
            ("legacy", "POST", f"/panel/inbound/{inbound_id}/resetClientTraffic/{email}"),
        ])
        return data is not None
