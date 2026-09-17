import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import smoke


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.managed = self.home / ".codex-bedrock/.codex"
        self.managed.mkdir(parents=True)
        (self.managed / "config.toml").write_text('model_provider = "amazon-bedrock-runtime"\n')
        self.removed_variables = (
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
            "AWS_BEARER_TOKEN_BEDROCK", "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION",
            "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL",
        )
        env = {name: "test-value" for name in self.removed_variables}
        env.update(HOME=str(self.home), CODEX_HOME=str(self.home / "old-codex"))
        self.environment = patch.dict(os.environ, env)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.source = patch.object(smoke, "__file__", str(self.home / "smoke.py"))
        self.source.start()
        self.addCleanup(self.source.stop)
        self.argv = patch("sys.argv", ["smoke.py", "--model", smoke.MODELS[0]])
        self.argv.start()
        self.addCleanup(self.argv.stop)

    def invoke(self, process=None, error=None):
        if process is None:
            event = {"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}}
            process = subprocess.CompletedProcess([], 0, json.dumps(event) + "\n", "")
        stdout = io.StringIO()
        with patch.object(smoke.subprocess, "check_output", side_effect=[
            '{"Arn": "test-identity"}', "codex-cli test\n",
        ]) as checks, patch.object(smoke.subprocess, "run",
                                  return_value=process, side_effect=error) as run:
            with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as exit_info:
                smoke.main()
        result = json.loads(stdout.getvalue()) if stdout.getvalue() else None
        return exit_info.exception.code, result, checks, run

    def test_selects_managed_home_without_parent_shell_export(self):
        code, result, checks, run = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["configuration"], "managed-bedrock")
        self.assertTrue(result["aws_identity_checked"])
        self.assertNotIn("caller_arn", result)
        self.assertNotIn("region_from_config", result)
        self.assertNotIn("auth", result)
        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["CODEX_HOME"], str(self.managed))
        for name in self.removed_variables:
            self.assertNotIn(name, child_env)
            self.assertEqual(os.environ[name], "test-value")
        self.assertEqual(os.environ["CODEX_HOME"], str(self.home / "old-codex"))
        self.assertEqual(checks.call_args.kwargs["env"], child_env)
        self.assertEqual(checks.call_args.kwargs["timeout"], 15)
        self.assertEqual(run.call_args.kwargs["timeout"], 150)
        output = self.home / ("result-" + smoke.MODELS[0] + ".json")
        self.assertEqual(json.loads(output.read_text()), result)

    def test_missing_configuration_fails_before_aws_or_codex(self):
        (self.managed / "config.toml").unlink()
        code, result, checks, run = self.invoke()
        self.assertIn("python3 bootstrap.py", code)
        self.assertIsNone(result)
        checks.assert_not_called()
        run.assert_not_called()

    def test_credential_files_are_never_removed(self):
        for path in (self.home / ".aws/credentials", self.home / ".codex/.env",
                     self.managed / ".env"):
            with self.subTest(path=path.name):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("user-owned configuration\n")
                code, result, checks, run = self.invoke()
                self.assertIn("do not delete", code)
                self.assertIsNone(result)
                checks.assert_not_called()
                run.assert_not_called()
                self.assertEqual(path.read_text(), "user-owned configuration\n")
                path.unlink()

    def test_failed_model_returns_nonzero(self):
        process = subprocess.CompletedProcess([], 1, "", "Synthetic failure")
        code, result, _, _ = self.invoke(process=process)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 1)

    def test_wrong_response_returns_nonzero_even_when_codex_succeeds(self):
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": "NO"}}
        process = subprocess.CompletedProcess([], 0, json.dumps(event) + "\n", "")
        code, result, _, _ = self.invoke(process=process)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 0)

    def test_timeout_returns_nonzero_and_records_failure(self):
        code, result, _, _ = self.invoke(error=subprocess.TimeoutExpired("codex", 150))
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "150 second timeout")


if __name__ == "__main__":
    unittest.main()
