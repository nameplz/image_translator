#!/usr/bin/env python3
"""Codex Stop hook for lightweight project validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

import project_validation

LIGHTWEIGHT_VALIDATION_COMMANDS = (
    ("uv", "run", "ruff", "check", "."),
    ("uv", "run", "mypy", "src"),
)

run_validation = project_validation.run_validation


def select_validation_commands(cwd: Path) -> list[list[str]]:
    """Select the cheap Stop-hook gate for the current Python project."""
    if not (cwd / "pyproject.toml").is_file():
        return []
    return [list(command) for command in LIGHTWEIGHT_VALIDATION_COMMANDS]


def validation_failure(cwd: Path) -> str | None:
    """Return a failure reason when lightweight Stop-hook validation fails."""
    commands = select_validation_commands(cwd)
    if not commands:
        return None

    passed, reason = run_validation(commands, cwd)
    return None if passed else reason


def _continue() -> dict[str, Any]:
    return {"continue": True}


def _continue_with_validation_feedback(reason: str) -> dict[str, Any]:
    return {
        "decision": "block",
        "reason": f"Project validation failed. Address this before finishing:\n\n{reason}",
    }


def evaluate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("stop_hook_active") is True:
        return _continue()

    cwd = Path(str(payload.get("cwd") or ".")).resolve()
    reason = validation_failure(cwd)
    if reason is None:
        return _continue()
    return _continue_with_validation_feedback(reason)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}

    print(json.dumps(evaluate_payload(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
