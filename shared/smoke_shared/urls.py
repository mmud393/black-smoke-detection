"""Camera source URL validation and sanitization (SSRF-aware)."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = {"rtsp", "rtsps"}


class SourceError(ValueError):
    pass


def sanitize_rtsp(url: str) -> str:
    """Return the URL with credentials and query removed (safe for display/logs)."""
    p = urlsplit(url)
    host = p.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = host + (f":{p.port}" if p.port else "")
    return urlunsplit((p.scheme, netloc, p.path, "", ""))


def validate_rtsp(url: str, allowed_cidrs: list[str] | None = None) -> str:
    """Validate scheme/host; optionally enforce camera-subnet allowlist. Returns sanitized URL."""
    try:
        p = urlsplit(url.strip())
        host = p.hostname
        p.port  # noqa: B018 - raises on invalid port
    except ValueError as exc:
        raise SourceError("invalid URL") from exc
    if p.scheme not in ALLOWED_SCHEMES:
        raise SourceError("only rtsp:// and rtsps:// URLs are allowed")
    if not host:
        raise SourceError("URL has no host")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise SourceError("loopback/link-local/multicast addresses are not allowed")
        if allowed_cidrs and not any(ip in ipaddress.ip_network(c, strict=False) for c in allowed_cidrs):
            raise SourceError("host is outside the allowed camera subnets")
    except ValueError as exc:
        if isinstance(exc, SourceError):
            raise
        # hostname, not literal IP: allowed only when no CIDR allowlist is enforced
        if allowed_cidrs:
            raise SourceError("use an IP address inside the allowed camera subnets") from exc
        if host.lower() in {"localhost", "metadata.google.internal"}:
            raise SourceError("host not allowed") from exc
    return sanitize_rtsp(url)
