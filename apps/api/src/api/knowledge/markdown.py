"""Prepare immutable Markdown revisions from trusted manifest configuration."""

import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from markdown_it import MarkdownIt
from pydantic import Field, TypeAdapter, ValidationError

from api.knowledge.metadata import (
    DocumentMetadata,
    KnowledgeContract,
    MarkdownLocation,
    PassageLocation,
)


class IngestionFailure(StrEnum):
    INVALID_MANIFEST = "invalid_manifest"
    INVALID_PATH = "invalid_path"
    READ_FAILED = "read_failed"
    INVALID_ENCODING = "invalid_encoding"
    EMPTY_SOURCE = "empty_source"
    VERSION_CONFLICT = "version_conflict"


class IngestionError(ValueError):
    def __init__(self, reason: IngestionFailure) -> None:
        self.reason = reason
        super().__init__(reason.value)


class MarkdownSection(KnowledgeContract):
    text: str
    location: PassageLocation


class MarkdownDocument(KnowledgeContract):
    metadata: DocumentMetadata
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    metadata_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    text: str
    sections: tuple[MarkdownSection, ...]


def validate_manifest(entries: tuple[DocumentMetadata, ...]) -> None:
    by_id = {entry.document_id: entry for entry in entries}
    if len(by_id) != len(entries):
        raise IngestionError(IngestionFailure.INVALID_MANIFEST)
    if len({entry.source_path for entry in entries}) != len(entries):
        raise IngestionError(IngestionFailure.INVALID_MANIFEST)
    for entry in entries:
        visited: set[str] = set()
        current = entry
        while current.superseded_by is not None:
            visited.add(current.document_id)
            target = current.superseded_by
            if target not in by_id or target in visited:
                raise IngestionError(IngestionFailure.INVALID_MANIFEST)
            current = by_id[target]


def load_manifest(path: Path) -> tuple[DocumentMetadata, ...]:
    """The caller selects a trusted config file; source prose cannot set policy."""
    try:
        entries = TypeAdapter(tuple[DocumentMetadata, ...]).validate_json(
            path.read_bytes()
        )
    except OSError as error:
        raise IngestionError(IngestionFailure.READ_FAILED) from error
    except ValidationError as error:
        raise IngestionError(IngestionFailure.INVALID_MANIFEST) from error
    validate_manifest(entries)
    return entries


def parse_sections(
    text: str, metadata: DocumentMetadata
) -> tuple[MarkdownSection, ...]:
    # Markdown source mappings count CRLF, CR and LF as logical line breaks.
    # Preserve original bytes in each excerpt instead of normalized parser text.
    exact_lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
    if exact_lines and exact_lines[-1] == "":
        exact_lines.pop()
    line_count = len(exact_lines)
    tokens = MarkdownIt("commonmark").parse(text)
    boundaries: list[tuple[int, tuple[str, ...]]] = [(0, ())]
    headings: list[tuple[int, str]] = []
    for index, token in enumerate(tokens):
        # Only document-level headings define sections, not quoted/list headings.
        if token.type != "heading_open" or token.level != 0 or token.map is None:
            continue
        title = tokens[index + 1].content.strip()
        if not title:
            # Empty headings remain content, not invalid metadata paths.
            continue
        depth = int(token.tag[1:])
        while headings and headings[-1][0] >= depth:
            headings.pop()
        headings.append((depth, title))
        start = token.map[0]
        path = tuple(title for _, title in headings)
        if start == boundaries[-1][0]:
            boundaries[-1] = (start, path)
        else:
            boundaries.append((start, path))
    sections: list[MarkdownSection] = []
    for index, (start, path) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else line_count
        if end <= start:
            continue
        sections.append(
            MarkdownSection(
                text="".join(exact_lines[start:end]),
                location=PassageLocation(
                    document_id=metadata.document_id,
                    version=metadata.version,
                    location=MarkdownLocation(
                        kind="markdown",
                        heading_path=path,
                        line_start=start + 1,
                        line_end=end,
                    ),
                ),
            )
        )
    return tuple(sections)


def prepare_markdown(root: Path, metadata: DocumentMetadata) -> MarkdownDocument:
    metadata = DocumentMetadata.model_validate(metadata)
    try:
        resolved_root = root.resolve(strict=True)
        source = (resolved_root / metadata.source_path).resolve(strict=True)
        if (
            not source.is_relative_to(resolved_root)
            or source.suffix.lower() != ".md"
            or not source.is_file()
        ):
            raise IngestionError(IngestionFailure.INVALID_PATH)
        raw = source.read_bytes()
    except (OSError, RuntimeError) as error:
        raise IngestionError(IngestionFailure.READ_FAILED) from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IngestionError(IngestionFailure.INVALID_ENCODING) from error
    if not text.strip():
        raise IngestionError(IngestionFailure.EMPTY_SOURCE)
    canonical = json.dumps(
        metadata.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return MarkdownDocument(
        metadata=metadata,
        content_hash=hashlib.sha256(raw).hexdigest(),
        metadata_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        text=text,
        sections=parse_sections(text, metadata),
    )
