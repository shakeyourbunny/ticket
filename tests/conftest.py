# This file is part of the ticket Project.
# License: MIT. Contact: ticket-project@trinity2k.net
#

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def tickets_dir(tmp_path: Path) -> Path:
    """Create a .tickets directory for testing."""
    d = tmp_path / ".tickets"
    d.mkdir()
    return d


def make_ticket(
    tickets_dir: Path,
    *,
    id: str = "tst-0001",
    status: str = "open",
    deps: list[str] | None = None,
    links: list[str] | None = None,
    type: str = "task",
    priority: int = 2,
    assignee: str = "",
    external_ref: str = "",
    parent: str = "",
    tags: list[str] | None = None,
    repo: str = "",
    title: str = "Test ticket",
    body: str = "",
) -> Path:
    """Write a ticket file and return its path."""
    deps = deps or []
    links = links or []
    tags = tags or []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    deps_str = "[" + ", ".join(deps) + "]" if deps else "[]"
    links_str = "[" + ", ".join(links) + "]" if links else "[]"
    tags_str = "[" + ", ".join(tags) + "]" if tags else "[]"

    lines = [
        "---",
        f"id: {id}",
        f"status: {status}",
        f"deps: {deps_str}",
        f"links: {links_str}",
        f"created: {now}",
        f"type: {type}",
        f"priority: {priority}",
    ]
    if assignee:
        lines.append(f"assignee: {assignee}")
    if external_ref:
        lines.append(f"external-ref: {external_ref}")
    if parent:
        lines.append(f"parent: {parent}")
    if repo:
        lines.append(f"repo: {repo}")
    if tags:
        lines.append(f"tags: {tags_str}")
    lines.append("---")
    lines.append(f"# {title}")
    lines.append("")
    if body:
        lines.append(body)
        lines.append("")

    path = tickets_dir / f"{id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
