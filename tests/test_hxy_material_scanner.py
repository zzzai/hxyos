from __future__ import annotations

import importlib
import socket
import struct
from pathlib import Path

import pytest


class FakeSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = bytearray()
        self.timeout: float | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def sendall(self, payload: bytes) -> None:
        self.sent.extend(payload)

    def recv(self, _size: int) -> bytes:
        response, self.response = self.response, b""
        return response


def test_clamav_scanner_streams_file_and_returns_clean_result(tmp_path: Path) -> None:
    module = importlib.import_module("apps.api.hxy_product.material_scanner")
    source = tmp_path / "upload.txt"
    source.write_bytes(b"store operating note")
    version_socket = FakeSocket(b"ClamAV 1.4.2/27300/Sun Jul 19 00:00:00 2026\0")
    scan_socket = FakeSocket(b"stream: OK\0")
    sockets = iter((version_socket, scan_socket))

    scanner = module.ClamAVScanner(
        host="127.0.0.1",
        port=3310,
        timeout_seconds=3,
        max_stream_bytes=1024,
        connector=lambda *_args, **_kwargs: next(sockets),
    )

    result = scanner.scan(source)

    assert result.status == "clean"
    assert result.engine == "clamav"
    assert result.engine_version == "1.4.2"
    assert result.signature is None
    assert version_socket.sent == b"zVERSION\0"
    assert scan_socket.sent.startswith(b"zINSTREAM\0")
    assert struct.pack("!I", len(source.read_bytes())) + source.read_bytes() in scan_socket.sent
    assert scan_socket.sent.endswith(struct.pack("!I", 0))


def test_clamav_scanner_returns_blocked_signature_without_exposing_path(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("apps.api.hxy_product.material_scanner")
    source = tmp_path / "private-upload.txt"
    source.write_bytes(b"unsafe")
    sockets = iter(
        (
            FakeSocket(b"ClamAV 1.4.2/27300/Sun Jul 19 00:00:00 2026\0"),
            FakeSocket(b"stream: Eicar-Signature FOUND\0"),
        )
    )
    scanner = module.ClamAVScanner(
        host="clamav",
        port=3310,
        timeout_seconds=3,
        max_stream_bytes=1024,
        connector=lambda *_args, **_kwargs: next(sockets),
    )

    result = scanner.scan(source)

    assert result.status == "blocked"
    assert result.signature == "Eicar-Signature"
    assert str(source) not in repr(result)


def test_clamav_scanner_marks_transport_timeout_retryable(tmp_path: Path) -> None:
    module = importlib.import_module("apps.api.hxy_product.material_scanner")
    source = tmp_path / "upload.txt"
    source.write_bytes(b"content")

    def timeout(*_args, **_kwargs):
        raise socket.timeout("private endpoint timed out")

    scanner = module.ClamAVScanner(
        host="clamav",
        port=3310,
        timeout_seconds=1,
        max_stream_bytes=1024,
        connector=timeout,
    )

    with pytest.raises(module.MaterialScanError) as raised:
        scanner.scan(source)

    assert raised.value.code == "scanner_unavailable"
    assert raised.value.retryable is True
    assert str(source) not in str(raised.value)
