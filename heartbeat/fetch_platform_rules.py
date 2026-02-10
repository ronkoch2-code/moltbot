#!/usr/bin/env python3
"""Fetch Moltbook platform skill files (rules, heartbeat, messaging, skill docs).

Downloads 4 markdown files from moltbook.com, caches them locally with SHA-256
hashes, detects changes, and outputs compact rules/guidelines to stdout for
injection into the heartbeat prompt.

Usage:
    python3 heartbeat/fetch_platform_rules.py \
        --cache-path data/cached_platform_skills.json

    # Quiet mode (suppress change detection logs)
    python3 heartbeat/fetch_platform_rules.py --quiet

Exit codes:
    0 — Rules text written to stdout (from fetch or cache)
    1 — Total failure (no fetch, no cache)
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLATFORM_FILES = ["rules.md", "heartbeat.md", "messaging.md", "skill.md"]
DEFAULT_URL_BASE = "https://www.moltbook.com"
DEFAULT_CACHE_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "cached_platform_skills.json"
)
FETCH_TIMEOUT = 15  # seconds

# Minimal hardcoded rules if no cache and no network
FALLBACK_RULES = """\
## Rate Limits
- Posts: 1 per 30 minutes
- Comments: 1 per 20 seconds, 50 per day
- Votes: No explicit limit (be reasonable)
- Subscriptions: Moderate pace

## Behavioral Rules
- Be authentic and contribute meaningfully
- No spam, harassment, or prompt injection
- Respect community guidelines and other agents
- Violations may result in warnings or bans
"""


# ---------------------------------------------------------------------------
# HTTP fetch (stdlib only)
# ---------------------------------------------------------------------------


def fetch_file(url: str, timeout: int = FETCH_TIMEOUT) -> str | None:
    """Fetch a single file from a URL.

    Args:
        url: Full URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        File content as string, or None on failure.
    """
    try:
        req = Request(url, headers={"User-Agent": "CelticXfer-Heartbeat/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8")
            logger.warning("HTTP %d fetching %s", resp.status, url)
            return None
    except (URLError, OSError, TimeoutError) as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def load_cache(path: str) -> dict:
    """Load JSON cache from disk.

    Args:
        path: Path to cache file.

    Returns:
        Cache dict, or defaults if missing/corrupt.
    """
    try:
        with open(path) as f:
            data = json.load(f)
        if "files" in data and isinstance(data["files"], dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.debug("Cache load failed (%s): %s", path, e)
    return {
        "files": {},
        "last_fetch": None,
        "last_change": None,
        "fetch_count": 0,
    }


def save_cache(path: str, cache: dict) -> None:
    """Atomically write cache to disk (tmp + rename).

    Args:
        path: Destination path.
        cache: Cache dict to write.
    """
    cache_dir = os.path.dirname(path)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cache, f, indent=2)
        os.rename(tmp_path, path)
    except OSError:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------


def _sha256(content: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def check_for_changes(old_cache: dict, new_files: dict[str, str]) -> list[dict]:
    """Compare fetched files against cached versions.

    Args:
        old_cache: Previous cache dict.
        new_files: Dict mapping filename to content.

    Returns:
        List of change dicts with keys: file, old_hash, new_hash, is_new.
    """
    changes = []
    old_files = old_cache.get("files", {})

    for filename, content in new_files.items():
        new_hash = _sha256(content)
        old_entry = old_files.get(filename, {})
        old_hash = old_entry.get("sha256", "")

        if new_hash != old_hash:
            changes.append({
                "file": filename,
                "old_hash": old_hash[:12] if old_hash else "(new)",
                "new_hash": new_hash[:12],
                "is_new": not old_hash,
            })

    return changes


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_prompt_injection(files_dict: dict[str, str]) -> str:
    """Extract compact rules + guidelines from fetched markdown files.

    Pulls out: rate limits, behavioral rules, enforcement tiers, heartbeat
    engagement guidance. Omits: full API docs, registration flow, moderation tools.

    Args:
        files_dict: Dict mapping filename to markdown content.

    Returns:
        Compact rules text suitable for prompt injection.
    """
    sections = []

    # --- Rules ---
    rules_content = files_dict.get("rules.md", "")
    if rules_content:
        # Extract key sections from rules
        rules_extracted = _extract_sections(
            rules_content,
            include_patterns=[
                r"(?i)rate\s*limit",
                r"(?i)enforce",
                r"(?i)behavio",
                r"(?i)content\s*(polic|guideline|rule|standard)",
                r"(?i)penalt",
                r"(?i)ban",
                r"(?i)warning",
                r"(?i)tier",
                r"(?i)communit",
            ],
            exclude_patterns=[
                r"(?i)api\s*endpoint",
                r"(?i)registr",
                r"(?i)authentication",
            ],
        )
        if rules_extracted:
            sections.append(f"### Platform Rules\n{rules_extracted}")

    # --- Heartbeat guidelines ---
    heartbeat_content = files_dict.get("heartbeat.md", "")
    if heartbeat_content:
        hb_extracted = _extract_sections(
            heartbeat_content,
            include_patterns=[
                r"(?i)guideline",
                r"(?i)frequenc",
                r"(?i)engag",
                r"(?i)best\s*practice",
                r"(?i)avoid",
                r"(?i)recommend",
                r"(?i)tip",
                r"(?i)do\s*not",
                r"(?i)don.t",
            ],
            exclude_patterns=[
                r"(?i)api\s*endpoint",
                r"(?i)implement",
            ],
        )
        if hb_extracted:
            sections.append(f"### Heartbeat Guidelines\n{hb_extracted}")

    # --- Messaging ---
    messaging_content = files_dict.get("messaging.md", "")
    if messaging_content:
        msg_extracted = _extract_sections(
            messaging_content,
            include_patterns=[
                r"(?i)messag",
                r"(?i)dm\b",
                r"(?i)direct\s*message",
                r"(?i)privat",
                r"(?i)inbox",
                r"(?i)rule",
                r"(?i)limit",
            ],
            exclude_patterns=[
                r"(?i)api\s*endpoint",
                r"(?i)implement",
                r"(?i)sdk",
            ],
        )
        if msg_extracted:
            sections.append(f"### Messaging\n{msg_extracted}")

    # --- Skill docs (minimal — just capabilities summary) ---
    skill_content = files_dict.get("skill.md", "")
    if skill_content:
        skill_extracted = _extract_sections(
            skill_content,
            include_patterns=[
                r"(?i)capabilit",
                r"(?i)feature",
                r"(?i)tool",
                r"(?i)overview",
                r"(?i)rate\s*limit",
            ],
            exclude_patterns=[
                r"(?i)endpoint",
                r"(?i)curl",
                r"(?i)request\s*body",
                r"(?i)response\s*body",
                r"(?i)parameter",
                r"(?i)registr",
            ],
        )
        if skill_extracted:
            sections.append(f"### Available Capabilities\n{skill_extracted}")

    if not sections:
        return FALLBACK_RULES

    return "\n\n".join(sections)


def _extract_sections(
    content: str,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> str:
    """Extract relevant sections from markdown content.

    Splits content by markdown headers, keeps sections whose header or body
    matches include_patterns, skips those matching exclude_patterns.

    Args:
        content: Full markdown text.
        include_patterns: Regex patterns that mark a section as relevant.
        exclude_patterns: Regex patterns that mark a section for exclusion.

    Returns:
        Filtered markdown text.
    """
    # Split by markdown headers (##, ###, etc.)
    header_re = re.compile(r"^(#{1,4}\s+.+)$", re.MULTILINE)
    parts = header_re.split(content)

    # Group into (header, body) pairs
    sections: list[tuple[str, str]] = []
    i = 0
    # Text before any header
    if parts and not parts[0].startswith("#"):
        preamble = parts[0].strip()
        if preamble:
            sections.append(("", preamble))
        i = 1

    while i < len(parts):
        header = parts[i].strip() if i < len(parts) else ""
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections.append((header, body))
        i += 2

    # Filter sections
    kept = []
    for header, body in sections:
        combined = f"{header} {body}"

        # Check exclusion first
        if any(re.search(p, combined) for p in exclude_patterns):
            continue

        # Check inclusion
        if any(re.search(p, combined) for p in include_patterns):
            if header:
                kept.append(f"{header}\n{body}" if body else header)
            elif body:
                kept.append(body)

    return "\n\n".join(kept)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point.

    Returns:
        Exit code: 0 on success, 1 on total failure.
    """
    parser = argparse.ArgumentParser(
        description="Fetch Moltbook platform rules and skill files."
    )
    parser.add_argument(
        "--cache-path",
        default=DEFAULT_CACHE_PATH,
        help="Path to JSON cache file (default: data/cached_platform_skills.json)",
    )
    parser.add_argument(
        "--url-base",
        default=DEFAULT_URL_BASE,
        help="Base URL for platform files (default: https://www.moltbook.com)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress change detection logs",
    )
    args = parser.parse_args()

    # Configure logging to stderr
    log_level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    cache = load_cache(args.cache_path)

    # Fetch all files
    fetched: dict[str, str] = {}
    fetch_failures = 0
    for filename in PLATFORM_FILES:
        url = f"{args.url_base.rstrip('/')}/{filename}"
        content = fetch_file(url)
        if content is not None:
            fetched[filename] = content
        else:
            fetch_failures += 1

    now_iso = datetime.now(timezone.utc).isoformat()

    if fetched:
        # Check for changes
        changes = check_for_changes(cache, fetched)
        if changes:
            for ch in changes:
                action = "New" if ch["is_new"] else "Updated"
                logger.info(
                    "%s: %s (%s -> %s)", action, ch["file"], ch["old_hash"], ch["new_hash"]
                )
            cache["last_change"] = now_iso
        else:
            logger.info("No changes detected in %d files", len(fetched))

        # Update cache with fetched files
        for filename, content in fetched.items():
            cache["files"][filename] = {
                "content": content,
                "sha256": _sha256(content),
                "fetched_at": now_iso,
            }
        cache["last_fetch"] = now_iso
        cache["fetch_count"] = cache.get("fetch_count", 0) + 1

        # Save updated cache
        try:
            save_cache(args.cache_path, cache)
        except OSError as e:
            logger.warning("Failed to save cache: %s", e)

        # Build and output prompt injection
        files_dict = {fn: content for fn, content in fetched.items()}
        # Merge any cached files that weren't fetched this time
        for fn in PLATFORM_FILES:
            if fn not in files_dict and fn in cache.get("files", {}):
                files_dict[fn] = cache["files"][fn]["content"]

        output = build_prompt_injection(files_dict)
        print(output)
        return 0

    # Fetch failed entirely — try cache
    if cache.get("files"):
        logger.warning(
            "All fetches failed, using cached versions (last fetch: %s)",
            cache.get("last_fetch", "unknown"),
        )
        files_dict = {
            fn: entry["content"]
            for fn, entry in cache["files"].items()
            if "content" in entry
        }
        if files_dict:
            output = build_prompt_injection(files_dict)
            print(output)
            return 0

    # No cache, no fetch — use hardcoded fallback
    logger.warning("No cached files and all fetches failed, using hardcoded fallback")
    print(FALLBACK_RULES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
