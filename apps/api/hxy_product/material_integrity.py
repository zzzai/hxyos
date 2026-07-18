from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import BinaryIO


class MaterialSourceUnavailable(Exception):
    pass


class MaterialSourceIntegrityMismatch(Exception):
    pass


def _open_regular_source(source: Path) -> BinaryIO:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as error:
        raise MaterialSourceUnavailable from error

    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise MaterialSourceUnavailable
        return os.fdopen(descriptor, "rb")
    except Exception:
        os.close(descriptor)
        raise


def copy_verified_source(
    source: Path,
    destination: BinaryIO,
    *,
    expected_size: int,
    expected_sha256: str,
) -> None:
    digest = hashlib.sha256()
    size = 0
    try:
        with _open_regular_source(source) as stream:
            while chunk := stream.read(1024 * 1024):
                destination.write(chunk)
                size += len(chunk)
                digest.update(chunk)
    except MaterialSourceUnavailable:
        raise
    except OSError as error:
        raise MaterialSourceUnavailable from error

    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise MaterialSourceIntegrityMismatch


def verify_source_integrity(
    source: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> None:
    digest = hashlib.sha256()
    size = 0
    try:
        with _open_regular_source(source) as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
    except MaterialSourceUnavailable:
        raise
    except OSError as error:
        raise MaterialSourceUnavailable from error

    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise MaterialSourceIntegrityMismatch
