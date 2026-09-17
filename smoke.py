#!/usr/bin/env python3
"""Run one bounded Codex invocation with EC2's existing instance-role credentials."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

MODELS = (
    "us.openai.gpt-5.6-sol", "us.openai.gpt-5.6-terra",
    "us.openai.gpt-5.6-luna", "us.openai.gpt-6-astra",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=MODELS, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    work = root / "smoke-workspace"
    work.mkdir(exist_ok=True)
    env = dict(os.environ)
    for name in (
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK", "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION",
    ):
        env.pop(name, None)
    assert not (Path.home() / ".aws/credentials").exists()
    assert not (Path.home() / ".codex/.env").exists()
    identity = json.loads(subprocess.check_output(
        ["aws", "sts", "get-caller-identity", "--region", "us-west-2", "--output", "json"],
        text=True, env=env, timeout=30,
    ))
    binary = str(Path.home() / ".local/bin/codex")
    version = subprocess.check_output([binary, "--version"], text=True).strip()
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
        "codex_version": version, "caller_arn": identity["Arn"],
        "auth": "Existing EC2 instance role; no API key or static credential file",
        "region_from_config": True,
    })
    output = root / ("result-" + args.model + ".json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
