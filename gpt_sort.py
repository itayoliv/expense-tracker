"""Group unsorted expenses and ask ChatGPT to assign existing categories."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import db
from models import Category, Transaction

GPT_MODEL = os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"


class GptSortError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def openai_key_path() -> Path:
    parent = Path(db.DB_PATH).parent if db.DB_PATH is not None else db.DATA_DIR
    parent.mkdir(parents=True, exist_ok=True)
    return parent / "openai_key.txt"


def get_api_key() -> str | None:
    path = openai_key_path()
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    return env or None


def has_api_key() -> bool:
    return bool(get_api_key())


def save_api_key(key: str) -> None:
    text = (key or "").strip()
    if not text:
        raise GptSortError("API key is required")
    openai_key_path().write_text(text, encoding="utf-8")


def clear_api_key() -> None:
    path = openai_key_path()
    if path.exists():
        path.unlink()


def group_unsorted_names(txns: list[Transaction]) -> list[dict[str, Any]]:
    """Unique descriptions (case-insensitive), keeping a display name and sample details."""
    seen: dict[str, dict[str, Any]] = {}
    for txn in txns:
        name = (txn.description or "").strip()
        key = name.lower()
        if not key:
            continue
        if key not in seen:
            seen[key] = {
                "name": name,
                "details": (txn.details or "").strip(),
                "count": 0,
            }
        seen[key]["count"] += 1
        if not seen[key]["details"]:
            seen[key]["details"] = (txn.details or "").strip()
    return list(seen.values())


def _category_index(categories: list[Category]) -> dict[str, int]:
    index: dict[str, int] = {}
    for cat in categories:
        index[str(cat.id)] = cat.id
        for label in (cat.name_en, cat.name_he, getattr(cat, "name", None)):
            text = (label or "").strip().lower()
            if text:
                index[text] = cat.id
    return index


def parse_gpt_json(raw: Any, categories: list[Category]) -> dict[str, int]:
    """Map lowercase transaction name -> category_id. Unknown categories are skipped."""
    data = raw
    if isinstance(raw, str):
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise GptSortError("ChatGPT did not return a JSON object")
    if isinstance(data.get("assignments"), dict):
        data = data["assignments"]

    index = _category_index(categories)
    assignments: dict[str, int] = {}
    for cat_key, names in data.items():
        cid = index.get(str(cat_key).strip().lower())
        if cid is None:
            continue
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, list):
            continue
        for name in names:
            key = str(name or "").strip().lower()
            if key:
                assignments[key] = cid
    return assignments


def apply_assignments(session: Session, assignments: dict[str, int]) -> int:
    """Set category on currently unsorted debit rows with a matching description."""
    assigned = 0
    for name_key, category_id in assignments.items():
        matches = session.scalars(
            select(Transaction).where(
                Transaction.category_id.is_(None),
                Transaction.direction == "debit",
                func.lower(Transaction.description) == name_key,
            )
        ).all()
        for txn in matches:
            txn.category_id = category_id
            txn.categorized_by = "gpt"
            assigned += 1
    return assigned


def _blocked_by_antivirus(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "avgmonfltproxy" in text or ("avast" in text and "proxy" in text)


def _antivirus_sort_error(exc: BaseException) -> GptSortError:
    return GptSortError(
        "Could not reach OpenAI (antivirus blocked Python HTTPS). "
        "Tried Windows curl as a fallback and that failed too."
    )


def _chat_content_from_body(body: dict[str, Any]) -> str:
    err = body.get("error")
    if err:
        raise GptSortError(f"OpenAI API error: {err}")
    try:
        return (body["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise GptSortError("Unexpected OpenAI response") from exc


def ask_openai(
    api_key: str, categories: list[Category], names: list[dict[str, Any]]
) -> dict[str, Any]:
    cats_payload = [
        {
            "id": cat.id,
            "name_en": cat.name_en,
            "name_he": cat.name_he,
            "kind": cat.kind,
        }
        for cat in categories
    ]
    names_payload = [
        {
            "name": item["name"],
            "details": item.get("details") or "",
            "count": item.get("count", 1),
        }
        for item in names
    ]
    payload = {
        "model": GPT_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You categorize bank and credit-card expenses. "
                    "Use only the provided categories. "
                    "Return a JSON object whose keys are category names "
                    "(English or Hebrew) or category ids, and whose values "
                    "are arrays of transaction names from the input. "
                    "Omit names you cannot classify."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"categories": cats_payload, "transactions": names_payload},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    try:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(**payload)
            content = (response.choices[0].message.content or "").strip()
        except ImportError:
            content = _ask_openai_http(api_key, payload)
    except GptSortError:
        raise
    except OSError as exc:
        if _blocked_by_antivirus(exc):
            content = _ask_openai_curl(api_key, payload)
        else:
            raise GptSortError(f"Could not reach OpenAI: {exc}") from exc
    if not content:
        raise GptSortError("ChatGPT returned an empty response")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise GptSortError("ChatGPT did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise GptSortError("ChatGPT did not return a JSON object")
    return parsed


def _ask_openai_http(api_key: str, payload: dict[str, Any]) -> str:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GptSortError(f"OpenAI API error ({exc.code}): {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        if _blocked_by_antivirus(exc) or _blocked_by_antivirus(exc.reason):
            return _ask_openai_curl(api_key, payload)
        raise GptSortError(f"Could not reach OpenAI: {exc.reason}") from exc
    except OSError as exc:
        if _blocked_by_antivirus(exc):
            return _ask_openai_curl(api_key, payload)
        raise GptSortError(f"Could not reach OpenAI: {exc}") from exc
    return _chat_content_from_body(body)


def _ask_openai_curl(api_key: str, payload: dict[str, Any]) -> str:
    """Bypass Python's SSL stack (often hooked by AVG) via Windows curl."""
    import shutil
    import subprocess

    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise _antivirus_sort_error(RuntimeError("curl not found"))
    proc = subprocess.run(
        [
            curl,
            "-sS",
            "--http1.1",
            "-X",
            "POST",
            "https://api.openai.com/v1/chat/completions",
            "-H",
            f"Authorization: Bearer {api_key}",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
            "--max-time",
            "90",
        ],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=100,
    )
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        if _blocked_by_antivirus(stderr) or _blocked_by_antivirus(stdout):
            raise _antivirus_sort_error(RuntimeError(stderr or stdout))
        raise GptSortError(
            f"Could not reach OpenAI: {(stderr or stdout or str(proc.returncode))[:300]}"
        )
    try:
        body = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise GptSortError("ChatGPT did not return valid JSON") from exc
    if not isinstance(body, dict):
        raise GptSortError("Unexpected OpenAI response")
    return _chat_content_from_body(body)


def sort_unsorted_expenses(session: Session, ask=None) -> dict[str, int]:
    ask_fn = ask or ask_openai
    api_key = get_api_key()
    if not api_key:
        raise GptSortError("Add an OpenAI API key in Settings first.")

    txns = list(
        session.scalars(
            select(Transaction).where(
                Transaction.category_id.is_(None),
                Transaction.direction == "debit",
            )
        ).all()
    )
    names = group_unsorted_names(txns)
    if not names:
        return {"assigned": 0, "skipped": 0}

    cats = list(
        session.scalars(
            select(Category).where(Category.kind == "expense").order_by(Category.sort_order)
        ).all()
    )
    if not cats:
        raise GptSortError("Add expense categories before sorting with ChatGPT.")

    allowed = {item["name"].strip().lower() for item in names}
    raw = ask_fn(api_key, cats, names)
    parsed = parse_gpt_json(raw, cats)
    filtered = {key: cid for key, cid in parsed.items() if key in allowed}
    skipped = len(allowed) - len(filtered)
    assigned = apply_assignments(session, filtered)
    return {"assigned": assigned, "skipped": skipped}
