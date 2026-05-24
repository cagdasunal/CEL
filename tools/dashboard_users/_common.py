"""Shared helpers for the dashboard user/password workflows (CEL repo only).

Invoked by .github/workflows/dashboard-{change,forgot,reset}-password.yml.
Stdlib only — no third-party imports.

Model (see the dashboard plan's CRYPTO SPEC):
  inner(P)  = SHA256(utf8(P))           hex   (what the client sends as "current")
  pwHash(P) = SHA256(utf8(inner(P)))    hex   (stored, public, in docs/admin/users.json)

Storing the *double* hash lets change-password verify "you know the current
password" even though pwHash is public: only someone who knows P can produce
inner(P); the public pwHash does not yield inner(P) (preimage resistance).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# Repo-root-relative; the workflows run with cwd = repo root (actions/checkout).
USERS_FILE = Path("docs/admin/users.json")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def valid_email(email: str) -> bool:
    e = normalize_email(email)
    return bool(e) and len(e) <= 254 and "\n" not in e and "\r" not in e and bool(_EMAIL_RE.match(e))


def valid_hex64(h: str) -> bool:
    return bool(h) and bool(_HEX64_RE.match((h or "").strip().lower()))


def load_users(path: Path | None = None) -> list[dict]:
    p = path if path is not None else USERS_FILE
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("users.json must be a JSON array")
    return data


def save_users(users: list[dict], path: Path | None = None) -> None:
    """Write atomically; callers mutate records in place so all fields persist."""
    p = Path(path if path is not None else USERS_FILE)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(users, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def find_user(users: list[dict], email: str) -> dict | None:
    target = normalize_email(email)
    for u in users:
        if normalize_email(u.get("email", "")) == target:
            return u
    return None
