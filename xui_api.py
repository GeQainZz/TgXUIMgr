# xui_api.py
import httpx
from typing import Dict, Any, Optional

class XUIApi:
    def __init__(self, url: str, username: str, password: str):
        self.base_url = url.rstrip('/')
        self.username = username
        self.password = password
        self.client = httpx.AsyncClient(verify=False) # Insecure, but common for self-signed certs
        self.session_cookie = None

    async def login(self) -> bool:
        """Logs into the panel and stores the session cookie."""
        login_url = f"{self.base_url}/login"
        credentials = {"username": self.username, "password": self.password}
        try:
            response = await self.client.post(login_url, data=credentials)
            if response.status_code == 200 and response.json().get("success"):
                self.session_cookie = response.cookies.get("session")
                return True
        except httpx.RequestError as e:
            print(f"Error connecting to panel: {e}")
        return False

    async def get_inbounds(self) -> Optional[Dict[str, Any]]:
        """Fetches the list of all inbounds."""
        if not self.session_cookie:
            if not await self.login():
                return None
        
        list_url = f"{self.base_url}/panel/inbound/list"
        cookies = {"session": self.session_cookie}
        try:
            response = await self.client.post(list_url, cookies=cookies)
            if response.status_code == 200 and response.json().get("success"):
                return response.json()
        except httpx.RequestError as e:
            print(f"Error fetching inbounds: {e}")
        return None

    async def get_server_status(self) -> Optional[Dict[str, Any]]:
        """Fetches the server's system status."""
        if not self.session_cookie:
            if not await self.login():
                return None
        
        status_url = f"{self.base_url}/server/status"
        cookies = {"session": self.session_cookie}
        try:
            response = await self.client.post(status_url, cookies=cookies)
            if response.status_code == 200 and response.json().get("success"):
                return response.json().get("obj")
        except httpx.RequestError:
            return None
        return None

    async def reset_all_client_traffic(self) -> bool:
        """Resets all client traffic for all inbounds."""
        if not self.session_cookie:
            if not await self.login():
                return False
        
        reset_url = f"{self.base_url}/panel/inbound/resetAllClientTraffics/-1"
        cookies = {"session": self.session_cookie}
        try:
            response = await self.client.post(reset_url, cookies=cookies)
            return response.status_code == 200 and response.json().get("success")
        except httpx.RequestError as e:
            print(f"Error resetting traffic: {e}")
            return False

