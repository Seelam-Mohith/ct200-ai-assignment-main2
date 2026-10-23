from datetime import datetime
from sqlalchemy import create_engine, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

engine = create_engine("sqlite:///ct200.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)

class Version(Base):
    __tablename__ = "versions"
    __table_args__ = (UniqueConstraint("document_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String, default="")
    created: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class Node(Base):
    """One row per node PER VERSION. Rows are never updated after ingest, so a
    node id always resolves to the exact text it had (this is the version pin).
    logical_id ties together 'the same section' across versions."""
    __tablename__ = "nodes"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("versions.id"), index=True)
    logical_id: Mapped[str] = mapped_column(String, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True)
    number: Mapped[str]
    heading: Mapped[str]
    level: Mapped[int]
    path: Mapped[str]
    page: Mapped[int]
    body: Mapped[str] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(String)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    match_method: Mapped[str] = mapped_column(String, default="new")  # new|path|fuzzy

def init_db(): Base.metadata.create_all(engine)
