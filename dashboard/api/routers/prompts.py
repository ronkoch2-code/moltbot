"""API routes for heartbeat prompt version management."""

import math

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from dashboard.api.database import get_db
from dashboard.api.models import PaginatedPrompts, PromptCreateIn, PromptOut

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


def _row_to_prompt(row) -> dict:
    """Convert a sqlite3.Row to a PromptOut-compatible dict."""
    return {
        "id": row["id"],
        "version": row["version"],
        "prompt_text": row["prompt_text"],
        "change_summary": row["change_summary"],
        "author": row["author"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


@router.get("", response_model=PaginatedPrompts)
def list_prompts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all prompt versions, newest first."""
    with get_db() as conn:
        total_row = conn.execute(
            "SELECT COUNT(*) as total FROM heartbeat_prompts"
        ).fetchone()
        total = total_row["total"]

        offset = (page - 1) * per_page
        rows = conn.execute(
            """
            SELECT * FROM heartbeat_prompts
            ORDER BY version DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        ).fetchall()

    prompts = [PromptOut(**_row_to_prompt(row)) for row in rows]
    return PaginatedPrompts(
        prompts=prompts,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, math.ceil(total / per_page)),
    )


@router.get("/active", response_model=PromptOut)
def get_active_prompt():
    """Get the currently active prompt."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM heartbeat_prompts WHERE is_active = 1"
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No active prompt")
    return PromptOut(**_row_to_prompt(row))


@router.get("/active/text", response_class=PlainTextResponse)
def get_active_prompt_text():
    """Get the active prompt as plain text (for shell script curl)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT prompt_text FROM heartbeat_prompts WHERE is_active = 1"
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No active prompt")
    return PlainTextResponse(content=row["prompt_text"])


@router.get("/{prompt_id}", response_model=PromptOut)
def get_prompt(prompt_id: int):
    """Get a specific prompt version by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM heartbeat_prompts WHERE id = ?", (prompt_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return PromptOut(**_row_to_prompt(row))


@router.post("", response_model=PromptOut, status_code=201)
def create_prompt(body: PromptCreateIn):
    """Create a new prompt version. Deactivates all previous versions."""
    with get_db() as conn:
        # Get the next version number
        max_row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) as max_ver FROM heartbeat_prompts"
        ).fetchone()
        next_version = max_row["max_ver"] + 1

        # Deactivate all existing prompts
        conn.execute("UPDATE heartbeat_prompts SET is_active = 0")

        # Insert new active prompt
        cursor = conn.execute(
            """
            INSERT INTO heartbeat_prompts
                (version, prompt_text, change_summary, author, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (next_version, body.prompt_text, body.change_summary, body.author),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM heartbeat_prompts WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    return PromptOut(**_row_to_prompt(row))
