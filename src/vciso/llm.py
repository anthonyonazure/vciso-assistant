"""Shared helpers for reading Anthropic Messages API responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # for typing only; callers import the SDK lazily
    from anthropic.types import Message


def first_text(msg: Message) -> str:
    """Return the prose from a Messages API response.

    ``content`` is a list of typed blocks (text, thinking, tool use, ...), so
    reading ``.text`` off block zero is only valid when that block really is a
    text block. These prompts ask for plain prose, but a response with no text
    block is a real failure mode worth naming rather than hitting an
    AttributeError several frames away.
    """
    for block in msg.content:
        if block.type == "text":
            return block.text
    raise RuntimeError("Claude returned no text block for this prompt")
