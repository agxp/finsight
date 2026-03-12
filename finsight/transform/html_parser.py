from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

# Mapping from EDGAR Item headings to canonical section names
ITEM_SECTION_MAP: dict[str, str] = {
    "item1": "business",
    "item1a": "risk_factors",
    "item1b": "unresolved_staff_comments",
    "item2": "properties",
    "item3": "legal",
    "item6": "selected_data",
    "item7": "mda",
    "item7a": "market",
    "item8": "financials",
    "item9a": "controls",
}

STANDARD_SECTIONS = set(ITEM_SECTION_MAP.values())

# Regex to detect Item headings (e.g. "ITEM 1A.", "Item 7", "ITEM 1A —")
ITEM_HEADING_RE = re.compile(
    r"^\s*item\s+(\d+[a-z]?)\b",
    re.IGNORECASE,
)


@dataclass
class ParsedSection:
    section_key: str  # canonical name e.g. "risk_factors"
    raw_item: str  # e.g. "item1a"
    content: str  # cleaned text


def parse_filing_html(html_bytes: bytes) -> list[ParsedSection]:
    """
    Parse SEC filing HTML into sections. Strips XBRL, preserves tables as markdown.
    """
    soup = BeautifulSoup(html_bytes, "lxml")

    # Remove inline XBRL tags (ix:*) but keep their text content
    for tag in soup.find_all(re.compile(r"^ix:")):
        tag.unwrap()

    # Remove script, style, head
    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    sections: list[ParsedSection] = []
    current_item: str | None = None
    current_lines: list[str] = []

    def flush_section() -> None:
        if current_item and current_lines:
            canonical = ITEM_SECTION_MAP.get(current_item, current_item)
            content = "\n".join(current_lines).strip()
            if len(content) > 100:
                sections.append(
                    ParsedSection(
                        section_key=canonical,
                        raw_item=current_item,
                        content=content,
                    )
                )

    body = soup.find("body") or soup

    for element in body.descendants:
        if not isinstance(element, Tag):
            continue

        element_text = element.get_text(separator=" ").strip()
        if not element_text:
            continue

        if len(element_text) < 200:
            match = ITEM_HEADING_RE.match(element_text)
            if match:
                flush_section()
                item_key = "item" + match.group(1).lower()
                current_item = item_key
                current_lines = []
                continue

        if current_item is not None:
            if element.name == "table":
                md_table = _table_to_markdown(element)
                if md_table:
                    current_lines.append(md_table)
            elif element.name in ("p", "div", "span", "li"):
                text = element.get_text(separator=" ").strip()
                if text and len(text) > 10:
                    current_lines.append(text)

    flush_section()
    return sections


def _table_to_markdown(table: Tag) -> str:
    """Convert an HTML table to a simplified pipe-delimited markdown table."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    md_rows: list[str] = []
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        cell_texts = [c.get_text(separator=" ").strip().replace("|", "\\|") for c in cells]
        if not any(cell_texts):
            continue
        md_rows.append("| " + " | ".join(cell_texts) + " |")
        if i == 0:
            md_rows.append("| " + " | ".join(["---"] * len(cell_texts)) + " |")

    return "\n".join(md_rows)


def get_section_coverage(sections: list[ParsedSection]) -> set[str]:
    """Return the set of canonical section names found."""
    return {s.section_key for s in sections}
