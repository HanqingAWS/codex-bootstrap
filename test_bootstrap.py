import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import bootstrap


ROOT = Path(__file__).resolve().parent


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bootstrap test '")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.managed = self.home / ".codex-bedrock/.codex"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / "old-codex"),
            "PATH": str(self.home / ".local/bin") + os.pathsep + os.defpath,
        }

    def run_bootstrap(self, success=True):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bootstrap.py")],
            env=self.env, capture_output=True, text=True, timeout=15,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return result.stderr

    def test_fresh_setup_preserves_legacy_configuration(self):
        legacy = self.home / ".codex"
        legacy.mkdir()
        old_config = legacy / "config.toml"
        old_config.write_text('model_provider = "openai"\n')
        old_auth = legacy / "auth.json"
        old_auth.write_text('{"existing": "leave unchanged"}\n')
        existing_override = self.home / "old-codex"
        existing_override.mkdir()
        override_config = existing_override / "config.toml"
        override_config.write_text("# Keep this configuration\n")

        result = self.run_bootstrap()

        self.assertEqual(result["codex_home"], str(self.managed))
        self.assertFalse(result["configuration_reused"])
        self.assertTrue(result["shell_changed"])
        self.assertFalse(result["current_shell_updated"])
        self.assertFalse(result["credentials_written"])
        self.assertEqual(old_config.read_text(), 'model_provider = "openai"\n')
        self.assertEqual(old_auth.read_text(), '{"existing": "leave unchanged"}\n')
        self.assertEqual(override_config.read_text(), "# Keep this configuration\n")
        catalog = self.managed / "model-catalogs/bedrock-models.json"
        self.assertEqual(catalog.read_bytes(), (ROOT / "bedrock-models.json").read_bytes())
        for directory in (self.managed.parent, self.managed, catalog.parent):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        for path in (catalog, self.managed / "config.toml", self.home / ".bashrc"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_shell_export_is_added_even_when_path_already_contains_codex(self):
        self.run_bootstrap()
        result = subprocess.run(
            ["/bin/bash", "--noprofile", "--norc", "-c",
             'source "$HOME/.bashrc"\nprintf "%s\\n%s" "$CODEX_HOME" "$PATH"'],
            env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        codex_home, path = result.stdout.splitlines()
        self.assertEqual(codex_home, str(self.managed))
        self.assertEqual(path.split(os.pathsep).count(str(self.home / ".local/bin")), 1)

    def test_missing_path_is_added_by_shell_block(self):
        self.env["PATH"] = os.defpath
        self.run_bootstrap()
        result = subprocess.run(
            ["/bin/bash", "--noprofile", "--norc", "-c",
             'source "$HOME/.bashrc"\nprintf "%s" "$PATH"'],
            env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(os.pathsep)[0], str(self.home / ".local/bin"))

    def test_new_interactive_bash_loads_codex_home_automatically(self):
        self.run_bootstrap()
        result = subprocess.run(
            ["/bin/bash", "--noprofile", "-ic", 'printf "%s" "$CODEX_HOME"'],
            env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(self.managed))

    def test_bashrc_backup_and_repeated_execution(self):
        bashrc = self.home / ".bashrc"
        original = b'# Existing shell configuration\nexport CODEX_HOME="$HOME/old-codex"\n'
        bashrc.write_bytes(original)
        bashrc.chmod(0o640)
        first = self.run_bootstrap()
        backup = Path(first["bashrc_backup"])
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(bashrc.stat().st_mode & 0o777, 0o640)
        paths = [self.managed / "config.toml",
                 self.managed / "model-catalogs/bedrock-models.json", bashrc]
        snapshots = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]

        second = self.run_bootstrap()

        self.assertTrue(second["configuration_reused"])
        self.assertFalse(second["shell_changed"])
        self.assertIsNone(second["bashrc_backup"])
        self.assertEqual(snapshots, [
            (path.read_bytes(), path.stat().st_mtime_ns) for path in paths
        ])
        self.assertEqual(bashrc.read_bytes().count(bootstrap.BASHRC_MARKER.encode()), 1)
        self.assertEqual(len(list(self.home.glob(".bashrc.backup-codex-*"))), 1)

    def test_previous_manual_isolated_setup_can_be_reused(self):
        catalog = self.managed / "model-catalogs/bedrock-models.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_bytes((ROOT / "bedrock-models.json").read_bytes())
        (self.managed / "config.toml").write_bytes(bootstrap.config_content(catalog))
        result = self.run_bootstrap()
        self.assertTrue(result["configuration_reused"])
        self.assertTrue(result["shell_changed"])

    def test_changed_files_are_not_overwritten(self):
        self.run_bootstrap()
        for relative in ("config.toml", "model-catalogs/bedrock-models.json"):
            with self.subTest(file=relative):
                path = self.managed / relative
                original = path.read_bytes()
                changed = original + b"\n# User customization\n"
                path.write_bytes(changed)
                shell_before = (self.home / ".bashrc").read_bytes()
                self.assertIn("refusing to overwrite", self.run_bootstrap(success=False))
                self.assertEqual(path.read_bytes(), changed)
                self.assertEqual((self.home / ".bashrc").read_bytes(), shell_before)
                path.write_bytes(original)

    def test_catalog_conflict_does_not_create_config_or_shell_files(self):
        catalog = self.managed / "model-catalogs/bedrock-models.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text('{"models": []}\n')
        self.run_bootstrap(success=False)
        self.assertFalse((self.managed / "config.toml").exists())
        self.assertFalse((self.home / ".bashrc").exists())
        self.assertEqual(catalog.read_text(), '{"models": []}\n')

    def test_changed_shell_block_is_not_overwritten(self):
        self.run_bootstrap()
        bashrc = self.home / ".bashrc"
        edited = bashrc.read_bytes().replace(b".codex-bedrock", b".custom-codex")
        bashrc.write_bytes(edited)
        self.assertIn("shell block differs", self.run_bootstrap(success=False))
        self.assertEqual(bashrc.read_bytes(), edited)

    def test_symbolic_links_are_rejected(self):
        for relative in (".codex-bedrock", ".bashrc",
                         ".codex-bedrock/.codex/config.toml",
                         ".codex-bedrock/.codex/model-catalogs/bedrock-models.json"):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as home:
                self.env["HOME"] = home
                target = Path(home) / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(Path(home) / "absent-target")
                self.run_bootstrap(success=False)
                self.assertTrue(target.is_symlink())
                self.assertFalse((Path(home) / "absent-target").exists())

    def test_example_and_readme_match_generated_configuration(self):
        def normalized(content):
            return [
                'model_catalog_json = "PLACEHOLDER"' if line.startswith("model_catalog_json = ")
                else line for line in content.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]

        self.run_bootstrap()
        example = (ROOT / "config.example.toml").read_text()
        self.assertEqual(normalized(example),
                         normalized((self.managed / "config.toml").read_text()))
        self.assertIn(example.strip(), (ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
