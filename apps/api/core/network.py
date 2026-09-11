"""
AIDSE Platform — Local Network Isolation & Free Port Allocation
Section 3: Network Security & Isolation

Provides dynamic port selection for binding FastAPI exclusively to 127.0.0.1
on an available loopback port, avoiding fixed ports or public 0.0.0.0 bindings.
"""
from __future__ import annotations

import socket


def find_free_loopback_port() -> int:
    """
    Find and return a free TCP port available on 127.0.0.1 (loopback interface).
    Binds temporarily to port 0, retrieves the OS-assigned port, and closes the socket.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = sock.getsockname()[1]
        return port


def validate_host_binding(host: str) -> None:
    """
    Guard: ensure host binding is restricted strictly to loopback (127.0.0.1 / localhost).
    Raises ValueError if 0.0.0.0 or a non-loopback public interface is configured.
    """
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    forbidden_hosts = {"0.0.0.0", "::", "0:0:0:0:0:0:0:0"}
    if host in forbidden_hosts or (host not in allowed_hosts and not host.startswith("127.")):
        raise ValueError(
            f"Security Error: Binding to '{host}' is strictly forbidden in desktop mode. "
            "FastAPI must bind strictly to 127.0.0.1 (loopback interface)."
        )
