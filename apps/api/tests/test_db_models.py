from sqlalchemy import CheckConstraint

from api.db.models import Base
from api.knowledge.models import KnowledgeDocument


def test_model_metadata_matches_reviewed_tables() -> None:
    assert KnowledgeDocument.metadata is Base.metadata
    assert set(Base.metadata.tables) == {
        "customer_accounts",
        "users",
        "services",
        "issue_reports",
        "knowledge_documents",
        "knowledge_chunks",
        "knowledge_embeddings",
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
