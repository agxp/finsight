from __future__ import annotations

from finsight.transform.chunker import chunk_sections
from finsight.transform.html_parser import ParsedSection


def make_section(key: str, content: str) -> ParsedSection:
    return ParsedSection(section_key=key, raw_item=key, content=content)


def test_chunk_short_section():
    """Short section produces at least one chunk."""
    sections = [make_section("mda", "Apple reported strong revenue growth. Net income increased YOY.")]
    chunks = chunk_sections(sections, max_tokens=400, overlap_tokens=50, min_tokens=5)
    assert len(chunks) >= 1
    assert chunks[0].section == "mda"


def test_chunk_respects_section_boundary():
    """Chunks never cross section boundaries."""
    sections = [
        make_section("risk_factors", "There are many risks. " * 100),
        make_section("mda", "Revenue grew significantly. " * 100),
    ]
    chunks = chunk_sections(sections, max_tokens=100, overlap_tokens=20, min_tokens=10)

    risk_chunks = [c for c in chunks if c.section == "risk_factors"]
    mda_chunks = [c for c in chunks if c.section == "mda"]

    assert len(risk_chunks) > 0
    assert len(mda_chunks) > 0
    for chunk in risk_chunks:
        assert chunk.section == "risk_factors"
    for chunk in mda_chunks:
        assert chunk.section == "mda"


def test_chunk_max_tokens_respected():
    """No chunk significantly exceeds max_tokens."""
    long_text = "The company experienced significant growth in all segments. " * 200
    sections = [make_section("mda", long_text)]
    chunks = chunk_sections(sections, max_tokens=100, overlap_tokens=20, min_tokens=10)

    for chunk in chunks:
        # Allow some slack for sentence boundary splits
        assert chunk.token_count <= 150, f"Chunk too large: {chunk.token_count}"


def test_chunk_min_tokens_filter():
    """Chunks smaller than min_tokens are discarded."""
    sections = [make_section("mda", "Short text.")]
    chunks = chunk_sections(sections, max_tokens=400, overlap_tokens=50, min_tokens=100)
    assert len(chunks) == 0


def test_chunk_has_tables_flag():
    """Chunks with pipe characters are flagged as has_tables."""
    table_content = "| Revenue | $100B |\n| --- | --- |\n| Net Income | $20B |"
    sections = [make_section("financials", table_content)]
    chunks = chunk_sections(sections, max_tokens=400, overlap_tokens=50, min_tokens=5)
    assert any(c.has_tables for c in chunks)


def test_chunk_indices_sequential():
    """Chunk indices are sequential across the full run."""
    sections = [
        make_section("risk_factors", "Risk content. " * 50),
        make_section("mda", "MDA content. " * 50),
    ]
    chunks = chunk_sections(sections, max_tokens=50, overlap_tokens=10, min_tokens=5)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(indices)))


def test_empty_sections():
    """Empty sections list produces no chunks."""
    assert chunk_sections([]) == []
