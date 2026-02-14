"""Unit tests: import parsers (CSV/JSON)."""
import pytest

from utils.import_parsers import parse_csv, parse_json, parse_upload

pytestmark = pytest.mark.unit


def test_parse_csv_empty():
    """parse_csv with header-only returns empty list."""
    assert parse_csv(b"a,b,c\n") == []


def test_parse_csv_one_row():
    """parse_csv returns list of dicts."""
    content = b"name,idTag,battery_capacity_kWh\nV1,TAG1,75\n"
    rows = parse_csv(content, charger_format=False)
    assert len(rows) == 1
    assert rows[0]["name"] == "V1" and rows[0]["idTag"] == "TAG1"


def test_parse_csv_charger_format_normalizes_evse_count():
    """parse_csv with charger_format normalizes number_of_evses to evse_count."""
    content = b"connection_url,charger_name,charge_point_id,number_of_evses\nws://x/o,C1,CP1,2\n"
    rows = parse_csv(content, charger_format=True)
    assert rows[0].get("evse_count") == "2"
    assert "number_of_evses" not in rows[0]


def test_parse_json_array():
    """parse_json returns list of dicts from JSON array."""
    content = b'[{"name":"V1","idTag":"T1","battery_capacity_kWh":60}]'
    rows = parse_json(content)
    assert len(rows) == 1 and rows[0]["name"] == "V1"


def test_parse_json_not_array_raises():
    """parse_json with non-array raises ValueError."""
    with pytest.raises(ValueError, match="array"):
        parse_json(b'{"x":1}')


def test_parse_upload_detects_csv_by_filename():
    """parse_upload with .csv filename uses parse_csv."""
    rows = parse_upload(b"a,b\n1,2\n", "file.csv")
    assert len(rows) == 1 and rows[0]["a"] == "1"


def test_parse_upload_detects_json_by_filename():
    """parse_upload with .json filename uses parse_json."""
    rows = parse_upload(b'[{"a":1}]', "file.json")
    assert len(rows) == 1 and rows[0]["a"] == 1


def test_parse_json_row_not_object_raises():
    """parse_json with non-object element raises ValueError."""
    with pytest.raises(ValueError, match="not an object"):
        parse_json(b"[1,2]")


def test_parse_json_skips_empty_normalized():
    """parse_json skips items that normalize to empty (all keys empty after strip)."""
    content = b'[{"  ":"x","   ":""}]'
    rows = parse_json(content)
    assert len(rows) == 0


def test_parse_upload_detects_json_by_content():
    """parse_upload with unknown ext but content [ uses JSON."""
    rows = parse_upload(b'[{"x":1}]', "file.txt")
    assert len(rows) == 1 and rows[0]["x"] == 1


def test_parse_upload_fallback_csv():
    """parse_upload with no .json and content not [ uses CSV."""
    rows = parse_upload(b"x,y\n1,2\n", "file.dat")
    assert len(rows) == 1 and rows[0]["x"] == "1"
