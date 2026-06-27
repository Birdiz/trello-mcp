#!/usr/bin/env python3
"""
MCP Server for Trello.

Provides tools to interact with the Trello REST API:
boards, lists, cards, labels, members, search.

Authentication via TRELLO_API_KEY and TRELLO_TOKEN environment variables.
Get them at: https://trello.com/power-ups/admin
"""

import json
import os
from enum import Enum
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------

mcp = FastMCP("trello_mcp")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://api.trello.com/1"

LABEL_COLORS = [
    "yellow", "purple", "blue", "red", "green",
    "orange", "black", "sky", "pink", "lime",
]

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _auth_params() -> dict[str, str]:
    """Return Trello API key + token from env vars."""
    key = os.environ.get("TRELLO_API_KEY", "")
    token = os.environ.get("TRELLO_TOKEN", "")
    if not key or not token:
        raise RuntimeError(
            "TRELLO_API_KEY and TRELLO_TOKEN must be set as environment variables. "
            "Generate them at https://trello.com/power-ups/admin"
        )
    return {"key": key, "token": token}


# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------

async def _request(
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
) -> Any:
    """Perform a Trello API request and return parsed JSON."""
    query = {**_auth_params(), **(params or {})}
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            f"{API_BASE}/{path}",
            params=query,
            json=json_body,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def _handle_error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 401:
            return "Error: Invalid API key or token. Check TRELLO_API_KEY and TRELLO_TOKEN."
        if status == 403:
            return "Error: Permission denied. You don't have access to this resource."
        if status == 404:
            return "Error: Resource not found. Check that the ID is correct."
        if status == 429:
            return "Error: Rate limit exceeded. Please wait before making more requests."
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return f"Error: API request failed (HTTP {status}): {detail}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Please try again."
    if isinstance(e, RuntimeError):
        return f"Configuration error: {e}"
    return f"Error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Response format enum (shared)
# ---------------------------------------------------------------------------

class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


# ---------------------------------------------------------------------------
# ── BOARDS ──────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class ListBoardsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    filter: str = Field(
        default="open",
        description="Board filter: 'open', 'closed', 'all' (default: 'open')",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="trello_list_boards",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
async def trello_list_boards(params: ListBoardsInput) -> str:
    """List all Trello boards for the authenticated user.

    Returns board id, name, url, and status.
    Use the board id in other trello_* tools.
    """
    try:
        boards = await _request("GET", "members/me/boards", {"filter": params.filter})
        if not boards:
            return "No boards found."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(boards, indent=2)
        lines = ["# Your Trello Boards\n"]
        for b in boards:
            status = "closed" if b.get("closed") else "open"
            lines.append(f"- **{b['name']}** (id: `{b['id']}`) — {status}")
            lines.append(f"  {b.get('url', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


class GetBoardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    board_id: str = Field(..., description="Trello board ID", min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="trello_get_board",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
async def trello_get_board(params: GetBoardInput) -> str:
    """Get details of a specific Trello board including its lists and labels."""
    try:
        board = await _request("GET", f"boards/{params.board_id}", {"lists": "open", "labels": "all"})
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(board, indent=2)
        lines = [
            f"# {board['name']}",
            f"**ID**: `{board['id']}`",
            f"**URL**: {board.get('url', '')}",
            f"**Status**: {'Closed' if board.get('closed') else 'Open'}",
            "",
        ]
        if board.get("lists"):
            lines.append("## Lists")
            for lst in board["lists"]:
                lines.append(f"- **{lst['name']}** (id: `{lst['id']}`)")
        if board.get("labels"):
            lines.append("\n## Labels")
            for lbl in board["labels"]:
                name = lbl.get("name") or "(unnamed)"
                lines.append(f"- **{name}** — color: {lbl.get('color', 'none')} (id: `{lbl['id']}`)")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


class CreateBoardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Board name", min_length=1, max_length=16384)
    description: Optional[str] = Field(default=None, description="Board description")
    default_lists: bool = Field(
        default=True,
        description="Create default lists (To Do, Doing, Done) — default: true",
    )


@mcp.tool(
    name="trello_create_board",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
async def trello_create_board(params: CreateBoardInput) -> str:
    """Create a new Trello board.

    Returns the new board id and url.
    """
    try:
        body: dict = {
            "name": params.name,
            "defaultLists": str(params.default_lists).lower(),
        }
        if params.description:
            body["desc"] = params.description
        board = await _request("POST", "boards", body)
        return (
            f"Board **{board['name']}** created.\n"
            f"- **ID**: `{board['id']}`\n"
            f"- **URL**: {board.get('url', '')}"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# ── LISTS ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class ListListsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    board_id: str = Field(..., description="Trello board ID", min_length=1)
    filter: str = Field(default="open", description="Filter: 'open', 'closed', 'all'")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="trello_list_lists",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
async def trello_list_lists(params: ListListsInput) -> str:
    """List all lists (columns) on a Trello board."""
    try:
        lists = await _request("GET", f"boards/{params.board_id}/lists", {"filter": params.filter})
        if not lists:
            return "No lists found on this board."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(lists, indent=2)
        lines = [f"# Lists on board `{params.board_id}`\n"]
        for lst in lists:
            pos = lst.get("pos", "")
            lines.append(f"- **{lst['name']}** (id: `{lst['id']}`, pos: {pos})")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


class CreateListInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    board_id: str = Field(..., description="Trello board ID", min_length=1)
    name: str = Field(..., description="List name", min_length=1, max_length=16384)
    position: str = Field(
        default="bottom",
        description="Position: 'top', 'bottom', or a positive number (default: 'bottom')",
    )


@mcp.tool(
    name="trello_create_list",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
async def trello_create_list(params: CreateListInput) -> str:
    """Create a new list (column) on a Trello board."""
    try:
        lst = await _request(
            "POST",
            "lists",
            {"name": params.name, "idBoard": params.board_id, "pos": params.position},
        )
        return (
            f"List **{lst['name']}** created on board `{params.board_id}`.\n"
            f"- **ID**: `{lst['id']}`"
        )
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# ── CARDS ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class ListCardsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    list_id: Optional[str] = Field(default=None, description="List ID (to get cards from a specific list)")
    board_id: Optional[str] = Field(default=None, description="Board ID (to get all cards on a board)")
    filter: str = Field(default="open", description="Filter: 'open', 'closed', 'all' (board-level only)")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @field_validator("list_id", "board_id", mode="before")
    @classmethod
    def not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("ID cannot be empty string")
        return v


@mcp.tool(
    name="trello_list_cards",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
async def trello_list_cards(params: ListCardsInput) -> str:
    """List cards from a Trello list or board.

    Provide either list_id OR board_id (not both).
    """
    try:
        if params.list_id:
            cards = await _request("GET", f"lists/{params.list_id}/cards")
            source = f"list `{params.list_id}`"
        elif params.board_id:
            cards = await _request(
                "GET", f"boards/{params.board_id}/cards", {"filter": params.filter}
            )
            source = f"board `{params.board_id}`"
        else:
            return "Error: Provide either list_id or board_id."

        if not cards:
            return f"No cards found in {source}."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(cards, indent=2)

        lines = [f"# Cards in {source}\n"]
        for card in cards:
            due = card.get("due") or ""
            due_str = f" — due: {due[:10]}" if due else ""
            labels = ", ".join(
                (lbl.get("name") or lbl.get("color", "?")) for lbl in card.get("labels", [])
            )
            label_str = f" [{labels}]" if labels else ""
            lines.append(
                f"- **{card['name']}**{label_str}{due_str}\n"
                f"  id: `{card['id']}` | list: `{card.get('idList', '')}`"
            )
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


class GetCardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    card_id: str = Field(..., description="Trello card ID", min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="trello_get_card",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
async def trello_get_card(params: GetCardInput) -> str:
    """Get full details of a specific Trello card."""
    try:
        card = await _request("GET", f"cards/{params.card_id}")
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(card, indent=2)
        labels = ", ".join(
            (lbl.get("name") or lbl.get("color", "?")) for lbl in card.get("labels", [])
        )
        lines = [
            f"# {card['name']}",
            f"**ID**: `{card['id']}`",
            f"**List**: `{card.get('idList', '')}`",
            f"**Board**: `{card.get('idBoard', '')}`",
            f"**URL**: {card.get('url', card.get('shortUrl', ''))}",
        ]
        if card.get("desc"):
            lines.append(f"**Description**: {card['desc']}")
        if card.get("due"):
            lines.append(f"**Due**: {card['due'][:10]}")
        if labels:
            lines.append(f"**Labels**: {labels}")
        if card.get("dueComplete"):
            lines.append("**Status**: ✅ Complete")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


class CreateCardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    list_id: str = Field(..., description="ID of the list to add the card to", min_length=1)
    name: str = Field(..., description="Card name / title", min_length=1, max_length=16384)
    description: Optional[str] = Field(default=None, description="Card description (markdown supported)")
    due: Optional[str] = Field(
        default=None,
        description="Due date in ISO 8601 format (e.g. '2024-12-31T23:59:00.000Z')",
    )
    label_ids: Optional[list[str]] = Field(
        default=None, description="List of label IDs to apply to the card"
    )
    position: str = Field(default="bottom", description="Position: 'top', 'bottom', or a number")


@mcp.tool(
    name="trello_create_card",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
async def trello_create_card(params: CreateCardInput) -> str:
    """Create a new card in a Trello list.

    Returns the new card id and url.
    """
    try:
        body: dict = {
            "name": params.name,
            "idList": params.list_id,
            "pos": params.position,
        }
        if params.description:
            body["desc"] = params.description
        if params.due:
            body["due"] = params.due
        if params.label_ids:
            body["idLabels"] = ",".join(params.label_ids)
        card = await _request("POST", "cards", body)
        return (
            f"Card **{card['name']}** created.\n"
            f"- **ID**: `{card['id']}`\n"
            f"- **URL**: {card.get('shortUrl', '')}"
        )
    except Exception as e:
        return _handle_error(e)


class UpdateCardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    card_id: str = Field(..., description="Trello card ID", min_length=1)
    name: Optional[str] = Field(default=None, description="New card name")
    description: Optional[str] = Field(default=None, description="New card description")
    list_id: Optional[str] = Field(default=None, description="Move card to this list ID")
    due: Optional[str] = Field(default=None, description="New due date (ISO 8601) or 'null' to remove")
    due_complete: Optional[bool] = Field(default=None, description="Mark due date as complete/incomplete")
    closed: Optional[bool] = Field(default=None, description="Archive (true) or unarchive (false) the card")
    position: Optional[str] = Field(default=None, description="New position: 'top', 'bottom', or a number")


@mcp.tool(
    name="trello_update_card",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
async def trello_update_card(params: UpdateCardInput) -> str:
    """Update an existing Trello card (name, description, list, due date, etc.)."""
    try:
        body: dict = {}
        if params.name is not None:
            body["name"] = params.name
        if params.description is not None:
            body["desc"] = params.description
        if params.list_id is not None:
            body["idList"] = params.list_id
        if params.due is not None:
            body["due"] = None if params.due.lower() == "null" else params.due
        if params.due_complete is not None:
            body["dueComplete"] = params.due_complete
        if params.closed is not None:
            body["closed"] = params.closed
        if params.position is not None:
            body["pos"] = params.position
        if not body:
            return "Nothing to update — provide at least one field to change."
        card = await _request("PUT", f"cards/{params.card_id}", body)
        return f"Card **{card['name']}** (id: `{card['id']}`) updated successfully."
    except Exception as e:
        return _handle_error(e)


class DeleteCardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    card_id: str = Field(..., description="Trello card ID to delete", min_length=1)


@mcp.tool(
    name="trello_delete_card",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
)
async def trello_delete_card(params: DeleteCardInput) -> str:
    """Permanently delete a Trello card. This action cannot be undone.
    Consider using trello_update_card with closed=true to archive instead.
    """
    try:
        await _request("DELETE", f"cards/{params.card_id}")
        return f"Card `{params.card_id}` deleted permanently."
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# ── LABELS ───────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class ListLabelsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    board_id: str = Field(..., description="Trello board ID", min_length=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="trello_list_labels",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
async def trello_list_labels(params: ListLabelsInput) -> str:
    """List all labels defined on a Trello board."""
    try:
        labels = await _request("GET", f"boards/{params.board_id}/labels")
        if not labels:
            return "No labels found on this board."
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(labels, indent=2)
        lines = [f"# Labels on board `{params.board_id}`\n"]
        for lbl in labels:
            name = lbl.get("name") or "(unnamed)"
            lines.append(f"- **{name}** — color: `{lbl.get('color', 'none')}` (id: `{lbl['id']}`)")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


class CreateLabelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    board_id: str = Field(..., description="Trello board ID", min_length=1)
    name: str = Field(..., description="Label name", min_length=1, max_length=16384)
    color: str = Field(
        ...,
        description=(
            f"Label color. Options: {', '.join(LABEL_COLORS)}. "
            "Use 'null' for no color (transparent)."
        ),
    )

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if v != "null" and v not in LABEL_COLORS:
            raise ValueError(
                f"Invalid color '{v}'. Choose from: {', '.join(LABEL_COLORS)} or 'null'."
            )
        return v


@mcp.tool(
    name="trello_create_label",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
)
async def trello_create_label(params: CreateLabelInput) -> str:
    """Create a new label on a Trello board.

    Returns the new label id to use with trello_add_label_to_card.
    """
    try:
        color = None if params.color == "null" else params.color
        label = await _request(
            "POST",
            "labels",
            {"name": params.name, "color": color, "idBoard": params.board_id},
        )
        return (
            f"Label **{label['name']}** (color: {label.get('color', 'none')}) created.\n"
            f"- **ID**: `{label['id']}`"
        )
    except Exception as e:
        return _handle_error(e)


class UpdateLabelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    label_id: str = Field(..., description="Trello label ID", min_length=1)
    name: Optional[str] = Field(default=None, description="New label name")
    color: Optional[str] = Field(
        default=None,
        description=f"New color. Options: {', '.join(LABEL_COLORS)} or 'null'",
    )

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "null" and v not in LABEL_COLORS:
            raise ValueError(
                f"Invalid color '{v}'. Choose from: {', '.join(LABEL_COLORS)} or 'null'."
            )
        return v


@mcp.tool(
    name="trello_update_label",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
async def trello_update_label(params: UpdateLabelInput) -> str:
    """Update a Trello label's name or color."""
    try:
        body: dict = {}
        if params.name is not None:
            body["name"] = params.name
        if params.color is not None:
            body["color"] = None if params.color == "null" else params.color
        if not body:
            return "Nothing to update — provide name and/or color."
        label = await _request("PUT", f"labels/{params.label_id}", body)
        return f"Label `{params.label_id}` updated: name=**{label.get('name')}**, color={label.get('color')}."
    except Exception as e:
        return _handle_error(e)


class DeleteLabelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    label_id: str = Field(..., description="Trello label ID to delete", min_length=1)


@mcp.tool(
    name="trello_delete_label",
    annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
)
async def trello_delete_label(params: DeleteLabelInput) -> str:
    """Permanently delete a label from a Trello board."""
    try:
        await _request("DELETE", f"labels/{params.label_id}")
        return f"Label `{params.label_id}` deleted."
    except Exception as e:
        return _handle_error(e)


class AddLabelToCardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    card_id: str = Field(..., description="Trello card ID", min_length=1)
    label_id: str = Field(..., description="Trello label ID to add to the card", min_length=1)


@mcp.tool(
    name="trello_add_label_to_card",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
async def trello_add_label_to_card(params: AddLabelToCardInput) -> str:
    """Add a label to a Trello card."""
    try:
        await _request("POST", f"cards/{params.card_id}/idLabels", {"value": params.label_id})
        return f"Label `{params.label_id}` added to card `{params.card_id}`."
    except Exception as e:
        return _handle_error(e)


class RemoveLabelFromCardInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    card_id: str = Field(..., description="Trello card ID", min_length=1)
    label_id: str = Field(..., description="Trello label ID to remove from the card", min_length=1)


@mcp.tool(
    name="trello_remove_label_from_card",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
async def trello_remove_label_from_card(params: RemoveLabelFromCardInput) -> str:
    """Remove a label from a Trello card."""
    try:
        await _request("DELETE", f"cards/{params.card_id}/idLabels/{params.label_id}")
        return f"Label `{params.label_id}` removed from card `{params.card_id}`."
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# ── SEARCH ───────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(..., description="Search query string", min_length=1, max_length=16384)
    model_types: str = Field(
        default="cards,boards",
        description="Comma-separated types to search: 'cards', 'boards', 'organizations', 'members', 'actions'",
    )
    cards_limit: int = Field(default=10, ge=1, le=1000, description="Max cards to return (default: 10)")
    boards_limit: int = Field(default=5, ge=1, le=1000, description="Max boards to return (default: 5)")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="trello_search",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
async def trello_search(params: SearchInput) -> str:
    """Search across Trello for cards, boards, members, and more."""
    try:
        results = await _request(
            "GET",
            "search",
            {
                "query": params.query,
                "modelTypes": params.model_types,
                "cards_limit": params.cards_limit,
                "boards_limit": params.boards_limit,
                "cards_fields": "name,idList,idBoard,labels,shortUrl,due",
                "boards_fields": "name,url,closed",
            },
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(results, indent=2)

        lines = [f"# Search Results for '{params.query}'\n"]

        cards = results.get("cards", [])
        if cards:
            lines.append(f"## Cards ({len(cards)})")
            for card in cards:
                labels = ", ".join(
                    (lbl.get("name") or lbl.get("color", "?")) for lbl in card.get("labels", [])
                )
                label_str = f" [{labels}]" if labels else ""
                lines.append(f"- **{card['name']}**{label_str} — id: `{card['id']}`")
            lines.append("")

        boards = results.get("boards", [])
        if boards:
            lines.append(f"## Boards ({len(boards)})")
            for board in boards:
                lines.append(f"- **{board['name']}** — id: `{board['id']}` | {board.get('url', '')}")

        if not cards and not boards:
            return f"No results found for '{params.query}'."

        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# ── MEMBERS ──────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class GetMeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="trello_get_me",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
)
async def trello_get_me(params: GetMeInput) -> str:
    """Get the profile of the currently authenticated Trello user."""
    try:
        me = await _request("GET", "members/me")
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(me, indent=2)
        return (
            f"# {me.get('fullName', me.get('username'))}\n"
            f"**Username**: @{me.get('username')}\n"
            f"**ID**: `{me.get('id')}`\n"
            f"**Email**: {me.get('email', 'hidden')}"
        )
    except Exception as e:
        return _handle_error(e)


class AssignMemberInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    card_id: str = Field(..., description="Trello card ID", min_length=1)
    member_id: str = Field(..., description="Trello member ID to assign to the card", min_length=1)


@mcp.tool(
    name="trello_assign_member_to_card",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
)
async def trello_assign_member_to_card(params: AssignMemberInput) -> str:
    """Assign a member to a Trello card."""
    try:
        await _request("POST", f"cards/{params.card_id}/idMembers", {"value": params.member_id})
        return f"Member `{params.member_id}` assigned to card `{params.card_id}`."
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    # Use streamable HTTP when PORT is set (remote/Railway deployment)
    # Fall back to stdio for local use
    if os.environ.get("PORT"):
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run()
