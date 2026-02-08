"""Parse CSV and JSON uploads for charger/vehicle import."""
import csv
import json
from io import StringIO
from typing import Any


def _normalize_key(k: str) -> str:
    """Strip and return key; empty after strip treated as missing."""
    return k.strip() if k else ""


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip keys and string values; drop empty keys."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        key = _normalize_key(k)
        if not key:
            continue
        if isinstance(v, str):
            val = v.strip()
        else:
            val = v
        out[key] = val
    return out


def _charger_normalize(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize charger row: number_of_evses -> evse_count for internal use."""
    out = dict(row)
    if "number_of_evses" in out and "evse_count" not in out:
        out["evse_count"] = out.pop("number_of_evses")
    return out


def parse_csv(content: bytes, charger_format: bool = False) -> list[dict[str, Any]]:
    """Parse CSV bytes into list of dicts. Skip empty rows. If charger_format, normalize number_of_evses -> evse_count."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(StringIO(text))
    rows: list[dict[str, Any]] = []
    for row in reader:
        normalized = _normalize_row(dict(row))
        if not normalized:
            continue
        if charger_format:
            normalized = _charger_normalize(normalized)
        rows.append(normalized)
    return rows


def parse_json(content: bytes, charger_format: bool = False) -> list[dict[str, Any]]:
    """Parse JSON bytes (expect list of objects) into list of dicts. If charger_format, normalize number_of_evses -> evse_count."""
    data = json.loads(content.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON must be an array of objects")
    rows: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Row {i + 1} is not an object")
        normalized = _normalize_row(item)
        if not normalized:
            continue
        if charger_format:
            normalized = _charger_normalize(normalized)
        rows.append(normalized)
    return rows


def parse_upload(content: bytes, filename: str | None, charger_format: bool = False) -> list[dict[str, Any]]:
    """Detect format from filename or content and parse. Raises ValueError if invalid."""
    if filename and filename.lower().endswith(".json"):
        return parse_json(content, charger_format=charger_format)
    if filename and filename.lower().endswith(".csv"):
        return parse_csv(content, charger_format=charger_format)
    # Detect from content: JSON array starts with [
    stripped = content.lstrip()
    if stripped.startswith(b"["):
        return parse_json(content, charger_format=charger_format)
    return parse_csv(content, charger_format=charger_format)
