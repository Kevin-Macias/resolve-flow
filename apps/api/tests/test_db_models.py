from sqlalchemy import CheckConstraint

from api.db.models import Base
from api.identity.models import AuthCredential
from api.intake.models import IntakeRun
from api.knowledge.models import KnowledgeDocument
from api.support.action_models import SupportActionRun
from api.support.evidence_models import EvidenceAnalysis


def test_model_metadata_matches_reviewed_tables() -> None:
    assert KnowledgeDocument.metadata is Base.metadata
    assert IntakeRun.metadata is Base.metadata
    assert EvidenceAnalysis.metadata is Base.metadata
    assert SupportActionRun.metadata is Base.metadata
    assert AuthCredential.metadata is Base.metadata
    assert set(Base.metadata.tables) == {
        "customer_accounts",
        "users",
        "services",
        "issue_reports",
        "knowledge_documents",
        "knowledge_chunks",
        "knowledge_embeddings",
        "intake_runs",
        "intake_operations",
        "evidence_analyses",
        "support_action_runs",
        "proposal_preparations",
        "execution_operations",
        "simulated_ticket_effects",
        "auth_credentials",
        "auth_sessions",
        "auth_invitations",
        "support_account_grants",
        "auth_attempt_windows",
        "model_call_attempts",
        "request_limit_windows",
    }

    reports = Base.metadata.tables["issue_reports"]
    assert not reports.c.customer_account_id.nullable
    assert not reports.c.submitted_by_user_id.nullable
    assert reports.c.affected_service_id.nullable
    assert reports.c.status.server_default is None

    for name in ("customer_accounts", "users", "services", "issue_reports"):
        table = Base.metadata.tables[name]
        assert table.c.id.server_default is not None
        assert table.c.created_at.server_default is not None
        assert table.c.updated_at.server_default is not None
        assert table.c.updated_at.onupdate is not None


def test_foreign_keys_restrict_physical_deletion() -> None:
    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            assert foreign_key.ondelete == "RESTRICT"


def test_database_constraints_cover_status_description_and_user_type() -> None:
    reports = Base.metadata.tables["issue_reports"]
    users = Base.metadata.tables["users"]

    report_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in reports.constraints
        if isinstance(constraint, CheckConstraint)
    }
    user_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in users.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "BETWEEN 1 AND 5000" in report_checks["ck_issue_reports_description_length"]
    assert "'submitted'" in report_checks["ck_issue_reports_status"]
    assert "customer_account_id IS NULL" in user_checks["ck_users_user_type_account"]
