#!/usr/bin/env python3
"""Install an isolated Bedrock configuration without replacing existing settings."""
import datetime
import json
import os
from pathlib import Path

MODELS = (
    "us.openai.gpt-5.6-sol", "us.openai.gpt-5.6-terra",
    "us.openai.gpt-5.6-luna", "us.openai.gpt-6-astra",
)
BASHRC_MARKER = "# Codex Bedrock bootstrap"
BASHRC_BLOCK = "\n".join([
    "", BASHRC_MARKER,
    'export CODEX_HOME="$HOME/.codex-bedrock/.codex"',
    'case ":$PATH:" in',
    '  *":$HOME/.local/bin:"*) ;;',
    '  *) export PATH="$HOME/.local/bin:$PATH" ;;',
    'esac',
    "# End Codex Bedrock bootstrap",
    "",
]).encode()


def bedrock_home():
    return Path.home() / ".codex-bedrock" / ".codex"


def config_content(catalog_target):
    return "\n".join([
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
    ]).encode()


def read_existing(path):
    if path.is_symlink():
        raise SystemExit("Refusing to follow an existing symbolic link: " + str(path))
    if path.exists():
        if not path.is_file():
            raise SystemExit("Expected a regular file: " + str(path))
        return path.read_bytes()
    return None


def write_new(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)


def main():
    home = Path.home()
    root = bedrock_home()
    config = root / "config.toml"
    catalog_dir = root / "model-catalogs"
    catalog_target = catalog_dir / "bedrock-models.json"
    catalog_source = Path(__file__).resolve().parent / "bedrock-models.json"
    catalog_bytes = catalog_source.read_bytes()
    catalog = json.loads(catalog_bytes)
    slugs = [model["slug"] for model in catalog["models"]]
    if len(slugs) != len(MODELS) or set(slugs) != set(MODELS):
        raise SystemExit("Model catalog does not match the supported models")

    # Validate all existing destinations before creating files or changing the shell.
    directories = (root.parent, root, catalog_dir)
    for directory in directories:
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise SystemExit("Expected a directory, not a file or symlink: " + str(directory))
    files = {
        config: config_content(catalog_target),
        catalog_target: catalog_bytes,
    }
    existing_files = {}
    for path, content in files.items():
        existing_files[path] = read_existing(path)
        if existing_files[path] is not None and existing_files[path] != content:
            raise SystemExit("Existing file differs; refusing to overwrite it: " + str(path))

    bashrc = home / ".bashrc"
    existing_bashrc = read_existing(bashrc)
    shell_content = existing_bashrc or b""
    if BASHRC_MARKER.encode() in shell_content and BASHRC_BLOCK not in shell_content:
        raise SystemExit("Existing Bedrock shell block differs; refusing to overwrite it")
    shell_changed = BASHRC_BLOCK not in shell_content

    for directory in directories:
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
    for path, content in files.items():
        if existing_files[path] is None:
            write_new(path, content)
        path.chmod(0o600)

    backup = None
    if shell_changed:
        if existing_bashrc is not None:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup = bashrc.with_name(".bashrc.backup-codex-" + stamp)
            write_new(backup, existing_bashrc)
        if existing_bashrc is None:
            write_new(bashrc, BASHRC_BLOCK)
        else:
            fd = os.open(bashrc, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
            with os.fdopen(fd, "wb") as stream:
                stream.write(BASHRC_BLOCK)
    print(json.dumps({
        "codex_home": str(root),
        "config": str(config),
        "catalog": str(catalog_target),
        "configuration_reused": all(value is not None for value in existing_files.values()),
        "shell_changed": shell_changed,
        "bashrc_backup": str(backup) if backup else None,
        "current_shell_updated": False,
        "next_step": "smoke.py works immediately; open a new Bash terminal or run: source ~/.bashrc",
        "credentials_written": False,
        "models": sorted(MODELS),
    }, indent=2))


if __name__ == "__main__":
    main()
