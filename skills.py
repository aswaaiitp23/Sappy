"""
Skills subsystem.

A skill is a Markdown file in ./skills/*.md.

At startup we scan the folder, pull the title (first # heading) and the first
real paragraph from each file, and inject that index into the system prompt.
The model can call load_skill to retrieve the full content of any skill on demand.

Keeping only summaries in the system prompt avoids filling the context window
with skill content that may never be needed.
"""

import os

SKILLS_DIR = "skills"


def _extract_title_and_summary(text: str) -> tuple[str, str]:
    """Return (title, one-sentence summary) from a skill's markdown content."""
    title = "Unnamed"
    summary = ""

    lines = text.strip().splitlines()
    found_title = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if not found_title:
                title = stripped.lstrip("#").strip()
                found_title = True
        elif found_title:
            # First non-heading, non-empty line after the title is the summary.
            summary = stripped[:200]
            break

    return title, summary


def load_skill_summaries() -> str:
    """
    Scan ./skills/ and return a formatted index of available skills.

    This string is injected into the system prompt so the model knows
    what expertise it can load, without reading every skill file upfront.
    """
    if not os.path.exists(SKILLS_DIR):
        os.makedirs(SKILLS_DIR)
        return ""

    skill_files = sorted(f for f in os.listdir(SKILLS_DIR) if f.endswith(".md"))
    if not skill_files:
        return ""

    lines = [
        "## Available Skills",
        "",
        "Call `load_skill` with the skill name to get full instructions.",
        "",
    ]

    for fname in skill_files:
        skill_name = fname[:-3]  # strip .md
        path = os.path.join(SKILLS_DIR, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        title, summary = _extract_title_and_summary(content)
        lines.append(f"- **{title}** (`{skill_name}`): {summary}")

    lines.append("")
    return "\n".join(lines)
