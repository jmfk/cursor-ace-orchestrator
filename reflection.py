import re
from typing import List
from pydantic import BaseModel, Field


class ReflectionEntry(BaseModel):
    id: str
    type: str  # 'str', 'mis', or 'dec'
    helpful: int = 0
    harmful: int = 0
    content: str


class ReflectionResult(BaseModel):
    entries: List[ReflectionEntry] = Field(default_factory=list)


class ReflectionEngine:
    """
    Extracts learnings from agent output using structured patterns.
    [str-XXX] helpful=X harmful=Y :: <strategy>
    [mis-XXX] helpful=X harmful=Y :: <pitfall>
    [dec-XXX] :: <decision>
    """

    # Regex patterns for the three types of reflections
    STR_PATTERN = r"\[str-(\w+)\]\s+helpful=(\d+)\s+harmful=(\d+)\s+::\s+(.*)"
    MIS_PATTERN = r"\[mis-(\w+)\]\s+helpful=(\d+)\s+harmful=(\d+)\s+::\s+(.*)"
    DEC_PATTERN = r"\[dec-(\w+)\]\s+::\s+(.*)"

    def parse_output(self, text: str) -> ReflectionResult:
        """Parse structured reflection output."""
        result = ReflectionResult(entries=[])

        # Find all matches for strategies
        for match in re.finditer(self.STR_PATTERN, text):
            result.entries.append(
                ReflectionEntry(
                    id=match.group(1),
                    type="str",
                    helpful=int(match.group(2)),
                    harmful=int(match.group(3)),
                    content=match.group(4).strip(),
                )
            )

        # Find all matches for pitfalls
        for match in re.finditer(self.MIS_PATTERN, text):
            result.entries.append(
                ReflectionEntry(
                    id=match.group(1),
                    type="mis",
                    helpful=int(match.group(2)),
                    harmful=int(match.group(3)),
                    content=match.group(4).strip(),
                )
            )

        # Find all matches for decisions
        for match in re.finditer(self.DEC_PATTERN, text, re.MULTILINE):
            result.entries.append(
                ReflectionEntry(
                    id=match.group(1), type="dec", content=match.group(2).strip()
                )
            )

        return result


class PlaybookUpdater:
    """
    Updates .mdc files with new reflections while preserving structure.
    """

    def __init__(self, playbook_path: str):
        self.playbook_path = playbook_path

    def update(self, reflections: ReflectionResult):
        """Updates .mdc files with new reflections."""
        if not reflections.entries:
            return

        with open(self.playbook_path, "r") as f:
            content = f.read()

        new_content = content
        for entry in reflections.entries:
            if entry.type == "str":
                new_content = self._update_section(
                    new_content, "## Strategier & patterns", entry
                )
            elif entry.type == "mis":
                new_content = self._update_section(
                    new_content, "## Kända fallgropar", entry
                )
            elif entry.type == "dec":
                new_content = self._update_section(
                    new_content, "## Arkitekturella beslut", entry
                )

        if new_content != content:
            with open(self.playbook_path, "w") as f:
                f.write(new_content)

    def _update_section(
        self, content: str, section_header: str, entry: ReflectionEntry
    ) -> str:
        """Update a section with a new or existing entry."""
        # Find the section
        section_start = content.find(section_header)
        if section_start == -1:
            # Section doesn't exist, append it to the end
            content = content.rstrip() + f"\n\n{section_header}\n"
            section_start = content.find(section_header)

        # Find the end of the section (next header or end of file)
        next_section = content.find("\n## ", section_start + len(section_header))
        if next_section == -1:
            section_content = content[section_start:]
            post_content = ""
        else:
            section_content = content[section_start:next_section]
            post_content = content[next_section:]

        # Check if the entry already exists in the section
        entry_id_marker = f"[{entry.type}-{entry.id}]"
        if entry_id_marker in section_content:
            # Update existing entry
            if entry.type == "dec":
                new_entry_line = f"<!-- [dec-{entry.id}] :: {entry.content} -->"
                old_entry_pattern = rf"<!-- \[dec-{entry.id}\] :: .*? -->"
            else:
                # Extract existing counters
                old_entry_pattern = (
                    rf"<!-- \[{entry.type}-{entry.id}\] "
                    rf"helpful=(\d+) harmful=(\d+) :: (.*?) -->"
                )
                match = re.search(old_entry_pattern, section_content)
                if match:
                    old_helpful = int(match.group(1))
                    old_harmful = int(match.group(2))
                    # Increment counters
                    new_helpful = old_helpful + entry.helpful
                    new_harmful = old_harmful + entry.harmful
                    new_entry_line = (
                        f"<!-- [{entry.type}-{entry.id}] "
                        f"helpful={new_helpful} harmful={new_harmful} :: "
                        f"{entry.content} -->"
                    )
                else:
                    new_entry_line = (
                        f"<!-- [{entry.type}-{entry.id}] "
                        f"helpful={entry.helpful} harmful={entry.harmful} :: "
                        f"{entry.content} -->"
                    )

            if match:
                section_content = (
                    section_content[: match.start()]
                    + new_entry_line
                    + section_content[match.end() :]
                )
        else:
            # Add new entry
            if entry.type == "dec":
                new_entry_line = f"<!-- [dec-{entry.id}] :: {entry.content} -->"
            else:
                new_entry_line = (
                    f"<!-- [{entry.type}-{entry.id}] "
                    f"helpful={entry.helpful} harmful={entry.harmful} :: "
                    f"{entry.content} -->"
                )

            section_content = section_content.rstrip() + f"\n{new_entry_line}\n"

        return content[:section_start] + section_content + post_content
