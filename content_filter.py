"""
Content Filter for Moltbook MCP Server
========================================
Defence layer against prompt injection attacks embedded in Moltbook
posts and comments. Uses LLM Guard's fine-tuned DeBERTa v3 model for
ML-based injection classification, with a lightweight regex layer
for patterns the model may not cover (credential exfiltration, etc.).

Since any agent can post anything on Moltbook, content returned to the
reasoning LLM must be scanned before it reaches the tool output.
"""

import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger("moltbook_mcp.content_filter")

# ---------------------------------------------------------------------------
# Security audit logger — dedicated log for injection detection events
# ---------------------------------------------------------------------------

SECURITY_LOG_PATH = os.environ.get("SECURITY_LOG_PATH", "")

_security_logger = None


def _get_security_logger() -> logging.Logger:
    """Lazy-initialise a dedicated security audit logger.

    Writes JSON-lines to a separate file so injection events can be
    audited independently of application logs. If SECURITY_LOG_PATH is
    not set, logs to stderr via the main logger instead.
    """
    global _security_logger
    if _security_logger is None:
        if SECURITY_LOG_PATH:
            _security_logger = logging.getLogger("moltbook_mcp.security_audit")
            _security_logger.setLevel(logging.INFO)
            _security_logger.propagate = False  # don't duplicate to root logger
            try:
                os.makedirs(os.path.dirname(SECURITY_LOG_PATH), exist_ok=True)
                handler = RotatingFileHandler(
                    SECURITY_LOG_PATH,
                    maxBytes=5_000_000,  # 5MB per file
                    backupCount=3  # Keep 3 rotated backups (20MB total max)
                )
                handler.setFormatter(logging.Formatter("%(message)s"))  # raw JSON lines
                _security_logger.addHandler(handler)
            except Exception as e:
                logger.warning(f"Could not create security audit log at {SECURITY_LOG_PATH}: {e}")
                # Fall back to main logger
                _security_logger = logger
        else:
            # Log to stderr via main logger when no file path configured
            _security_logger = logger
    return _security_logger

# Configurable threshold via environment variable (default: 0.5)
DEFAULT_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# LLM Guard scanner (lazy-loaded to avoid import-time model download)
# ---------------------------------------------------------------------------

_scanner = None


def _get_threshold() -> float:
    """Get the content filter threshold from environment or default."""
    try:
        return float(os.environ.get("CONTENT_FILTER_THRESHOLD", DEFAULT_THRESHOLD))
    except (ValueError, TypeError):
        logger.warning(
            f"Invalid CONTENT_FILTER_THRESHOLD value, using default: {DEFAULT_THRESHOLD}"
        )
        return DEFAULT_THRESHOLD


def _get_scanner():
    """Lazy-initialise the LLM Guard PromptInjection scanner.

    The DeBERTa model is loaded on first call and cached for the
    lifetime of the process.  This avoids blocking server startup
    and handles the case where llm-guard isn't installed gracefully.

    Set CONTENT_FILTER_ML=false to skip ML model loading entirely
    (saves ~1.5GB RAM). Regex patterns still apply.
    Threshold is configurable via CONTENT_FILTER_THRESHOLD env var.
    """
    global _scanner
    if _scanner is None:
        # Allow disabling ML model to save memory on constrained hosts
        ml_enabled = os.environ.get("CONTENT_FILTER_ML", "true").lower()
        if ml_enabled in ("false", "0", "no", "off"):
            logger.info(
                "CONTENT_FILTER_ML=false — ML model disabled, using regex-only filtering"
            )
            _scanner = "unavailable"
            return _scanner

        try:
            from llm_guard.input_scanners import PromptInjection
            from llm_guard.input_scanners.prompt_injection import MatchType

            threshold = _get_threshold()
            _scanner = PromptInjection(
                threshold=threshold,
                match_type=MatchType.FULL,
            )
            logger.info(
                f"LLM Guard PromptInjection scanner loaded (threshold={threshold})"
            )
        except ImportError:
            logger.warning(
                "llm-guard not installed — falling back to regex-only filtering. "
                "Install with: pip install llm-guard"
            )
            _scanner = "unavailable"
        except Exception as e:
            logger.error(f"Failed to load LLM Guard scanner: {e}")
            _scanner = "unavailable"
    return _scanner


# ---------------------------------------------------------------------------
# ML scan result cache — avoids re-scanning identical content across requests
# ---------------------------------------------------------------------------

_SCAN_CACHE_MAX = 512  # max cached results (covers several full feed loads)
_scan_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()


def _cache_key(text: str) -> str:
    """Hash text content for cache lookup."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_get(text: str) -> Dict[str, Any] | None:
    """Look up a cached scan result. Returns None on miss."""
    key = _cache_key(text)
    if key in _scan_cache:
        _scan_cache.move_to_end(key)
        return _scan_cache[key]
    return None


def _cache_put(text: str, result: Dict[str, Any]) -> None:
    """Store a scan result in the cache, evicting oldest if full."""
    key = _cache_key(text)
    _scan_cache[key] = result
    _scan_cache.move_to_end(key)
    while len(_scan_cache) > _SCAN_CACHE_MAX:
        _scan_cache.popitem(last=False)


# ---------------------------------------------------------------------------
# Regex patterns — catch things the ML model may not flag
# ---------------------------------------------------------------------------

# Hard block: redact these outright
INJECTION_PATTERNS = [
    # Credential exfiltration
    re.compile(
        r"send\s+(?:your\s+)?(?:api[_\s]?key|token|credentials?|secret)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:curl|fetch|post|get)\s+https?://(?!www\.moltbook\.com)",
        re.IGNORECASE,
    ),
    # Skill / code injection
    re.compile(r"download\s+(?:and\s+)?(?:run|execute|install)", re.IGNORECASE),
    re.compile(r"(?:run|execute|eval)\s*\(", re.IGNORECASE),
    re.compile(r"import\s+(?:os|sys|subprocess|shutil)", re.IGNORECASE),
]

# Informational: flag but don't redact
SUSPICIOUS_PATTERNS = [
    re.compile(
        r"(?:api[_\s]?key|bearer|authorization)\s*[=:]\s*\S+", re.IGNORECASE
    ),
    re.compile(r"moltbook_[a-zA-Z0-9]{20,}", re.IGNORECASE),
]


def _regex_scan(text: str) -> Dict[str, Any]:
    """Regex-based scan for patterns the ML model may not cover."""
    if not text:
        return {"clean": True, "flags": [], "sanitised": text}

    flags: List[str] = []
    sanitised = text

    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            flags.append(f"Regex hard-block: /{pattern.pattern}/")
            sanitised = pattern.sub("[REDACTED — blocked by filter]", sanitised)

    for pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            flags.append(f"Regex suspicious: /{pattern.pattern}/")

    return {"clean": len(flags) == 0, "flags": flags, "sanitised": sanitised}


# ---------------------------------------------------------------------------
# Combined scan: ML model + regex
# ---------------------------------------------------------------------------


def scan_text(text: str) -> Dict[str, Any]:
    """Scan a text string for prompt injection using LLM Guard + regex.

    Results are cached by content hash so repeated scans of the same
    text (common across heartbeat cycles) skip the expensive ML inference.

    Returns:
        dict with keys:
            clean (bool): True if no threats detected.
            risk_score (float): 0.0-1.0 injection confidence from ML model.
            flags (list[str]): Human-readable descriptions of detections.
            sanitised (str): Text with dangerous content redacted.
    """
    if not text:
        return {"clean": True, "risk_score": 0.0, "flags": [], "sanitised": text}

    # Check cache first — avoids ML inference for previously-seen content
    cached = _cache_get(text)
    if cached is not None:
        return cached

    flags: List[str] = []
    risk_score = 0.0
    sanitised = text

    # --- Layer 1: ML-based detection via LLM Guard ---
    scanner = _get_scanner()
    if scanner and scanner != "unavailable":
        try:
            ml_sanitised, is_valid, score = scanner.scan(text)
            risk_score = score

            if not is_valid:
                flags.append(
                    f"LLM Guard: injection detected (score={score:.3f})"
                )
                sanitised = ml_sanitised
        except Exception as e:
            logger.error(f"LLM Guard scan error: {e}")
            flags.append(f"LLM Guard scan failed: {type(e).__name__}")

    # --- Layer 2: Regex patterns (applied to original text) ---
    regex_result = _regex_scan(text)
    if not regex_result["clean"]:
        flags.extend(regex_result["flags"])
        # Apply regex redactions on top of whatever ML returned
        sanitised = _regex_scan(sanitised)["sanitised"]

    result = {
        "clean": len(flags) == 0,
        "risk_score": risk_score,
        "flags": flags,
        "sanitised": sanitised,
    }

    _cache_put(text, result)
    return result


# ---------------------------------------------------------------------------
# Post / comment filtering
# ---------------------------------------------------------------------------


def filter_post(post: Dict[str, Any]) -> Dict[str, Any]:
    """Filter a single Moltbook post object.

    Scans all user-controllable text fields (title, content, name,
    description, author_name, submolt_name); attaches _security metadata
    if anything suspicious is found.
    """
    if not isinstance(post, dict):
        return post

    flags: List[str] = []
    max_risk = 0.0

    for field in ("title", "content", "name", "description", "author_name", "submolt_name"):
        value = post.get(field)
        if isinstance(value, str):
            result = scan_text(value)
            max_risk = max(max_risk, result["risk_score"])
            if not result["clean"]:
                flags.extend(result["flags"])
                post[field] = result["sanitised"]

    if flags:
        post["_security"] = {
            "flags": flags,
            "risk_score": round(max_risk, 4),
            "filtered": True,
        }

        # Audit log
        try:
            audit_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "content_flagged",
                "post_id": post.get("id", "unknown"),
                "author": post.get("author", post.get("author_name", "unknown")),
                "submolt": post.get("submolt", post.get("submolt_name", "unknown")),
                "risk_score": round(max_risk, 4),
                "flags": flags,
                "fields_affected": [
                    f for f in ("title", "content", "name", "description", "author_name", "submolt_name")
                    if isinstance(post.get(f), str)
                ],
            }
            _get_security_logger().info(json.dumps(audit_entry))
        except Exception as e:
            logger.warning(f"Failed to write security audit log: {e}")

    return post


def filter_posts(posts: Any) -> Any:
    """Filter a list of posts or a response envelope containing posts."""
    if isinstance(posts, list):
        return [filter_post(p) for p in posts]
    if isinstance(posts, dict):
        for key in ("posts", "data", "results", "items"):
            if key in posts and isinstance(posts[key], list):
                posts[key] = [filter_post(p) for p in posts[key]]
        return posts
    return posts


def filter_comments(comments: Any) -> Any:
    """Filter a list of comments (same shape concern as posts)."""
    return filter_posts(comments)
