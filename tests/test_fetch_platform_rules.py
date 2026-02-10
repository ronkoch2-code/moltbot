"""Tests for heartbeat/fetch_platform_rules.py — platform skill file sync."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys

# Add project root so imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "heartbeat"))

from heartbeat.fetch_platform_rules import (
    FALLBACK_RULES,
    _sha256,
    build_prompt_injection,
    check_for_changes,
    fetch_file,
    load_cache,
    main,
    save_cache,
)


# ===========================================================================
# fetch_file()
# ===========================================================================


class TestFetchFile:
    """Tests for HTTP file fetching."""

    def test_fetch_file_success(self):
        """Successful HTTP fetch returns content."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"# Rules\nBe nice."
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("heartbeat.fetch_platform_rules.urlopen", return_value=mock_resp):
            result = fetch_file("https://example.com/rules.md")
        assert result == "# Rules\nBe nice."

    def test_fetch_file_timeout(self):
        """Timeout returns None."""
        with patch(
            "heartbeat.fetch_platform_rules.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            result = fetch_file("https://example.com/rules.md", timeout=1)
        assert result is None

    def test_fetch_file_url_error(self):
        """URLError returns None."""
        from urllib.error import URLError

        with patch(
            "heartbeat.fetch_platform_rules.urlopen",
            side_effect=URLError("connection refused"),
        ):
            result = fetch_file("https://example.com/rules.md")
        assert result is None

    def test_fetch_file_non_200(self):
        """Non-200 status returns None."""
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("heartbeat.fetch_platform_rules.urlopen", return_value=mock_resp):
            result = fetch_file("https://example.com/missing.md")
        assert result is None


# ===========================================================================
# Cache management
# ===========================================================================


class TestLoadCache:
    """Tests for cache loading."""

    def test_load_cache_missing(self, tmp_path):
        """Missing cache file returns defaults."""
        cache = load_cache(str(tmp_path / "nonexistent.json"))
        assert cache["files"] == {}
        assert cache["last_fetch"] is None
        assert cache["fetch_count"] == 0

    def test_load_cache_corrupt(self, tmp_path):
        """Corrupt JSON returns defaults."""
        cache_file = tmp_path / "bad.json"
        cache_file.write_text("{invalid json!!")
        cache = load_cache(str(cache_file))
        assert cache["files"] == {}

    def test_load_cache_valid(self, tmp_path):
        """Valid cache file is loaded correctly."""
        cache_file = tmp_path / "cache.json"
        data = {
            "files": {"rules.md": {"content": "test", "sha256": "abc", "fetched_at": "2026-01-01"}},
            "last_fetch": "2026-01-01",
            "last_change": None,
            "fetch_count": 5,
        }
        cache_file.write_text(json.dumps(data))
        cache = load_cache(str(cache_file))
        assert cache["fetch_count"] == 5
        assert "rules.md" in cache["files"]


class TestSaveCache:
    """Tests for cache saving."""

    def test_save_cache_atomic(self, tmp_path):
        """Cache is written atomically (file exists after save)."""
        cache_path = str(tmp_path / "cache.json")
        data = {"files": {}, "last_fetch": "now", "fetch_count": 1}
        save_cache(cache_path, data)

        with open(cache_path) as f:
            loaded = json.load(f)
        assert loaded["fetch_count"] == 1

    def test_save_cache_creates_dirs(self, tmp_path):
        """Save creates parent directories if missing."""
        cache_path = str(tmp_path / "subdir" / "deep" / "cache.json")
        save_cache(cache_path, {"files": {}, "fetch_count": 0})
        assert os.path.exists(cache_path)


# ===========================================================================
# Change detection
# ===========================================================================


class TestCheckForChanges:
    """Tests for hash-based change detection."""

    def test_no_change(self):
        """Same content returns empty change list."""
        content = "# Rules\nBe nice."
        old_cache = {
            "files": {
                "rules.md": {"content": content, "sha256": _sha256(content)},
            }
        }
        changes = check_for_changes(old_cache, {"rules.md": content})
        assert changes == []

    def test_with_diff(self):
        """Changed content returns change details."""
        old_content = "# Rules v1"
        new_content = "# Rules v2 — updated"
        old_cache = {
            "files": {
                "rules.md": {"content": old_content, "sha256": _sha256(old_content)},
            }
        }
        changes = check_for_changes(old_cache, {"rules.md": new_content})
        assert len(changes) == 1
        assert changes[0]["file"] == "rules.md"
        assert changes[0]["is_new"] is False

    def test_new_file(self):
        """New file not in cache is flagged as new."""
        old_cache = {"files": {}}
        changes = check_for_changes(old_cache, {"heartbeat.md": "# Heartbeat"})
        assert len(changes) == 1
        assert changes[0]["is_new"] is True
        assert changes[0]["old_hash"] == "(new)"


# ===========================================================================
# Prompt builder
# ===========================================================================


class TestBuildPromptInjection:
    """Tests for prompt injection text builder."""

    def test_contains_rate_limits(self):
        """Output should contain rate limit information when present in rules."""
        files = {
            "rules.md": "## Rate Limits\n- Posts: 1 per 30 minutes\n- Comments: 50 per day\n",
        }
        output = build_prompt_injection(files)
        assert "Rate Limit" in output
        assert "30 minutes" in output or "per day" in output

    def test_contains_behavioral_rules(self):
        """Output should contain behavioral guidance."""
        files = {
            "rules.md": "## Community Behavioral Standards\nNo spam. Be authentic.\n",
        }
        output = build_prompt_injection(files)
        assert "spam" in output or "authentic" in output

    def test_excludes_api_endpoints(self):
        """Output should not include raw API endpoint documentation."""
        files = {
            "skill.md": (
                "## API Endpoints\nGET /api/v1/posts\ncurl -X GET ...\n\n"
                "## Overview\nMoltbook features include posting and commenting."
            ),
        }
        output = build_prompt_injection(files)
        assert "curl" not in output

    def test_empty_files_returns_fallback(self):
        """Empty files dict should return fallback rules."""
        output = build_prompt_injection({})
        assert output == FALLBACK_RULES

    def test_heartbeat_guidelines_included(self):
        """Heartbeat guidelines should be extracted."""
        files = {
            "heartbeat.md": "## Engagement Guidelines\nEngage thoughtfully. Avoid spam.\n",
        }
        output = build_prompt_injection(files)
        assert "Engage" in output or "Guidelines" in output


# ===========================================================================
# main() integration
# ===========================================================================


class TestMain:
    """Integration tests for CLI main()."""

    def test_main_fresh_fetch(self, tmp_path, capsys):
        """No cache + successful fetch should output rules to stdout."""
        cache_path = str(tmp_path / "cache.json")
        rules_content = "## Rate Limits\n- Posts: 1 per 30 min\n"

        def mock_fetch(url, timeout=15):
            if "rules.md" in url:
                return rules_content
            return "## Overview\nFeatures include posting."

        with (
            patch("heartbeat.fetch_platform_rules.fetch_file", side_effect=mock_fetch),
            patch(
                "sys.argv",
                ["fetch_platform_rules.py", "--cache-path", cache_path, "--quiet"],
            ),
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert len(captured.out.strip()) > 0
        # Cache should have been created
        assert os.path.exists(cache_path)

    def test_main_fallback_to_cache(self, tmp_path, capsys):
        """Fetch fails + cache exists should use cached output."""
        cache_path = str(tmp_path / "cache.json")
        cache_data = {
            "files": {
                "rules.md": {
                    "content": "## Rate Limits\n- Posts: 1 per 30 min\n",
                    "sha256": "abc123",
                    "fetched_at": "2026-01-01T00:00:00+00:00",
                },
            },
            "last_fetch": "2026-01-01T00:00:00+00:00",
            "last_change": None,
            "fetch_count": 1,
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)

        with (
            patch("heartbeat.fetch_platform_rules.fetch_file", return_value=None),
            patch(
                "sys.argv",
                ["fetch_platform_rules.py", "--cache-path", cache_path, "--quiet"],
            ),
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Rate Limit" in captured.out

    def test_main_total_failure_uses_hardcoded(self, tmp_path, capsys):
        """No fetch + no cache should output hardcoded fallback."""
        cache_path = str(tmp_path / "nonexistent.json")

        with (
            patch("heartbeat.fetch_platform_rules.fetch_file", return_value=None),
            patch(
                "sys.argv",
                ["fetch_platform_rules.py", "--cache-path", cache_path, "--quiet"],
            ),
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Rate Limits" in captured.out
