"""Allow complete CQC service type lists.

Revision ID: 0002_location_service_type_text
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision="0002_location_service_type_text"
down_revision="0001_initial"
branch_labels=None
depends_on=None

def upgrade():
    op.alter_column("company_locations","service_type",existing_type=sa.String(length=200),type_=sa.Text(),existing_nullable=True)

def downgrade():
    op.alter_column("company_locations","service_type",existing_type=sa.Text(),type_=sa.String(length=200),existing_nullable=True)
