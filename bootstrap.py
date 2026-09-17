#!/usr/bin/env python3
"""Configure a fresh EC2 user's Codex installation without copying credentials."""
import datetime
import json
import os
from pathlib import Path
import shutil


def main():
    home = Path.home()
    root = home / ".codex"
    config = root / "config.toml"
    catalog_source = Path(__file__).resolve().parent / "bedrock-models.json"
    catalog = json.loads(catalog_source.read_text())
    expected = {
        "us.openai.gpt-5.6-sol", "us.openai.gpt-5.6-terra",
        "us.openai.gpt-5.6-luna", "us.openai.gpt-6-astra",
    }
    assert {model["slug"] for model in catalog["models"]} == expected
    if config.exists():
        raise SystemExit("Existing config.toml detected; refusing to overwrite it")
    root.mkdir(mode=0o700, exist_ok=True)
    catalog_dir = root / "model-catalogs"
    catalog_dir.mkdir(mode=0o700, exist_ok=True)
    catalog_target = catalog_dir / "bedrock-models.json"
    if catalog_target.exists():
        raise SystemExit("Existing model catalog detected; refusing to overwrite it")
    shutil.copyfile(catalog_source, catalog_target)
    os.chmod(catalog_target, 0o600)
    content = '\n'.join([
        'model = "us.openai.gpt-6-astra"',
        'model_provider = "amazon-bedrock-runtime"',
        'model_reasoning_effort = "high"',
        'web_search = "disabled"',
        'approval_policy = "on-request"',
        'sandbox_mode = "workspace-write"',
        'model_catalog_json = ' + json.dumps(str(catalog_target)),
        '',
        '[model_providers.amazon-bedrock-runtime]',
        'base_url = "https://bedrock-runtime.us-west-2.amazonaws.com/openai/v1"',
        'wire_api = "responses"',
        '',
        '[model_providers.amazon-bedrock-runtime.aws]',
        'region = "us-west-2"',
        '',
        '# Kept for compatibility with clients that inspect the original provider.',
        '[model_providers.amazon-bedrock.aws]',
        'region = "us-west-2"',
        '',
    ])
    fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    bashrc = home / ".bashrc"
    path_changed = False
    backup = None
    if str(home / ".local/bin") not in os.environ.get("PATH", "").split(":"):
        existing = bashrc.read_text() if bashrc.exists() else ""
        marker = "# Codex CLI user installation"
        if marker not in existing:
            if bashrc.exists():
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                backup = bashrc.with_name(".bashrc.backup-codex-" + stamp)
                shutil.copy2(bashrc, backup)
            block = '\n'.join([
                '', marker, 'case ":$PATH:" in',
                '  *":$HOME/.local/bin:"*) ;;',
                '  *) export PATH="$HOME/.local/bin:$PATH" ;;',
                'esac', '',
            ])
            with bashrc.open("a") as stream:
                stream.write(block)
            path_changed = True
    print(json.dumps({
        "config": str(config),
        "catalog": str(catalog_target),
        "path_changed": path_changed,
        "bashrc_backup": str(backup) if backup else None,
        "credentials_written": False,
        "models": sorted(expected),
    }, indent=2))


if __name__ == "__main__":
    main()
