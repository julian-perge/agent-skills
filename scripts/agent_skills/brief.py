STAGES = ("idea", "design", "spec", "plan", "build", "bug", "review")
COMMAND_NAMES = {"idea-refine": "idea", "interview-me": "design", "test": "bug"}

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
    "review": ("review",),
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


def stage_sections(text: str, stage: str) -> list[str]:
    stage = stage_name(stage)
    return [section for section in sections(text) if stage in SECTION_STAGES.get(section_key(section), STAGES)]
