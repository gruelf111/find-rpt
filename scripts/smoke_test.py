#!/usr/bin/env python3
"""Safe installation/configuration smoke test without printing report contents."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "skills" / "find-rpt" / "scripts" / "find_rpt.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("find-rpt.toml"))
    parser.add_argument("--ticker")
    parser.add_argument("--date")
    parser.add_argument("--broker")
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    try:
        import find_rpt  # noqa: F401
    except Exception as error:
        checks.append({"check": "package_import", "ok": False, "action": f"install the package: {error}"})
    else:
        checks.append({"check": "package_import", "ok": True})

    cli = subprocess.run(
        [sys.executable, "-m", "find_rpt", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    checks.append({
        "check": "cli_available",
        "ok": cli.returncode == 0,
        "action": None if cli.returncode == 0 else "run python -m pip install -e .",
    })

    spec = importlib.util.spec_from_file_location("find_rpt_smoke_launcher", LAUNCHER)
    if not spec or not spec.loader:
        checks.append({"check": "skill_launcher", "ok": False, "action": "restore skills/find-rpt"})
        settings = None
    else:
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            settings = module.load_settings(config_path=args.config)
        except Exception as error:
            checks.append({"check": "configuration", "ok": False, "action": str(error)})
            settings = None
        else:
            checks.append({"check": "configuration", "ok": True})

    if settings is not None:
        corpus_ok = settings.corpus_path.is_dir()
        pdf_count = sum(1 for item in settings.corpus_path.glob("*.pdf") if item.is_file()) if corpus_ok else 0
        checks.append({
            "check": "corpus_access",
            "ok": corpus_ok,
            "pdf_count": pdf_count,
            "action": None if corpus_ok else "configure corpus_path to a readable local directory",
        })
        viewer_ok = module.citation_viewer_available(settings)
        checks.append({
            "check": "citation_viewer",
            "ok": viewer_ok,
            "action": None if viewer_ok else "start: find-rpt citations serve",
        })
        model_ok = settings.no_model or bool(os.environ.get(settings.model_api_key_env))
        checks.append({
            "check": "model_configuration",
            "ok": model_ok,
            "mode": "no-model" if settings.no_model else "local-model",
            "action": None if model_ok else f"set {settings.model_api_key_env} or enable no_model",
        })

    safety_files = [
        *(ROOT / "src").rglob("*.py"),
        *(ROOT / "skills" / "find-rpt").rglob("*.py"),
        *(ROOT / "skills" / "find-rpt").rglob("*.md"),
        *(ROOT / ".claude" / "commands").glob("*.md"),
        ROOT / "pyproject.toml",
    ]
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in safety_files
        if path.is_file()
    ).casefold()
    forbidden = ("smtplib", "mailto:", "send_email", "send_message", "clipboard")
    matches = [item for item in forbidden if item in source]
    checks.append({
        "check": "no_send_architecture",
        "ok": not matches,
        "action": None if not matches else "remove prohibited delivery capability",
    })

    provided = [args.ticker, args.date, args.broker]
    if any(provided):
        if not all(provided):
            checks.append({"check": "optional_report", "ok": False, "action": "provide ticker, date, and broker together"})
        elif settings is not None:
            request = module.Request(args.ticker, module._normalize_date(args.date), args.broker)
            result = module.execute_request(request, settings)
            checks.append({
                "check": "optional_report",
                "ok": result["status"] in {"found", "partial"},
                "status": result["status"],
                "action": result.get("message"),
            })

    ok = all(bool(item["ok"]) for item in checks)
    print(json.dumps({"status": "ok" if ok else "action_required", "checks": checks}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
