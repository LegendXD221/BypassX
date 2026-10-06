from __future__ import annotations

from pydantic import BaseModel, Field


class BypassRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=4096)


class BypassResponse(BaseModel):
    success: bool
    destination: str | None = None
    service: str | None = None
    method: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str


class RootResponse(BaseModel):
    name: str
    status: str
