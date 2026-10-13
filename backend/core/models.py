"""ORM models for the essay corpus.

Design notes that are not obvious from the column names:

**`date` is text, not a DATE.** Paul Graham's essays carry month-precision dates
("September 2024", "1993", or nothing at all). Parsing that into a real DATE
would invent a day that does not exist and would lose the exact string the UI
renders. So the original text is kept verbatim and `date_year`/`date_month` are
derived purely for ordering. This mirrors `dateKey()` in the frontend.

**Paragraphs and footnotes are rows, not JSONB.** Phase 5 chunks need to cite a
specific paragraph, and a citation that cannot be resolved back to a paragraph
is not a citation. Storing them as rows keeps that lookup natural and keeps the
corpus queryable.

**`content_hash` on every ingested entity.** Ingest is idempotent: re-running it
after re-scraping one essay must not rewrite 233 rows or re-embed the corpus. The
hash lets unchanged content be skipped. This is the same trick the TypeScript
pipeline used for its LLM caches.
"""

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for every table.

    Alembic autogenerate and `alembic/env.py` both resolve metadata through this
    one object, which is why migrations cannot drift from the ORM.
    """


class Essay(Base):
    """One essay. `slug` is the natural key and matches the source filename."""

    __tablename__ = "essays"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # Verbatim source value, e.g. "September 2024" or None. Never parsed back.
    date: Mapped[str | None] = mapped_column(Text)
    date_year: Mapped[int | None] = mapped_column(Integer, index=True)
    date_month: Mapped[int | None] = mapped_column(Integer)

    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reading_time_min: Mapped[int] = mapped_column(Integer, nullable=False)

    # sha256 of the canonical body; drives idempotent ingest.
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 of title+date+url, so metadata-only edits are also detected.
    meta_hash: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    paragraphs: Mapped[list[EssayParagraph]] = relationship(
        back_populates="essay", cascade="all, delete-orphan", order_by="EssayParagraph.position"
    )
    footnotes: Mapped[list[EssayFootnote]] = relationship(
        back_populates="essay", cascade="all, delete-orphan", order_by="EssayFootnote.position"
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="essay", cascade="all, delete-orphan", order_by="Chunk.position"
    )

    def __repr__(self) -> str:
        return f"<Essay {self.slug}>"


class EssayParagraph(Base):
    """A paragraph. `position` is what citations point at."""

    __tablename__ = "essay_paragraphs"
    __table_args__ = (
        UniqueConstraint("slug", "position", name="uq_paragraph_slug_position"),
        Index("ix_paragraphs_slug_position", "slug", "position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(
        Text, ForeignKey("essays.slug", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    essay: Mapped[Essay] = relationship(back_populates="paragraphs")


class EssayFootnote(Base):
    """A footnote, addressed by the `[n]` marker left in the paragraph text."""

    __tablename__ = "essay_footnotes"
    __table_args__ = (
        UniqueConstraint("slug", "marker", name="uq_footnote_slug_marker"),
        Index("ix_footnotes_slug_position", "slug", "position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(
        Text, ForeignKey("essays.slug", ondelete="CASCADE"), nullable=False
    )
    marker: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    essay: Mapped[Essay] = relationship(back_populates="footnotes")


class GenerationMeta(Base):
    """Where each derived artefact came from.

    One row per artefact rather than a column on each table, because the values
    are file-level, not row-level: `data/phases.json` has one model and one
    timestamp covering all 233 essays.

    This exists so the snapshot can report real provenance instead of null. It
    matters for two reasons: the README should be able to say which model
    produced the reading paths, and a cache key that includes the model needs
    the model recorded somewhere durable.
    """

    __tablename__ = "generation_meta"

    # 'taxonomy' | 'phases' | 'paths'
    artifact: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int | None] = mapped_column(Integer)
    generated: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)


class Phase(Base):
    """A startup stage from the taxonomy. Referenced by `essay_phases`."""

    __tablename__ = "phases"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class EssayPhase(Base):
    """Essay → phase assignment. `rank` preserves the model's ordering.

    The reader's filter chips key off rank 0, so the order the LLM returned is
    meaningful and must not be flattened.
    """

    __tablename__ = "essay_phases"
    __table_args__ = (
        UniqueConstraint("slug", "phase_id", name="uq_essay_phase"),
        Index("ix_essay_phases_phase_id", "phase_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(
        Text, ForeignKey("essays.slug", ondelete="CASCADE"), nullable=False
    )
    phase_id: Mapped[str] = mapped_column(Text, ForeignKey("phases.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(Text)


class ReadingPath(Base):
    """An ordered reading path produced by the curator."""

    __tablename__ = "reading_paths"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    hash: Mapped[str | None] = mapped_column(Text)

    steps: Mapped[list[PathStep]] = relationship(
        back_populates="path", cascade="all, delete-orphan", order_by="PathStep.position"
    )

    def __repr__(self) -> str:
        return f"<ReadingPath {self.id}>"


class PathStep(Base):
    """One step of a reading path. `slug` is not a FK on purpose.

    A path may reference an essay that is missing from the corpus; the frontend
    already filters those out rather than failing. A hard FK would make an
    unrelated deletion break path generation.
    """

    __tablename__ = "path_steps"
    __table_args__ = (
        UniqueConstraint("path_id", "position", name="uq_path_step_position"),
        Index("ix_path_steps_slug", "slug"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    path_id: Mapped[str] = mapped_column(
        Text, ForeignKey("reading_paths.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    path: Mapped[ReadingPath] = relationship(back_populates="steps")


class Chunk(Base):
    """One retrieval unit: a few adjacent paragraphs, embedded and full-text indexed.

    Paragraphs are grouped rather than split per paragraph so a chunk can carry
    enough context to be worth retrieving, but `start_paragraph`/`end_paragraph`
    keep the link back to the source. A citation resolves to those paragraph
    positions, which is why the range is stored and not just the text.

    Three derived columns are deliberate:

    - `embedding` — pgvector, cosine distance. `Vector(384)` matches
      `settings.embedding_model`; changing the model means a migration.
    - `tsv` — a *generated* column, so the lexical index cannot drift from
      `text`. Nothing in Python has to remember to update it.
    - `content_hash` — sha256 of `text`, so `index` re-embeds only chunks whose
      text changed. Embedding is the expensive step.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("slug", "position", name="uq_chunk_slug_position"),
        Index("ix_chunks_slug_position", "slug", "position"),
        # Lexical arm of hybrid search.
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        # Vector arm. HNSW is the right default for a read-mostly corpus of this
        # size: recall comparable to IVFFlat without a training step, and no
        # rebuild when rows are added.
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(
        Text, ForeignKey("essays.slug", ondelete="CASCADE"), nullable=False
    )
    # Chunk ordinal within the essay. Stable only while the essay text is.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    start_paragraph: Mapped[int] = mapped_column(Integer, nullable=False)
    end_paragraph: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # `Any` rather than `list[float]`: pgvector's TypeDecorator is what turns the
    # Python list into a `vector` literal, and mypy cannot see through it.
    embedding: Mapped[Any | None] = mapped_column(Vector(384))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
        nullable=False,
    )

    essay: Mapped[Essay] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return f"<Chunk {self.slug}#{self.position}>"


class IngestRun(Base):
    """Audit row for each ingest. Makes `was this corpus ever loaded?` answerable."""

    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    essays_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    essays_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    essays_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


__all__ = [
    "Base",
    "Chunk",
    "Essay",
    "EssayFootnote",
    "EssayParagraph",
    "EssayPhase",
    "GenerationMeta",
    "IngestRun",
    "PathStep",
    "Phase",
    "ReadingPath",
]
