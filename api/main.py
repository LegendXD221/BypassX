from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shortlink_bypass.bypass import get_handler

from .models import BypassRequest, BypassResponse, HealthResponse, RootResponse

MAX_URL_LENGTH = int(os.getenv("MAX_URL_LENGTH", "4096"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "60"))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

app = FastAPI(title="Shortlink Bypass API", version="1.0.0")

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").strip()
allowed_origins = [origin.strip() for origin in frontend_url.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


class URLValidationError(ValueError):
    pass


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_url(raw_url: str) -> str:
    if not isinstance(raw_url, str):
        raise URLValidationError("URL must be a string")
    value = raw_url.strip()
    if len(value) > MAX_URL_LENGTH:
        raise URLValidationError("URL exceeds the maximum allowed length")

    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise URLValidationError("Only HTTP and HTTPS URLs are supported")
    if not parsed.hostname or parsed.username or parsed.password:
        raise URLValidationError("URL must contain a valid public hostname")
    if parsed.fragment:
        # Fragments are not sent to servers and can hide misleading payloads.
        value = value.split("#", 1)[0]
        parsed = urlparse(value)
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        raise URLValidationError("Localhost URLs are not allowed")

    try:
        direct_ip = ipaddress.ip_address(hostname)
    except ValueError:
        direct_ip = None
    if direct_ip is not None:
        if not _is_public_ip(str(direct_ip)):
            raise URLValidationError("Private or reserved addresses are not allowed")
    else:
        try:
            addresses = {
                result[4][0]
                for result in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            }
        except (OSError, socket.gaierror):
            raise URLValidationError("Hostname could not be resolved") from None
        if not addresses or any(not _is_public_ip(address) for address in addresses):
            raise URLValidationError("Hostname resolves to a private or reserved address")

    return value


def _client_ip(request: Request) -> str:
    # Do not trust forwarded headers unless a trusted proxy is explicitly configured.
    return request.client.host if request.client else "unknown"


def _allow_request(client_ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets[client_ip]
        while bucket and now - bucket[0] >= RATE_LIMIT_WINDOW:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            return False
        bucket.append(now)
        return True


def _service_name(url: str) -> str:
    return (urlparse(url).hostname or "unknown").lower()


def _resolve(handler, url: str) -> str | None:
    destination = handler(url)
    if not destination:
        return None
    return _validate_url(destination)


@app.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    return RootResponse(name="Shortlink Bypass API", status="online")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/bypass", response_model=BypassResponse)
async def bypass_endpoint(payload: BypassRequest, request: Request) -> BypassResponse | JSONResponse:
    if not _allow_request(_client_ip(request)):
        return JSONResponse(status_code=429, content={"success": False, "error": "Rate limit exceeded"})

    try:
        url = _validate_url(payload.url)
        handler, method = get_handler(url)
        if handler is None:
            return JSONResponse(status_code=422, content={"success": False, "error": "Unsupported service"})
        destination = await asyncio.wait_for(
            run_in_threadpool(_resolve, handler, url), timeout=REQUEST_TIMEOUT
        )
        if not destination:
            return JSONResponse(status_code=502, content={"success": False, "error": "Unable to resolve this URL"})
        return BypassResponse(
            success=True,
            destination=destination,
            service=_service_name(url),
            method=method,
        )
    except URLValidationError as exc:
        return JSONResponse(status_code=400, content={"success": False, "error": str(exc)})
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"success": False, "error": "Request timed out"})
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid URL"})
    except Exception:
        # Never expose resolver, network, or filesystem details to API clients.
        return JSONResponse(status_code=502, content={"success": False, "error": "Resolver failed"})
