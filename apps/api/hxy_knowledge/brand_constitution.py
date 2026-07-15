from __future__ import annotations

import json
import hashlib
import os
import re
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = "hxy-brand-constitution.v1"
ALLOWED_AUTHORITIES = {"official_internal", "approved_answer_card"}
REQUIRED_ROLE_VARIANTS = {"founder", "headquarters", "store_manager", "store_staff"}
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class BrandConstitutionError(ValueError):
    pass


@dataclass(frozen=True)
class ConstitutionLoadResult:
    payload: dict[str, Any] | None
    reason: str


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


class BrandConstitutionAdapter:
    """Read-only answer adapter for the local, owner-approved brand constitution."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.constitution_root = (
            self.root_dir / "data" / "private" / "brand-constitution"
        )
        self.versions_dir = self.constitution_root / "versions"
        self.active_path = self.constitution_root / "active.json"
        self.events_path = self.constitution_root / "events.jsonl"

    def _active_pointer(self) -> dict[str, str] | None:
        try:
            pointer = json.loads(self.active_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(pointer, dict):
            return None
        version = pointer.get("version")
        digest = pointer.get("content_sha256")
        activation_event_id = pointer.get("activation_event_id")
        if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
            return None
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            return None
        if not isinstance(activation_event_id, str) or not activation_event_id.strip():
            return None
        return {
            "version": version,
            "content_sha256": digest,
            "activation_event_id": activation_event_id.strip(),
        }

    def active_version(self) -> str | None:
        pointer = self._active_pointer()
        return pointer["version"] if pointer else None

    def _version_path(self, version: str) -> Path:
        if not VERSION_PATTERN.fullmatch(version):
            raise BrandConstitutionError("invalid constitution version")
        return self.versions_dir / f"{version}.json"

    def _validate(self, payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        now = datetime.now(timezone.utc)
        if payload.get("schema_version") != SCHEMA_VERSION:
            errors.append("schema_version")
        version = payload.get("version")
        if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
            errors.append("version")
        if not isinstance(payload.get("owner"), str) or not payload["owner"].strip():
            errors.append("owner")
        if payload.get("status") != "approved":
            errors.append("approved status")
        if payload.get("owner_approved") is not True:
            errors.append("owner approved")
        if not isinstance(payload.get("approved_by"), str) or not payload["approved_by"].strip():
            errors.append("approved_by")

        approved_at = _parse_timestamp(payload.get("approved_at"))
        effective_at = _parse_timestamp(payload.get("effective_at"))
        expires_value = payload.get("expires_at")
        expires_at = _parse_timestamp(expires_value) if expires_value is not None else None
        if approved_at is None or approved_at > now:
            errors.append("approved_at")
        if effective_at is None or effective_at > now:
            errors.append("effective_at")
        if expires_value is not None and (expires_at is None or expires_at <= now):
            errors.append("expires_at")

        core = payload.get("core_statements")
        if not isinstance(core, dict):
            errors.append("core_statements")
        else:
            identity = core.get("brand_identity")
            facts = core.get("service_facts")
            if not isinstance(identity, str) or not identity.strip():
                errors.append("brand_identity")
            if not isinstance(facts, list) or not facts or not all(
                isinstance(item, str) and item.strip() for item in facts
            ):
                errors.append("service_facts")

        forbidden = payload.get("forbidden_interpretations")
        blocked_terms: list[str] = []
        if not isinstance(forbidden, list) or not forbidden:
            errors.append("forbidden_interpretations")
        else:
            for item in forbidden:
                if not isinstance(item, dict):
                    errors.append("forbidden_interpretations")
                    break
                statement = item.get("statement")
                terms = item.get("blocked_terms")
                if not isinstance(statement, str) or not statement.strip():
                    errors.append("forbidden_interpretations")
                    break
                if not isinstance(terms, list) or not terms or not all(
                    isinstance(term, str) and term.strip() for term in terms
                ):
                    errors.append("forbidden_interpretations")
                    break
                blocked_terms.extend(term.strip() for term in terms)

        role_variants = payload.get("role_variants")
        if not isinstance(role_variants, dict) or any(
            not isinstance(role_variants.get(role), str) or not role_variants[role].strip()
            for role in REQUIRED_ROLE_VARIANTS
        ):
            errors.append("role_variants")

        if isinstance(core, dict) and isinstance(role_variants, dict):
            formal_texts = [
                core.get("brand_identity") or "",
                *(core.get("service_facts") or []),
                *(role_variants.values()),
            ]
            from .compliance_rules import check_brand_risk_text

            if any(
                isinstance(text, str)
                and check_brand_risk_text(text, root_dir=self.root_dir).get("status") != "ok"
                for text in formal_texts
            ):
                errors.append("unsafe formal wording")
            if any(
                blocked_term in text
                for text in formal_texts
                if isinstance(text, str)
                for blocked_term in blocked_terms
            ):
                errors.append("forbidden interpretation used in formal wording")

        source_references = payload.get("source_references")
        if not isinstance(source_references, list) or not source_references:
            errors.append("source_references")
        else:
            for reference in source_references:
                if not isinstance(reference, dict):
                    errors.append("source authority")
                    break
                if reference.get("authority") not in ALLOWED_AUTHORITIES:
                    errors.append("source authority")
                    break
                source_id = reference.get("source_id")
                if not isinstance(source_id, str) or not source_id.strip():
                    errors.append("source_id")
                    break
        return errors

    @staticmethod
    def _digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _load_version(
        self,
        version: str,
        *,
        expected_digest: str | None = None,
    ) -> ConstitutionLoadResult:
        try:
            version_path = self._version_path(version)
            raw = version_path.read_bytes()
            if expected_digest and hashlib.sha256(raw).hexdigest() != expected_digest:
                return ConstitutionLoadResult(None, "content_digest_mismatch")
            payload = json.loads(raw.decode("utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError, BrandConstitutionError):
            return ConstitutionLoadResult(None, "missing_or_unreadable")
        if not isinstance(payload, dict) or payload.get("version") != version:
            return ConstitutionLoadResult(None, "version_mismatch")
        errors = self._validate(payload)
        if errors:
            return ConstitutionLoadResult(None, ", ".join(errors))
        return ConstitutionLoadResult(payload, "active")

    def load_active(self) -> ConstitutionLoadResult:
        pointer = self._active_pointer()
        if not pointer:
            return ConstitutionLoadResult(None, "missing_active_version")
        if not self._activation_event_matches(pointer):
            return ConstitutionLoadResult(None, "activation_event_mismatch")
        return self._load_version(
            pointer["version"],
            expected_digest=pointer["content_sha256"],
        )

    @staticmethod
    def covers_question(question: str) -> bool:
        normalized = re.sub(r"[\s？?。！!，,]", "", question or "")
        exact = {
            "荷小悦",
            "荷小悦是什么",
            "荷小悦做什么",
            "荷小悦是做什么的",
            "介绍荷小悦",
            "介绍一下荷小悦",
            "介绍下荷小悦",
            "荷小悦品牌是什么",
        }
        if normalized in exact:
            return True
        if "荷小悦" not in normalized:
            return False
        if "品牌定位" in normalized or "核爆点定位" in normalized:
            return True
        if re.search(
            r"荷小悦(?:的)?定位(?:是什么|怎么说|如何说|怎么理解|如何理解)$",
            normalized,
        ):
            return True
        if normalized.endswith("荷小悦") and any(
            signal in normalized for signal in ("介绍", "说说", "聊聊", "了解")
        ):
            return True
        identity_patterns = (
            r"(?:请问)?荷小悦(?:是)?(?:做什么|干什么|干嘛)(?:的)?$",
            r"(?:请问)?荷小悦(?:是什么品牌|品牌是什么)$",
            r"(?:请问)?荷小悦(?:属于什么(?:类型的|样的)?品牌|是哪类品牌)$",
        )
        return any(re.fullmatch(pattern, normalized) for pattern in identity_patterns)

    @staticmethod
    def _working_boundary(reason: str) -> dict[str, Any]:
        return {
            "answer": "当前没有有效且已核定的品牌宪法版本，现有内容只能作为工作判断，不能作为正式品牌口径。",
            "intent": "brand_positioning",
            "audience": "brand",
            "answer_mode": "working",
            "authority_source": "none",
            "usage_boundary": "review_required",
            "answer_status": "待复核",
            "confidence": "low",
            "needs_review": True,
            "from_brand_constitution": False,
            "constitution_status": reason,
            "evidence": [],
            "sources": [],
            "next_actions": ["由品牌负责人核定并启用一个品牌宪法版本"],
        }

    def answer_for_brand_identity(self, *, role: str) -> dict[str, Any]:
        loaded = self.load_active()
        if loaded.payload is None:
            return self._working_boundary(loaded.reason)
        payload = loaded.payload
        core = payload["core_statements"]
        role_variants = payload["role_variants"]
        answer = role_variants.get(role) or core["brand_identity"]
        evidence = [
            {
                "type": "brand_constitution",
                "source_type": "official_internal",
                "title": f"品牌宪法 {payload['version']}",
                "version": payload["version"],
                "authority_source": "official_internal",
                "strength": "high",
                "excerpt": "当前生效的已核定品牌宪法版本。",
            }
        ]
        return {
            "answer": answer,
            "intent": "brand_positioning",
            "audience": "brand",
            "answer_mode": "formal",
            "authority_source": "official_internal",
            "usage_boundary": "team_standard",
            "answer_status": "已批准",
            "confidence": "high",
            "needs_review": False,
            "from_answer_card": False,
            "from_brand_constitution": True,
            "constitution_version": payload["version"],
            "review_status": "approved",
            "version": payload["version"],
            "policy_boundaries_applied": True,
            "evidence": evidence,
            "sources": evidence,
            "conflicts": [],
            "corrections": [],
            "reasoning": ["回答来自当前生效且由负责人核定的品牌宪法版本。"],
            "next_actions": [],
        }

    def _write_active_pointer(self, version: str, digest: str, activation_event_id: str) -> None:
        self.constitution_root.mkdir(parents=True, exist_ok=True)
        temporary = self.constitution_root / f".active-{uuid4().hex}.tmp"
        temporary.write_text(
            json.dumps(
                {
                    "version": version,
                    "content_sha256": digest,
                    "activation_event_id": activation_event_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.active_path)

    def _append_event(self, event: dict[str, Any]) -> None:
        self.constitution_root.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _published_digest(self, version: str) -> str | None:
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            return None
        digest: str | None = None
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("event_type") != "publish":
                continue
            if event.get("version") != version:
                continue
            candidate = event.get("content_sha256")
            if isinstance(candidate, str) and SHA256_PATTERN.fullmatch(candidate):
                digest = candidate
        return digest

    def _activation_event_matches(self, pointer: dict[str, str]) -> bool:
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            return False
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("event_id") != pointer["activation_event_id"]:
                continue
            if event.get("event_type") == "publish":
                return (
                    event.get("version") == pointer["version"]
                    and event.get("content_sha256") == pointer["content_sha256"]
                )
            if event.get("event_type") == "rollback":
                return (
                    event.get("to_version") == pointer["version"]
                    and event.get("to_content_sha256") == pointer["content_sha256"]
                )
        return False

    @staticmethod
    def _version_order(version: str) -> tuple[int, int, int]:
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-.].*)?$", version)
        if not match:
            raise BrandConstitutionError("constitution version must use semantic versioning")
        return tuple(int(part) for part in match.groups())

    @contextmanager
    def _operation_lock(self):
        self.constitution_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.constitution_root / ".operations.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def rollback(self, *, target_version: str, actor: str, reason: str) -> dict[str, Any]:
        if not actor.strip() or not reason.strip():
            raise BrandConstitutionError("rollback actor and reason are required")
        with self._operation_lock():
            current_pointer = self._active_pointer()
            if not current_pointer:
                raise BrandConstitutionError("active constitution version is required")
            current_version = current_pointer["version"]
            if self._version_order(target_version) >= self._version_order(current_version):
                raise BrandConstitutionError("rollback target must be a prior version")
            target_digest = self._published_digest(target_version)
            if not target_digest:
                raise BrandConstitutionError("rollback target must have a published content digest")
            target = self._load_version(target_version, expected_digest=target_digest)
            if target.payload is None:
                raise BrandConstitutionError(
                    f"rollback target must be an approved constitution version: {target.reason}"
                )
            event_id = str(uuid4())
            event_base = {
                "event_id": event_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "actor": actor.strip(),
                "reason": reason.strip(),
                "from_version": current_version,
                "from_content_sha256": current_pointer["content_sha256"],
                "to_version": target_version,
                "to_content_sha256": target_digest,
            }
            event = {**event_base, "event_type": "rollback", "state": "authorized"}
            self._append_event(event)
            self._write_active_pointer(target_version, target_digest, event_id)
            return {**event, "state": "committed"}
