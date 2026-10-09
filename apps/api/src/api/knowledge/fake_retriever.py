"""Offline fixture ranking; this adapter performs no semantic search."""

from api.knowledge.retrieval import (
    EvidenceCandidate,
    RankedEvidence,
    RetrievalError,
    RetrievalFailure,
    RetrievalRequest,
    RetrievalResult,
    is_eligible,
)


class FakeRetriever:
    def __init__(
        self,
        candidates: tuple[EvidenceCandidate, ...] = (),
        *,
        failure: RetrievalFailure | None = None,
    ) -> None:
        self._candidates = tuple(
            EvidenceCandidate.model_validate(candidate) for candidate in candidates
        )
        identities = [candidate.chunk_id for candidate in self._candidates]
        if len(identities) != len(set(identities)):
            raise ValueError("Fake candidate chunk identities must be unique")
        if any(candidate.score_metric != "fixture" for candidate in self._candidates):
            raise ValueError("Fake candidates must explicitly use fixture scores")
        self._failure = failure

    async def search(self, request: RetrievalRequest) -> RetrievalResult:
        request = RetrievalRequest.model_validate(request)
        if self._failure is not None:
            raise RetrievalError(self._failure)
        eligible = [
            candidate
            for candidate in self._candidates
            if is_eligible(candidate.metadata, request)
        ]
        ordered = sorted(eligible, key=lambda item: (-item.score, str(item.chunk_id)))
        return RetrievalResult(
            evidence=tuple(
                RankedEvidence.model_validate(candidate.model_dump() | {"rank": rank})
                for rank, candidate in enumerate(ordered[: request.top_k], start=1)
            )
        )
