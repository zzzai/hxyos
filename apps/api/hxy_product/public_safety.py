from __future__ import annotations

import re


_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![:/\w])(?:[A-Za-z]:[\\/]|/(?!/))[^\s，。；;]+"
)
_HXY_RELATIVE_PATH_RE = re.compile(
    r"(?<!\w)(?:knowledge|data|apps|packages|ops|scripts|tests)/(?:[^\s，。；;]+)"
)


def redact_internal_paths(value: str) -> str:
    redacted = _ABSOLUTE_PATH_RE.sub("[已隐藏内部路径]", value)
    return _HXY_RELATIVE_PATH_RE.sub("[已隐藏内部路径]", redacted)
