"""Strict folder naming for NEW construction reference imports.

Stable internal key: "SAM 0004". Human-readable folder: "SAM 0004 — Гагарина 64".
Old SAM-xxxx references are NOT interpreted as new import names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CITIES = {"SAM": "Самара", "TLT": "Тольятти"}  # Examples for UI, not a city allowlist.
_NAME = re.compile(r"(?P<city>[A-Z]{2,5}) (?P<number>[0-9]{1,8}) — (?P<address>.+)\Z")
_KEY = re.compile(r"(?P<city>[A-Z]{2,5}) (?P<number>[0-9]{1,8})\Z")
_UNSAFE_ADDRESS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class Construction:
    key: str
    city_code: str
    number: str
    address: str

    @property
    def title(self) -> str:
        return f"{self.key} — {self.address}"


def parse_key(value: str) -> tuple[str, str]:
    match = _KEY.fullmatch(value)
    if match is None:
        raise ValueError("Идентификатор должен иметь вид SAM 0004")
    city = match["city"]
    return city, match["number"]


def parse_folder_name(value: str) -> Construction:
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError("Слишком длинное или некорректное название папки")
    match = _NAME.fullmatch(value)
    if match is None:
        raise ValueError("Ожидается формат: SAM 0004 — Гагарина 64")
    city, number, address = match["city"], match["number"], match["address"]
    if (len(address) > 120 or address != address.strip() or
            address.endswith(".") or not address.strip() or
            _UNSAFE_ADDRESS.search(address) or "  " in address):
        raise ValueError("Некорректный адрес в названии папки")
    return Construction(f"{city} {number}", city, number, address)
