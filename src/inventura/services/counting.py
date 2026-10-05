"""Record counted quantities."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from inventura.core.counting import status_after_count, validate_counted_quantity
from inventura.db.models import CountDocument, CountItem
from inventura.services import ConflictError, NotFoundError
from inventura.services.documents import is_latest_round


def record_count(
    session: Session,
    item_id: int,
    quantity: Decimal | None,
    counter: str | None,
    now: datetime,
) -> CountItem:
    """Set (or with None, clear) the counted quantity of an item in the latest round.

    Raises NotFoundError, ConflictError for an item of an earlier round,
    DocumentClosedError for a closed document and CountError for an invalid quantity.
    """
    item = session.get(CountItem, item_id, with_for_update=True)
    if item is None:
        raise NotFoundError(f"count item {item_id} not found")
    document = session.scalars(
        select(CountDocument).where(CountDocument.id == item.document_id).with_for_update()
    ).one()

    if not session.scalar(select(is_latest_round()).where(CountItem.id == item.id)):
        raise ConflictError(f"item {item_id} belongs to an earlier count round")

    status = status_after_count(document.status)
    value = validate_counted_quantity(quantity, item.material.merska_enota)

    item.presteta_kolicina = value
    item.stevec = counter if value is not None else None
    item.presteto_ob = now if value is not None else None
    document.status = status
    session.flush()
    return item
