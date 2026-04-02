"""
Excel/CSV importer for marketing client lists.
"""
import csv
import io
import json
from typing import Any

from openpyxl import load_workbook

# Column aliases — maps raw header names to internal field names
_COLUMN_ALIASES: dict[str, str] = {
    "name": "name",
    "nama": "name",
    "nama perusahaan": "name",
    "company": "name",
    "company name": "name",
    "organization": "name",
    "organisation": "name",
    "perusahaan": "name",
    "client": "name",
    "client name": "name",
    "lembaga": "name",
    "instansi": "name",
    # Province
    "province": "province",
    "provinsi": "province",
    # Website
    "website": "website",
    "web": "website",
    "url": "website",
    # Email
    "email": "email",
    "e-mail": "email",
    # Phone
    "phone": "phone",
    "telephone": "phone",
    "telp": "phone",
    "no telepon": "phone",
    # Contact Person
    "contact person": "contact_person",
    "pic": "contact_person",
    "cp": "contact_person",
}


def _normalize_headers(raw_headers: list[str]) -> dict[int, str]:
    """Map column indices to internal field names using aliases."""
    mapping: dict[int, str] = {}
    found_name = False
    for i, h in enumerate(raw_headers):
        key = h.strip().lower()
        if key in _COLUMN_ALIASES:
            field = _COLUMN_ALIASES[key]
            if field not in mapping.values():
                mapping[i] = field
                if field == "name":
                    found_name = True
    if not found_name and raw_headers:
        mapping[0] = "name"
    return mapping


def parse_excel_file(file_path: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse an Excel or CSV file and return (rows, detected_columns)."""
    ext = file_path.lower().split(".")[-1]
    rows_data: list[dict[str, Any]] = []

    if ext in ("xlsx", "xls"):
        wb = load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            wb.close()
            return [], []
        raw_headers = [str(h).strip() if h else "" for h in header_row]
        col_map = _normalize_headers(raw_headers)
        for row in ws.iter_rows(min_row=2, values_only=True):
            row_dict: dict[str, Any] = {}
            extra: dict[str, Any] = {}
            for i, val in enumerate(row):
                if i in col_map:
                    field = col_map[i]
                    row_dict[field] = str(val).strip() if val is not None else ""
                elif val is not None and str(val).strip():
                    extra[str(raw_headers[i])] = str(val).strip()
            if extra:
                row_dict["_extra"] = extra
            rows_data.append(row_dict)
        wb.close()
        return rows_data, raw_headers

    elif ext == "csv":
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            raw_headers = list(reader.fieldnames or [])
            col_map = _normalize_headers(raw_headers)
            header_to_field = {raw_headers[i]: field for i, field in col_map.items()}
            for row in reader:
                row_dict: dict[str, Any] = {}
                extra: dict[str, Any] = {}
                for orig_header, field in header_to_field.items():
                    val = row.get(orig_header, "")
                    if val:
                        row_dict[field] = val.strip()
                for k, v in row.items():
                    if k not in header_to_field and v and v.strip():
                        extra[k] = v.strip()
                if extra:
                    row_dict["_extra"] = extra
                rows_data.append(row_dict)
        return rows_data, raw_headers

    return [], []


def parse_excel_bytes(content: bytes, filename: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse Excel/CSV content from bytes. Returns (rows, detected_columns)."""
    rows_data: list[dict[str, Any]] = []
    ext = filename.lower().split(".")[-1]

    if ext in ("xlsx", "xls"):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            wb.close()
            return [], []
        raw_headers = [str(h).strip() if h else "" for h in header_row]
        col_map = _normalize_headers(raw_headers)
        for row in ws.iter_rows(min_row=2, values_only=True):
            row_dict: dict[str, Any] = {}
            extra: dict[str, Any] = {}
            for i, val in enumerate(row):
                if i in col_map:
                    field = col_map[i]
                    row_dict[field] = str(val).strip() if val is not None else ""
                elif val is not None and str(val).strip():
                    extra[str(raw_headers[i])] = str(val).strip()
            if extra:
                row_dict["_extra"] = extra
            rows_data.append(row_dict)
        wb.close()
        return rows_data, raw_headers

    elif ext == "csv":
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        raw_headers = list(reader.fieldnames or [])
        col_map = _normalize_headers(raw_headers)
        header_to_field = {raw_headers[i]: field for i, field in col_map.items()}
        for row in reader:
            row_dict: dict[str, Any] = {}
            extra: dict[str, Any] = {}
            for orig_header, field in header_to_field.items():
                val = row.get(orig_header, "")
                if val:
                    row_dict[field] = val.strip()
            for k, v in row.items():
                if k not in header_to_field and v and v.strip():
                    extra[k] = v.strip()
            if extra:
                row_dict["_extra"] = extra
            rows_data.append(row_dict)
        return rows_data, raw_headers

    return [], []
