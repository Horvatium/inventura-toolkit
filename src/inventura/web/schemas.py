"""API request and response models.

Decimals are sent as JSON strings (e.g. "12.500"), so no precision is lost to floats.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from inventura.core.counting import DocumentStatus
from inventura.core.stock import RowError
from inventura.db.models import CountItem
from inventura.services.documents import DocumentProgress
from inventura.services.snapshots import SnapshotSummary


class RowErrorOut(BaseModel):
    vrstica: int
    polje: str | None
    vrednost: str
    sporocilo: str

    @classmethod
    def of(cls, error: RowError) -> "RowErrorOut":
        return cls(
            vrstica=error.row_number,
            polje=error.field,
            vrednost=error.value,
            sporocilo=error.message,
        )


class ImportRejected(BaseModel):
    detail: str
    vrstic_z_napakami: int
    napake: list[RowErrorOut]


class SnapshotOut(BaseModel):
    id: int
    uvozeno_ob: datetime
    izvorna_datoteka: str
    stevilo_vrstic: int
    stevilo_postavk: int
    stevilo_dokumentov: int

    @classmethod
    def of(cls, summary: SnapshotSummary) -> "SnapshotOut":
        snapshot = summary.snapshot
        return cls(
            id=snapshot.id,
            uvozeno_ob=snapshot.uvozeno_ob,
            izvorna_datoteka=snapshot.izvorna_datoteka,
            stevilo_vrstic=snapshot.stevilo_vrstic,
            stevilo_postavk=summary.item_count,
            stevilo_dokumentov=summary.document_count,
        )


class DocumentOut(BaseModel):
    id: int
    snapshot_id: int
    regal: str
    zaporedna_st: int
    status: DocumentStatus
    ustvarjen_ob: datetime
    zakljucen_ob: datetime | None
    stevilo_postavk: int
    presteto: int

    @classmethod
    def of(cls, progress: DocumentProgress) -> "DocumentOut":
        document = progress.document
        return cls(
            id=document.id,
            snapshot_id=document.snapshot_id,
            regal=document.regal,
            zaporedna_st=document.zaporedna_st,
            status=document.status,
            ustvarjen_ob=document.ustvarjen_ob,
            zakljucen_ob=document.zakljucen_ob,
            stevilo_postavk=progress.item_count,
            presteto=progress.counted,
        )


class ItemOut(BaseModel):
    id: int
    sifra: str
    opis: str
    merska_enota: str
    lokacija: str
    nivo: int
    polozaj: int
    sarza: str | None
    knjizena_kolicina: Decimal
    cena_na_enoto: Decimal
    presteta_kolicina: Decimal | None
    stevec: str | None
    presteto_ob: datetime | None
    krog: int

    @classmethod
    def of(cls, item: CountItem) -> "ItemOut":
        return cls(
            id=item.id,
            sifra=item.material.sifra,
            opis=item.material.opis,
            merska_enota=item.material.merska_enota,
            lokacija=item.lokacija,
            nivo=item.nivo,
            polozaj=item.polozaj,
            sarza=item.sarza,
            knjizena_kolicina=item.knjizena_kolicina,
            cena_na_enoto=item.cena_na_enoto,
            presteta_kolicina=item.presteta_kolicina,
            stevec=item.stevec,
            presteto_ob=item.presteto_ob,
            krog=item.krog,
        )


class DocumentDetail(DocumentOut):
    postavke: list[ItemOut]


class CountIn(BaseModel):
    """A counted quantity; null clears it (back to "not counted")."""

    model_config = ConfigDict(extra="forbid")

    presteta_kolicina: Decimal | None
    stevec: str | None = Field(default=None, max_length=100)
