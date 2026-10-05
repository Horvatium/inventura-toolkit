"""API request and response models.

Decimals are sent as JSON strings (e.g. "12.500"), so no precision is lost to floats.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from inventura.core.counting import DocumentStatus
from inventura.core.stock import RowError
from inventura.core.variance import VarianceSummary
from inventura.db.models import CountItem
from inventura.services.counting import SheetImportSummary
from inventura.services.dashboard import Dashboard, TopVariance
from inventura.services.documents import DocumentProgress
from inventura.services.snapshots import SnapshotSummary
from inventura.services.variances import DocumentVariances, ItemVariance, RoundResult


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
    najdeno: bool

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
            najdeno=item.najdeno,
        )


class DocumentDetail(DocumentOut):
    postavke: list[ItemOut]


class CountIn(BaseModel):
    """A counted quantity; null clears it (back to "not counted")."""

    model_config = ConfigDict(extra="forbid")

    presteta_kolicina: Decimal | None
    stevec: str | None = Field(default=None, max_length=100)


class FoundIn(BaseModel):
    """Goods found on the shelf that are not on the document."""

    model_config = ConfigDict(extra="forbid")

    lokacija: str = Field(max_length=40)
    sifra: str = Field(max_length=40)
    sarza: str | None = Field(default=None, max_length=40)
    presteta_kolicina: Decimal
    stevec: str | None = Field(default=None, max_length=100)


class CountSheetImportOut(BaseModel):
    posodobljeno: int
    prepisano: int
    najdeno: int
    brez_kolicine: int

    @classmethod
    def of(cls, summary: SheetImportSummary) -> "CountSheetImportOut":
        return cls(
            posodobljeno=summary.updated,
            prepisano=summary.overwritten,
            najdeno=summary.found,
            brez_kolicine=summary.without_quantity,
        )


class VarianceItemOut(BaseModel):
    id: int
    sifra: str
    opis: str
    merska_enota: str
    lokacija: str
    sarza: str | None
    krog: int
    najdeno: bool
    knjizena_kolicina: Decimal
    presteta_kolicina: Decimal | None
    cena_na_enoto: Decimal
    razlika_kolicina: Decimal | None
    razlika_vrednost: Decimal | None
    odstopanje_odstotek: Decimal | None  # None when not counted or the book quantity is 0
    ponovno_stetje: bool

    @classmethod
    def of(cls, entry: ItemVariance) -> "VarianceItemOut":
        item, variance = entry.item, entry.variance
        return cls(
            id=item.id,
            sifra=item.material.sifra,
            opis=item.material.opis,
            merska_enota=item.material.merska_enota,
            lokacija=item.lokacija,
            sarza=item.sarza,
            krog=item.krog,
            najdeno=item.najdeno,
            knjizena_kolicina=item.knjizena_kolicina,
            presteta_kolicina=item.presteta_kolicina,
            cena_na_enoto=item.cena_na_enoto,
            razlika_kolicina=variance.quantity if variance else None,
            razlika_vrednost=variance.value if variance else None,
            odstopanje_odstotek=variance.percent if variance else None,
            ponovno_stetje=bool(variance and variance.recount),
        )


class VarianceSummaryOut(BaseModel):
    postavk: int
    presteto: int
    nepresteto: int
    z_razliko: int
    za_ponovno_stetje: int
    visek: Decimal
    manjko: Decimal
    neto: Decimal
    absolutno: Decimal

    @classmethod
    def of(cls, summary: VarianceSummary) -> "VarianceSummaryOut":
        return cls(
            postavk=summary.items,
            presteto=summary.counted,
            nepresteto=summary.uncounted,
            z_razliko=summary.with_difference,
            za_ponovno_stetje=summary.recount,
            visek=summary.surplus_value,
            manjko=summary.shortage_value,
            neto=summary.net_value,
            absolutno=summary.absolute_value,
        )


class DocumentVariancesOut(DocumentOut):
    trenutni_krog: int
    povzetek: VarianceSummaryOut
    postavke: list[VarianceItemOut]

    @classmethod
    def of_variances(cls, result: DocumentVariances) -> "DocumentVariancesOut":
        return cls(
            **DocumentOut.of(result.progress).model_dump(),
            trenutni_krog=result.current_round,
            povzetek=VarianceSummaryOut.of(result.summary),
            postavke=[VarianceItemOut.of(entry) for entry in result.items],
        )


class RoundResultOut(BaseModel):
    status: DocumentStatus
    zakljuceni_krog: int
    za_ponovno_stetje: int

    @classmethod
    def of(cls, result: RoundResult) -> "RoundResultOut":
        return cls(
            status=result.status,
            zakljuceni_krog=result.finished_round,
            za_ponovno_stetje=result.recount_items,
        )


class RackDashboardOut(BaseModel):
    dokument_id: int
    zaporedna_st: int
    regal: str
    status: DocumentStatus
    postavk: int
    presteto: int
    z_razliko: int
    visek: Decimal
    manjko: Decimal
    neto: Decimal


class TopVarianceOut(BaseModel):
    dokument_id: int
    regal: str
    lokacija: str
    sifra: str
    opis: str
    merska_enota: str
    knjizena_kolicina: Decimal
    presteta_kolicina: Decimal
    razlika_kolicina: Decimal
    razlika_vrednost: Decimal


class DashboardOut(BaseModel):
    uvoz_id: int
    izvorna_datoteka: str
    uvozeno_ob: datetime
    dokumentov: int
    zakljucenih: int
    po_statusu: dict[DocumentStatus, int]
    povzetek: VarianceSummaryOut
    regali: list[RackDashboardOut]
    najvecje_razlike: list[TopVarianceOut]

    @classmethod
    def of(cls, dashboard: Dashboard) -> "DashboardOut":
        return cls(
            uvoz_id=dashboard.snapshot.id,
            izvorna_datoteka=dashboard.snapshot.izvorna_datoteka,
            uvozeno_ob=dashboard.snapshot.uvozeno_ob,
            dokumentov=dashboard.documents,
            zakljucenih=dashboard.closed,
            po_statusu=dashboard.status_counts,
            povzetek=VarianceSummaryOut.of(dashboard.totals),
            regali=[
                RackDashboardOut(
                    dokument_id=rack.progress.document.id,
                    zaporedna_st=rack.progress.document.zaporedna_st,
                    regal=rack.progress.document.regal,
                    status=rack.progress.document.status,
                    postavk=rack.progress.item_count,
                    presteto=rack.progress.counted,
                    z_razliko=rack.summary.with_difference,
                    visek=rack.summary.surplus_value,
                    manjko=rack.summary.shortage_value,
                    neto=rack.summary.net_value,
                )
                for rack in dashboard.racks
            ],
            najvecje_razlike=[_top(top) for top in dashboard.top],
        )


def _top(top: TopVariance) -> TopVarianceOut:
    item, variance = top.item, top.variance
    return TopVarianceOut(
        dokument_id=top.document_id,
        regal=top.rack,
        lokacija=item.lokacija,
        sifra=item.material.sifra,
        opis=item.material.opis,
        merska_enota=item.material.merska_enota,
        knjizena_kolicina=variance.book,
        presteta_kolicina=variance.counted,
        razlika_kolicina=variance.quantity,
        razlika_vrednost=variance.value,
    )
