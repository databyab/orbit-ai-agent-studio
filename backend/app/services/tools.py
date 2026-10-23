import ipaddress
import re
from urllib.parse import urlparse
import httpx
from typing import Dict, Any, Optional

class SafeToolExecutor:
    """
    Executes Server-Side REST Actions with SSRF protection,
    templated parameter interpolation, and strict timeout boundaries.
    """
    BLOCKED_IP_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),      # Loopback
        ipaddress.ip_network("10.0.0.0/8"),       # Private A
        ipaddress.ip_network("172.16.0.0/12"),    # Private B
        ipaddress.ip_network("192.168.0.0/16"),   # Private C
        ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud metadata
    ]

    @classmethod
    def validate_url(cls, url: str):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}. Must be http or https.")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL must have a valid hostname.")

        # Check if IP address directly
        try:
            ip = ipaddress.ip_address(hostname)
            for net in cls.BLOCKED_IP_NETWORKS:
                if ip in net:
                    raise ValueError(f"Access to private IP range {ip} is restricted for security (SSRF prevention).")
        except ValueError as e:
            if "restricted" in str(e):
                raise e
            # Not an IP literal, it's a domain name

    @classmethod
    def interpolate_template(cls, template: str, params: Dict[str, Any]) -> str:
        """
        Replaces {{param_name}} with values from params dict.
        """
        if not template:
            return ""
        
        def replace(match):
            key = match.group(1).strip()
            return str(params.get(key, ""))

        return re.sub(r"\{\{([a-zA-Z0-9_\-]+)\}\}", replace, template)

    async def execute_server_action(
        self,
        method: str,
        url_template: str,
        headers: Dict[str, str],
        body_template: Optional[str],
        input_args: Dict[str, Any],
        timeout: float = 8.0
    ) -> Dict[str, Any]:
        # Interpolate URL and Body
        target_url = self.interpolate_template(url_template, input_args)
        self.validate_url(target_url)

        req_headers = {k: self.interpolate_template(v, input_args) for k, v in headers.items()}
        req_headers.setdefault("User-Agent", "ChatbaseReplicaToolExecutor/1.0")

        req_body = None
        if body_template:
            interpolated_body = self.interpolate_template(body_template, input_args)
            req_body = interpolated_body.encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.request(
                method=method.upper(),
                url=target_url,
                headers=req_headers,
                content=req_body
            )
            
            try:
                data = resp.json()
            except Exception:
                data = resp.text

            return {
                "status_code": resp.status_code,
                "data": data,
                "success": resp.is_success
            }
