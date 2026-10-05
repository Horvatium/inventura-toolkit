"""HTML pages: stock imports and documents, and the count page for a tablet.

Every counted quantity is saved on its own (HTMX), so a dropped connection loses at most
the value being typed. Error responses are still 200, so HTMX swaps the message in.
"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from inventura.core.counting import CountError, DocumentStatus, parse_counted_input
from inventura.io.column_mapping import ColumnMappingError
from inventura.io.count_sheet_reader import CountSheetError
from inventura.io.importer import UnreadableFileError, UnsupportedFileError, import_stock_bytes
from inventura.services import ConflictError, counting, documents, snapshots
from inventura.web.dependencies import MappingDep, SessionDep, SettingsDep
from inventura.web.templating import templates

router = APIRouter(include_in_schema=False)

MAX_ERRORS_SHOWN = 50
Counter = Annotated[str | None, Form(max_length=100)]


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: SessionDep) -> HTMLResponse:
    imports = [
        (summary, documents.list_documents(session, summary.snapshot.id))
        for summary in snapshots.list_snapshots(session)
    ]
    return templates.TemplateResponse(request, "index.html", {"imports": imports})


@router.post("/snapshots", response_class=HTMLResponse)
def import_stock(
    request: Request,
    file: UploadFile,
    session: SessionDep,
    settings: SettingsDep,
    mapping: MappingDep,
) -> Response:
    data = file.file.read(settings.max_upload_bytes + 1)
    context: dict[str, Any] = {"message": None, "errors": [], "error_rows": 0}
    if len(data) > settings.max_upload_bytes:
        context["message"] = "Datoteka je prevelika."
        return templates.TemplateResponse(request, "partials/import_result.html", context)
    try:
        report = import_stock_bytes(data, file.filename or "", mapping)
    except (UnsupportedFileError, UnreadableFileError, ColumnMappingError) as exc:
        context["message"] = f"Datoteke ni mogoče uvoziti: {exc}"
        return templates.TemplateResponse(request, "partials/import_result.html", context)
    result = report.result
    if not result.is_valid or not result.rows:
        context["message"] = (
            "Datoteka ima napake, nič ni uvoženo." if result.errors else "Datoteka nima vrstic."
        )
        context["errors"] = result.errors[:MAX_ERRORS_SHOWN]
        context["error_rows"] = result.error_row_count
        return templates.TemplateResponse(request, "partials/import_result.html", context)
    snapshots.save_snapshot(session, report.source, result.rows)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"HX-Redirect": "/"})


@router.post("/snapshots/{snapshot_id}/documents")
def create_documents(snapshot_id: int, session: SessionDep) -> RedirectResponse:
    documents.create_documents(session, snapshot_id)
    session.commit()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/documents/{document_id}", response_class=HTMLResponse)
def count_page(request: Request, document_id: int, session: SessionDep) -> HTMLResponse:
    context = _document_context(session, document_id)
    return templates.TemplateResponse(request, "document.html", context)


@router.patch("/items/{item_id}", response_class=HTMLResponse)
def save_count(
    request: Request,
    item_id: int,
    session: SessionDep,
    kolicina: Annotated[str, Form(max_length=40)] = "",
    stevec: Counter = None,
) -> HTMLResponse:
    """Save one counted quantity; returns the row and the updated progress."""
    error = None
    try:
        quantity = parse_counted_input(kolicina)
        item = counting.record_count(session, item_id, quantity, stevec, datetime.now(UTC))
        session.commit()
    except (CountError, ConflictError) as exc:
        session.rollback()
        error = _message(exc)
        item = documents.get_item(session, item_id)
    progress = documents.get_document(session, item.document_id)
    context = {
        "item": item,
        "error": error,
        "typed": kolicina if error else None,
        "progress": progress,
        "closed": progress.document.status is DocumentStatus.ZAKLJUCEN,
        "row_oob": True,
    }
    return templates.TemplateResponse(request, "partials/item_row.html", context)


@router.post("/documents/{document_id}/found", response_class=HTMLResponse)
def add_found(
    request: Request,
    document_id: int,
    session: SessionDep,
    lokacija: Annotated[str, Form(max_length=40)] = "",
    sifra: Annotated[str, Form(max_length=40)] = "",
    sarza: Annotated[str, Form(max_length=40)] = "",
    kolicina: Annotated[str, Form(max_length=40)] = "",
    stevec: Counter = None,
) -> HTMLResponse:
    """Add found goods; on success the form is cleared and the item list refreshed."""
    form = {"lokacija": lokacija, "sifra": sifra, "sarza": sarza, "kolicina": kolicina}
    try:
        counting.add_found_item(
            session,
            document_id,
            location=lokacija,
            sifra=sifra,
            sarza=sarza,
            quantity=parse_counted_input(kolicina),
            counter=stevec,
            now=datetime.now(UTC),
        )
        session.commit()
    except (CountError, ConflictError) as exc:
        session.rollback()
        context = _document_context(session, document_id) | {"form": form, "error": _message(exc)}
        return templates.TemplateResponse(request, "partials/found_form.html", context)
    context = _document_context(session, document_id) | {
        "form": None,
        "error": None,
        "saved": f"Dodano: {sifra.strip()} na {lokacija.strip()}",
        "oob": True,
    }
    return templates.TemplateResponse(request, "partials/found_form.html", context)


@router.delete("/items/{item_id}", response_class=HTMLResponse)
def delete_found(request: Request, item_id: int, session: SessionDep) -> HTMLResponse:
    document_id = counting.delete_found_item(session, item_id)
    session.commit()
    context = _document_context(session, document_id) | {"oob": True}
    return templates.TemplateResponse(request, "partials/refresh.html", context)


@router.post("/documents/{document_id}/upload", response_class=HTMLResponse)
def upload_count_sheet(
    request: Request,
    document_id: int,
    file: UploadFile,
    session: SessionDep,
    settings: SettingsDep,
    mapping: MappingDep,
    stevec: Counter = None,
) -> HTMLResponse:
    """Import a filled Excel count sheet for this document (all rows or none)."""
    data = file.file.read(settings.max_upload_bytes + 1)
    result: dict[str, Any] = {"summary": None, "message": None, "errors": [], "error_rows": 0}
    oob = False
    if len(data) > settings.max_upload_bytes:
        result["message"] = "Datoteka je prevelika."
    else:
        try:
            result["summary"] = counting.import_count_sheet(
                session,
                document_id,
                data,
                stevec,
                datetime.now(UTC),
                mapping.numbers.to_format(),
            )
            session.commit()
            oob = True
        except CountSheetError as exc:
            result["message"] = f"To ni popisni list tega regala: {exc}"
        except counting.CountSheetRejected as exc:
            session.rollback()
            result["message"] = "Popisni list ima napake, nič ni shranjeno."
            result["errors"] = exc.errors[:MAX_ERRORS_SHOWN]
            result["error_rows"] = len({error.row_number for error in exc.errors})
        except (CountError, ConflictError) as exc:
            session.rollback()
            result["message"] = _message(exc)
    context = _document_context(session, document_id) | result | {"oob": oob}
    return templates.TemplateResponse(request, "partials/upload_result.html", context)


def _document_context(session: SessionDep, document_id: int) -> dict[str, Any]:
    progress = documents.get_document(session, document_id)
    return {
        "document": progress.document,
        "progress": progress,
        "items": documents.document_items(session, document_id),
        "closed": progress.document.status is DocumentStatus.ZAKLJUCEN,
    }


def _message(exc: Exception) -> str:
    text = str(exc)
    return text[:1].upper() + text[1:] + "."
