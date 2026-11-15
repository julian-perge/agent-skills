from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SubIssue:
    number: int
    title: str
    state: str
    assignees: tuple[str, ...]
    open_blockers: int


@dataclass(frozen=True)
class Frontier:
    number: int | None
    reason: str = ""


def frontier(subs: Sequence[SubIssue]) -> Frontier:
    if not subs:
        return Frontier(None, "no sub-issues")
    open_subs = [s for s in subs if s.state == "OPEN"]
    if not open_subs:
        return Frontier(None, f"all {len(subs)} sub-issues are closed")
    ready = [s.number for s in open_subs if not s.assignees and s.open_blockers == 0]
    if ready:
        return Frontier(min(ready))
    blocked = sum(1 for s in open_subs if s.open_blockers)
    assigned = sum(1 for s in open_subs if s.assignees)
    return Frontier(None, f"each open sub-issue is blocked or assigned: {blocked} blocked, {assigned} assigned")
