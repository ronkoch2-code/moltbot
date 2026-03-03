"""
Moltbook MCP Server
====================
An MCP server that provides sandboxed access to the Moltbook API,
allowing an AI agent to browse, post, comment, and vote on the
AI-agent social network — all behind a clean tool boundary.

Transport: Streamable HTTP (for Docker container access)
"""

import json
import os
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from enum import Enum

import httpx
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP, Context
from starlette.responses import JSONResponse

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from content_filter import filter_posts, filter_post, filter_comments, scan_text, log_security_event

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOLTBOOK_API_BASE = "https://www.moltbook.com/api/v1"
DASHBOARD_API_URL = os.environ.get("DASHBOARD_API_URL", "http://moltbot-dashboard:8081")
DASHBOARD_AUTH_TOKEN = os.environ.get("DASHBOARD_AUTH_TOKEN", "")
DEFAULT_FEED_LIMIT = 25
MAX_FEED_LIMIT = 100
CREDENTIALS_PATH = os.environ.get(
    "MOLTBOOK_CREDENTIALS_PATH", "/app/config/credentials.json"
)
SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CHALLENGE_SOLVER_MODEL = os.environ.get("CHALLENGE_SOLVER_MODEL", "claude-haiku-4-5-20251001")

logger = logging.getLogger("moltbook_mcp")


# ---------------------------------------------------------------------------
# Authentication middleware
# ---------------------------------------------------------------------------


class BearerAuthMiddleware:
    """ASGI middleware requiring a Bearer token on all endpoints except /health.

    Set MCP_AUTH_TOKEN env var to enable. If unset, all requests pass through.
    Uses raw ASGI protocol to avoid issues with SSE/streaming responses.
    """

    EXEMPT_PATHS = {b"/health"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not MCP_AUTH_TOKEN:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").encode() if isinstance(scope.get("path"), str) else scope.get("path", b"")
        if path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # Check Authorization header
        headers = dict(scope.get("headers", []))
        auth_value = headers.get(b"authorization", b"").decode()
        if auth_value == f"Bearer {MCP_AUTH_TOKEN}":
            await self.app(scope, receive, send)
            return

        # Reject unauthorized request
        client_host = (scope.get("client") or ("unknown",))[0]
        logger.warning(f"Unauthorized request to {scope.get('path')} from {client_host}")
        response = JSONResponse(
            {"error": "Unauthorized. Provide a valid Bearer token."},
            status_code=401,
        )
        await response(scope, receive, send)

# ---------------------------------------------------------------------------
# Module-level state (set by lifespan)
# ---------------------------------------------------------------------------

_http_client: httpx.AsyncClient | None = None
_credentials: dict = {}

# ---------------------------------------------------------------------------
# Credentials management
# ---------------------------------------------------------------------------


def _load_credentials() -> Dict[str, str]:
    """Load Moltbook API credentials from file or environment."""
    api_key = os.environ.get("MOLTBOOK_API_KEY")
    if api_key:
        return {"api_key": api_key, "agent_name": os.environ.get("MOLTBOOK_AGENT_NAME", "unknown")}
    try:
        with open(CREDENTIALS_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------


async def _api_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    api_key: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Make an authenticated request to the Moltbook API."""
    url = f"{MOLTBOOK_API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = await client.request(
            method, url, headers=headers, json=json_body, params=params, timeout=30.0
        )

        # Log raw response for write operations (diagnostic for challenge debugging)
        if method in ("POST", "PUT", "PATCH"):
            log_security_event({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "write_response_raw",
                "status_code": response.status_code,
                "path": path,
                "method": method,
                "body_preview": response.text[:500],
            })

        response.raise_for_status()
        data = response.json()
        # Auto-solve verification challenges on write operations
        if method in ("POST", "PUT", "PATCH") and isinstance(data, dict):
            data = await _auto_verify(client, api_key, data)
        return data
    except httpx.HTTPStatusError as e:
        # Scan error response body through content filter
        body_text = e.response.text[:500]
        scan_result = scan_text(body_text) if body_text else {"clean": True, "flags": [], "risk_score": 0.0, "sanitised": ""}

        # Log all API errors to security audit
        log_security_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "api_error",
            "status_code": e.response.status_code,
            "path": path,
            "method": method,
            "flagged": not scan_result["clean"],
            "risk_score": scan_result["risk_score"],
            "flags": scan_result["flags"],
            "body_preview": scan_result["sanitised"][:200] if not scan_result["clean"] else body_text[:200],
        })

        # Check for verification challenges in error responses (e.g. 403 with embedded challenge)
        if method in ("POST", "PUT", "PATCH") and e.response.status_code in (403, 401):
            try:
                error_data = e.response.json()
                if isinstance(error_data, dict) and ("verification_code" in error_data or "challenge" in error_data):
                    logger.info(f"Verification challenge found in {e.response.status_code} error response")
                    error_data = await _auto_verify(client, api_key, error_data)
                    if error_data.get("verification_status") == "verified":
                        return error_data
            except (json.JSONDecodeError, Exception) as ve:
                logger.warning(f"Could not parse error response for challenge check: {ve}")

        # Pass filtered body if flagged
        filtered_body = scan_result["sanitised"] if not scan_result["clean"] else None
        return _http_error_response(e, filtered_body=filtered_body)
    except httpx.TimeoutException:
        return {"error": "Request to Moltbook API timed out. Try again shortly."}
    except Exception as e:
        logger.error(f"Unexpected API error: {type(e).__name__}: {e}")
        return {"error": "An unexpected error occurred while communicating with Moltbook."}


def _http_error_response(e: httpx.HTTPStatusError, *, filtered_body: str | None = None) -> Dict[str, Any]:
    """Convert HTTP errors into actionable messages."""
    status = e.response.status_code
    if filtered_body is not None:
        body = filtered_body
    else:
        try:
            body = e.response.json()
        except Exception:
            body = e.response.text[:500]
    logger.warning(f"HTTP {status} from Moltbook API: {body}")
    messages = {
        401: "Authentication failed. Check your MOLTBOOK_API_KEY.",
        403: "Forbidden. Account may be suspended or not yet claimed. Check agent status.",
        404: "Resource not found. Check the post/comment/submolt ID.",
        429: "Rate limited by Moltbook. Wait a moment before retrying.",
    }
    return {
        "error": messages.get(status, f"HTTP {status} from Moltbook API."),
        "status": status,
        "detail": body,
    }


# ---------------------------------------------------------------------------
# Verification challenge solver
# ---------------------------------------------------------------------------

_WORD_NUMBERS: Dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
_NUMBER_WORDS = set(_WORD_NUMBERS.keys()) | {"hundred", "thousand"}

_CHALLENGE_OPS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "\u00d7": lambda a, b: a * b,
    "/": lambda a, b: a / b if b != 0 else 0.0,
    "\u00f7": lambda a, b: a / b if b != 0 else 0.0,
}


def _words_to_number(text: str) -> float | None:
    """Convert word-form numbers to float. E.g. 'thirty two' -> 32.0."""
    text = text.strip().lower()
    try:
        return float(text)
    except ValueError:
        pass

    words = text.split()
    if not words:
        return None

    total = 0
    current = 0
    found_any = False

    for word in words:
        if word in _WORD_NUMBERS:
            current += _WORD_NUMBERS[word]
            found_any = True
        elif word == "hundred":
            current = (current or 1) * 100
            found_any = True
        elif word == "thousand":
            current = (current or 1) * 1000
            total += current
            current = 0
            found_any = True

    total += current
    return float(total) if found_any else None


def _extract_number(text: str) -> float | None:
    """Extract a number from narrative text (digit or word form)."""
    # Try digit-form numbers first
    digit_matches = re.findall(r"[\d]+(?:\.[\d]+)?", text)
    if digit_matches:
        return float(digit_matches[-1])

    # Strip intra-word obfuscation so "Tw^En]Ty" becomes "TwEnTy"
    deobfuscated = _strip_intra_word_separators(text)

    # Scan for longest contiguous sequence of number words
    words = re.findall(r"[a-z]+", deobfuscated.lower())
    best_num: float | None = None
    best_len = 0

    for i in range(len(words)):
        if words[i] in _NUMBER_WORDS:
            num_words = []
            j = i
            while j < len(words) and words[j] in _NUMBER_WORDS:
                num_words.append(words[j])
                j += 1
            if len(num_words) > best_len:
                candidate = _words_to_number(" ".join(num_words))
                if candidate is not None:
                    best_num = candidate
                    best_len = len(num_words)

    return best_num


def _strip_intra_word_separators(text: str) -> str:
    """Remove obfuscation characters embedded inside words.

    Moltbook inserts separator chars (^, ], ~, etc.) within words:
    'Tw^En]Ty' -> 'TwEnTy', 'NeW/ToNs' -> 'NeWToNs'
    Separators at word boundaries are replaced with spaces:
    'FiVe~ NeW' -> 'FiVe NeW', 'ClAw^' -> 'ClAw '
    """
    # Step 1: Remove separators between letters (intra-word)
    cleaned = re.sub(
        r"(?<=[a-zA-Z])[\]\[\^~|<>/{}()]+(?=[a-zA-Z])", "", text
    )
    # Step 2: Replace remaining separators with spaces (word boundaries)
    cleaned = re.sub(r"[\]\[\^~|<>/{}()]+", " ", cleaned)
    return cleaned


def _normalize_challenge_text(text: str) -> str:
    """Strip obfuscation from challenge text.

    Moltbook challenges use mixed case and special-char separators:
    'A] LoB-stEr] ClAw^ ExErTs- ThIrTy] FiVe~ NeW/ToNs'
    -> 'a lobster claw exerts thirty five newtons'
    Also handles intra-word separators:
    'Tw^En]Ty Ei]GhT' -> 'twenty eight'
    """
    # Strip intra-word separator chars, replace boundary ones with spaces
    cleaned = _strip_intra_word_separators(text)
    # Replace hyphens surrounded by letters (intra-word) with nothing,
    # but keep standalone hyphens (minus signs between spaces)
    cleaned = re.sub(r"(?<=[a-zA-Z])-(?=[a-zA-Z])", "", cleaned)
    # Remove stray hyphens adjacent to letters (e.g., "ExErTs- " or " -ThIrTy")
    cleaned = re.sub(r"(?<=[a-zA-Z])-(?=\s)", "", cleaned)
    cleaned = re.sub(r"(?<=\s)-(?=[a-zA-Z])", "", cleaned)
    # Collapse commas/periods used as separators (but keep decimal points)
    cleaned = re.sub(r"(?<![0-9])[,.](?![0-9])", " ", cleaned)
    # Collapse whitespace and lowercase
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


# Narrative operator patterns: regex patterns allowing intervening words
# between verb and preposition (e.g., "reduces force by" matches "reduc...by").
_NARRATIVE_OPS: list[tuple[str, Callable[[float, float], float]]] = [
    # Subtraction patterns (with optional intervening words before "by")
    (r"reduc(?:es|ed)(?:\s+\w+)*?\s+by", lambda a, b: a - b),
    (r"decreas(?:es|ed)(?:\s+\w+)*?\s+by", lambda a, b: a - b),
    (r"drops?(?:\s+\w+)*?\s+by", lambda a, b: a - b),
    (r"falls?(?:\s+\w+)*?\s+by", lambda a, b: a - b),
    (r"loses", lambda a, b: a - b),
    (r"lost", lambda a, b: a - b),
    (r"minus", lambda a, b: a - b),
    (r"subtract(?:s|ed)?(?:\s+\w+)*?\s+by", lambda a, b: a - b),
    (r"less(?:\s+\w+)*?\s+by", lambda a, b: a - b),
    (r"less", lambda a, b: a - b),
    # Addition patterns
    (r"adds", lambda a, b: a + b),
    (r"added(?:\s+\w+)*?\s+to", lambda a, b: a + b),
    (r"plus", lambda a, b: a + b),
    (r"gains", lambda a, b: a + b),
    (r"increas(?:es|ed)(?:\s+\w+)*?\s+by", lambda a, b: a + b),
    (r"grows?(?:\s+\w+)*?\s+by", lambda a, b: a + b),
    (r"combined(?:\s+\w+)*?\s+with", lambda a, b: a + b),
    # Multiplication patterns
    (r"times", lambda a, b: a * b),
    (r"multiplied(?:\s+\w+)*?\s+by", lambda a, b: a * b),
    (r"doubled", lambda a, b: a * 2),
    (r"tripled", lambda a, b: a * 3),
    # Division patterns
    (r"divided(?:\s+\w+)*?\s+by", lambda a, b: a / b if b != 0 else 0.0),
    (r"split(?:\s+\w+)*?\s+into", lambda a, b: a / b if b != 0 else 0.0),
    (r"halved", lambda a, b: a / 2),
]


def _match_narrative_op(
    text: str,
) -> tuple[list[str] | None, Callable[[float, float], float] | None]:
    """Match a narrative operator in normalized text using regex patterns.

    Returns (parts, op_func) where parts is [left, right] text split at the
    operator boundary, or (None, None) if no operator matched.
    """
    for pattern, func in _NARRATIVE_OPS:
        match = re.search(pattern, text)
        if match:
            left = text[: match.start()]
            right = text[match.end() :]
            logger.info(f"Matched narrative operator: '{match.group()}'")
            return [left, right], func
    return None, None


def _solve_challenge_regex(challenge_text: str) -> str | None:
    """Parse a lobster math challenge using regex and return the answer.

    Handles both symbolic operators ('+', '-') and narrative operators
    ('reduces by', 'adds', etc.) in potentially obfuscated text.

    Strategy:
    1. Try symbolic operators on lightly-cleaned text (preserves operator chars)
    2. If no symbolic match, normalize fully and try narrative operators

    Example: "A] LoB-stEr] ClAw^ ExErTs- ThIrTy] FiVe~ NeW/ToNs,
    Um BuT^ MoLt-InG ReDuCeS| FoRce- By< SeVeN> , WhAt^ ReMaInS?"
    -> "28.00"
    """
    if not challenge_text:
        return None

    # --- Phase 1: Try symbolic operators on lightly-cleaned text ---
    # Only collapse whitespace and lowercase; preserve operator chars (+, -, *, /)
    light_cleaned = re.sub(r"\s+", " ", challenge_text).strip().lower()

    op_func = None
    parts = None
    for op_char in _CHALLENGE_OPS:
        if f" {op_char} " in light_cleaned:
            parts = light_cleaned.split(f" {op_char} ", 1)
            op_func = _CHALLENGE_OPS[op_char]
            logger.info(f"Matched symbolic operator: '{op_char}'")
            break

    # --- Phase 2: Try narrative operators on fully normalized text ---
    if not parts or not op_func:
        normalized = _normalize_challenge_text(challenge_text)
        logger.info(f"Normalized challenge: {normalized[:120]}")
        parts, op_func = _match_narrative_op(normalized)

    if not parts or not op_func:
        logger.warning(f"Could not find operator in challenge: {challenge_text[:120]}")
        return None

    left_num = _extract_number(parts[0])
    right_num = _extract_number(parts[1])

    if left_num is None:
        logger.warning(
            f"Could not extract left number from challenge: "
            f"left={left_num}, text={challenge_text[:120]}"
        )
        return None

    # Handle unary operators (doubled, tripled, halved) — right_num not required
    if right_num is None:
        try:
            result = op_func(left_num, 0)
        except Exception:
            logger.warning(
                f"Could not extract right number from challenge: "
                f"right={right_num}, text={challenge_text[:120]}"
            )
            return None
    else:
        result = op_func(left_num, right_num)

    answer = f"{result:.2f}"
    logger.info(f"Challenge solved (regex): {left_num} op {right_num} = {answer}")
    return answer


# ---------------------------------------------------------------------------
# LLM-based challenge solver (Claude Haiku)
# ---------------------------------------------------------------------------

_CHALLENGE_SOLVER_PROMPT = (
    "You are a math solver. You receive a math word problem that may be "
    "obfuscated with random capitalization, special characters, or creative "
    "narrative framing. Your job is to:\n"
    "1. Interpret the narrative to identify the numbers and mathematical operation\n"
    "2. Compute the result\n"
    "3. Return ONLY the numeric answer with exactly 2 decimal places\n\n"
    "Examples:\n"
    "- 'A lobster claw exerts thirty five newtons + another fifteen' → '50.00'\n"
    "- 'A force of forty newtons halved' → '20.00'\n"
    "- 'ThIrTy FiVe NeWtOnS reduced by SeVeN' → '28.00'\n\n"
    "Rules:\n"
    "- Return ONLY the number, nothing else\n"
    "- Always use exactly 2 decimal places\n"
    "- If you cannot determine the answer, return 'ERROR'\n"
    "- Do not explain your reasoning\n"
    "- Do not include units, words, or any other text"
)

# Lazy-initialized Anthropic client (created on first use)
_anthropic_client: Optional["anthropic.AsyncAnthropic"] = None  # type: ignore[name-defined]


def _get_anthropic_client() -> "anthropic.AsyncAnthropic | None":
    """Get or create the Anthropic async client. Returns None if unavailable."""
    global _anthropic_client
    if anthropic is None or not ANTHROPIC_API_KEY:
        return None
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


async def _solve_challenge_llm(challenge_text: str) -> str | None:
    """Solve a verification challenge using Claude Haiku.

    Sends the challenge text to a small, fast LLM with a tightly constrained
    prompt that asks for only a numeric answer. The challenge text is treated
    as untrusted input and isolated in the user message.

    Args:
        challenge_text: The raw challenge text from Moltbook's API.

    Returns:
        The answer as a string with 2 decimal places, or None if the LLM
        could not solve it or the API call failed.
    """
    client = _get_anthropic_client()
    if client is None:
        logger.debug("Anthropic client unavailable — skipping LLM solver")
        return None

    # Truncate excessively long challenges (defense against payload inflation)
    sanitized_challenge = challenge_text[:500]

    try:
        response = await client.messages.create(
            model=CHALLENGE_SOLVER_MODEL,
            max_tokens=20,
            temperature=0.0,
            system=_CHALLENGE_SOLVER_PROMPT,
            messages=[
                {"role": "user", "content": sanitized_challenge},
            ],
        )

        answer_text = response.content[0].text.strip()
        logger.info(f"LLM solver raw response: '{answer_text}'")

        if answer_text == "ERROR":
            logger.warning("LLM solver returned ERROR — challenge may be ambiguous")
            return None

        # Validate: must contain a parseable float (defense against injection)
        number_match = re.search(r"-?\d+\.?\d*", answer_text)
        if not number_match:
            logger.warning(f"LLM solver returned non-numeric response: '{answer_text}'")
            return None

        result = float(number_match.group())
        answer = f"{result:.2f}"
        logger.info(f"LLM solver answer: {answer}")
        return answer

    except Exception as e:
        logger.warning(f"LLM solver failed: {type(e).__name__}: {e}")
        return None


async def _solve_challenge(challenge_text: str) -> str | None:
    """Solve a verification challenge, trying LLM first with regex fallback.

    Strategy:
    1. If Anthropic API key is configured, try the LLM solver (Claude Haiku)
    2. If LLM fails or is unavailable, fall back to regex-based solver
    3. Return None if neither can solve it

    Args:
        challenge_text: The raw challenge text from Moltbook's API.

    Returns:
        The answer as a string with 2 decimal places, or None.
    """
    if not challenge_text:
        return None

    # Phase 1: Try LLM solver
    answer = await _solve_challenge_llm(challenge_text)
    if answer is not None:
        log_security_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "challenge_solved_by_llm",
            "model": CHALLENGE_SOLVER_MODEL,
            "answer": answer,
            "challenge_preview": challenge_text[:200],
        })
        return answer

    # Phase 2: Fall back to regex solver
    logger.info("LLM solver unavailable or failed — trying regex solver")
    answer = _solve_challenge_regex(challenge_text)
    if answer is not None:
        log_security_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "challenge_solved_by_regex",
            "answer": answer,
            "challenge_preview": challenge_text[:200],
        })
    return answer


async def _auto_verify(
    client: httpx.AsyncClient,
    api_key: str,
    response_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Detect and solve verification challenges in API responses.

    When a write operation returns a verification challenge, this function
    parses the math problem, computes the answer, and submits it to the
    /verify endpoint — all transparently before returning to the caller.

    Handles both top-level and nested verification data structures:
    - Top-level: {"verification_code": ..., "challenge": ...}
    - Nested: {"comment": {..., "verification": {"verification_code": ..., "challenge_text": ...}}}
    """
    # Check top-level first
    verification_code = response_data.get("verification_code")
    challenge_text = response_data.get("challenge") or response_data.get("challenge_text")

    # Check nested structures (comment/post responses with verification block)
    if not verification_code:
        for key in ("comment", "post", "verification"):
            nested = response_data.get(key)
            if isinstance(nested, dict):
                v_block = nested.get("verification", nested)
                if "verification_code" in v_block:
                    verification_code = v_block["verification_code"]
                    challenge_text = v_block.get("challenge_text") or v_block.get("challenge")
                    break

    if not verification_code or not challenge_text:
        return response_data

    logger.info(f"Verification challenge detected: {challenge_text[:80]}...")
    log_security_event({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "verification_challenge_received",
        "challenge_text": challenge_text[:200],
        "verification_code": verification_code,
    })

    answer = await _solve_challenge(challenge_text)
    if answer is None:
        logger.error(f"Failed to solve verification challenge: {challenge_text}")
        log_security_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "verification_challenge_unsolved",
            "verification_code": verification_code,
            "challenge_text": challenge_text[:200],
            "error": "Could not parse the math challenge",
        })
        response_data["verification_status"] = "unsolved"
        response_data["verification_error"] = "Could not parse the math challenge"
        return response_data

    logger.info(f"Solved challenge: answer={answer}")

    url = f"{MOLTBOOK_API_BASE}/verify"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        verify_resp = await client.post(
            url,
            headers=headers,
            json={"verification_code": verification_code, "answer": answer},
            timeout=30.0,
        )
        verify_data = verify_resp.json()
        logger.info(f"Verification response: {verify_resp.status_code}")

        response_data["verification_status"] = (
            "verified" if verify_resp.status_code == 200 else "failed"
        )
        response_data["verification_response"] = verify_data
        log_security_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "verification_challenge_answered",
            "verification_code": verification_code,
            "answer": answer,
            "status_code": verify_resp.status_code,
            "result": "verified" if verify_resp.status_code == 200 else "failed",
        })
    except Exception as e:
        logger.error(f"Verification request failed: {e}")
        response_data["verification_status"] = "error"
        response_data["verification_error"] = str(e)
        log_security_event({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "verification_challenge_error",
            "verification_code": verification_code,
            "answer": answer,
            "error": str(e),
        })

    return response_data


# ---------------------------------------------------------------------------
# Lifespan — shared httpx client + credential loading
# ---------------------------------------------------------------------------


@asynccontextmanager
async def app_lifespan(app):
    """Initialise an httpx client and load credentials once at startup.

    Args:
        app: The FastMCP application instance (required by MCP lifespan protocol).
    """
    global _http_client, _credentials
    _credentials = _load_credentials()
    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
        timeout=httpx.Timeout(30.0, connect=10.0),
    ) as client:
        _http_client = client
        yield {"client": client, "credentials": _credentials}
    _http_client = None


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

mcp = FastMCP(
    "moltbook_mcp",
    lifespan=app_lifespan,
    host=MCP_HOST,
    port=8080,
)

if not MCP_AUTH_TOKEN:
    logger.warning(
        "MCP_AUTH_TOKEN not set — server has NO authentication. "
        "Set MCP_AUTH_TOKEN env var to secure the endpoint."
    )

# Register health check as a custom HTTP route
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Helpers to extract lifespan state
# ---------------------------------------------------------------------------


def _get_client(ctx: Context) -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client not initialized — lifespan not started")
    return _http_client


def _get_api_key(ctx: Context) -> str:
    key = _credentials.get("api_key", "")
    if not key:
        raise ValueError(
            "No Moltbook API key found. Set MOLTBOOK_API_KEY env var or "
            "mount credentials.json at /app/config/credentials.json"
        )
    return key


def _strip_security_metadata(data: Any) -> Any:
    """Remove _security metadata from content filter results before returning to LLM.

    The content filter attaches _security metadata for audit logging, but this
    information should not be exposed to the reasoning LLM as it could be
    exploited by crafted content.
    """
    if isinstance(data, dict):
        return {k: _strip_security_metadata(v) for k, v in data.items() if k != "_security"}
    if isinstance(data, list):
        return [_strip_security_metadata(item) for item in data]
    return data


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Simple in-memory rate limiter using sliding window.

    Supports multiple windows per action (e.g., burst + daily limits).
    """

    def __init__(self, limits: Dict[str, list[tuple[int, float]]]):
        """Initialize the rate limiter.

        Args:
            limits: Dict mapping action names to lists of (max_calls, window_seconds)
                   tuples. Each action can have multiple windows enforced simultaneously.
                   Example: {"comment": [(1, 20), (50, 86400)]} allows 1 comment per
                   20 seconds AND 50 comments per day.
        """
        self.limits = limits
        self.call_history: Dict[str, List[float]] = {action: [] for action in limits.keys()}

    def _format_window(self, window_seconds: float) -> str:
        """Format a window duration as a human-readable string."""
        if window_seconds < 60:
            return f"{window_seconds:.0f} second{'s' if window_seconds != 1 else ''}"
        if window_seconds < 3600:
            minutes = window_seconds / 60
            return f"{minutes:.0f} minute{'s' if minutes != 1 else ''}"
        if window_seconds < 86400:
            hours = window_seconds / 3600
            return f"{hours:.0f} hour{'s' if hours != 1 else ''}"
        days = window_seconds / 86400
        return f"{days:.0f} day{'s' if days != 1 else ''}"

    def check(self, action: str) -> None:
        """Check if an action is allowed under rate limits.

        Args:
            action: The action type to check (e.g., "post", "comment", "vote").

        Raises:
            ValueError: If any rate limit window for this action has been exceeded.
        """
        if action not in self.limits:
            return

        now = time.monotonic()

        # Check each window for this action
        for max_calls, window_seconds in self.limits[action]:
            cutoff = now - window_seconds
            recent = [ts for ts in self.call_history[action] if ts > cutoff]
            if len(recent) >= max_calls:
                window_str = self._format_window(window_seconds)
                raise ValueError(
                    f"Rate limit exceeded: maximum {max_calls} {action}s per "
                    f"{window_str}. Try again later."
                )

        # Prune old timestamps (beyond the largest window)
        max_window = max(w for _, w in self.limits[action])
        cutoff = now - max_window
        self.call_history[action] = [ts for ts in self.call_history[action] if ts > cutoff]

        # Record this call
        self.call_history[action].append(now)


# Create module-level rate limiter instance with platform-correct values
_rate_limiter = RateLimiter({
    "post": [(1, 1800)],                # 1 per 30 minutes
    "comment": [(1, 20), (50, 86400)],  # 1 per 20 sec + 50 per day
    "vote": [(30, 3600)],               # Safety limit (no explicit platform cap)
    "subscribe": [(1, 3600)],           # 1 submolt per hour
})


# ===================================================================
# Input Models
# ===================================================================


class SortOption(str, Enum):
    HOT = "hot"
    NEW = "new"
    TOP = "top"
    RISING = "rising"


class CommentSortOption(str, Enum):
    TOP = "top"
    NEW = "new"
    CONTROVERSIAL = "controversial"


class MoltbookRegisterInput(BaseModel):
    """Input for registering a new agent on Moltbook."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Agent display name on Moltbook", min_length=1, max_length=64)
    description: str = Field(
        ..., description="Short bio / description of the agent", min_length=1, max_length=500
    )


class MoltbookBrowseFeedInput(BaseModel):
    """Input for browsing the Moltbook feed."""
    model_config = ConfigDict(extra="forbid")
    sort: SortOption = Field(default=SortOption.HOT, description="Feed sort order")
    limit: int = Field(default=DEFAULT_FEED_LIMIT, ge=1, le=MAX_FEED_LIMIT, description="Posts to fetch")
    submolt: Optional[str] = Field(
        default=None, description="Filter to a specific submolt community (e.g. 'general', 'aithoughts')"
    )

    @field_validator("submolt")
    @classmethod
    def validate_submolt(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not SAFE_ID_PATTERN.match(v):
            raise ValueError("Submolt name must contain only alphanumeric characters, hyphens, and underscores")
        return v


class MoltbookGetPostInput(BaseModel):
    """Input for getting a single post and its comments."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    post_id: str = Field(..., description="The Moltbook post ID", min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    comment_sort: CommentSortOption = Field(default=CommentSortOption.TOP, description="Comment sort order")


class MoltbookCreatePostInput(BaseModel):
    """Input for creating a new post."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    submolt: str = Field(
        default="general",
        description="The submolt community to post in (e.g. 'general')",
        min_length=1,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    title: str = Field(..., description="Post title", min_length=1, max_length=300)
    content: Optional[str] = Field(default=None, description="Post body text")
    url: Optional[str] = Field(default=None, description="URL for a link post (mutually exclusive with content)")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith("https://"):
            raise ValueError("URL must start with https://")
        return v


class MoltbookCommentInput(BaseModel):
    """Input for commenting on a post or replying to a comment."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    post_id: str = Field(..., description="The post to comment on", min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    content: str = Field(..., description="Comment text", min_length=1, max_length=10000)
    parent_id: Optional[str] = Field(default=None, description="Parent comment ID for threaded replies")

    @field_validator("parent_id")
    @classmethod
    def validate_parent_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not SAFE_ID_PATTERN.match(v):
            raise ValueError("ID must contain only alphanumeric characters, hyphens, and underscores")
        return v


class MoltbookVoteInput(BaseModel):
    """Input for voting on a post or comment."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    target_id: str = Field(..., description="The post or comment ID to vote on", min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    target_type: str = Field(..., description="'post' or 'comment'", pattern=r"^(post|comment)$")
    direction: str = Field(..., description="'up' or 'down'", pattern=r"^(up|down)$")


class MoltbookListSubmoltsInput(BaseModel):
    """Input for listing available submolt communities."""
    model_config = ConfigDict(extra="forbid")


class MoltbookAgentStatusInput(BaseModel):
    """Input for checking agent claim/auth status."""
    model_config = ConfigDict(extra="forbid")


class MoltbookSearchSubmoltInput(BaseModel):
    """Input for getting submolt info."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    submolt_name: str = Field(..., description="Name of the submolt to look up", min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")


class MoltbookSubscribeInput(BaseModel):
    """Input for subscribing/unsubscribing from a submolt."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    submolt_name: str = Field(..., description="Submolt to subscribe/unsubscribe", min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    action: str = Field(..., description="'subscribe' or 'unsubscribe'", pattern=r"^(subscribe|unsubscribe)$")


class MoltbookSetupOwnerEmailInput(BaseModel):
    """Input for setting up the owner's email address."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: str = Field(
        ..., description="The owner's email address for Moltbook login.", max_length=254
    )


class MoltbookUpdateIdentityInput(BaseModel):
    """Input for updating the agent's identity prompt."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    prompt_text: str = Field(
        ..., description="The full updated prompt text.", min_length=50, max_length=50000
    )
    change_summary: str = Field(
        ..., description="Brief description of what changed and why.", min_length=5, max_length=500
    )


# ===================================================================
# Tools — Read Operations
# ===================================================================


@mcp.tool(
    name="moltbook_agent_status",
    annotations={
        "title": "Check Moltbook Agent Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def moltbook_agent_status(params: MoltbookAgentStatusInput, ctx: Context) -> str:
    """Check the current agent's claim and authentication status on Moltbook.

    Returns the agent's profile info and whether the account has been claimed
    by a human via the verification tweet flow.

    Returns:
        str: JSON with agent status, name, and claim info.
    """
    client = _get_client(ctx)
    api_key = _get_api_key(ctx)

    status = await _api_request(client, "GET", "/agents/status", api_key)
    me = await _api_request(client, "GET", "/agents/me", api_key)
    return json.dumps({"status": status, "profile": me}, indent=2)


@mcp.tool(
    name="moltbook_browse_feed",
    annotations={
        "title": "Browse Moltbook Feed",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def moltbook_browse_feed(params: MoltbookBrowseFeedInput, ctx: Context) -> str:
    """Browse the Moltbook feed — the main stream of agent posts.

    Returns a list of posts sorted by the chosen algorithm. Optionally
    filter to a specific submolt community.

    Args:
        params: Feed parameters (sort, limit, submolt).

    Returns:
        str: JSON array of post objects with title, content, author,
             vote count, comment count, and submolt.
    """
    client = _get_client(ctx)
    api_key = _get_api_key(ctx)
    query: Dict[str, Any] = {"sort": params.sort.value, "limit": params.limit}
    if params.submolt:
        query["submolt"] = params.submolt

    data = await _api_request(client, "GET", "/posts", api_key, params=query)
    data = filter_posts(data)
    data = _strip_security_metadata(data)
    return json.dumps(data, indent=2)


@mcp.tool(
    name="moltbook_get_post",
    annotations={
        "title": "Get Moltbook Post and Comments",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def moltbook_get_post(params: MoltbookGetPostInput, ctx: Context) -> str:
    """Retrieve a single Moltbook post along with its comment thread.

    Useful for reading a full discussion before deciding whether to engage.

    Args:
        params: Post ID and comment sort preference.

    Returns:
        str: JSON with the post object and nested comments array.
    """
    client = _get_client(ctx)
    api_key = _get_api_key(ctx)

    post = await _api_request(client, "GET", f"/posts/{params.post_id}", api_key)
    comments = await _api_request(
        client,
        "GET",
        f"/posts/{params.post_id}/comments",
        api_key,
        params={"sort": params.comment_sort.value},
    )
    post = filter_post(post)
    comments = filter_comments(comments)
    post = _strip_security_metadata(post)
    comments = _strip_security_metadata(comments)
    return json.dumps({"post": post, "comments": comments}, indent=2)


@mcp.tool(
    name="moltbook_list_submolts",
    annotations={
        "title": "List Moltbook Communities",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def moltbook_list_submolts(params: MoltbookListSubmoltsInput, ctx: Context) -> str:
    """List all available submolt communities on Moltbook.

    Returns:
        str: JSON array of submolt objects with name, description,
             subscriber count, and recent activity.
    """
    client = _get_client(ctx)
    api_key = _get_api_key(ctx)
    data = await _api_request(client, "GET", "/submolts", api_key)
    return json.dumps(data, indent=2)


@mcp.tool(
    name="moltbook_get_submolt",
    annotations={
        "title": "Get Submolt Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def moltbook_get_submolt(params: MoltbookSearchSubmoltInput, ctx: Context) -> str:
    """Get detailed information about a specific submolt community.

    Args:
        params: The submolt name to look up.

    Returns:
        str: JSON with submolt metadata, rules, subscriber count.
    """
    client = _get_client(ctx)
    api_key = _get_api_key(ctx)
    data = await _api_request(client, "GET", f"/submolts/{params.submolt_name}", api_key)
    return json.dumps(data, indent=2)


# ===================================================================
# Tools — Write Operations
# ===================================================================


@mcp.tool(
    name="moltbook_register",
    annotations={
        "title": "Register Agent on Moltbook",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def moltbook_register(params: MoltbookRegisterInput, ctx: Context) -> str:
    """Register a new agent account on Moltbook.

    This creates the agent and returns an API key + claim URL. The human
    owner must visit the claim URL and post a verification tweet to
    activate the account.

    ⚠️  SAVE THE API KEY — it cannot be recovered later.

    Args:
        params: Agent name and description.

    Returns:
        str: JSON with api_key, claim_url, and verification_code.
    """
    client = _get_client(ctx)
    # Registration does not require an existing API key
    data = await _api_request(
        client,
        "POST",
        "/agents/register",
        "",  # no auth needed for registration
        json_body={"name": params.name, "description": params.description},
    )
    return json.dumps(data, indent=2)


@mcp.tool(
    name="moltbook_create_post",
    annotations={
        "title": "Create a Moltbook Post",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def moltbook_create_post(params: MoltbookCreatePostInput, ctx: Context) -> str:
    """Create a new post on Moltbook in a specified submolt.

    Supports text posts (with content) and link posts (with url).

    Args:
        params: Submolt, title, and either content or url.

    Returns:
        str: JSON with the created post object.
    """
    try:
        _rate_limiter.check("post")
    except ValueError as e:
        return json.dumps({"error": str(e)})

    client = _get_client(ctx)
    api_key = _get_api_key(ctx)

    body: Dict[str, Any] = {"submolt": params.submolt, "title": params.title}
    if params.url:
        body["url"] = params.url
    elif params.content:
        body["content"] = params.content

    data = await _api_request(client, "POST", "/posts", api_key, json_body=body)
    return json.dumps(data, indent=2)


@mcp.tool(
    name="moltbook_comment",
    annotations={
        "title": "Comment on a Moltbook Post",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def moltbook_comment(params: MoltbookCommentInput, ctx: Context) -> str:
    """Add a comment to a Moltbook post, or reply to an existing comment.

    Args:
        params: Post ID, comment content, and optional parent comment ID
                for threaded replies.

    Returns:
        str: JSON with the created comment object.
    """
    try:
        _rate_limiter.check("comment")
    except ValueError as e:
        return json.dumps({"error": str(e)})

    client = _get_client(ctx)
    api_key = _get_api_key(ctx)

    body: Dict[str, Any] = {"content": params.content}
    if params.parent_id:
        body["parent_id"] = params.parent_id

    data = await _api_request(
        client, "POST", f"/posts/{params.post_id}/comments", api_key, json_body=body
    )
    return json.dumps(data, indent=2)


@mcp.tool(
    name="moltbook_vote",
    annotations={
        "title": "Vote on Moltbook Content",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def moltbook_vote(params: MoltbookVoteInput, ctx: Context) -> str:
    """Upvote or downvote a Moltbook post or comment.

    Args:
        params: Target ID, type (post/comment), and direction (up/down).

    Returns:
        str: JSON confirmation with updated vote count.
    """
    try:
        _rate_limiter.check("vote")
    except ValueError as e:
        return json.dumps({"error": str(e)})

    client = _get_client(ctx)
    api_key = _get_api_key(ctx)

    if params.target_type == "post":
        path = f"/posts/{params.target_id}/{params.direction}vote"
    else:
        path = f"/comments/{params.target_id}/{params.direction}vote"

    data = await _api_request(client, "POST", path, api_key)
    return json.dumps(data, indent=2)


@mcp.tool(
    name="moltbook_subscribe",
    annotations={
        "title": "Subscribe/Unsubscribe to Submolt",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def moltbook_subscribe(params: MoltbookSubscribeInput, ctx: Context) -> str:
    """Subscribe to or unsubscribe from a submolt community.

    Args:
        params: Submolt name and action (subscribe/unsubscribe).

    Returns:
        str: JSON confirmation.
    """
    try:
        _rate_limiter.check("subscribe")
    except ValueError as e:
        return json.dumps({"error": str(e)})

    client = _get_client(ctx)
    api_key = _get_api_key(ctx)

    method = "POST" if params.action == "subscribe" else "DELETE"
    data = await _api_request(
        client, method, f"/submolts/{params.submolt_name}/subscribe", api_key
    )
    return json.dumps(data, indent=2)


# ===================================================================
# Tools — Account Management
# ===================================================================


@mcp.tool(
    name="moltbook_setup_owner_email",
    annotations={
        "title": "Set Up Owner Email",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def moltbook_setup_owner_email(params: MoltbookSetupOwnerEmailInput, ctx: Context) -> str:
    """Set up the owner's email address for Moltbook login.

    This associates an email address with the agent's human owner,
    enabling email-based login to the Moltbook platform.

    Args:
        params: The owner's email address.

    Returns:
        str: JSON confirmation or error message.
    """
    client = _get_client(ctx)
    api_key = _get_api_key(ctx)
    data = await _api_request(
        client, "POST", "/agents/me/setup-owner-email", api_key,
        json_body={"email": params.email},
    )
    return json.dumps(data, indent=2)


# ===================================================================
# Tools — Identity Management
# ===================================================================


@mcp.tool(
    name="moltbook_update_identity",
    annotations={
        "title": "Update Agent Identity",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def moltbook_update_identity(params: MoltbookUpdateIdentityInput, ctx: Context) -> str:
    """Update the agent's identity prompt by creating a new version.

    This stores the full prompt text as a new version in the dashboard,
    making it the active prompt for future heartbeats. Use this when your
    identity has genuinely evolved through community interactions.

    Args:
        params: Full prompt text and a summary of what changed.

    Returns:
        str: JSON confirmation with the new version number, or an error message.
    """
    client = _get_client(ctx)
    agent_name = _credentials.get("agent_name", "unknown")

    url = f"{DASHBOARD_API_URL}/api/prompts"
    body = {
        "prompt_text": params.prompt_text,
        "change_summary": params.change_summary,
        "author": agent_name,
    }

    headers = {}
    if DASHBOARD_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {DASHBOARD_AUTH_TOKEN}"

    try:
        response = await client.post(url, json=body, headers=headers, timeout=15.0)
        response.raise_for_status()
        data = response.json()
        version = data.get("version", "?")
        return json.dumps({
            "success": True,
            "message": f"Identity updated — now version {version}.",
            "version": version,
        })
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        logger.warning(f"Dashboard API returned HTTP {status} on identity update")
        return json.dumps({
            "error": f"Failed to update identity (HTTP {status}). The dashboard API may be unavailable.",
        })
    except httpx.TimeoutException:
        return json.dumps({
            "error": "Dashboard API timed out. Identity was not updated — try again later.",
        })


# ===================================================================
# Entrypoint
# ===================================================================


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Moltbook MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable_http"],
        default="streamable_http",
        help="MCP transport (default: streamable_http for Docker)",
    )
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    args = parser.parse_args()

    if args.transport == "streamable_http":
        # Get the ASGI app and wrap with auth middleware
        app = mcp.streamable_http_app()
        if MCP_AUTH_TOKEN:
            app = BearerAuthMiddleware(app)
            logger.info("Bearer token authentication enabled")
        uvicorn.run(app, host=MCP_HOST, port=args.port)
    else:
        mcp.run()  # stdio
