#!/usr/bin/env python3
"""Thin agent launcher for the installed find-rpt Python package."""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit


SCHEMA_VERSION = "1.0"
DEFAULTS: dict[str, object] = {
    "corpus_path": "corpus",
    "cache_path": ".cache/find-rpt/citations",
    "model_mode": "api",
    "model_provider": "local-openai-compatible",
    "model_name": "local-rationale-model",
    "model_url": "http://127.0.0.1:11434/v1/chat/completions",
    "model_api_key_env": "FIND_RPT_MODEL_API_KEY",
    "citation_viewer_host": "127.0.0.1",
    "citation_viewer_port": 8765,
    "no_model": False,
}
ENVIRONMENT = {
    "corpus_path": "FIND_RPT_CORPUS",
    "cache_path": "FIND_RPT_CACHE_DIR",
    "model_mode": "FIND_RPT_MODEL_MODE",
    "model_provider": "FIND_RPT_MODEL_PROVIDER",
    "model_name": "FIND_RPT_MODEL_NAME",
    "model_url": "FIND_RPT_MODEL_URL",
    "model_api_key_env": "FIND_RPT_MODEL_API_KEY_ENV",
    "citation_viewer_host": "FIND_RPT_CITATION_HOST",
    "citation_viewer_port": "FIND_RPT_CITATION_PORT",
    "no_model": "FIND_RPT_NO_MODEL",
}
DATE_SINGLE_RE = re.compile(r"^(?:\d{8}|\d{4}-\d{2}-\d{2})$")
DATE_WORD_RE = re.compile(r"^\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}$")
WINDOWS_ABSOLUTE_RE = re.compile(r"(?i)(?:^|[\s\"'])(?:[A-Z]:[\\/]|\\\\)")
Runner = Callable[..., subprocess.CompletedProcess[str]]


class InvocationError(ValueError):
    pass


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Request:
    ticker: str
    date: str
    broker: str


@dataclass(frozen=True)
class Settings:
    corpus_path: Path
    cache_path: Path
    model_provider: str
    model_name: str
    model_url: str
    model_api_key_env: str
    citation_viewer_host: str
    citation_viewer_port: int
    no_model: bool
    model_mode: str = "api"

    @property
    def citation_base_url(self) -> str:
        return f"http://{self.citation_viewer_host}:{self.citation_viewer_port}"


def _parse_bool(value: object, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigurationError(f"{field} must be true or false")


def _normalize_date(value: str) -> str:
    value = " ".join(value.split())
    formats = ("%Y%m%d", "%Y-%m-%d", "%d %b %Y", "%d %B %Y")
    for format_string in formats:
        try:
            return datetime.strptime(value, format_string).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise InvocationError(
        "date must be YYYYMMDD, YYYY-MM-DD, or D Mon YYYY (for example 22 Jun 2026)"
    )


def parse_command(command: str) -> Request:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as error:
        raise InvocationError(f"invalid quoting: {error}") from error
    if tokens and tokens[0] in {"/find-rpt", "find-rpt"}:
        tokens = tokens[1:]
    if not tokens:
        raise InvocationError("usage: /find-rpt {ticker} {date} {broker}")

    candidates: list[tuple[int, int, str]] = []
    for index, token in enumerate(tokens):
        if DATE_SINGLE_RE.fullmatch(token):
            candidates.append((index, index + 1, token))
        if index + 2 < len(tokens):
            joined = " ".join(tokens[index : index + 3])
            if DATE_WORD_RE.fullmatch(joined):
                try:
                    _normalize_date(joined)
                except InvocationError:
                    pass
                else:
                    candidates.append((index, index + 3, joined))
    if len(candidates) != 1:
        raise InvocationError("provide exactly one supported date between the ticker and broker")
    start, end, raw_date = candidates[0]
    ticker = " ".join(tokens[:start]).strip()
    broker = " ".join(tokens[end:]).strip()
    if not ticker or not broker:
        raise InvocationError("ticker, date, and broker are all required; missing values are not guessed")
    return Request(ticker=ticker, date=_normalize_date(raw_date), broker=broker)


def _read_config(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    if not path.is_file():
        raise ConfigurationError(f"configuration path is not a file: {path}")
    try:
        with path.open("rb") as source:
            parsed = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"cannot read configuration: {error}") from error
    section = parsed.get("find_rpt", {})
    if not isinstance(section, dict):
        raise ConfigurationError("[find_rpt] must be a TOML table")
    unknown = set(section) - set(DEFAULTS)
    if unknown:
        raise ConfigurationError(f"unknown configuration field(s): {', '.join(sorted(unknown))}")
    return dict(section)


def load_settings(
    *,
    config_path: Path = Path("find-rpt.toml"),
    environment: Mapping[str, str] | None = None,
    overrides: Mapping[str, object | None] | None = None,
) -> Settings:
    env = os.environ if environment is None else environment
    values = dict(DEFAULTS)
    values.update(_read_config(config_path))
    for field, variable in ENVIRONMENT.items():
        if variable in env and env[variable] != "":
            values[field] = env[variable]
    for field, value in (overrides or {}).items():
        if value is not None:
            values[field] = value

    no_model = _parse_bool(values["no_model"], field="no_model")
    model_mode = str(values["model_mode"]).strip().casefold()
    if model_mode not in {"agent-hosted", "api", "none"}:
        raise ConfigurationError("model_mode must be agent-hosted, api, or none")
    provider = str(values["model_provider"]).strip().casefold()
    if provider == "none":
        no_model = True
        model_mode = "none"
    elif provider != "local-openai-compatible":
        raise ConfigurationError(
            "model_provider must be local-openai-compatible or none; external providers are unsupported"
        )
    if model_mode == "none":
        no_model = True
    host = str(values["citation_viewer_host"]).strip()
    try:
        if not ipaddress.ip_address(socket.gethostbyname(host)).is_loopback:
            raise ConfigurationError("citation_viewer_host must resolve to loopback")
    except OSError as error:
        raise ConfigurationError("citation_viewer_host cannot be resolved") from error
    try:
        port = int(values["citation_viewer_port"])
    except (TypeError, ValueError) as error:
        raise ConfigurationError("citation_viewer_port must be an integer") from error
    if not 1 <= port <= 65535:
        raise ConfigurationError("citation_viewer_port must be between 1 and 65535")

    key_env = str(values["model_api_key_env"]).strip()
    if not key_env or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
        raise ConfigurationError("model_api_key_env must be an environment-variable name")
    model_url = str(values["model_url"]).strip()
    parsed_model_url = urlsplit(model_url)
    if (
        parsed_model_url.scheme not in {"http", "https"}
        or not parsed_model_url.hostname
        or parsed_model_url.username is not None
        or parsed_model_url.password is not None
        or parsed_model_url.query
        or parsed_model_url.fragment
    ):
        raise ConfigurationError("model_url must be a plain local HTTP(S) endpoint")
    try:
        if not ipaddress.ip_address(socket.gethostbyname(parsed_model_url.hostname)).is_loopback:
            raise ConfigurationError("model_url must resolve to loopback")
    except OSError as error:
        raise ConfigurationError("model_url host cannot be resolved") from error
    return Settings(
        corpus_path=Path(str(values["corpus_path"])),
        cache_path=Path(str(values["cache_path"])),
        model_provider=provider,
        model_name=str(values["model_name"]),
        model_url=model_url,
        model_api_key_env=key_env,
        citation_viewer_host=host,
        citation_viewer_port=port,
        no_model=no_model,
        model_mode=model_mode,
    )


def citation_viewer_available(settings: Settings, *, timeout: float = 0.2) -> bool:
    connection = http.client.HTTPConnection(
        settings.citation_viewer_host,
        settings.citation_viewer_port,
        timeout=timeout,
    )
    try:
        connection.request("GET", "/__find_rpt_health__")
        response = connection.getresponse()
        response.read()
        return response.getheader("Server", "").startswith("find-rpt-citations/1")
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def _error_payload(status: str, message: str, request: Request | None = None) -> dict[str, Any]:
    if _contains_absolute_path(message):
        message = (
            "Configuration failed; check the configured local paths."
            if status == "configuration_error"
            else "The operation failed without exposing local paths."
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "normalized_request": (
            {"ticker": request.ticker, "date": request.date, "broker": request.broker}
            if request
            else None
        ),
        "message": message,
        "warnings": [],
        "requires_analyst_escalation": False,
        "email_draft": None,
        "sent": False,
    }


def _parse_json_stream(value: str) -> dict[str, Any] | None:
    if not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _serialize_payload(value: Mapping[str, Any]) -> str:
    """Keep JSON transport safe on Windows consoles without changing parsed text."""
    return json.dumps(value, indent=2, ensure_ascii=True)


def _contains_absolute_path(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_absolute_path(item) for item in value)
    if not isinstance(value, str) or value.startswith(("http://", "https://")):
        return False
    if WINDOWS_ABSOLUTE_RE.search(value):
        return True
    return value.startswith("/") and not value.startswith("/find-rpt")


def _has_sent_true(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "sent" and item is not False) or _has_sent_true(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_has_sent_true(item) for item in value)
    return False


def execute_request(
    request: Request,
    settings: Settings,
    *,
    runner: Runner = subprocess.run,
    viewer_check: Callable[[Settings], bool] = citation_viewer_available,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "find_rpt",
        "brief",
        "--ticker",
        request.ticker,
        "--date",
        request.date,
        "--broker",
        request.broker,
        "--corpus",
        str(settings.corpus_path),
        "--cache-dir",
        str(settings.cache_path),
        "--base-url",
        settings.citation_base_url,
        "--format",
        "agent-json",
    ]
    if settings.no_model:
        command.append("--no-model")
    child_env = dict(os.environ if environment is None else environment)
    child_env["FIND_RPT_MODEL_NAME"] = settings.model_name
    child_env["FIND_RPT_MODEL_URL"] = settings.model_url
    child_env["FIND_RPT_MODEL_MODE"] = settings.model_mode
    if settings.model_api_key_env in child_env:
        child_env["FIND_RPT_MODEL_API_KEY"] = child_env[settings.model_api_key_env]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env,
            check=False,
        )
    except OSError as error:
        return _error_payload("configuration_error", f"find-rpt CLI could not start: {error}", request)

    stdout_payload = _parse_json_stream(completed.stdout)
    stderr_payload = _parse_json_stream(completed.stderr)
    if completed.returncode == 2:
        if stdout_payload and "corpus path does not exist" in str(stdout_payload.get("reason", "")).casefold():
            return _error_payload("configuration_error", str(stdout_payload["reason"]), request)
        return _error_payload(
            "not_found",
            str((stdout_payload or {}).get("reason", "No matching report was found.")),
            request,
        )
    if completed.returncode == 3:
        result = _error_payload(
            "ambiguous",
            str((stdout_payload or {}).get("reason", "Multiple reports matched; none was selected.")),
            request,
        )
        result["candidates"] = (stdout_payload or {}).get("candidates", [])
        return result
    if completed.returncode != 0:
        error = stderr_payload or stdout_payload or {}
        error_name = str(error.get("error", ""))
        if error_name in {"ModelConfigurationError", "ModelResponseError"} or error.get("status") == "model_error":
            status = "model_unavailable"
        elif error_name:
            status = "configuration_error"
        else:
            status = "cli_error"
        message = str(error.get("message", completed.stderr.strip() or "find-rpt CLI failed"))
        return _error_payload(status, message, request)
    if stdout_payload is None:
        return _error_payload("malformed_cli_json", "find-rpt returned malformed JSON", request)
    required = {
        "schema_version",
        "status",
        "normalized_request",
        "brief",
        "citations",
        "warnings",
        "requires_analyst_escalation",
        "sent",
        "rendered_markdown",
    }
    missing = required - set(stdout_payload)
    if missing:
        return _error_payload(
            "malformed_cli_json",
            f"find-rpt JSON is missing required field(s): {', '.join(sorted(missing))}",
            request,
        )
    if _has_sent_true(stdout_payload):
        return _error_payload("safety_error", "find-rpt violated the immutable no-send contract", request)
    if _contains_absolute_path(stdout_payload):
        return _error_payload("safety_error", "find-rpt output contained an absolute path", request)

    result = dict(stdout_payload)
    result["normalized_request"] = {
        "ticker": request.ticker,
        "date": request.date,
        "broker": request.broker,
    }
    available = viewer_check(settings)
    result["citation_viewer_available"] = available
    if not available and result.get("citations"):
        warnings = list(result.get("warnings", []))
        warnings.append("citation_viewer_unavailable")
        result["warnings"] = list(dict.fromkeys(warnings))
        if result.get("status") == "found":
            result["status"] = "partial"
    result["sent"] = False
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="find-rpt-agent")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--command", nargs="+", help="complete /find-rpt invocation")
    inputs.add_argument("--ticker", help="Bloomberg ticker; use with --date and --broker")
    parser.add_argument("--date")
    parser.add_argument("--broker")
    parser.add_argument("--config", type=Path, default=Path("find-rpt.toml"))
    parser.add_argument("--corpus", dest="corpus_path")
    parser.add_argument("--cache-dir", dest="cache_path")
    parser.add_argument("--model-provider")
    parser.add_argument("--model-mode", choices=("agent-hosted", "api", "none"))
    parser.add_argument("--model-name")
    parser.add_argument("--model-url")
    parser.add_argument("--model-api-key-env")
    parser.add_argument("--citation-viewer-host")
    parser.add_argument("--citation-viewer-port", type=int)
    parser.add_argument("--no-model", action="store_true", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command is not None:
            request = parse_command(" ".join(args.command))
        else:
            if not args.date or not args.broker:
                raise InvocationError("--date and --broker are required with --ticker")
            request = Request(args.ticker, _normalize_date(args.date), args.broker)
        settings = load_settings(
            config_path=args.config,
            overrides={
                key: getattr(args, key)
                for key in DEFAULTS
                if hasattr(args, key)
            },
        )
        result = execute_request(request, settings)
    except (InvocationError, ConfigurationError) as error:
        result = _error_payload(
            "invalid_invocation" if isinstance(error, InvocationError) else "configuration_error",
            str(error),
        )
    print(_serialize_payload(result))
    return 0 if result["status"] in {"found", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
