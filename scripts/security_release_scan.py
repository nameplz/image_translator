#!/usr/bin/env python3
"""Scan release-sensitive committed surfaces for obvious secrets and personal paths."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "htmlcov",
}
BINARY_SUFFIXES = {
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".sqlite",
    ".sqlite3",
    ".webp",
}
CONFIG_SUFFIXES = {".cfg", ".conf", ".env", ".ini", ".json", ".toml", ".yaml", ".yml"}
FIXTURE_SUFFIXES = CONFIG_SUFFIXES | {".log", ".txt"}
ROOT_CONFIG_FILES = {
    ".harness/validation.json",
    ".codex/config.toml",
    "pyproject.toml",
}
PLACEHOLDER_WORDS = {
    "changeme",
    "change_me",
    "dummy",
    "example",
    "fake",
    "local",
    "mock",
    "placeholder",
    "redacted",
    "sample",
    "test",
    "your",
}

OPENAI_KEY_RE = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b")
GITHUB_TOKEN_RE = re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")
GOOGLE_API_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")
AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
GENERIC_SECRET_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*"
    r"[\"']?([A-Za-z0-9_./+=-]{16,})"
)
UNIX_PERSONAL_PATH_RE = re.compile(r"(?P<prefix>/(?:Users|home)/)(?P<user>[A-Za-z0-9._-]+)")
WINDOWS_PERSONAL_PATH_RE = re.compile(
    r"(?i)(?P<prefix>[A-Z]:\\Users\\)(?P<user>[A-Za-z0-9._-]+)"
)


@dataclass(frozen=True, slots=True)
class ReleaseScanFinding:
    relative_path: str
    line: int
    kind: str
    excerpt: str


def scan_release_surfaces(root: Path) -> tuple[ReleaseScanFinding, ...]:
    resolved_root = root.resolve()
    findings: list[ReleaseScanFinding] = []
    for path in _iter_release_surface_files(resolved_root):
        relative_path = path.relative_to(resolved_root).as_posix()
        findings.extend(_scan_file(path, relative_path))
    return tuple(findings)


def _iter_release_surface_files(root: Path) -> tuple[Path, ...]:
    files = _git_tracked_files(root) or _walk_files(root)
    return tuple(path for path in files if _is_release_surface(root, path))


def _git_tracked_files(root: Path) -> tuple[Path, ...]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if result.returncode != 0 or not result.stdout:
        return ()
    return tuple(
        root / item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    )


def _walk_files(root: Path) -> tuple[Path, ...]:
    return tuple(path for path in root.rglob("*") if path.is_file())


def _is_release_surface(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    parts = relative.parts
    if not parts or any(part in EXCLUDED_DIRS for part in parts):
        return False
    suffix = path.suffix.lower()
    if suffix in BINARY_SUFFIXES:
        return False

    relative_posix = relative.as_posix()
    if relative_posix in ROOT_CONFIG_FILES:
        return True
    if parts[0] in {"config", ".harness"} and suffix in CONFIG_SUFFIXES:
        return True
    if path.name.endswith(".log"):
        return True
    if "fixtures" in parts or "fixture" in path.stem.lower():
        return suffix in FIXTURE_SUFFIXES
    if parts[0] == "tests" and suffix in {".json", ".toml", ".yaml", ".yml", ".env", ".txt"}:
        return True
    return False


def _scan_file(path: Path, relative_path: str) -> tuple[ReleaseScanFinding, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ()

    findings: list[ReleaseScanFinding] = []
    for line_number, line in enumerate(lines, start=1):
        findings.extend(
            _scan_line(
                relative_path=relative_path,
                line_number=line_number,
                line=line,
            )
        )
    return tuple(findings)


def _scan_line(
    *,
    relative_path: str,
    line_number: int,
    line: str,
) -> tuple[ReleaseScanFinding, ...]:
    findings: list[ReleaseScanFinding] = []
    for kind, pattern in (
        ("openai_secret_key", OPENAI_KEY_RE),
        ("github_token", GITHUB_TOKEN_RE),
        ("google_api_key", GOOGLE_API_KEY_RE),
        ("aws_access_key", AWS_ACCESS_KEY_RE),
    ):
        for match in pattern.finditer(line):
            if _is_placeholder(match.group(0)):
                continue
            findings.append(
                ReleaseScanFinding(
                    relative_path=relative_path,
                    line=line_number,
                    kind=kind,
                    excerpt=_redacted_excerpt(line, match),
                )
            )

    for match in GENERIC_SECRET_RE.finditer(line):
        value = match.group(1)
        if _is_placeholder(value):
            continue
        findings.append(
            ReleaseScanFinding(
                relative_path=relative_path,
                line=line_number,
                kind="generic_secret_assignment",
                excerpt=_redacted_excerpt(line, match),
            )
        )

    for pattern in (UNIX_PERSONAL_PATH_RE, WINDOWS_PERSONAL_PATH_RE):
        for match in pattern.finditer(line):
            findings.append(
                ReleaseScanFinding(
                    relative_path=relative_path,
                    line=line_number,
                    kind="personal_path",
                    excerpt=_personal_path_excerpt(line, match),
                )
            )
    return tuple(findings)


def _is_placeholder(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(word in normalized for word in PLACEHOLDER_WORDS)


def _redacted_excerpt(line: str, match: re.Match[str]) -> str:
    return _trim_excerpt(f"{line[: match.start()]}[redacted]{line[match.end() :]}")


def _personal_path_excerpt(line: str, match: re.Match[str]) -> str:
    safe_line = (
        f"{line[: match.start()]}{match.group('prefix')}<user>"
        f"{line[match.end() :]}"
    )
    return _trim_excerpt(safe_line)


def _trim_excerpt(value: str, *, limit: int = 140) -> str:
    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[: limit - 3]}..."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Project root to scan")
    parser.add_argument("--json", action="store_true", help="Emit JSON findings")
    args = parser.parse_args()

    findings = scan_release_surfaces(Path(args.root))
    if args.json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
    elif findings:
        for finding in findings:
            print(
                f"{finding.relative_path}:{finding.line}: "
                f"{finding.kind}: {finding.excerpt}"
            )
    else:
        print("No obvious release-surface secrets or personal paths found.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
