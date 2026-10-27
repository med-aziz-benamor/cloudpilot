"""Tests for api.deps.client_ip: the rate-limiter's IP source must not be
spoofable via a client-suppliable header."""

from __future__ import annotations

from dataclasses import dataclass

from cloudpilot.api.deps import client_ip


@dataclass
class _FakeClient:
    host: str


class _FakeRequest:
    def __init__(self, headers: dict[str, str], client_host: str | None = "10.0.0.5") -> None:
        self.headers = headers
        self.client = _FakeClient(client_host) if client_host else None


def test_trusts_x_real_ip_over_a_spoofable_forwarded_for() -> None:
    # nginx sets X-Real-IP itself ($remote_addr) — a client cannot override it.
    req = _FakeRequest({"x-real-ip": "203.0.113.9", "x-forwarded-for": "1.2.3.4, 203.0.113.9"})
    assert client_ip(req) == "203.0.113.9"  # type: ignore[arg-type]


def test_falls_back_to_the_last_forwarded_for_hop_not_the_first() -> None:
    # The first value is whatever the client sent; only the last one is the
    # hop nginx itself appended, so a spoofed first value must not win.
    req = _FakeRequest({"x-forwarded-for": "1.2.3.4, 203.0.113.9"})
    assert client_ip(req) == "203.0.113.9"  # type: ignore[arg-type]


def test_falls_back_to_the_socket_peer_with_no_proxy_headers() -> None:
    req = _FakeRequest({})
    assert client_ip(req) == "10.0.0.5"  # type: ignore[arg-type]


def test_returns_unknown_with_no_headers_and_no_client() -> None:
    req = _FakeRequest({}, client_host=None)
    assert client_ip(req) == "unknown"  # type: ignore[arg-type]
