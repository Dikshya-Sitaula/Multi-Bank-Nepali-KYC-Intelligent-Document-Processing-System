"""add customer_profiles table

Revision ID: 0dc8d84625fb
Revises: 64e8d6b6c07f
Create Date: 2026-11-16 13:45:42.005980

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0dc8d84625fb'
down_revision: Union[str, Sequence[str], None] = '64e8d6b6c07f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'customer_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('name_english', sa.String(length=256), nullable=True),
        sa.Column('customer_id', sa.String(length=64), nullable=True),
        sa.Column('account_number', sa.String(length=64), nullable=True),
        sa.Column('branch_name', sa.String(length=128), nullable=True),
        sa.Column('gender', sa.String(length=32), nullable=True),
        sa.Column('marital_status', sa.String(length=32), nullable=True),
        sa.Column('dob_bs', sa.String(length=32), nullable=True),
        sa.Column('nationality', sa.String(length=64), nullable=True),
        sa.Column('email', sa.String(length=128), nullable=True),
        sa.Column('mobile', sa.String(length=32), nullable=True),
        sa.Column('permanent_address', sa.Text(), nullable=True),
        sa.Column('current_address', sa.Text(), nullable=True),
        sa.Column('education', sa.String(length=64), nullable=True),
        sa.Column('verification_status', sa.String(length=32), nullable=True, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_customer_profiles_document_id_documents'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_customer_profiles')),
        sa.UniqueConstraint('document_id', name=op.f('uq_customer_profiles_document_id'))
    )


def downgrade() -> None:
    op.drop_table('customer_profiles')
