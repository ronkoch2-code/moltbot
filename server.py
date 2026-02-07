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
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from enum import Enum

import httpx
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP, Context
from starlette.responses import JSONResponse

from content_filter import filter_posts, filter_post, filter_comments

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
DEFAULT_FEED_LIMIT = 25
MAX_FEED_LIMIT = 100
CREDENTIALS_PATH = os.environ.get(
    "MOLTBOOK_CREDENTIALS_PATH", "/app/config/credentials.json"
)

logger = logging.getLogger("moltbook_mcp")

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
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        return _http_error_response(e)
    except httpx.TimeoutException:
        return {"error": "Request to Moltbook API timed out. Try again shortly."}
    except Exception as e:
        return {"error": f"Unexpected error: {type(e).__name__}: {e}"}


def _http_error_response(e: httpx.HTTPStatusError) -> Dict[str, Any]:
    """Convert HTTP errors into actionable messages."""
    status = e.response.status_code
    body = ""
    try:
        body = e.response.json()
    except Exception:
        body = e.response.text[:500]
    messages = {
        401: "Authentication failed. Check your MOLTBOOK_API_KEY.",
        403: "Agent is not yet claimed. Have your human visit the claim URL first.",
        404: "Resource not found. Check the post/comment/submolt ID.",
        429: "Rate limited by Moltbook. Wait a moment before retrying.",
    }
    return {
        "error": messages.get(status, f"HTTP {status} from Moltbook API."),
        "status": status,
        "detail": body,
    }


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
    async with httpx.AsyncClient() as client:
        _http_client = client
        yield {"client": client, "credentials": _credentials}
    _http_client = None


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "moltbook_mcp",
    lifespan=app_lifespan,
    host="0.0.0.0",
    port=8080,
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


class MoltbookGetPostInput(BaseModel):
    """Input for getting a single post and its comments."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    post_id: str = Field(..., description="The Moltbook post ID", min_length=1)
    comment_sort: CommentSortOption = Field(default=CommentSortOption.TOP, description="Comment sort order")


class MoltbookCreatePostInput(BaseModel):
    """Input for creating a new post."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    submolt: str = Field(
        default="general",
        description="The submolt community to post in (e.g. 'general')",
        min_length=1,
    )
    title: str = Field(..., description="Post title", min_length=1, max_length=300)
    content: Optional[str] = Field(default=None, description="Post body text")
    url: Optional[str] = Field(default=None, description="URL for a link post (mutually exclusive with content)")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class MoltbookCommentInput(BaseModel):
    """Input for commenting on a post or replying to a comment."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    post_id: str = Field(..., description="The post to comment on", min_length=1)
    content: str = Field(..., description="Comment text", min_length=1, max_length=10000)
    parent_id: Optional[str] = Field(default=None, description="Parent comment ID for threaded replies")


class MoltbookVoteInput(BaseModel):
    """Input for voting on a post or comment."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    target_id: str = Field(..., description="The post or comment ID to vote on", min_length=1)
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
    submolt_name: str = Field(..., description="Name of the submolt to look up", min_length=1)


class MoltbookSubscribeInput(BaseModel):
    """Input for subscribing/unsubscribing from a submolt."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    submolt_name: str = Field(..., description="Submolt to subscribe/unsubscribe", min_length=1)
    action: str = Field(..., description="'subscribe' or 'unsubscribe'", pattern=r"^(subscribe|unsubscribe)$")


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
    client = _get_client(ctx)
    api_key = _get_api_key(ctx)

    method = "POST" if params.action == "subscribe" else "DELETE"
    data = await _api_request(
        client, method, f"/submolts/{params.submolt_name}/subscribe", api_key
    )
    return json.dumps(data, indent=2)


# ===================================================================
# Entrypoint
# ===================================================================


if __name__ == "__main__":
    import argparse

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
        mcp.run(transport="streamable-http")
    else:
        mcp.run()  # stdio
