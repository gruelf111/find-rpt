from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "skills" / "find-rpt" / "scripts" / "find_rpt.py"
SPEC = importlib.util.spec_from_file_location("find_rpt_skill_launcher", LAUNCHER)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = launcher
SPEC.loader.exec_module(launcher)


def settings(**changes):
    values = {
        "corpus_path": Path("corpus"),
        "cache_path": Path(".cache/find-rpt/citations"),
        "model_provider": "local-openai-compatible",
        "model_name": "local-rationale-model",
        "model_url": "http://127.0.0.1:11434/v1/chat/completions",
        "model_api_key_env": "FIND_RPT_MODEL_API_KEY",
        "citation_viewer_host": "127.0.0.1",
        "citation_viewer_port": 8765,
        "no_model": True,
    }
    values.update(changes)
    return launcher.Settings(**values)


def agent_payload(**changes):
    payload = {
        "schema_version": "1.0",
        "status": "found",
        "normalized_request": {
            "ticker": "ABC LN",
            "date": "20260622",
            "broker": "Example Broker",
        },
        "selected_report": {
            "source_identifier": "synthetic.pdf",
            "title": "Synthetic report",
            "internal_publication_date": None,
        },
        "brief": {"revisions_status": "revisions_found", "revision_rows": []},
        "revisions": {"status": "revisions_found", "rows": [], "omitted_rows": 0},
        "rationale_clarity": "clear",
        "context": {
            "report_context": "results_preview",
            "management_contact": "false",
            "people_met": [],
        },
        "citations": [
            {
                "citation_id": "cit-0123456789abcdef01234567",
                "label": "synthetic evidence",
                "local_url": "http://127.0.0.1:8765/citation/cit-0123456789abcdef01234567#evidence-target",
                "page_number": 1,
                "validation_status": "valid",
            }
        ],
        "warnings": [],
        "requires_analyst_escalation": False,
        "analyst": [],
        "email_draft": None,
        "sent": False,
        "rendered_markdown": "**ABC LN - Example Broker - 22 Jun 2026** [source](http://127.0.0.1:8765/citation/cit-0123456789abcdef01234567#evidence-target)\n",
    }
    payload.update(changes)
    return payload


class InvocationTests(unittest.TestCase):
    def test_valid_skill_invocation_preserves_ticker_and_quoted_broker(self):
        request = launcher.parse_command('/find-rpt BP/ LN 22 Jun 2026 "J.P. Morgan"')
        self.assertEqual(request.ticker, "BP/ LN")
        self.assertEqual(request.date, "2026-06-22")
        self.assertEqual(request.broker, "J.P. Morgan")

    def test_supported_date_formats(self):
        for raw in ("20260622", "2026-06-22", "22 Jun 2026"):
            with self.subTest(raw=raw):
                request = launcher.parse_command(f'/find-rpt SAP GY {raw} "Kepler Cheuvreux"')
                self.assertEqual(request.date, "2026-06-22")

    def test_missing_arguments_are_rejected_without_guessing(self):
        with self.assertRaises(launcher.InvocationError):
            launcher.parse_command("/find-rpt SAP GY 2026-06-22")


class ConfigurationTests(unittest.TestCase):
    def test_precedence_cli_environment_config_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "find-rpt.toml"
            config.write_text('[find_rpt]\ncorpus_path = "from-config"\nno_model = false\n', encoding="utf-8")
            loaded = launcher.load_settings(
                config_path=config,
                environment={"FIND_RPT_CORPUS": "from-env", "FIND_RPT_NO_MODEL": "true"},
                overrides={"corpus_path": "from-cli"},
            )
        self.assertEqual(loaded.corpus_path, Path("from-cli"))
        self.assertTrue(loaded.no_model)

    def test_external_model_provider_and_non_loopback_viewer_are_rejected(self):
        with self.assertRaises(launcher.ConfigurationError):
            launcher.load_settings(
                config_path=Path("missing.toml"),
                environment={},
                overrides={"model_provider": "external"},
            )
        with self.assertRaises(launcher.ConfigurationError):
            launcher.load_settings(
                config_path=Path("missing.toml"),
                environment={},
                overrides={"citation_viewer_host": "8.8.8.8"},
            )
        with self.assertRaises(launcher.ConfigurationError):
            launcher.load_settings(
                config_path=Path("missing.toml"),
                environment={},
                overrides={"model_url": "https://example.com/v1/chat/completions"},
            )

    def test_configuration_errors_do_not_expose_absolute_paths(self):
        result = launcher._error_payload(
            "configuration_error",
            r"cannot read configuration: C:\private\find-rpt.toml",
        )
        self.assertEqual(result["status"], "configuration_error")
        self.assertNotIn("C:\\private", result["message"])


class LauncherIntegrationTests(unittest.TestCase):
    request = launcher.Request("BP/ LN", "2026-06-22", "J.P. Morgan")

    @staticmethod
    def runner_for(payload, returncode=0, *, stderr=""):
        def run(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                returncode,
                stdout=json.dumps(payload) if not isinstance(payload, str) else payload,
                stderr=stderr,
            )
        return run

    def test_success_calls_brief_agent_json_and_preserves_citations(self):
        result = launcher.execute_request(
            self.request,
            settings(),
            runner=self.runner_for(agent_payload()),
            viewer_check=lambda _: True,
            environment={},
        )
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["normalized_request"]["date"], "2026-06-22")
        self.assertIn("#evidence-target", result["rendered_markdown"])
        self.assertFalse(result["sent"])

    def test_not_found_and_ambiguous_are_transparent(self):
        not_found = {"status": "not_found", "reason": "No ticker evidence was found."}
        ambiguous = {"status": "ambiguous", "reason": "Candidates tied.", "candidates": [{"filename": "safe.pdf"}]}
        first = launcher.execute_request(
            self.request, settings(), runner=self.runner_for(not_found, 2), viewer_check=lambda _: True
        )
        second = launcher.execute_request(
            self.request, settings(), runner=self.runner_for(ambiguous, 3), viewer_check=lambda _: True
        )
        self.assertEqual(first["status"], "not_found")
        self.assertEqual(second["status"], "ambiguous")
        self.assertEqual(second["candidates"], ambiguous["candidates"])

    def test_partial_no_revisions_and_unclear_escalation_are_preserved(self):
        draft = {
            "to": "[TODO: address]",
            "analyst_names": ["Synthetic Analyst"],
            "questions": ["What drove the synthetic revision?"],
            "sent": False,
        }
        payload = agent_payload(
            status="partial",
            revisions={"status": "no_revisions", "rows": [], "omitted_rows": 0},
            rationale_clarity="unclear",
            requires_analyst_escalation=True,
            analyst=[{"name": "Synthetic Analyst", "email": None}],
            email_draft=draft,
            warnings=["no_estimate_revisions_found"],
        )
        result = launcher.execute_request(
            self.request, settings(), runner=self.runner_for(payload), viewer_check=lambda _: True
        )
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["requires_analyst_escalation"])
        self.assertEqual(result["email_draft"]["to"], "[TODO: address]")
        self.assertFalse(result["email_draft"]["sent"])

    def test_model_and_viewer_unavailable_are_distinct(self):
        model_error = {"error": "ModelConfigurationError", "message": "local model key missing"}
        unavailable = launcher.execute_request(
            self.request,
            settings(no_model=False),
            runner=self.runner_for("", 1, stderr=json.dumps(model_error)),
            viewer_check=lambda _: True,
        )
        partial = launcher.execute_request(
            self.request,
            settings(),
            runner=self.runner_for(agent_payload()),
            viewer_check=lambda _: False,
        )
        self.assertEqual(unavailable["status"], "model_unavailable")
        self.assertEqual(partial["status"], "partial")
        self.assertIn("citation_viewer_unavailable", partial["warnings"])

    def test_malformed_cli_json_fails_closed(self):
        result = launcher.execute_request(
            self.request, settings(), runner=self.runner_for("not-json"), viewer_check=lambda _: True
        )
        self.assertEqual(result["status"], "malformed_cli_json")

    def test_no_send_and_absolute_path_guards_fail_closed(self):
        sent = launcher.execute_request(
            self.request,
            settings(),
            runner=self.runner_for(agent_payload(sent=True)),
            viewer_check=lambda _: True,
        )
        leaked = launcher.execute_request(
            self.request,
            settings(),
            runner=self.runner_for(agent_payload(rendered_markdown="C:\\private\\report.pdf")),
            viewer_check=lambda _: True,
        )
        self.assertEqual(sent["status"], "safety_error")
        self.assertEqual(leaked["status"], "safety_error")

    def test_rendering_is_deterministic(self):
        runner = self.runner_for(agent_payload())
        first = launcher.execute_request(self.request, settings(), runner=runner, viewer_check=lambda _: True)
        second = launcher.execute_request(self.request, settings(), runner=runner, viewer_check=lambda _: True)
        self.assertEqual(first, second)

    def test_unicode_markdown_uses_console_safe_json_transport(self):
        payload = agent_payload(rendered_markdown="Old |███ — 1.0\nNew |████ — 1.2\n")
        serialized = launcher._serialize_payload(payload)
        serialized.encode("cp1252")
        self.assertEqual(json.loads(serialized)["rendered_markdown"], payload["rendered_markdown"])


class PackagingFilesTests(unittest.TestCase):
    def test_codex_and_optional_claude_wrappers_are_thin(self):
        skill = (ROOT / "skills" / "find-rpt" / "SKILL.md").read_text(encoding="utf-8")
        claude = (ROOT / ".claude" / "commands" / "find-rpt.md").read_text(encoding="utf-8")
        launcher_text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("python -m find_rpt", skill)
        self.assertIn("agent prepare", skill)
        self.assertIn("agent finalize", skill)
        self.assertIn("--input -", skill)
        self.assertNotIn("python skills/find-rpt/scripts/find_rpt.py", skill)
        self.assertIn("skills/find-rpt/scripts/find_rpt.py", claude)
        for forbidden in ("PdfEvidenceExtractor", "RevisionExtractor", "RationaleExtractor", "CitationBuilder"):
            self.assertNotIn(forbidden, launcher_text)

    def test_skill_files_have_no_machine_specific_absolute_paths(self):
        for path in (ROOT / "skills" / "find-rpt").rglob("*"):
            if path.is_file() and path.suffix in {".md", ".py", ".yaml", ".toml"}:
                text = path.read_text(encoding="utf-8")
                without_urls = text.replace("http://", "").replace("https://", "")
                self.assertNotRegex(without_urls, r"(?i)[A-Z]:[\\/]")
                self.assertNotIn("/Users/", text)

    def test_clean_install_command(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--no-cache-dir",
                    "--no-deps",
                    "--no-build-isolation",
                    "--target",
                    directory,
                    str(ROOT),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
