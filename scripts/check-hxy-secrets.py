#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SK_LIKE_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
ENV_ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+)?(?P<key>POSTGRES_PASSWORD|HXY_MODEL_API_KEY|HXY_API_TOKEN|HXY_DATABASE_URL)\s*=\s*(?P<value>[^#]+)"
)
URL_WITH_PASSWORD_RE = re.compile(
    r"(?:postgres(?:ql)?|mysql|redis)://[^:\s/@]+:(?P<password>[^@\s]+)@"
)
DSN_PASSWORD_FIELD_RE = re.compile(r"(?:^|\s)password=(?P<password>[^\s\"']+)")

PLACEHOLDER_TOKENS = {
    "",
    "change-me",
    "changeme",
    "dummy",
    "example",
    "fake",
    "placeholder",
    "redacted",
    "test",
    "todo",
    "your-key-here",
    "your-secret-here",
}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    rule: str
    key: str | None = None


def _git_files(repo: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [repo / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def _is_binary(data: bytes) -> bool:
    return b"\0" in data


def _normalized(value: str) -> str:
    return value.strip().strip("'\"`").strip("<>{}").lower()


def _is_placeholder(value: str) -> bool:
    stripped = value.strip().strip("'\"`")
    lowered = _normalized(stripped)
    if lowered in PLACEHOLDER_TOKENS:
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    if stripped.startswith("${") and stripped.endswith("}"):
        return True
    if lowered.startswith("your_") or lowered.startswith("your-"):
        return True
    return False


def _is_variable_or_placeholder(value: str) -> bool:
    return _is_placeholder(value) or "$" in value or "{" in value or "}" in value


def _contains_hardcoded_database_password(value: str) -> bool:
    for match in URL_WITH_PASSWORD_RE.finditer(value):
        if not _is_variable_or_placeholder(match.group("password")):
            return True
    for match in DSN_PASSWORD_FIELD_RE.finditer(value):
        if not _is_variable_or_placeholder(match.group("password")):
            return True
    return False


def _should_flag_assignment(key: str, value: str) -> bool:
    if _is_placeholder(value):
        return False
    if key == "HXY_DATABASE_URL":
        return _contains_hardcoded_database_password(value)
    if _is_variable_or_placeholder(value):
        return False
    return True


def scan_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for _ in SK_LIKE_RE.finditer(line):
            findings.append(Finding(path=path, line=line_no, rule="sk-like-api-key"))

        assignment = ENV_ASSIGNMENT_RE.search(line)
        if assignment and _should_flag_assignment(assignment.group("key"), assignment.group("value")):
            findings.append(
                Finding(
                    path=path,
                    line=line_no,
                    rule="secret-env-assignment",
                    key=assignment.group("key"),
                )
            )

        for match in URL_WITH_PASSWORD_RE.finditer(line):
            if not _is_variable_or_placeholder(match.group("password")):
                findings.append(Finding(path=path, line=line_no, rule="url-with-password"))

    return findings


def scan_repo(repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _git_files(repo):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if _is_binary(data):
            continue
        rel_path = path.relative_to(repo)
        findings.extend(scan_text(rel_path, data.decode("utf-8", errors="replace")))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan committed and commit-eligible HXY files for accidental secrets."
    )
    parser.add_argument("--repo", default=".", help="Git repository root to scan.")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    try:
        findings = scan_repo(repo)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"Unable to list Git files in {repo}: {exc.stderr.decode(errors='replace')}\n")
        return 2

    if not findings:
        print("No committed or commit-eligible HXY secrets found.")
        return 0

    print("Potential HXY secret exposure found:")
    for finding in findings:
        suffix = f" key={finding.key}" if finding.key else ""
        print(f"- {finding.path}:{finding.line} rule={finding.rule}{suffix}")
    print("Secret values are intentionally not printed. Rotate externally if exposure is confirmed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
