"""JSON API: import stock, create count documents, read them and record counts."""

from datetime import UTC, datetime
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import select

from inventura.core.documents import RackDocument
from inventura.io.column_mapping import ColumnMappingError
from inventura.io.count_sheets import (
    SheetOptions,
    render_count_sheets_html,
    write_count_sheets_xlsx,
)
from inventura.io.importer import UnreadableFileError, UnsupportedFileError, import_stock_bytes
from inventura.services import counting, documents, snapshots
from inventura.web.dependencies import MappingDep, SessionDep, SettingsDep
from inventura.web.schemas import (
    CountIn,
    DocumentDetail,
    DocumentOut,
    ImportRejected,
    ItemOut,
    RowErrorOut,
    SnapshotOut,
)

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter(prefix="/api")


@router.get("/health", tags=["system"])
def health(session: SessionDep) -> dict[str, str]:
    session.execute(select(1))
    return {"status": "ok"}


@router.post(
    "/snapshots",
    status_code=status.HTTP_201_CREATED,
    response_model=SnapshotOut,
    tags=["snapshots"],
    responses={
        400: {"description": "Unsupported or unreadable file, or missing columns"},
        413: {"description": "File too large"},
        422: {"model": ImportRejected, "description": "Rows with errors; nothing was stored"},
    },
)
def import_snapshot(
    file: UploadFile, session: SessionDep, settings: SettingsDep, mapping: MappingDep
) -> SnapshotOut | JSONResponse:
    """Import a stock export (CSV or XLSX). Stored only if every row is valid."""
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file is too large")
    try:
        report = import_stock_bytes(data, file.filename or "", mapping)
    except (UnsupportedFileError, UnreadableFileError, ColumnMappingError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    result = report.result
    if not result.is_valid:
        rejected = ImportRejected(
            detail="the file has rows with errors; nothing was imported",
            vrstic_z_napakami=result.error_row_count,
            napake=[RowErrorOut.of(error) for error in result.errors],
        )
        return JSONResponse(
            rejected.model_dump(mode="json"), status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        )
    if not result.rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "the file has no stock rows")

    snapshot = snapshots.save_snapshot(session, report.source, result.rows)
    session.commit()
    return SnapshotOut.of(snapshots.get_snapshot(session, snapshot.id))


@router.get("/snapshots", tags=["snapshots"])
def list_snapshots(session: SessionDep) -> list[SnapshotOut]:
    return [SnapshotOut.of(summary) for summary in snapshots.list_snapshots(session)]


@router.get("/snapshots/{snapshot_id}", tags=["snapshots"])
def get_snapshot(snapshot_id: int, session: SessionDep) -> SnapshotOut:
    return SnapshotOut.of(snapshots.get_snapshot(session, snapshot_id))


@router.post(
    "/snapshots/{snapshot_id}/documents",
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
    responses={409: {"description": "The snapshot already has count documents"}},
)
def create_documents(snapshot_id: int, session: SessionDep) -> list[DocumentOut]:
    """Start the count: one document per rack, book quantities and prices frozen."""
    documents.create_documents(session, snapshot_id)
    session.commit()
    return [DocumentOut.of(p) for p in documents.list_documents(session, snapshot_id)]


@router.get("/documents", tags=["documents"])
def list_documents(
    session: SessionDep, snapshot_id: Annotated[int | None, Query()] = None
) -> list[DocumentOut]:
    return [DocumentOut.of(p) for p in documents.list_documents(session, snapshot_id)]


@router.get("/documents/{document_id}", tags=["documents"])
def get_document(document_id: int, session: SessionDep) -> DocumentDetail:
    """A document with the items of its latest count round in walking order."""
    progress = documents.get_document(session, document_id)
    items = documents.document_items(session, document_id)
    return DocumentDetail(
        **DocumentOut.of(progress).model_dump(), postavke=[ItemOut.of(item) for item in items]
    )


@router.get(
    "/documents/{document_id}/count-sheet.xlsx",
    tags=["documents"],
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
def count_sheet_xlsx(
    document_id: int, session: SessionDep, book_quantities: bool = False
) -> Response:
    rack, options = _sheet(session, document_id, book_quantities)
    buffer = BytesIO()
    write_count_sheets_xlsx([rack], buffer, options)
    filename = f"popisni_list_{rack.rack}.xlsx"
    return Response(
        buffer.getvalue(),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/documents/{document_id}/count-sheet.html", tags=["documents"], response_class=HTMLResponse
)
def count_sheet_html(
    document_id: int, session: SessionDep, book_quantities: bool = False
) -> HTMLResponse:
    rack, options = _sheet(session, document_id, book_quantities)
    return HTMLResponse(render_count_sheets_html([rack], options))


@router.patch(
    "/items/{item_id}",
    tags=["items"],
    responses={
        409: {"description": "Closed document or an earlier count round"},
        422: {"description": "Quantity not allowed for the unit"},
    },
)
def record_count(item_id: int, body: CountIn, session: SessionDep) -> ItemOut:
    """Record a counted quantity (0 = counted, nothing there) or clear it with null."""
    item = counting.record_count(
        session, item_id, body.presteta_kolicina, body.stevec, now=datetime.now(UTC)
    )
    session.commit()
    return ItemOut.of(item)


def _sheet(
    session: SessionDep, document_id: int, book_quantities: bool
) -> tuple[RackDocument, SheetOptions]:
    rack, total = documents.rack_document(session, document_id)
    created = documents.get_document(session, document_id).document.ustvarjen_ob
    options = SheetOptions(
        created=created.astimezone().date(),
        total_documents=total,
        show_book_quantity=book_quantities,
    )
    return rack, options
