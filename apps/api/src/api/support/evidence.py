"""Authorized, durable preliminary analysis, independent of intake execution."""

import hashlib
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.db.models import IssueReport, Service
from api.intake.locks import IntakeLocks
from api.intake.models import IntakeRun
from api.intake.schemas import CustomerRun, CustomerTurn
from api.knowledge.citations import CitationReport, verify_evidence_catalog
from api.knowledge.evidence_analysis import (
    EvidenceAnalysisOutput,
    validate_evidence_analysis_output,
)
from api.knowledge.markdown import MarkdownDocument
from api.knowledge.metadata import AccessClass, DocumentStatus, KnowledgeContract
from api.knowledge.retrieval import (
    DocumentRevision,
    RetrievalRequest,
    RetrievalResult,
    RetrievalScope,
)
from api.support.access import allowed_accounts
from api.support.evidence_models import EvidenceAnalysis
from api.support.evidence_runtime import EvidenceRuntime
from api.support.evidence_schemas import EvidencePassage, SupportEvidence


class AnalysisInput(KnowledgeContract):
    description: str
    service_code: str | None
    intake_id: UUID | None
    intake_revision: int | None = Field(ge=1)
    turns: tuple[CustomerTurn, ...]
    operation_pending: bool

    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def query(self) -> str:
        return self.description + "".join(
            f"\nQuestion: {question}\nAnswer: {answer}"
            for turn in self.turns
            for question, answer in zip(turn.questions, turn.answers, strict=True)
        )


class SavedEvidence(KnowledgeContract):
    request: RetrievalRequest
    result: RetrievalResult
    sources: tuple[MarkdownDocument, ...]
    report: CitationReport


class SupportEvidenceService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], database_url: str):
        self.sessions = sessions
        # Shares the intake report lock so accepted turns cannot change mid-analysis.
        self.locks = IntakeLocks(database_url)
        self.runtime = EvidenceRuntime(sessions)

    async def inputs(self, token: str, report_id: UUID) -> tuple[UUID, AnalysisInput]:
        async with self.sessions() as session:
            accounts = await allowed_accounts(token, session)
            report = await session.scalar(
                select(IssueReport).where(
                    IssueReport.id == report_id,
                    IssueReport.customer_account_id.in_(accounts),
                )
            )
            if report is None:
                raise HTTPException(404, "Report unavailable")
            service = (
                await session.get(Service, report.affected_service_id)
                if report.affected_service_id
                else None
            )
            run = await session.scalar(
                select(IntakeRun).where(IntakeRun.report_id == report_id)
            )
            view = (
                CustomerRun.model_validate_json(json.dumps(run.public_view))
                if run is not None
                else None
            )
            if run is not None and (
                run.customer_account_id != report.customer_account_id
                or view is None
                or view.report_id != report_id
                or view.run_id != run.id
                or view.revision != run.revision
            ):
                raise ValueError("Inconsistent intake binding")
            return report.customer_account_id, AnalysisInput(
                description=report.description,
                service_code=service.code if service else None,
                intake_id=run.id if run else None,
                intake_revision=run.revision if run else None,
                turns=view.turns if view else (),
                operation_pending=bool(run and run.pending_operation_id is not None),
            )

    async def get(
        self, token: str, report_id: UUID, analysis_id: UUID | None = None
    ) -> SupportEvidence:
        owner, _ = await self.inputs(token, report_id)
        async with self.sessions() as session:
            statement = select(EvidenceAnalysis).where(
                EvidenceAnalysis.report_id == report_id
            )
            if analysis_id is not None:
                statement = statement.where(EvidenceAnalysis.id == analysis_id)
            row = await session.scalar(
                statement.order_by(
                    EvidenceAnalysis.created_at.desc(), EvidenceAnalysis.id.desc()
                ).limit(1)
            )
        if row is None:
            if analysis_id is not None:
                raise ValueError("Missing saved analysis")
            return SupportEvidence(
                report_id=report_id,
                analysis_id=None,
                operation_id=None,
                status="absent",
                created_at=None,
                provider_mode=None,
                simulated=False,
                input_revision=None,
                older_input=False,
                passages=(),
                report=CitationReport(),
            )
        original = AnalysisInput.model_validate(row.input_record)
        if row.customer_account_id != owner or original.fingerprint() != row.input_hash:
            raise ValueError("Inconsistent saved binding")
        mode: Literal["offline", "live"]
        if row.provider_mode not in ("offline", "live") or row.status not in (
            "pending",
            "ready",
            "failed",
        ):
            raise ValueError("Invalid saved state")
        mode = "offline" if row.provider_mode == "offline" else "live"
        passages: tuple[EvidencePassage, ...] = ()
        report = CitationReport()
        if row.status == "ready":
            saved = SavedEvidence.model_validate(row.result_record)
            scope = RetrievalScope(
                allow_internal=True, customer_account_ids=frozenset({owner})
            )
            if (
                saved.request.scope != scope
                or saved.request.service_code != original.service_code
                or saved.request.query != original.query().strip()
            ):
                raise ValueError("Inconsistent saved scope")
            catalog = verify_evidence_catalog(
                saved.request, saved.result, saved.sources
            )
            # Reassemble claims to reject altered quotations or claim/catalog bindings.
            report = validate_evidence_analysis_output(
                EvidenceAnalysisOutput(
                    claims=tuple(claim.draft for claim in saved.report.claims)
                ).model_dump_json(),
                saved.request,
                saved.result,
                saved.sources,
            )
            if report != saved.report:
                raise ValueError("Invalid saved citation report")
            current_sources = {
                source.metadata.document_id: source.metadata
                for source in await self.runtime.sources()
            }
            items: list[EvidencePassage] = []
            for citation, ranked in zip(catalog, saved.result.evidence, strict=True):
                meta = current_sources.get(citation.metadata.document_id)
                if meta is None or (
                    meta.access_class == AccessClass.CUSTOMER_ACCOUNT
                    and meta.customer_account_id != owner
                ):
                    raise HTTPException(404, "Evidence unavailable")
                items.append(
                    EvidencePassage(
                        citation=citation,
                        rank=ranked.rank,
                        score=ranked.score,
                        score_metric=ranked.score_metric,
                        historical=meta.version != citation.metadata.version
                        or meta.status != DocumentStatus.CURRENT,
                    )
                )
            passages = tuple(items)
        elif row.result_record is not None:
            raise ValueError("Unfinished analysis contains result data")
        final_owner, final_input = await self.inputs(token, report_id)
        if final_owner != owner:
            raise ValueError("Report ownership changed")
        return SupportEvidence(
            report_id=report_id,
            analysis_id=row.id,
            operation_id=row.operation_id,
            status=row.status,
            created_at=row.created_at,
            provider_mode=mode,
            simulated=mode == "offline",
            input_revision=original.intake_revision,
            older_input=original.fingerprint() != final_input.fingerprint(),
            passages=passages,
            report=report,
        )

    async def create(
        self, token: str, report_id: UUID, operation_id: UUID
    ) -> SupportEvidence:
        await self.inputs(token, report_id)
        async with self.locks.hold(report_id):
            owner, inputs = await self.inputs(token, report_id)
            async with self.sessions() as session:
                existing = await session.scalar(
                    select(EvidenceAnalysis).where(
                        EvidenceAnalysis.report_id == report_id,
                        EvidenceAnalysis.operation_id == operation_id,
                    )
                )
                if existing is not None:
                    return await self.get(token, report_id, existing.id)
                pending = await session.scalar(
                    select(EvidenceAnalysis.id).where(
                        EvidenceAnalysis.report_id == report_id,
                        EvidenceAnalysis.status == "pending",
                    )
                )
                if pending is not None or inputs.operation_pending:
                    raise HTTPException(
                        409, "An operation needs review before another analysis"
                    )
                mode = self.runtime.mode()
                row = EvidenceAnalysis(
                    id=uuid4(),
                    report_id=report_id,
                    customer_account_id=owner,
                    operation_id=operation_id,
                    status="pending",
                    provider_mode=mode,
                    input_hash=inputs.fingerprint(),
                    input_record=inputs.model_dump(mode="json"),
                )
                session.add(row)
                await session.commit()
            try:
                sources = await self.runtime.sources()
                request = RetrievalRequest(
                    query=inputs.query(),
                    scope=RetrievalScope(
                        allow_internal=True, customer_account_ids=frozenset({owner})
                    ),
                    active_revisions=tuple(
                        DocumentRevision(
                            document_id=s.metadata.document_id,
                            version=s.metadata.version,
                        )
                        for s in sources
                    ),
                    service_code=inputs.service_code,
                )
                result, report = await self.runtime.generate(request, sources, mode)
                verify_evidence_catalog(request, result, sources)
                saved = SavedEvidence(
                    request=request,
                    result=result,
                    sources=tuple(
                        source
                        for source in sources
                        if any(
                            item.metadata.document_id == source.metadata.document_id
                            and item.metadata.version == source.metadata.version
                            for item in result.evidence
                        )
                    ),
                    report=report,
                )
                final_owner, final_inputs = await self.inputs(token, report_id)
                if final_owner != owner or final_inputs != inputs:
                    raise HTTPException(409, "Report observations changed")
                # Validate current source access before publishing; GET repeats checks.
                latest = {
                    s.metadata.document_id: s.metadata
                    for s in await self.runtime.sources()
                }
                if any(
                    latest.get(item.metadata.document_id) != item.metadata
                    for item in result.evidence
                ):
                    raise ValueError("Source policy changed")
                async with self.sessions() as session:
                    persisted = await session.get(EvidenceAnalysis, row.id)
                    if persisted is None:
                        raise ValueError("Missing operation")
                    persisted.result_record = saved.model_dump(mode="json")
                    persisted.status = "ready"
                    await session.commit()
            except Exception:
                # Cancellation/process loss deliberately leaves durable pending state.
                async with self.sessions() as session:
                    persisted = await session.get(EvidenceAnalysis, row.id)
                    if persisted is not None:
                        persisted.status = "failed"
                        persisted.result_record = None
                        await session.commit()
                raise
            return await self.get(token, report_id, row.id)
