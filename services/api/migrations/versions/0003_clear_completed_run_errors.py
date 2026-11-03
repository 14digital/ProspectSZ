"""Clear stale errors from successfully retried discovery runs.

Revision ID: 0003_clear_completed_run_errors
Revises: 0002_location_service_type_text
"""
from alembic import op

revision="0003_clear_completed_run_errors"
down_revision="0002_location_service_type_text"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("UPDATE discovery_runs SET error = NULL WHERE state = 'SUCCEEDED'")
    op.execute("UPDATE discovery_runs SET state = 'AWAITING_UPLOAD' WHERE state = 'QUEUED' AND NOT EXISTS (SELECT 1 FROM source_imports WHERE source_imports.discovery_run_id = discovery_runs.id)")

def downgrade():
    pass
