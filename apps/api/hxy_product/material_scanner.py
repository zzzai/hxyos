from __future__ import annotations

import os
import socket
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol


class SocketLike(Protocol):
    def __enter__(self): ...

    def __exit__(self, *_args): ...

    def settimeout(self, timeout: float) -> None: ...

    def sendall(self, payload: bytes) -> None: ...

    def recv(self, size: int) -> bytes: ...


Connector = Callable[..., SocketLike]


class MaterialScanError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class MaterialScanResult:
    status: Literal["clean", "blocked"]
    engine: str
    engine_version: str
    signature: str | None


def _bounded_response(connection: SocketLike, *, limit: int = 8192) -> str:
    response = bytearray()
    while len(response) < limit:
        chunk = connection.recv(min(4096, limit - len(response)))
        if not chunk:
            break
        response.extend(chunk)
        if b"\0" in chunk:
            break
    return bytes(response).split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()


class ClamAVScanner:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout_seconds: float,
        max_stream_bytes: int,
        connector: Connector = socket.create_connection,
        chunk_bytes: int = 1024 * 1024,
    ) -> None:
        if not host.strip():
            raise ValueError("ClamAV host is required")
        if not 1 <= port <= 65535:
            raise ValueError("ClamAV port is invalid")
        if timeout_seconds <= 0 or max_stream_bytes <= 0 or chunk_bytes <= 0:
            raise ValueError("ClamAV scanner limits must be positive")
        self.host = host.strip()
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.max_stream_bytes = max_stream_bytes
        self.chunk_bytes = min(chunk_bytes, max_stream_bytes)
        self.connector = connector
        self._version: str | None = None

    def _connect(self) -> SocketLike:
        connection = self.connector(
            (self.host, self.port),
            timeout=self.timeout_seconds,
        )
        connection.settimeout(self.timeout_seconds)
        return connection

    def _engine_version(self) -> str:
        if self._version is not None:
            return self._version
        with self._connect() as connection:
            connection.sendall(b"zVERSION\0")
            response = _bounded_response(connection)
        if not response.startswith("ClamAV "):
            raise MaterialScanError(
                "scanner_protocol_error",
                "file safety scanner returned an invalid version response",
                retryable=True,
            )
        self._version = response.split(maxsplit=2)[1].split("/", 1)[0][:80]
        return self._version

    def scan(self, source: Path) -> MaterialScanResult:
        try:
            size = source.stat().st_size
        except OSError as exc:
            raise MaterialScanError(
                "scanner_io_error",
                "file safety scanner could not read the source",
                retryable=False,
            ) from exc
        if size > self.max_stream_bytes:
            raise MaterialScanError(
                "scanner_size_exceeded",
                "source exceeds the configured file safety scan limit",
                retryable=False,
            )

        try:
            version = self._engine_version()
            with self._connect() as connection:
                connection.sendall(b"zINSTREAM\0")
                with source.open("rb") as input_file:
                    while chunk := input_file.read(self.chunk_bytes):
                        connection.sendall(struct.pack("!I", len(chunk)))
                        connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                response = _bounded_response(connection)
        except MaterialScanError:
            raise
        except (OSError, TimeoutError) as exc:
            raise MaterialScanError(
                "scanner_unavailable",
                "file safety scanner is temporarily unavailable",
                retryable=True,
            ) from exc

        if response == "stream: OK":
            return MaterialScanResult(
                status="clean",
                engine="clamav",
                engine_version=version,
                signature=None,
            )
        prefix = "stream: "
        suffix = " FOUND"
        if response.startswith(prefix) and response.endswith(suffix):
            signature = response[len(prefix) : -len(suffix)].strip()[:160]
            if signature:
                return MaterialScanResult(
                    status="blocked",
                    engine="clamav",
                    engine_version=version,
                    signature=signature,
                )
        raise MaterialScanError(
            "scanner_protocol_error",
            "file safety scanner returned an invalid scan response",
            retryable=True,
        )


def scanner_from_environment() -> ClamAVScanner:
    return ClamAVScanner(
        host=os.getenv("HXY_CLAMAV_HOST", "127.0.0.1"),
        port=int(os.getenv("HXY_CLAMAV_PORT", "3310")),
        timeout_seconds=float(os.getenv("HXY_CLAMAV_TIMEOUT_SECONDS", "10")),
        max_stream_bytes=int(
            os.getenv(
                "HXY_CLAMAV_MAX_STREAM_BYTES",
                os.getenv("HXY_MAX_UPLOAD_BYTES", "10485760"),
            )
        ),
    )
