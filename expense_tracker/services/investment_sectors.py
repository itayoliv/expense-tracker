"""GICS sector taxonomy, symbol assignments, and GPT classification for investments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from expense_tracker import db
from expense_tracker.integrations.gpt_sort import GPT_MODEL, get_api_key

SECTOR_UNKNOWN = "unknown"
SECTOR_ETF = "etf_diversified"

SECTORS: list[dict[str, str]] = [
    {
        "id": "communication_services",
        "name_en": "Communication Services",
        "name_he": "שירותי תקשורת",
        "color": "#8b5cf6",
    },
    {
        "id": "consumer_discretionary",
        "name_en": "Consumer Discretionary",
        "name_he": "מוצרי צריכה מחזוריים",
        "color": "#f97316",
    },
    {
        "id": "consumer_staples",
        "name_en": "Consumer Staples",
        "name_he": "מוצרי צריכה בסיסיים",
        "color": "#22c55e",
    },
    {
        "id": "energy",
        "name_en": "Energy",
        "name_he": "אנרגיה",
        "color": "#eab308",
    },
    {
        "id": "financials",
        "name_en": "Financials",
        "name_he": "פיננסים",
        "color": "#0ea5e9",
    },
    {
        "id": "health_care",
        "name_en": "Health Care",
        "name_he": "בריאות",
        "color": "#ec4899",
    },
    {
        "id": "industrials",
        "name_en": "Industrials",
        "name_he": "תעשייה",
        "color": "#64748b",
    },
    {
        "id": "information_technology",
        "name_en": "Information Technology",
        "name_he": "טכנולוגיה",
        "color": "#2563eb",
    },
    {
        "id": "materials",
        "name_en": "Materials",
        "name_he": "חומרים",
        "color": "#a16207",
    },
    {
        "id": "real_estate",
        "name_en": "Real Estate",
        "name_he": "נדל\"ן",
        "color": "#14b8a6",
    },
    {
        "id": "utilities",
        "name_en": "Utilities",
        "name_he": "תשתיות",
        "color": "#06b6d4",
    },
    {
        "id": SECTOR_ETF,
        "name_en": "ETF / Diversified",
        "name_he": "ETF / מגוון",
        "color": "#7c3aed",
    },
    {
        "id": SECTOR_UNKNOWN,
        "name_en": "Unknown",
        "name_he": "לא מסווג",
        "color": "#94a3b8",
    },
]

VALID_SECTOR_IDS = {item["id"] for item in SECTORS}
SECTOR_BY_ID = {item["id"]: item for item in SECTORS}


class SectorClassificationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def sectors_path() -> Path:
    parent = Path(db.DB_PATH).parent if db.DB_PATH is not None else db.DATA_DIR
    parent.mkdir(parents=True, exist_ok=True)
    return parent / "investment_sectors.json"


def load_assignments() -> dict[str, dict[str, Any]]:
    path = sectors_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        symbol = str(key or "").strip().upper()
        if not symbol or not isinstance(value, dict):
            continue
        sector_id = str(value.get("sector_id") or SECTOR_UNKNOWN).strip()
        if sector_id not in VALID_SECTOR_IDS:
            sector_id = SECTOR_UNKNOWN
        out[symbol] = {
            "sector_id": sector_id,
            "assigned_by": str(value.get("assigned_by") or "").strip() or None,
            "assigned_at": value.get("assigned_at"),
            "name": str(value.get("name") or "").strip() or None,
        }
    return out


def save_assignments(assignments: dict[str, dict[str, Any]]) -> None:
    path = sectors_path()
    serializable: dict[str, dict[str, Any]] = {}
    for symbol, meta in sorted(assignments.items()):
        sym = str(symbol or "").strip().upper()
        if not sym:
            continue
        sector_id = str(meta.get("sector_id") or SECTOR_UNKNOWN).strip()
        if sector_id not in VALID_SECTOR_IDS:
            sector_id = SECTOR_UNKNOWN
        entry: dict[str, Any] = {"sector_id": sector_id}
        if meta.get("assigned_by"):
            entry["assigned_by"] = meta["assigned_by"]
        if meta.get("assigned_at"):
            entry["assigned_at"] = meta["assigned_at"]
        if meta.get("name"):
            entry["name"] = meta["name"]
        serializable[sym] = entry
    path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sector_label(sector_id: str, lang: str) -> str:
    meta = SECTOR_BY_ID.get(sector_id) or SECTOR_BY_ID[SECTOR_UNKNOWN]
    if lang == "he":
        return meta["name_he"]
    return meta["name_en"]


def sector_color(sector_id: str) -> str:
    meta = SECTOR_BY_ID.get(sector_id) or SECTOR_BY_ID[SECTOR_UNKNOWN]
    return meta["color"]


def collect_symbols(portfolios: list[dict[str, Any]]) -> dict[str, str]:
    """Unique symbols -> display name from portfolio holdings."""
    symbols: dict[str, str] = {}
    for pf in portfolios or []:
        for holding in pf.get("holdings") or []:
            symbol = str(holding.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            name = str(holding.get("name") or "").strip() or symbol
            if symbol not in symbols or symbols[symbol] == symbol:
                symbols[symbol] = name
    return symbols


def symbols_needing_classification(
    portfolios: list[dict[str, Any]], assignments: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, str]]:
    current = assignments if assignments is not None else load_assignments()
    pending: list[dict[str, str]] = []
    for symbol, name in collect_symbols(portfolios).items():
        if symbol not in current:
            pending.append({"symbol": symbol, "name": name})
    pending.sort(key=lambda item: item["symbol"])
    return pending


def count_unassigned_symbols(portfolios: list[dict[str, Any]]) -> int:
    return len(symbols_needing_classification(portfolios))


def parse_gpt_sector_response(raw: Any) -> dict[str, str]:
    data = raw
    if isinstance(raw, str):
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise SectorClassificationError("ChatGPT did not return a JSON object")
    if isinstance(data.get("assignments"), dict):
        data = data["assignments"]

    parsed: dict[str, str] = {}
    for key, value in data.items():
        symbol = str(key or "").strip().upper()
        if not symbol:
            continue
        sector_id = str(value or "").strip()
        if sector_id not in VALID_SECTOR_IDS:
            sector_id = SECTOR_UNKNOWN
        parsed[symbol] = sector_id
    return parsed


def _sector_prompt_payload(symbols: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "model": GPT_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You classify stock and fund tickers into investment sectors. "
                    "Use only the provided sector ids. "
                    "Return a JSON object mapping each input symbol to exactly one sector id. "
                    "Classify ETFs, index funds, and mutual funds as etf_diversified. "
                    "Use unknown only when you cannot determine a sector."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "sectors": [
                            {"id": item["id"], "name_en": item["name_en"]}
                            for item in SECTORS
                        ],
                        "symbols": symbols,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }


def _chat_content_from_body(body: dict[str, Any]) -> str:
    err = body.get("error")
    if err:
        raise SectorClassificationError(f"OpenAI API error: {err}")
    try:
        return (body["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise SectorClassificationError("Unexpected OpenAI response") from exc


def _blocked_by_antivirus(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "avgmonfltproxy" in text or ("avast" in text and "proxy" in text)


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
        raise SectorClassificationError(
            f"OpenAI API error ({exc.code}): {detail[:300]}"
        ) from exc
    except urllib.error.URLError as exc:
        if _blocked_by_antivirus(exc) or _blocked_by_antivirus(exc.reason):
            return _ask_openai_curl(api_key, payload)
        raise SectorClassificationError(f"Could not reach OpenAI: {exc.reason}") from exc
    except OSError as exc:
        if _blocked_by_antivirus(exc):
            return _ask_openai_curl(api_key, payload)
        raise SectorClassificationError(f"Could not reach OpenAI: {exc}") from exc
    return _chat_content_from_body(body)


def _ask_openai_curl(api_key: str, payload: dict[str, Any]) -> str:
    import shutil
    import subprocess

    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise SectorClassificationError(
            "Could not reach OpenAI (antivirus blocked Python HTTPS and curl is unavailable)."
        )
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
        raise SectorClassificationError(
            f"Could not reach OpenAI: {(stderr or stdout or str(proc.returncode))[:300]}"
        )
    try:
        body = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SectorClassificationError("ChatGPT did not return valid JSON") from exc
    if not isinstance(body, dict):
        raise SectorClassificationError("Unexpected OpenAI response")
    return _chat_content_from_body(body)


def ask_openai_sectors(api_key: str, symbols: list[dict[str, str]]) -> dict[str, Any]:
    payload = _sector_prompt_payload(symbols)
    try:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(**payload)
            content = (response.choices[0].message.content or "").strip()
        except ImportError:
            content = _ask_openai_http(api_key, payload)
    except SectorClassificationError:
        raise
    except OSError as exc:
        if _blocked_by_antivirus(exc):
            content = _ask_openai_curl(api_key, payload)
        else:
            raise SectorClassificationError(f"Could not reach OpenAI: {exc}") from exc
    if not content:
        raise SectorClassificationError("ChatGPT returned an empty response")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SectorClassificationError("ChatGPT did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise SectorClassificationError("ChatGPT did not return a JSON object")
    return parsed


def classify_symbols(
    symbols: list[dict[str, str]], ask: Callable[[str, list[dict[str, str]]], dict[str, Any]] | None = None
) -> dict[str, int]:
    if not symbols:
        return {"classified": 0, "unknown": 0, "skipped": 0}

    api_key = get_api_key()
    if not api_key:
        return {"classified": 0, "unknown": 0, "skipped": len(symbols)}

    ask_fn = ask or ask_openai_sectors
    assignments = load_assignments()
    allowed = {item["symbol"].upper() for item in symbols}
    raw = ask_fn(api_key, symbols)
    parsed = parse_gpt_sector_response(raw)

    now = datetime.now(timezone.utc).isoformat()
    classified = 0
    unknown = 0
    for item in symbols:
        symbol = item["symbol"].upper()
        if symbol not in allowed:
            continue
        sector_id = parsed.get(symbol, SECTOR_UNKNOWN)
        if sector_id not in VALID_SECTOR_IDS:
            sector_id = SECTOR_UNKNOWN
        assignments[symbol] = {
            "sector_id": sector_id,
            "assigned_by": "gpt",
            "assigned_at": now,
            "name": item.get("name") or symbol,
        }
        classified += 1
        if sector_id == SECTOR_UNKNOWN:
            unknown += 1
    save_assignments(assignments)
    return {"classified": classified, "unknown": unknown, "skipped": 0}


def classify_portfolio_symbols(
    portfolios: list[dict[str, Any]],
    ask: Callable[[str, list[dict[str, str]]], dict[str, Any]] | None = None,
) -> dict[str, int]:
    pending = symbols_needing_classification(portfolios)
    if not pending:
        return {"classified": 0, "unknown": 0, "skipped": 0}
    if not get_api_key():
        return {"classified": 0, "unknown": 0, "skipped": len(pending)}
    return classify_symbols(pending, ask=ask)


def _holding_value(holding: dict[str, Any]) -> float:
    qty = float(holding.get("quantity") or 0)
    price = float(holding.get("price") or 0)
    if qty > 0 and price > 0:
        return qty * price
    return float(holding.get("market_value") or 0)


def aggregate_sector_allocation(
    portfolios: list[dict[str, Any]],
    portfolio_id: str = "all",
    lang: str = "en",
    assignments: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current = assignments if assignments is not None else load_assignments()
    totals: dict[str, float] = {sector_id: 0.0 for sector_id in VALID_SECTOR_IDS}
    unclassified: list[dict[str, str]] = []
    assignment_map: dict[str, str] = {}
    seen_unclassified: set[str] = set()

    for pf in portfolios or []:
        pf_id = str(pf.get("id") or "")
        if portfolio_id != "all" and pf_id != portfolio_id:
            continue
        for holding in pf.get("holdings") or []:
            symbol = str(holding.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            name = str(holding.get("name") or "").strip() or symbol
            value = _holding_value(holding)
            meta = current.get(symbol)
            if meta:
                sector_id = meta.get("sector_id") or SECTOR_UNKNOWN
            else:
                sector_id = SECTOR_UNKNOWN
                if symbol not in seen_unclassified:
                    seen_unclassified.add(symbol)
                    unclassified.append({"symbol": symbol, "name": name})
            if sector_id not in VALID_SECTOR_IDS:
                sector_id = SECTOR_UNKNOWN
            assignment_map[symbol] = sector_id
            totals[sector_id] = totals.get(sector_id, 0.0) + value

    grand = sum(totals.values()) or 0.0
    sectors: list[dict[str, Any]] = []
    for sector_id, value in sorted(totals.items(), key=lambda item: (-item[1], item[0])):
        if value <= 0:
            continue
        pct = (value / grand * 100.0) if grand > 0 else 0.0
        sectors.append(
            {
                "id": sector_id,
                "label": sector_label(sector_id, lang),
                "color": sector_color(sector_id),
                "value": round(value, 2),
                "pct": round(pct, 2),
            }
        )

    return {
        "ok": True,
        "portfolio_id": portfolio_id,
        "total": round(grand, 2),
        "sectors": sectors,
        "catalog": [
            {
                "id": item["id"],
                "label": sector_label(item["id"], lang),
                "color": sector_color(item["id"]),
            }
            for item in SECTORS
        ],
        "assignments": assignment_map,
        "unclassified": sorted(unclassified, key=lambda item: item["symbol"]),
    }
