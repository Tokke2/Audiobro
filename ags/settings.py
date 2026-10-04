"""Spara mappar och inställningar i en JSON-fil (krav 20 i SPEC).

GUI:et läser filen vid start och skriver den vid stängning (samt via
menyn *Kom ihåg -> Spara inställningar nu*), så importmapp, outputmapp,
kryssrutor m.m. minnas mellan körningar. Filen innehåller även listor över
senast använda mappar som visas i *Kom ihåg*-menyn.
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import logging_setup

log = logging_setup.get(__name__)

MAX_RECENT = 8


def default_path() -> str:
    return os.environ.get(
        "AGS_SETTINGS",
        os.path.join(os.path.expanduser("~"), ".audiobook-goodreads",
                     "settings.json"),
    )


def load(path: str | None = None) -> dict[str, Any]:
    path = path or default_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            log.debug("inställningar lästa från %s", path)
            return data
    except (OSError, ValueError):
        pass  # första starten / trasig fil -> börja tomt
    return {}


def save(data: dict[str, Any], path: str | None = None) -> str:
    path = path or default_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # atomärt: ingen halvs kriven fil
        log.info("inställningar sparade till %s", path)
    except OSError as exc:
        log.warning("kunde inte spara inställningar: %s", exc)
    return path


def add_recent(items: list[str], value: str, max_n: int = MAX_RECENT) -> list[str]:
    """Lägg överst, utan dubbletter, begränsad längd."""
    value = (value or "").strip()
    if not value:
        return items
    out = [value] + [i for i in items if i != value]
    return out[:max_n]
