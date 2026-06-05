#!/usr/bin/env python3
from __future__ import annotations

import io
import re
import shutil
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST_ROOT = ROOT / "dist"

BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
DB_DIR = ROOT / "db"
SCRIPTS_DIR = ROOT / "scripts"

FILES_TO_COPY = [
    ROOT / "docker-compose.yml",
    DB_DIR / "init.sql",
    SCRIPTS_DIR / "auto-reset.sh",
    SCRIPTS_DIR / "reset-db.sh",
]

COMPOSE_PATTERNS = (
    "compose.yml",
    "compose.yaml",
    "docker-compose*.yml",
    "docker-compose*.yaml",
)
BACKEND_EXCLUDE_DIRS = {"__pycache__"}
BACKEND_EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
REDACT_TOKEN = "<REDACT>"


def collect_compose_files() -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in COMPOSE_PATTERNS:
        for candidate in sorted(ROOT.glob(pattern)):
            if candidate.is_file() and candidate not in seen:
                seen.add(candidate)
                files.append(candidate)
    return files


def should_skip_backend_file(path: Path) -> bool:
    return any(part in BACKEND_EXCLUDE_DIRS for part in path.parts) or (
        path.suffix in BACKEND_EXCLUDE_SUFFIXES
    )


def redact_text(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if path.name in {"docker-compose.yml", "docker-compose.yaml"} or suffix in {
        ".yml",
        ".yaml",
    }:
        return strip_comments(path, redact_compose_text(text))
    if suffix == ".sql":
        return strip_comments(path, redact_sql_text(text))
    if suffix == ".py":
        return strip_comments(path, redact_python_text(text))
    if suffix in {".sh", ".js", ".css", ".html"} or name == "dockerfile":
        return strip_comments(path, text)
    return strip_comments(path, text)


def strip_comments(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix == ".py":
        return strip_python_comments(text)
    if suffix in {".yml", ".yaml", ".sh"} or name == "dockerfile":
        return strip_hash_comments(text, preserve_shebang=suffix == ".sh")
    if suffix == ".sql":
        return strip_sql_comments(text)
    if suffix == ".js":
        return strip_c_style_comments(text, line_comments=True)
    if suffix == ".css":
        return strip_c_style_comments(text, line_comments=False)
    if suffix == ".html":
        return strip_html_comments(text)
    return text


def strip_hash_comments(text: str, preserve_shebang: bool = False) -> str:
    stripped_lines: list[str] = []
    for index, line in enumerate(text.splitlines()):
        if preserve_shebang and index == 0 and line.startswith("#!"):
            stripped_lines.append(line)
            continue

        quote = ""
        escaped = False
        comment_start: int | None = None
        for column, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char == "\\" and quote:
                escaped = True
                continue
            if quote:
                if char == quote:
                    quote = ""
                continue
            if char in {"'", '"'}:
                quote = char
                continue
            if char == "#":
                comment_start = column
                break

        uncommented = line[:comment_start].rstrip() if comment_start is not None else line
        if uncommented.strip():
            stripped_lines.append(uncommented)
    return "\n".join(stripped_lines) + "\n"


def strip_python_comments(text: str) -> str:
    result_tokens = []
    stream = io.StringIO(text)
    for token in tokenize.generate_tokens(stream.readline):
        if token.type == tokenize.COMMENT:
            continue
        result_tokens.append(token)
    return tokenize.untokenize(result_tokens)


def strip_sql_comments(text: str) -> str:
    result: list[str] = []
    index = 0
    quote = ""
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if quote:
            result.append(char)
            if char == quote:
                if next_char == quote:
                    result.append(next_char)
                    index += 2
                    continue
                quote = ""
            index += 1
            continue

        if char in {"'", '"'}:
            quote = char
            result.append(char)
            index += 1
            continue
        if char == "-" and next_char == "-":
            index = text.find("\n", index)
            if index == -1:
                break
            continue
        if char == "/" and next_char == "*":
            end = text.find("*/", index + 2)
            index = len(text) if end == -1 else end + 2
            continue

        result.append(char)
        index += 1
    return "\n".join(line.rstrip() for line in "".join(result).splitlines() if line.strip()) + "\n"


def strip_c_style_comments(text: str, line_comments: bool) -> str:
    result: list[str] = []
    index = 0
    quote = ""
    escaped = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if quote:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            result.append(char)
            index += 1
            continue
        if char == "/" and next_char == "*":
            end = text.find("*/", index + 2)
            index = len(text) if end == -1 else end + 2
            continue
        if line_comments and char == "/" and next_char == "/":
            index = text.find("\n", index)
            if index == -1:
                break
            continue

        result.append(char)
        index += 1
    return "\n".join(line.rstrip() for line in "".join(result).splitlines() if line.strip()) + "\n"


def strip_html_comments(text: str) -> str:
    text = re.sub(r"(?s)<!--.*?-->", "", text)
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip()) + "\n"


def redact_compose_text(text: str) -> str:
    text = re.sub(
        r"(?im)^(\s*[A-Z0-9_]*(?:PASS|PASSWORD|SECRET|TOKEN|KEY|FLAG|USER|USERNAME)[A-Z0-9_]*\s*:\s*)(.+?)\s*$",
        lambda match: f"{match.group(1)}{REDACT_TOKEN}",
        text,
    )
    text = re.sub(
        r"(?i)\b(password|flag|token|secret|key)=([^ \n\"']+)",
        lambda match: f"{match.group(1)}={REDACT_TOKEN}",
        text,
    )
    return text


def redact_sql_text(text: str) -> str:
    text = re.sub(
        r"(?i)(PASSWORD\s+)('(?:''|[^'])*')",
        lambda match: f"{match.group(1)}'{REDACT_TOKEN}'",
        text,
    )
    text = re.sub(
        r"(?i)(INSERT\s+INTO\s+public\.secrets\s*\([^)]*flag[^)]*\)\s*VALUES\s*\([^,]+,\s*)('(?:''|[^'])*')",
        lambda match: f"{match.group(1)}'{REDACT_TOKEN}'",
        text,
    )
    text = re.sub(
        r"(?i)(INSERT\s+INTO\s+public\.players\s*\([^)]*password[^)]*\)\s*VALUES\s*\()('(?:''|[^'])*')",
        lambda match: f"{match.group(1)}'{REDACT_TOKEN}'",
        text,
    )
    text = re.sub(
        r"(?i)(INSERT\s+INTO\s+public\.user_sessions\s*\([^)]*(?:session_token|username|profile_cache)[^)]*\)\s*VALUES\s*\()",
        lambda match: match.group(1),
        text,
    )
    text = re.sub(
        r"(?i)(VALUES\s*\()('(?:''|[^'])*')(\s*,\s*\d+\s*,\s*)('(?:''|[^'])*')",
        lambda match: f"{match.group(1)}'{REDACT_TOKEN}'{match.group(3)}'{REDACT_TOKEN}'",
        text,
    )
    text = re.sub(
        r"'flag\{[^']*?\}'",
        f"'{REDACT_TOKEN}'",
        text,
    )
    return text


def redact_python_text(text: str) -> str:
    text = re.sub(
        r'(DB_DSN\s*=\s*os\.getenv\(\s*"DB_DSN"\s*,\s*)"(.*?)"',
        lambda match: f'{match.group(1)}"{redact_dsn_credentials(match.group(2))}"',
        text,
    )
    text = re.sub(
        r'(?s)(CHALLENGE_FLAG\s*=\s*os\.getenv\(\s*"CHALLENGE_FLAG"\s*,\s*)"(.*?)"(\s*\))',
        lambda match: f'{match.group(1)}"{REDACT_TOKEN}"{match.group(3)}',
        text,
    )
    return text


def redact_dsn_credentials(dsn: str) -> str:
    return re.sub(
        r"(?i)\b(password=)([^ \n\"']+)",
        lambda match: f"{match.group(1)}{REDACT_TOKEN}",
        dsn,
    )


def copy_with_redaction(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text()
    destination.write_text(redact_text(source, text))


def copy_backend_tree() -> None:
    for source in sorted(BACKEND_DIR.rglob("*")):
        relative = source.relative_to(ROOT)
        if should_skip_backend_file(relative):
            continue

        destination = DIST_ROOT / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        copy_with_redaction(source, destination)


def copy_tree(source_root: Path) -> None:
    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(ROOT)
        if should_skip_backend_file(relative):
            continue

        destination = DIST_ROOT / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        copy_with_redaction(source, destination)


def build_package() -> None:
    if DIST_ROOT.exists():
        shutil.rmtree(DIST_ROOT)

    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    copy_backend_tree()
    copy_tree(FRONTEND_DIR)

    for source in collect_compose_files():
        copy_with_redaction(source, DIST_ROOT / source.relative_to(ROOT))

    for source in FILES_TO_COPY:
        if source.exists():
            copy_with_redaction(source, DIST_ROOT / source.relative_to(ROOT))


def main() -> None:
    build_package()
    print(f"created {DIST_ROOT}")


if __name__ == "__main__":
    main()
