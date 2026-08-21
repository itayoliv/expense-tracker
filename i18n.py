"""Simple JSON-based i18n helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LOCALES_DIR = ROOT / "locales"
SUPPORTED = ("en", "he")


def _load(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_lang(cookie_value: str | None) -> str:
    if cookie_value in SUPPORTED:
        return cookie_value
    return "en"


def t(lang: str, key: str, **kwargs: Any) -> str:
    strings = _load(lang if lang in SUPPORTED else "en")
    text = strings.get(key) or _load("en").get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def html_dir(lang: str) -> str:
    return "rtl" if lang == "he" else "ltr"


def category_name(lang: str, cat) -> str:
    if cat is None:
        return t(lang, "unsorted")
    return cat.name_he if lang == "he" else cat.name_en
