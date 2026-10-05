"""Data for the dashboard: progress by rack, the largest variances and their total value."""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from inventura.core.counting import DocumentStatus
from inventura.core.variance import Variance, VarianceSummary, largest_by_value, summarize
from inventura.db.models import CountDocument, CountItem, StockSnapshot
from inventura.services import NotFoundError
from inventura.services.documents import DocumentProgress, is_latest_round, list_documents
from inventura.services.variances import ItemVariance, item_variance

TOP_VARIANCES = 10


@dataclass(frozen=True, slots=True)
class RackStatus:
    progress: DocumentProgress
    summary: VarianceSummary


@dataclass(frozen=True, slots=True)
class TopVariance:
    rack: str
    document_id: int
    item: CountItem
    variance: Variance


@dataclass(frozen=True, slots=True)
class Dashboard:
    snapshot: StockSnapshot
    racks: list[RackStatus]
    totals: VarianceSummary
    top: list[TopVariance]
    status_counts: dict[DocumentStatus, int]

    @property
    def documents(self) -> int:
        return len(self.racks)

    @property
    def closed(self) -> int:
        return self.status_counts.get(DocumentStatus.ZAKLJUCEN, 0)


def latest_counted_snapshot(session: Session) -> int | None:
    """The newest stock import that already has count documents."""
    return session.scalar(
        select(CountDocument.snapshot_id).order_by(CountDocument.snapshot_id.desc()).limit(1)
    )


def build_dashboard(session: Session, snapshot_id: int, top: int = TOP_VARIANCES) -> Dashboard:
    snapshot = session.get(StockSnapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"uvoz {snapshot_id} ne obstaja")
    documents = list_documents(session, snapshot_id)

    # Every item of the latest round in the snapshot, in one query.
    items = session.scalars(
        select(CountItem)
        .join(CountDocument, CountItem.document_id == CountDocument.id)
        .options(joinedload(CountItem.material))
        .where(CountDocument.snapshot_id == snapshot_id, is_latest_round())
        .order_by(CountItem.document_id, CountItem.nivo, CountItem.polozaj, CountItem.id)
    )
    by_document: dict[int, list[ItemVariance]] = {}
    for item in items:
        by_document.setdefault(item.document_id, []).append(item_variance(item))

    racks = [
        RackStatus(
            progress,
            summarize(entry.variance for entry in by_document.get(progress.document.id, [])),
        )
        for progress in documents
    ]
    rack_names = {progress.document.id: progress.document.regal for progress in documents}
    ranked = largest_by_value(
        (
            ((document_id, entry.item), entry.variance)
            for document_id, entries in by_document.items()
            for entry in entries
        ),
        top,
    )
    return Dashboard(
        snapshot=snapshot,
        racks=racks,
        totals=summarize(entry.variance for entries in by_document.values() for entry in entries),
        top=[
            TopVariance(rack_names[document_id], document_id, item, variance)
            for (document_id, item), variance in ranked
        ],
        status_counts=dict(Counter(progress.document.status for progress in documents)),
    )
