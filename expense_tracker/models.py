"""SQLAlchemy models for the expense tracker."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


transaction_tags = Table(
    "transaction_tags",
    Base.metadata,
    Column("transaction_id", ForeignKey("transactions.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)

tag_formula_tags = Table(
    "tag_formula_tags",
    Base.metadata,
    Column("formula_id", ForeignKey("tag_sum_formulas.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    name_he: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#6B7280")
    icon: Mapped[str] = mapped_column(String(32), nullable=False, default="tag")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="expense")

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
    rules: Mapped[list["CategorizationRule"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#6B7280")

    transactions: Mapped[list["Transaction"]] = relationship(
        secondary=transaction_tags, back_populates="tags"
    )
    formulas: Mapped[list["TagSumFormula"]] = relationship(
        secondary=tag_formula_tags, back_populates="tags"
    )


class TagSumFormula(Base):
    __tablename__ = "tag_sum_formulas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, default="global")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    tags: Mapped[list[Tag]] = relationship(
        secondary=tag_formula_tags, back_populates="formulas"
    )


class InvestmentFxConversion(Base):
    __tablename__ = "investment_fx_conversions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversion_date: Mapped[date] = mapped_column(Date, nullable=False)
    nis_amount: Mapped[float] = mapped_column(Float, nullable=False)
    usd_ils_rate: Mapped[float] = mapped_column(Float, nullable=False)
    usd_amount: Mapped[float] = mapped_column(Float, nullable=False)
    onezero_fee_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.08)
    comparison_name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="Meitav Trade"
    )
    comparison_fee_rate: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.70
    )
    saved_nis: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "txn_date",
            "reference",
            "amount",
            "description",
            "direction",
            name="uq_txn_dedup",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    custom_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reference: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    beneficiary: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    purpose: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # debit | credit
    account: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    source_filename: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="bank")
    categorized_by: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    split_group: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    category: Mapped[Optional[Category]] = relationship(back_populates="transactions")
    tags: Mapped[list[Tag]] = relationship(
        secondary=transaction_tags, back_populates="transactions"
    )


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    category: Mapped[Category] = relationship(back_populates="rules")

    @property
    def display_name(self) -> str:
        return (self.name or "").strip() or self.pattern
