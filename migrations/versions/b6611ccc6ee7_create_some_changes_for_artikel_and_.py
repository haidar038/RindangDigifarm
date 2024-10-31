"""create some changes for Artikel and Forum models

Revision ID: b6611ccc6ee7
Revises: df089da02e89
Create Date: 2024-10-30 13:50:24.740504

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'b6611ccc6ee7'
down_revision = 'df089da02e89'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('artikel', schema=None) as batch_op:
        batch_op.add_column(sa.Column('thumbnail', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('is_approved', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('is_drafted', sa.Boolean(), nullable=True))
        batch_op.alter_column('created_by',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
        batch_op.alter_column('created_at',
               existing_type=mysql.DATETIME(),
               nullable=True)

    with op.batch_alter_table('forum', schema=None) as batch_op:
        batch_op.add_column(sa.Column('question', sa.Text(), nullable=False))
        batch_op.add_column(sa.Column('answer', sa.Text(), nullable=True))
        batch_op.alter_column('replied_at',
               existing_type=mysql.DATETIME(),
               nullable=True)
        batch_op.drop_column('content')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('forum', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content', mysql.TEXT(), nullable=False))
        batch_op.alter_column('replied_at',
               existing_type=mysql.DATETIME(),
               nullable=False)
        batch_op.drop_column('answer')
        batch_op.drop_column('question')

    with op.batch_alter_table('artikel', schema=None) as batch_op:
        batch_op.alter_column('created_at',
               existing_type=mysql.DATETIME(),
               nullable=False)
        batch_op.alter_column('created_by',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
        batch_op.drop_column('is_drafted')
        batch_op.drop_column('is_approved')
        batch_op.drop_column('thumbnail')

    # ### end Alembic commands ###
