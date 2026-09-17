#!/usr/bin/env python3
"""Run one bounded Codex invocation with EC2's existing instance-role credentials."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

from bootstrap import MODELS, bedrock_home


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=MODELS, required=True)
    args = parser.parse_args()
    codex_home = bedrock_home()
    if not (codex_home / "config.toml").is_file():
        raise SystemExit("Bedrock configuration not found; run: python3 bootstrap.py")
    for path in (
        Path.home() / ".aws/credentials",
        Path.home() / ".codex/.env",
        codex_home / ".env",
    ):
        if path.exists() or path.is_symlink():
            raise SystemExit("Credential file detected; do not delete it to run this test")
    root = Path(__file__).resolve().parent
    work = root / "smoke-workspace"
    work.mkdir(exist_ok=True)
    env = dict(os.environ)
    for name in (
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK", "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION",
        "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL",
    ):
        env.pop(name, None)
    env["CODEX_HOME"] = str(codex_home)
    identity = json.loads(subprocess.check_output(
        ["aws", "sts", "get-caller-identity", "--region", "us-west-2", "--output", "json"],
        text=True, env=env, timeout=30,
    ))
    binary = str(Path.home() / ".local/bin/codex")
    version = subprocess.check_output([binary, "--version"], text=True, env=env, timeout=15).strip()
    command = [
        binary, "exec", "--strict-config", "--ephemeral", "--skip-git-repo-check",
        "--ignore-rules", "--cd", str(work), "--sandbox", "read-only",
        "--model", args.model, "--json",
        "-c", 'model_reasoning_effort="low"',
        "-c", 'developer_instructions="Connection test only. Reply exactly OK. Never use tools."',
        "Reply with exactly OK. Do not use tools or read files.",
    ]
    start = time.monotonic()
    try:
        process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=150)
    except subprocess.TimeoutExpired:
        result = {"model": args.model, "ok": False, "error": "150 second timeout"}
    else:
        messages, errors, events = [], [], []
        for line in process.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            events.append(event.get("type"))
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    messages.append(item.get("text", ""))
            if event.get("type") in ("error", "turn.failed"):
                errors.append(event.get("message", event.get("error", {})))
        if process.returncode and not errors:
            errors = [process.stderr[-1800:]]
        result = {
            "model": args.model,
            "ok": bool(process.returncode == 0 and messages and messages[-1].strip() == "OK"),
            "response": messages[-1] if messages else None,
            "exit_code": process.returncode,
            "seconds": round(time.monotonic() - start, 1),
            "errors": errors, "events": events,
        }
    result.update({
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "codex_version": version,
        "aws_identity_checked": bool(identity.get("Arn")),
        "configuration": "managed-bedrock",
    })
    output = root / ("result-" + args.model + ".json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
