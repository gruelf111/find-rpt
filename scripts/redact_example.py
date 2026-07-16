#!/usr/bin/env python3
"""Replace sensitive free text and identifiers in a local agent-JSON transcript."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SENSITIVE_KEYS = {
    "title", "report_title", "takeaway", "rationale_paragraphs", "first_read_items",
    "body", "questions", "analyst_names", "name", "email", "phone",
}


def redact(value: Any, key: str | None = None) -> Any:
    if key in SENSITIVE_KEYS and value not in (None, [], ""):
        return [] if isinstance(value, list) else "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: redact(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, key) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED EMAIL]", value)
        value = re.sub(r"(?i)(?:[A-Z]:[\\/]|/Users/|/home/)[^\s\"']+", "[REDACTED PATH]", value)
        value = re.sub(r"(?i)\b[^\s/\\]+\.pdf\b", "synthetic-report.pdf", value)
        return value
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    parsed = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.write_text(
        json.dumps(redact(parsed), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("Structural redaction complete. Manually review every line; do not commit real-report output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
