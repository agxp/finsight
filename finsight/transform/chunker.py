from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

from finsight.transform.html_parser import ParsedSection

_ENCODER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


def encode(text: str) -> list[int]:
    return _ENCODER.encode(text)


def decode(tokens: list[int]) -> str:
    return _ENCODER.decode(tokens)


@dataclass
class Chunk:
    section: str
    chunk_index: int
    content: str
    token_count: int
    has_tables: bool


def chunk_sections(
    sections: list[ParsedSection],
    *,
    max_tokens: int = 400,
    overlap_tokens: int = 50,
    min_tokens: int = 50,
) -> list[Chunk]:
    """
    Chunk sections into token-bounded pieces with overlap.
    Never crosses section boundaries.
    """
    chunks: list[Chunk] = []
    global_index = 0

    for section in sections:
        section_chunks = _chunk_section(
            section.content,
            section.section_key,
            start_index=global_index,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            min_tokens=min_tokens,
        )
        chunks.extend(section_chunks)
        global_index += len(section_chunks)

    return chunks


def _chunk_section(
    text: str,
    section: str,
    *,
    start_index: int,
    max_tokens: int,
    overlap_tokens: int,
    min_tokens: int,
) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

    chunks: list[Chunk] = []
    overlap_buffer: list[int] = []
    chunk_index = start_index

    for para in paragraphs:
        para_tokens = encode(para)

        if len(para_tokens) <= max_tokens:
            candidate = overlap_buffer + para_tokens
            if len(candidate) > max_tokens:
                _maybe_emit(
                    chunks,
                    chunk_index,
                    section,
                    overlap_buffer + para_tokens[: max_tokens - len(overlap_buffer)],
                    min_tokens,
                )
                chunk_index += 1
                overlap_buffer = (
                    para_tokens[-overlap_tokens:]
                    if len(para_tokens) > overlap_tokens
                    else para_tokens
                )
            else:
                overlap_buffer = candidate
                if len(overlap_buffer) >= max_tokens - overlap_tokens:
                    _maybe_emit(chunks, chunk_index, section, overlap_buffer, min_tokens)
                    chunk_index += 1
                    overlap_buffer = overlap_buffer[-overlap_tokens:]
        else:
            sentences = _split_sentences(para)
            for sent in sentences:
                sent_tokens = encode(sent)
                candidate = overlap_buffer + sent_tokens

                if len(candidate) > max_tokens:
                    if overlap_buffer:
                        _maybe_emit(chunks, chunk_index, section, overlap_buffer, min_tokens)
                        chunk_index += 1
                        overlap_buffer = overlap_buffer[-overlap_tokens:]

                    while len(sent_tokens) > max_tokens:
                        _maybe_emit(
                            chunks,
                            chunk_index,
                            section,
                            overlap_buffer + sent_tokens[: max_tokens - len(overlap_buffer)],
                            min_tokens,
                        )
                        chunk_index += 1
                        sent_tokens = sent_tokens[max_tokens - overlap_tokens :]
                        overlap_buffer = []

                    overlap_buffer = overlap_buffer + sent_tokens
                else:
                    overlap_buffer = candidate

    if overlap_buffer:
        _maybe_emit(chunks, chunk_index, section, overlap_buffer, min_tokens)

    return chunks


def _maybe_emit(
    chunks: list[Chunk],
    index: int,
    section: str,
    tokens: list[int],
    min_tokens: int,
) -> None:
    if len(tokens) < min_tokens:
        return
    content = decode(tokens)
    chunks.append(
        Chunk(
            section=section,
            chunk_index=index,
            content=content,
            token_count=len(tokens),
            has_tables="|" in content,
        )
    )


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter on '. ', '! ', '? '."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]
