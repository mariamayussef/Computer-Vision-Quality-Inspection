import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, event, String, Text, ForeignKey, Integer, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now(): return datetime.now(timezone.utc).isoformat()
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
class Login(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[str] = mapped_column(String(40))
class Profile(Base):
    __tablename__ = 'profiles'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
class ModelVersion(Base):
    __tablename__ = 'model_versions'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey('profiles.id'))
    config: Mapped[dict] = mapped_column(JSON)
    registered_at: Mapped[str] = mapped_column(String(40))
class Inspection(Base):
    __tablename__ = 'inspections'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    submitted_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    request_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey('profiles.id'))
    model_version: Mapped[str | None] = mapped_column(ForeignKey('model_versions.id'), nullable=True)
    product: Mapped[str] = mapped_column(String(120))
    batch: Mapped[str] = mapped_column(String(120))
    capture_method: Mapped[str] = mapped_column(String(12))
    captured_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    submitted_at: Mapped[str] = mapped_column(String(40), index=True)
    processed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON)
    review_revision: Mapped[int] = mapped_column(Integer, default=0)
    deleted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
class Review(Base):
    __tablename__ = 'reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    inspection_id: Mapped[str] = mapped_column(ForeignKey('inspections.id'), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    reviewer_name: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer)
class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)

url = os.getenv('DATABASE_URL','sqlite:///data/inspection.db')
engine = create_engine(url, **({'connect_args':{'check_same_thread':False}} if url.startswith('sqlite') else {}))
if url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')
Session = sessionmaker(engine, expire_on_commit=False)
