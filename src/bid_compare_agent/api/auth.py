from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

from fastapi import Request


class AuthConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ApiAuthConfig:
    mode: str = "disabled"
    api_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in {"disabled", "api_key"}:
            raise AuthConfigurationError(f"不支持的鉴权模式: {self.mode}")
        if self.mode == "api_key" and not self.api_keys:
            raise AuthConfigurationError("api_key 模式至少需要一个 BID_COMPARE_API_KEYS")
        if any(len(key) < 16 for key in self.api_keys):
            raise AuthConfigurationError("API Key 长度不能少于 16 个字符")

    @classmethod
    def from_env(cls) -> "ApiAuthConfig":
        mode = os.environ.get("BID_COMPARE_AUTH_MODE", "disabled").strip().lower()
        keys = tuple(
            value.strip()
            for value in os.environ.get("BID_COMPARE_API_KEYS", "").split(",")
            if value.strip()
        )
        return cls(mode=mode, api_keys=keys)

    @staticmethod
    def _request_token(request: Request) -> str | None:
        authorization = request.headers.get("authorization", "").strip()
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        direct = request.headers.get("x-api-key", "").strip()
        return direct or None

    @staticmethod
    def _actor_id(token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"api-key:{digest[:16]}"

    def authenticate(self, request: Request) -> str | None:
        if self.mode == "disabled":
            return "local-anonymous"
        token = self._request_token(request)
        if token is None:
            return None
        for expected in self.api_keys:
            if hmac.compare_digest(token, expected):
                return self._actor_id(token)
        return None
