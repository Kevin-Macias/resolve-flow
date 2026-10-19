"""Persist approved operations and independent simulated effect receipts."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE execution_operations (
            idempotency_key UUID NOT NULL,
            run_id UUID NOT NULL,
            fingerprint TEXT NOT NULL,
            proposal JSONB NOT NULL,
            approval JSONB NOT NULL,
            result JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_execution_operations PRIMARY KEY (idempotency_key),
            CONSTRAINT uq_execution_operations_run_id UNIQUE (run_id),
            CONSTRAINT fk_execution_operations_run_id_support_action_runs
                FOREIGN KEY (run_id) REFERENCES support_action_runs(run_id) ON DELETE RESTRICT,
            CONSTRAINT ck_execution_operations_fingerprint CHECK (fingerprint ~ '^[0-9a-f]{64}$')
        )
    """)
    op.execute("""
        CREATE TABLE simulated_ticket_effects (
            idempotency_key UUID NOT NULL,
            fingerprint TEXT NOT NULL,
            ticket_id UUID NOT NULL,
            result JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_simulated_ticket_effects PRIMARY KEY (idempotency_key),
            CONSTRAINT uq_simulated_ticket_effects_ticket_id UNIQUE (ticket_id),
            CONSTRAINT ck_simulated_ticket_effects_fingerprint CHECK (fingerprint ~ '^[0-9a-f]{64}$')
        )
    """)


def downgrade() -> None:
    op.drop_table("simulated_ticket_effects")
    op.drop_table("execution_operations")
