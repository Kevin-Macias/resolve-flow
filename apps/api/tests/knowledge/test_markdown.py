import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from api.knowledge.markdown import (
    IngestionError,
    IngestionFailure,
    load_manifest,
    prepare_markdown,
)
from api.knowledge.metadata import DocumentMetadata
from api.knowledge.store import IngestionStatus, InMemoryDocumentStore, ingest_manifest

ROOT = Path(__file__).resolve().parents[4]


def entry(**changes: Any) -> DocumentMetadata:
    return DocumentMetadata.model_validate(
        {
            "document_id": "guide",
            "source": "curated_repository",
            "source_path": "guide.md",
            "title": "Guide",
            "document_type": "runbook",
            "service_code": "issue-reports",
            "version": "1",
            "document_date": "2026-10-06",
            "access_class": "INTERNAL",
            "status": "current",
            "fictional": False,
        }
        | changes
    )


def manifest(root: Path, entries: list[DocumentMetadata]) -> Path:
    path = root / "manifest.json"
    path.write_text(json.dumps([e.model_dump(mode="json") for e in entries]))
    return path


def test_real_corpus_ingests_once_and_replays_without_duplicates() -> None:
    store = InMemoryDocumentStore()
    first = ingest_manifest(ROOT, ROOT / "knowledge/manifest.json", store)
    second = ingest_manifest(ROOT, ROOT / "knowledge/manifest.json", store)
    assert len(first) == len(second) == 8
    assert all(r.status == IngestionStatus.CREATED for r in first)
    assert all(r.status == IngestionStatus.UNCHANGED for r in second)
    for meta in load_manifest(ROOT / "knowledge/manifest.json"):
        saved = store.get(meta.document_id, meta.version)
        assert saved is not None
        assert saved.metadata == meta
        assert "".join(s.text for s in saved.sections) == saved.text
        assert (
            saved.content_hash
            == hashlib.sha256((ROOT / meta.source_path).read_bytes()).hexdigest()
        )
    legacy = store.get("legacy-visibility", "1")
    assert legacy is not None and legacy.metadata.superseded_by == "archived-report"
    assert legacy.metadata.fictional


def test_sections_preserve_exact_lines_and_heading_hierarchy(tmp_path: Path) -> None:
    text = (
        "Prelude\n\n# Main\nbody\n## Child\n```md\n# Fake\n```\nSibling\n-------\nend\n"
    )
    (tmp_path / "guide.md").write_text(text)
    doc = prepare_markdown(tmp_path, entry())
    assert [
        s.location.location.heading_path
        for s in doc.sections
        if s.location.location.kind == "markdown"
    ] == [(), ("Main",), ("Main", "Child"), ("Main", "Sibling")]
    assert [s.text for s in doc.sections] == [
        "Prelude\n\n",
        "# Main\nbody\n",
        "## Child\n```md\n# Fake\n```\n",
        "Sibling\n-------\nend\n",
    ]
    lines = text.splitlines(keepends=True)
    for section in doc.sections:
        loc = section.location.location
        assert loc.kind == "markdown"
        assert section.text == "".join(lines[loc.line_start - 1 : loc.line_end])
        assert section.location.document_id == "guide"
        assert section.location.version == "1"


@pytest.mark.parametrize(
    "text",
    [
        "plain text",
        "# Heading",
        "#\ntext\n",
        "# Root\n> ## Quoted\n\n- item\n  ### Nested\n",
        "# Café\r\nBody\r\n",
        "# Root\rBody\r",
        "# Root\nUnicode\u2028separator\n",
    ],
)
def test_exact_text_is_preserved_without_rendering(tmp_path: Path, text: str) -> None:
    raw = text.encode()
    (tmp_path / "guide.md").write_bytes(raw)
    doc = prepare_markdown(tmp_path, entry())
    assert doc.text == text
    assert "".join(s.text for s in doc.sections) == text
    assert doc.content_hash == hashlib.sha256(raw).hexdigest()


def test_content_and_metadata_edits_require_new_version(tmp_path: Path) -> None:
    source = tmp_path / "guide.md"
    source.write_text("# Guide\nOriginal\n")
    store = InMemoryDocumentStore()
    original = prepare_markdown(tmp_path, entry())
    store.commit_batch((original,))
    for meta, text in [
        (entry(title="New title"), original.text),
        (entry(access_class="PUBLIC"), original.text),
        (entry(), "# Changed\n"),
    ]:
        source.write_text(text)
        with pytest.raises(IngestionError) as exc:
            store.commit_batch((prepare_markdown(tmp_path, meta),))
        assert exc.value.reason == IngestionFailure.VERSION_CONFLICT
        assert store.get("guide", "1") == original
    revised = prepare_markdown(tmp_path, entry(version="2"))
    assert store.commit_batch((revised,))[0].status == IngestionStatus.CREATED
    assert store.get("guide", "1") == original
    assert store.get("guide", "2") == revised


def test_line_ending_changes_are_content_conflicts(tmp_path: Path) -> None:
    source = tmp_path / "guide.md"
    source.write_bytes(b"# Guide\nBody\n")
    first = prepare_markdown(tmp_path, entry())
    source.write_bytes(b"# Guide\r\nBody\r\n")
    second = prepare_markdown(tmp_path, entry())
    assert first.content_hash != second.content_hash
    assert first.metadata_hash == second.metadata_hash


@pytest.mark.parametrize(
    "raw,reason",
    [
        (b"", IngestionFailure.EMPTY_SOURCE),
        (b" \n\t", IngestionFailure.EMPTY_SOURCE),
        (b"\xff", IngestionFailure.INVALID_ENCODING),
    ],
)
def test_invalid_sources_return_typed_failures(
    tmp_path: Path, raw: bytes, reason: IngestionFailure
) -> None:
    (tmp_path / "guide.md").write_bytes(raw)
    with pytest.raises(IngestionError) as exc:
        prepare_markdown(tmp_path, entry())
    assert exc.value.reason == reason
    assert str(exc.value) == reason.value


def test_missing_and_unsupported_sources(tmp_path: Path) -> None:
    with pytest.raises(IngestionError) as exc:
        prepare_markdown(tmp_path, entry())
    assert exc.value.reason == IngestionFailure.READ_FAILED
    (tmp_path / "guide.pdf").write_bytes(b"pdf")
    with pytest.raises(IngestionError) as exc:
        prepare_markdown(tmp_path, entry(source_path="guide.pdf"))
    assert exc.value.reason == IngestionFailure.INVALID_PATH


def test_symlink_outside_root_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("private")
    (root / "guide.md").symlink_to(outside)
    with pytest.raises(IngestionError) as exc:
        prepare_markdown(root, entry())
    assert exc.value.reason == IngestionFailure.INVALID_PATH


@pytest.mark.parametrize(
    "entries",
    [
        [entry(), entry()],
        [entry(), entry(document_id="other")],
        [entry(status="superseded", superseded_by="missing")],
        [
            entry(status="superseded", superseded_by="other"),
            entry(
                document_id="other",
                source_path="other.md",
                status="superseded",
                superseded_by="guide",
            ),
        ],
    ],
)
def test_invalid_registry_references_are_rejected(
    tmp_path: Path, entries: list[DocumentMetadata]
) -> None:
    with pytest.raises(IngestionError) as exc:
        load_manifest(manifest(tmp_path, entries))
    assert exc.value.reason == IngestionFailure.INVALID_MANIFEST


@pytest.mark.parametrize("raw", [b"not json", b"{}", b"[{}]", b"\xff"])
def test_malformed_manifest_is_rejected(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(raw)
    with pytest.raises(IngestionError) as exc:
        load_manifest(path)
    assert exc.value.reason == IngestionFailure.INVALID_MANIFEST


def test_batch_conflict_or_read_failure_leaves_store_unchanged(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text("original")
    store = InMemoryDocumentStore()
    original = prepare_markdown(tmp_path, entry())
    store.commit_batch((original,))
    (tmp_path / "other.md").write_text("other")
    other = entry(document_id="other", source_path="other.md")
    (tmp_path / "guide.md").write_text("changed")
    path = manifest(tmp_path, [other, entry()])
    with pytest.raises(IngestionError):
        ingest_manifest(tmp_path, path, store)
    assert store.get("other", "1") is None
    assert store.get("guide", "1") == original
    (tmp_path / "guide.md").unlink()
    with pytest.raises(IngestionError):
        ingest_manifest(tmp_path, path, store)
    assert store.get("other", "1") is None
    assert store.get("guide", "1") == original


def test_missing_manifest_has_typed_read_failure(tmp_path: Path) -> None:
    with pytest.raises(IngestionError) as exc:
        load_manifest(tmp_path / "missing.json")
    assert exc.value.reason == IngestionFailure.READ_FAILED


def test_section_locations_follow_commonmark_lines_with_unicode_separator(
    tmp_path: Path,
) -> None:
    text = "Preamble\u2028still same line\r\n# Title\r\ntext\r\n"
    (tmp_path / "guide.md").write_bytes(text.encode())
    doc = prepare_markdown(tmp_path, entry())
    loc = doc.sections[1].location.location
    assert loc.kind == "markdown"
    assert (loc.line_start, loc.line_end) == (2, 3)
    assert doc.sections[0].text == "Preamble\u2028still same line\r\n"


def test_metadata_hash_uses_canonical_validated_values(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text("text")
    first = prepare_markdown(tmp_path, entry(title=" Guide "))
    second = prepare_markdown(tmp_path, entry())
    assert first.metadata_hash == second.metadata_hash
    assert first == second
    assert type(first).model_validate_json(first.model_dump_json()) == first
