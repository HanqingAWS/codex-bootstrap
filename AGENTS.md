# Repository Guidelines

## Project Structure & Module Organization

This repository configures Codex CLI on EC2 for Bedrock Runtime using instance roles.

- `bootstrap.py`: installs user configuration and the model catalog; conditionally updates `.bashrc`.
- `smoke.py`: validates one model through a bounded, read-only Codex invocation.
- `bedrock-models.json`: complete metadata for the four supported models.
- `config.example.toml`: reference configuration; `README.md`: Chinese-language setup and troubleshooting guide.
- `result-us.openai.*.json`: recorded live-test results. `smoke-workspace/` is the generated invocation directory.

There are no separate source, unit-test, or asset directories.

## Build, Test, and Development Commands

Scripts use only Python's standard library; no build step is needed. Live validation requires AWS CLI, an authorized EC2 instance role, network access, and Codex at `~/.local/bin/codex` (verified version: `0.154.0`).

- `python3 -m py_compile bootstrap.py smoke.py`: check Python syntax.
- `python3 -m json.tool bedrock-models.json > /dev/null`: validate catalog JSON.
- `HOME="$(mktemp -d)" python3 bootstrap.py`: exercise configuration generation in a disposable home.
- `python3 bootstrap.py`: configure the actual user home; refuses existing configuration or catalog files.
- `python3 smoke.py --model us.openai.gpt-6-astra`: run one live check, overwriting its result JSON.
- `codex`: start the configured CLI.

## Coding Style & Naming Conventions

Follow existing Python conventions: four-space indentation, `snake_case` functions and variables, uppercase constants, and `main()` entry points. Prefer `pathlib`, structured JSON APIs, and explicit subprocess timeouts. No formatter or linter is configured.

Keep model identifiers synchronized across both scripts and the catalog. Preserve full catalog metadata and keep generated configuration aligned with `config.example.toml` and `README.md`.

## Testing Guidelines

No unit-test framework or coverage threshold is configured. After model, configuration, or CLI changes, run smoke checks for every entry in `smoke.py`'s `MODELS`.

Inspect each `result-<model-id>.json` for `ok: true`, `response: "OK"`, and `exit_code: 0`; the smoke script's own exit status does not reliably indicate model failure. Review bootstrap refusal-to-overwrite behavior in a disposable home.

## Commit & Pull Request Guidelines

Git history is unavailable here, so commit conventions cannot be verified. Use concise, imperative subjects, such as `Fix bootstrap catalog validation`.

PRs should describe affected configuration, link relevant issues, list validation commands and outcomes, and explain model or CLI-version changes. Review result artifacts for account identifiers before sharing.

## Security & Configuration Tips

Never commit credentials or weaken overwrite protections. Preserve restrictive configuration permissions. Keep the endpoint and both provider regions consistent. Smoke checks require absent `~/.aws/credentials` and `~/.codex/.env`; do not delete legitimate user files to satisfy them.
