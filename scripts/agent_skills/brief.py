STAGES = ("idea", "design", "spec", "plan", "build", "bug", "review")
COMMAND_NAMES = {"idea-refine": "idea", "interview-me": "design", "test": "bug"}
RULES_NOTE = "These are all the rules of docs/agents/workflow.md that this stage needs. Do not read that file."

# A heading that is not in this table goes to every stage, so that owner text is never dropped.
SECTION_STAGES = {
    "helpers": STAGES,
    "reports": STAGES,
    "stages": ("idea", "design"),
    "design": ("idea", "design", "spec"),
    "spec": ("spec",),
    "plan": ("plan",),
    "labels": ("plan",),
    "build": ("build", "bug"),
    "checks": ("build", "bug", "review"),
    "evidence": ("build", "bug", "review"),
    "review": ("review",),
    # The Earlier layout section names old spec and task paths that no stage works on.
    "earlier": (),
}


def stage_name(name: str) -> str:
    stage = COMMAND_NAMES.get(name, name)
    if stage not in STAGES:
        raise ValueError(f"expected one of {', '.join(STAGES)}, got {name!r}")
    return stage


def sections(text: str) -> list[str]:
    pieces: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("## ") or not pieces:
            pieces.append(line)
        else:
            pieces[-1] += line
    return pieces


def section_key(section: str) -> str | None:
    if not section.startswith("## "):
        return None
    words = section.removeprefix("## ").split(maxsplit=1)
    return words[0].lower() if words else ""


def stage_rules(intro: str) -> str:
    """Drops the title line and the first paragraph, which tells the agent to read the whole file."""
    lines = [line for line in intro.splitlines(keepends=True) if not line.startswith("# ")]
    start = 0
    for wanted_blank in (True, False, True):
        while start < len(lines) and (not lines[start].strip()) == wanted_blank:
            start += 1
    return "".join(lines[start:])


def stage_sections(text: str, stage: str) -> list[str]:
    stage = stage_name(stage)
    kept = []
    for section in sections(text):
        key = section_key(section)
        if key is None:
            section = stage_rules(section)
            if section:
                kept.append(section)
        elif stage in SECTION_STAGES.get(key, STAGES):
            kept.append(section)
    return kept
