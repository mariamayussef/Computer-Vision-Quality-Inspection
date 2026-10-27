"""Initial schema, frozen from v1 table definitions."""
from alembic import op
import sqlalchemy as s
revision = '001'
down_revision = None

def upgrade():
    op.create_table('users', s.Column('id',s.String(36),primary_key=True),s.Column('username',s.String(80),unique=True,nullable=False),s.Column('password',s.Text,nullable=False),s.Column('role',s.String(16),nullable=False))
    op.create_table('sessions',s.Column('token_hash',s.String(64),primary_key=True),s.Column('user_id',s.String(36),s.ForeignKey('users.id'),nullable=False),s.Column('expires',s.String(40),nullable=False))
    op.create_table('profiles',s.Column('id',s.String(40),primary_key=True),s.Column('description',s.Text,nullable=False))
    op.create_table('model_versions',s.Column('id',s.String(80),primary_key=True),s.Column('profile_id',s.String(40),s.ForeignKey('profiles.id'),nullable=False),s.Column('config',s.JSON,nullable=False),s.Column('registered_at',s.String(40),nullable=False))
    op.create_table('inspections',s.Column('id',s.String(36),primary_key=True),s.Column('idempotency_key',s.String(160),unique=True,nullable=False),s.Column('submitted_by',s.String(36),s.ForeignKey('users.id'),nullable=False),s.Column('request_hash',s.String(64),nullable=False),s.Column('source_hash',s.String(64),nullable=False,index=True),s.Column('profile_id',s.String(40),s.ForeignKey('profiles.id'),nullable=False),s.Column('model_version',s.String(80),s.ForeignKey('model_versions.id')),s.Column('product',s.String(120),nullable=False),s.Column('batch',s.String(120),nullable=False),s.Column('capture_method',s.String(12),nullable=False),s.Column('captured_at',s.String(40)),s.Column('submitted_at',s.String(40),nullable=False,index=True),s.Column('processed_at',s.String(40)),s.Column('width',s.Integer,nullable=False),s.Column('height',s.Integer,nullable=False),s.Column('result',s.JSON,nullable=False),s.Column('review_revision',s.Integer,nullable=False),s.Column('deleted_at',s.String(40)))
    op.create_table('reviews',s.Column('id',s.String(36),primary_key=True),s.Column('inspection_id',s.String(36),s.ForeignKey('inspections.id'),nullable=False,index=True),s.Column('reviewer_id',s.String(36),s.ForeignKey('users.id'),nullable=False),s.Column('reviewer_name',s.String(80),nullable=False),s.Column('decision',s.String(24),nullable=False),s.Column('reason',s.Text,nullable=False),s.Column('created_at',s.String(40),nullable=False),s.Column('revision',s.Integer,nullable=False))
    op.create_table('audit',s.Column('id',s.String(36),primary_key=True),s.Column('actor_id',s.String(36),s.ForeignKey('users.id'),nullable=False),s.Column('action',s.String(80),nullable=False),s.Column('created_at',s.String(40),nullable=False),s.Column('payload',s.JSON,nullable=False))

def downgrade():
    for name in ['audit','reviews','inspections','model_versions','profiles','sessions','users']: op.drop_table(name)
