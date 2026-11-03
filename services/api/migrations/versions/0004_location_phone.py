"""Store public CQC location phone numbers.

Revision ID: 0004_location_phone
Revises: 0003_clear_completed_run_errors
"""
from alembic import op
import sqlalchemy as sa

revision="0004_location_phone"
down_revision="0003_clear_completed_run_errors"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("company_locations",sa.Column("phone",sa.String(length=50),nullable=True))
    op.execute("""UPDATE company_locations AS location
        SET phone = COALESCE(record.payload->>'Phone number', record.payload->>'Phone', record.payload->>'Telephone')
        FROM source_records AS record
        WHERE record.external_key = location.cqc_location_id""")

def downgrade():
    op.drop_column("company_locations","phone")
