"""Database schema.

Quantities are Numeric(14,3) and money Numeric(14,2); nothing is stored as float.
Locations are stored as written (lokacija, for display) and parsed (regal, nivo, polozaj),
so uniqueness and sorting use the parsed values: K2-03-11 and K2-3-11 are one location.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from inventura.core.counting import DocumentStatus

Quantity = Numeric(14, 3)
Money = Numeric(14, 2)
Code = String(40)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Material(Base):
    """Master data; description, unit and price follow the latest import."""

    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    sifra: Mapped[str] = mapped_column(Code, unique=True)
    opis: Mapped[str] = mapped_column(String(200))
    merska_enota: Mapped[str] = mapped_column(Code)
    cena_na_enoto: Mapped[Decimal] = mapped_column(Money)

    __table_args__ = (CheckConstraint("cena_na_enoto >= 0", name="cena_not_negative"),)


class StockSnapshot(Base):
    """One imported stock export."""

    __tablename__ = "stock_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    uvozeno_ob: Mapped[datetime] = _now()
    izvorna_datoteka: Mapped[str] = mapped_column(String(255))
    stevilo_vrstic: Mapped[int]

    items: Mapped[list["StockItem"]] = relationship(back_populates="snapshot")
    documents: Mapped[list["CountDocument"]] = relationship(back_populates="snapshot")


class StockItem(Base):
    """Book stock of a material at a location (and batch) as imported."""

    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("stock_snapshots.id", ondelete="CASCADE"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    lokacija: Mapped[str] = mapped_column(Code)
    regal: Mapped[str] = mapped_column(Code)
    nivo: Mapped[int]
    polozaj: Mapped[int]
    sarza: Mapped[str | None] = mapped_column(Code)
    kolicina: Mapped[Decimal] = mapped_column(Quantity)
    cena_na_enoto: Mapped[Decimal] = mapped_column(Money)
    vrstica: Mapped[int]  # row in the source file, for tracing back

    snapshot: Mapped[StockSnapshot] = relationship(back_populates="items")
    material: Mapped[Material] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "material_id",
            "regal",
            "nivo",
            "polozaj",
            "sarza",
            name="uq_stock_items_position",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("kolicina >= 0", name="kolicina_not_negative"),
        CheckConstraint("cena_na_enoto >= 0", name="cena_not_negative"),
    )


class CountDocument(Base):
    """A count document: all items of one rack in one stock snapshot."""

    __tablename__ = "count_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("stock_snapshots.id", ondelete="CASCADE"))
    regal: Mapped[str] = mapped_column(Code)
    zaporedna_st: Mapped[int]  # position in natural rack order, 1-based
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=DocumentStatus.ODPRT,
    )
    ustvarjen_ob: Mapped[datetime] = _now()
    zakljucen_ob: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    snapshot: Mapped[StockSnapshot] = relationship(back_populates="documents")
    items: Mapped[list["CountItem"]] = relationship(back_populates="document")

    __table_args__ = (
        UniqueConstraint("snapshot_id", "regal", name="uq_count_documents_rack"),
        UniqueConstraint("snapshot_id", "zaporedna_st", name="uq_count_documents_number"),
    )


class CountItem(Base):
    """One line to count in one round.

    Book quantity and unit price are frozen when the document is created, so a later
    import does not change a count in progress. presteta_kolicina NULL means not counted
    yet, 0 means counted and nothing found. Every count round is a new row (krog 1, 2, ...);
    variances are computed from the latest round and never stored.
    """

    __tablename__ = "count_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("count_documents.id", ondelete="CASCADE"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    lokacija: Mapped[str] = mapped_column(Code)
    nivo: Mapped[int]
    polozaj: Mapped[int]
    sarza: Mapped[str | None] = mapped_column(Code)
    knjizena_kolicina: Mapped[Decimal] = mapped_column(Quantity)
    cena_na_enoto: Mapped[Decimal] = mapped_column(Money)
    presteta_kolicina: Mapped[Decimal | None] = mapped_column(Quantity)
    stevec: Mapped[str | None] = mapped_column(String(100))
    presteto_ob: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    krog: Mapped[int] = mapped_column(default=1)
    # Found goods: added during the count, not in the book (knjizena_kolicina is 0).
    najdeno: Mapped[bool] = mapped_column(default=False, server_default=false())

    document: Mapped[CountDocument] = relationship(back_populates="items")
    material: Mapped[Material] = relationship()

    __table_args__ = (
        # The rack is the document's, so the location is (nivo, polozaj) within it.
        UniqueConstraint(
            "document_id",
            "material_id",
            "nivo",
            "polozaj",
            "sarza",
            "krog",
            name="uq_count_items_position_round",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("knjizena_kolicina >= 0", name="knjizena_not_negative"),
        CheckConstraint("presteta_kolicina >= 0", name="presteta_not_negative"),
        CheckConstraint("cena_na_enoto >= 0", name="cena_not_negative"),
        CheckConstraint("krog >= 1", name="krog_positive"),
        CheckConstraint("NOT najdeno OR knjizena_kolicina = 0", name="najdeno_not_in_book"),
        Index("ix_count_items_document_order", "document_id", "nivo", "polozaj"),
    )
