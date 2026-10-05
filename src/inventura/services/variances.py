"""Variances of counted documents, finishing a count round, and the inventory report data."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from inventura.core.counting import DocumentClosedError, DocumentStatus
from inventura.core.variance import (
    Variance,
    VarianceRules,
    VarianceSummary,
    compute_variance,
    status_after_round,
    summarize,
)
from inventura.db.models import CountDocument, CountItem, StockSnapshot
from inventura.io.reports import ReportHeader, ReportLine, ReportRack
from inventura.services import ConflictError, NotFoundError, bulk_insert
from inventura.services.documents import (
    DocumentProgress,
    current_round,
    document_items,
    get_document,
    list_documents,
)


@dataclass(frozen=True, slots=True)
class ItemVariance:
    item: CountItem
    variance: Variance | None  # None: not counted yet


@dataclass(frozen=True, slots=True)
class DocumentVariances:
    progress: DocumentProgress
    current_round: int
    items: list[ItemVariance]
    summary: VarianceSummary


@dataclass(frozen=True, slots=True)
class RoundResult:
    status: DocumentStatus
    finished_round: int
    recount_items: int  # items sent to the next round (0 when the document was closed)


def item_variance(item: CountItem) -> ItemVariance:
    if item.presteta_kolicina is None:
        return ItemVariance(item, None)
    variance = compute_variance(item.knjizena_kolicina, item.presteta_kolicina, item.cena_na_enoto)
    return ItemVariance(item, variance)


def document_variances(session: Session, document_id: int) -> DocumentVariances:
    progress = get_document(session, document_id)
    items = [item_variance(item) for item in document_items(session, document_id)]
    return DocumentVariances(
        progress=progress,
        current_round=current_round(session, document_id),
        items=items,
        summary=summarize(entry.variance for entry in items),
    )


def finish_round(
    session: Session, document_id: int, rules: VarianceRules, now: datetime
) -> RoundResult:
    """Close the count round: items with a difference go to a new round, else (or after the
    last allowed round) the document is closed. Every item must be counted first."""
    document = session.scalars(
        select(CountDocument).where(CountDocument.id == document_id).with_for_update()
    ).one_or_none()
    if document is None:
        raise NotFoundError(f"dokument {document_id} ne obstaja")
    if document.status is DocumentStatus.ZAKLJUCEN:
        raise DocumentClosedError("dokument je že zaključen")

    entries = [item_variance(item) for item in document_items(session, document_id)]
    uncounted = sum(entry.variance is None for entry in entries)
    if uncounted:
        raise ConflictError(f"krog še ni končan, nepreštetih postavk: {uncounted}")

    this_round = current_round(session, document_id)
    recount = [e.item for e in entries if e.variance is not None and e.variance.recount]
    status = status_after_round(len(recount), this_round, rules)
    if status is DocumentStatus.PONOVNO_STETJE:
        _start_round(session, recount, this_round + 1)
    else:
        document.zakljucen_ob = now
    document.status = status
    session.flush()
    return RoundResult(
        status=status,
        finished_round=this_round,
        recount_items=len(recount) if status is DocumentStatus.PONOVNO_STETJE else 0,
    )


def _start_round(session: Session, items: Sequence[CountItem], round_number: int) -> None:
    """New rows for the next round: same position, same frozen book quantity and price."""
    session.execute(
        bulk_insert(CountItem),
        [
            {
                "document_id": item.document_id,
                "material_id": item.material_id,
                "lokacija": item.lokacija,
                "nivo": item.nivo,
                "polozaj": item.polozaj,
                "sarza": item.sarza,
                "knjizena_kolicina": item.knjizena_kolicina,
                "cena_na_enoto": item.cena_na_enoto,
                "krog": round_number,
                "najdeno": item.najdeno,
            }
            for item in items
        ],
    )


def snapshot_report(
    session: Session, snapshot_id: int, rules: VarianceRules, today: date
) -> tuple[list[ReportRack], ReportHeader]:
    """Variances of every document of a stock snapshot, in natural rack order."""
    snapshot = session.get(StockSnapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"uvoz {snapshot_id} ne obstaja")
    documents = list_documents(session, snapshot_id)
    if not documents:
        raise ConflictError(f"uvoz {snapshot_id} še nima popisnih dokumentov")
    racks = [
        ReportRack(
            number=progress.document.zaporedna_st,
            rack=progress.document.regal,
            status=progress.document.status.label,
            lines=[
                ReportLine(
                    lokacija=entry.item.lokacija,
                    sifra=entry.item.material.sifra,
                    opis=entry.item.material.opis,
                    sarza=entry.item.sarza,
                    merska_enota=entry.item.material.merska_enota,
                    krog=entry.item.krog,
                    najdeno=entry.item.najdeno,
                    variance=entry.variance,
                )
                for entry in (
                    item_variance(item) for item in document_items(session, progress.document.id)
                )
            ],
        )
        for progress in documents
    ]
    label = f"Uvoz {snapshot.id} · {snapshot.izvorna_datoteka}"
    return racks, ReportHeader(snapshot=label, created=today, rules=rules)
