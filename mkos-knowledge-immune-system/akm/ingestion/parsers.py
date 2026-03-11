"""Content parsers for markdown and JSON files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class Section:
    heading: str
    content: str
    level: int  # heading level (1, 2, 3)


@dataclass
class ParsedDocument:
    title: str
    sections: list[Section]
    metadata: dict = field(default_factory=dict)


class MarkdownParser:
    """Parse markdown files into structured sections."""

    _HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

    @classmethod
    def parse(cls, file_path: str) -> ParsedDocument:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            text = f.read()

        # Extract YAML frontmatter
        metadata: dict = {}
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                try:
                    import yaml
                    metadata = yaml.safe_load(text[3:end]) or {}
                except Exception:
                    pass
                text = text[end + 3:].strip()

        # Extract title from first H1 or metadata
        title = metadata.get("title", "")
        if not title:
            m = re.match(r"^#\s+(.+)$", text, re.MULTILINE)
            if m:
                title = m.group(1).strip()
            else:
                title = file_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]

        # Split into sections by headings
        sections: list[Section] = []
        matches = list(cls._HEADING_RE.finditer(text))

        if not matches:
            # No headings — treat entire text as one section
            content = text.strip()
            if content:
                sections.append(Section(heading=title, content=content, level=1))
            return ParsedDocument(title=title, sections=sections, metadata=metadata)

        # Content before first heading
        pre = text[:matches[0].start()].strip()
        if pre:
            sections.append(Section(heading=title, content=pre, level=1))

        # Each heading + content until next heading
        for i, m in enumerate(matches):
            level = len(m.group(1))
            heading = m.group(2).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content:
                sections.append(Section(heading=heading, content=content, level=level))

        return ParsedDocument(title=title, sections=sections, metadata=metadata)


class JSONParser:
    """Parse JSON files into searchable sections."""

    @classmethod
    def parse(cls, file_path: str) -> ParsedDocument:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)

        title = file_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        sections: list[Section] = []

        if isinstance(data, dict):
            cls._flatten_dict(data, sections, prefix="")
        elif isinstance(data, list):
            for i, item in enumerate(data[:50]):  # cap at 50 items
                if isinstance(item, dict):
                    text = " | ".join(f"{k}: {v}" for k, v in item.items()
                                      if isinstance(v, (str, int, float)))
                    if text:
                        sections.append(Section(heading=f"Item {i}", content=text, level=2))

        return ParsedDocument(title=title, sections=sections)

    @classmethod
    def _flatten_dict(cls, data: dict, sections: list[Section], prefix: str) -> None:
        for key, value in data.items():
            heading = f"{prefix}{key}" if prefix else key
            if isinstance(value, str) and len(value) > 20:
                sections.append(Section(heading=heading, content=value, level=2))
            elif isinstance(value, list):
                items = []
                for item in value[:30]:
                    if isinstance(item, str):
                        items.append(item)
                    elif isinstance(item, dict):
                        text = " | ".join(f"{k}: {v}" for k, v in item.items()
                                          if isinstance(v, (str, int, float)))
                        if text:
                            items.append(text)
                if items:
                    sections.append(Section(heading=heading, content="\n".join(items), level=2))
            elif isinstance(value, dict):
                cls._flatten_dict(value, sections, prefix=f"{heading}.")
