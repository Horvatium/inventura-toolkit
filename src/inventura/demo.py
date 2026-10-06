"""Demo data: a fictional inventory in progress, for docker compose and screenshots.

The stock comes from the generator and goes through the real import; counts are entered
through the same services the web pages use. Racks end up in every state: closed, in a
recount, partly counted and not started. The result is the same for the same seed.
"""

import random
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from faker import Faker
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from inventura.core.counting import DocumentStatus
from inventura.core.units import quantity_decimals
from inventura.core.variance import VarianceRules
from inventura.db.models import CountItem, StockSnapshot
from inventura.generator import generate_stock, write_csv
from inventura.io.column_mapping import ColumnMapping
from inventura.io.importer import import_stock_file
from inventura.services import counting, documents, snapshots, variances

# Share of items counted per rack, in rack order (B1 ... K3); 1.0 racks are also closed.
COUNT_PLAN = (1.0, 1.0, 1.0, 1.0, 1.0, 0.85, 0.7, 0.55, 0.4, 0.25, 0.1, 0.0)
CLOSED_RACKS = 3  # the first racks finish their recount; the next fully counted wait in it
DIFFERENCE_SHARE = 0.06  # first count
RECOUNT_DIFFERENCE_SHARE = 0.4  # of the items sent to a recount


@dataclass(frozen=True, slots=True)
class DemoResult:
    snapshot_id: int
    items: int
    documents: int
    statuses: dict[DocumentStatus, int]


def seed_demo(
    session: Session,
    mapping: ColumnMapping,
    rules: VarianceRules,
    materials: int = 2000,
    seed: int = 42,
) -> DemoResult | None:
    """Fill an empty database; returns None and changes nothing if any import exists."""
    if session.scalar(select(func.count()).select_from(StockSnapshot)):
        return None
    rng = random.Random(seed)
    fake = Faker("sl_SI")
    fake.seed_instance(seed)
    counters = [f"{fake.first_name()} {fake.last_name()[0]}." for _ in range(4)]
    now = datetime.now(UTC)

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "zaloga_demo.csv"
        write_csv(generate_stock(materials=materials, seed=seed), path)
        report = import_stock_file(path, mapping)
    snapshot = snapshots.save_snapshot(session, report.source, report.result.rows)
    created = documents.create_documents(session, snapshot.id)

    for index, document in enumerate(created):
        share = COUNT_PLAN[index % len(COUNT_PLAN)]
        counter = counters[index % len(counters)]
        for item in documents.document_items(session, document.id):
            if rng.random() < share:
                quantity = _counted(rng, item, DIFFERENCE_SHARE)
                counting.record_count(session, item.id, quantity, counter, now)
        if share < 1.0:
            continue
        result = variances.finish_round(session, document.id, rules, now)
        if result.status is DocumentStatus.PONOVNO_STETJE and index < CLOSED_RACKS:
            # The recount resolves most differences; the rest are accepted as counted.
            this_round = documents.current_round(session, document.id)
            for item in documents.document_items(session, document.id, round_only=this_round):
                quantity = _counted(rng, item, RECOUNT_DIFFERENCE_SHARE)
                counting.record_count(session, item.id, quantity, counter, now)
            variances.finish_round(session, document.id, rules, now)

    session.flush()
    progress = documents.list_documents(session, snapshot.id)
    statuses: dict[DocumentStatus, int] = {}
    for entry in progress:
        statuses[entry.document.status] = statuses.get(entry.document.status, 0) + 1
    return DemoResult(snapshot.id, len(report.result.rows), len(progress), statuses)


def _counted(rng: random.Random, item: CountItem, difference_share: float) -> Decimal:
    """The book quantity, or with the given share a few units more or less."""
    book = item.knjizena_kolicina
    if rng.random() >= difference_share:
        return book
    step = Decimal(1).scaleb(-quantity_decimals(item.material.merska_enota))
    change = rng.choice((-3, -2, -1, 1, 2)) * rng.randint(1, 4) * step
    return max(Decimal(0), book + change)
