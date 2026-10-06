"""Collect the closed count documents of an inventory for the ERP batch upload."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from inventura.core.counting import DocumentStatus
from inventura.core.erp_export import CountedLine, ErpDocument, build_erp_documents
from inventura.db.models import CountItem, StockSnapshot
from inventura.io.erp_export import SkippedDocument
from inventura.services import ConflictError, NotFoundError
from inventura.services.documents import is_latest_round, list_documents


@dataclass(frozen=True, slots=True)
class ErpExport:
    snapshot: str  # e.g. "Uvoz 7 · zaloga.csv"
    documents: list[ErpDocument]
    skipped: list[SkippedDocument]


def build_erp_export(session: Session, snapshot_id: int) -> ErpExport:
    snapshot = session.get(StockSnapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"uvoz {snapshot_id} ne obstaja")
    progress = list_documents(session, snapshot_id)
    if not progress:
        raise ConflictError(f"uvoz {snapshot_id} še nima popisnih dokumentov")
    closed = [p.document for p in progress if p.document.status is DocumentStatus.ZAKLJUCEN]
    if not closed:
        raise ConflictError("noben popisni dokument še ni zaključen")

    by_id = {document.id: document for document in closed}
    items = session.scalars(
        select(CountItem)
        .options(joinedload(CountItem.material))
        .where(CountItem.document_id.in_(by_id), is_latest_round())
    )
    lines = []
    for item in items:
        document = by_id[item.document_id]
        if item.presteta_kolicina is None:  # a closed document has every item counted
            raise ConflictError(f"dokument {document.regal} ima nepreštete postavke")
        lines.append(
            CountedLine(
                document_number=document.zaporedna_st,
                rack=document.regal,
                created=document.ustvarjen_ob.astimezone().date(),
                sifra=item.material.sifra,
                sarza=item.sarza,
                merska_enota=item.material.merska_enota,
                knjizena_kolicina=item.knjizena_kolicina,
                presteta_kolicina=item.presteta_kolicina,
            )
        )
    return ErpExport(
        snapshot=f"Uvoz {snapshot.id} · {snapshot.izvorna_datoteka}",
        documents=build_erp_documents(snapshot_id, lines),
        skipped=[
            SkippedDocument(p.document.zaporedna_st, p.document.regal, p.document.status.label)
            for p in progress
            if p.document.status is not DocumentStatus.ZAKLJUCEN
        ],
    )
