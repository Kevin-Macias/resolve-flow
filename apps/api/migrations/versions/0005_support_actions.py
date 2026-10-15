"""Bind support proposals and replayable preparation to customer intake runs."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE support_action_runs (
            run_id UUID NOT NULL,
            report_id UUID NOT NULL,
            customer_account_id UUID NOT NULL,
            proposal JSONB NOT NULL,
            input_record JSONB NOT NULL,
            input_hash TEXT NOT NULL,
            preparing BOOLEAN NOT NULL,
            operation_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_support_action_runs PRIMARY KEY (run_id),
            CONSTRAINT uq_support_action_runs_report_id UNIQUE (report_id),
            CONSTRAINT fk_support_action_runs_run_id_intake_runs FOREIGN KEY (run_id) REFERENCES intake_runs(id) ON DELETE RESTRICT,
            CONSTRAINT fk_support_action_runs_report_id_issue_reports FOREIGN KEY (report_id) REFERENCES issue_reports(id) ON DELETE RESTRICT,
            CONSTRAINT fk_support_action_runs_customer_account_id_customer_accounts FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id) ON DELETE RESTRICT,
            CONSTRAINT ck_support_action_runs_input_hash CHECK (input_hash ~ '^[0-9a-f]{64}$')
        )
    """)
    op.execute("""
        CREATE TABLE proposal_preparations (
            run_id UUID NOT NULL,
            id UUID NOT NULL,
            payload JSONB NOT NULL,
            payload_hash TEXT NOT NULL,
            proposal_fingerprint TEXT NOT NULL,
            completed BOOLEAN NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_proposal_preparations PRIMARY KEY (run_id, id),
            CONSTRAINT fk_proposal_preparations_run_id_support_action_runs FOREIGN KEY (run_id) REFERENCES support_action_runs(run_id) ON DELETE RESTRICT,
            CONSTRAINT uq_proposal_preparations_run_id UNIQUE (run_id, proposal_fingerprint),
            CONSTRAINT ck_proposal_preparations_payload_hash CHECK (payload_hash ~ '^[0-9a-f]{64}$')
        )
    """)


def downgrade() -> None:
    op.drop_table("proposal_preparations")
    op.drop_table("support_action_runs")
