"""ERP batch upload: only closed documents, quantities summed per material and batch.

Shared B6 document: 0000001 vijak 120 kos, 0000002 kabel 12,5 m, 0000003 olje 20 l (L01);
rack K1 holds 0000009.
"""

import csv
import io
import re
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from inventura.cli import app as cli_app
from inventura.settings import Settings, get_settings


def ids(client: TestClient, document: dict[str, Any]) -> dict[tuple[str, str], int]:
    detail = client.get(f"/api/documents/{document['id']}").json()
    return {(item["sifra"], item["lokacija"]): item["id"] for item in detail["postavke"]}


def count(client: TestClient, item_id: int, quantity: str) -> None:
    response = client.patch(f"/api/items/{item_id}", json={"presteta_kolicina": quantity})
    assert response.status_code == 200, response.text


def close_b6(client: TestClient, document: dict[str, Any]) -> None:
    """Count B6 (the oil is gone, extra screws found elsewhere) through two rounds."""
    items = ids(client, document)
    count(client, items[("0000001", "B6-1-1")], "120")
    count(client, items[("0000002", "B6-1-2")], "12.5")
    count(client, items[("0000003", "B6-2-1")], "0")
    found = client.post(
        f"/api/documents/{document['id']}/items",
        json={"lokacija": "B6-3-1", "sifra": "0000001", "presteta_kolicina": "5"},
    )
    assert found.status_code == 201
    assert client.post(f"/api/documents/{document['id']}/finish-round").json()["status"] == (
        "ponovno_stetje"
    )
    recount = ids(client, document)
    count(client, recount[("0000003", "B6-2-1")], "0")
    count(client, recount[("0000001", "B6-3-1")], "5")
    assert client.post(f"/api/documents/{document['id']}/finish-round").json()["status"] == (
        "zakljucen"
    )


def read_zip(data: bytes) -> dict[str, str]:
    archive = zipfile.ZipFile(io.BytesIO(data))
    return {name: archive.read(name).decode("utf-8-sig") for name in archive.namelist()}


def rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text), delimiter=";"))[1:]


def test_export_needs_a_closed_document(client: TestClient, document: dict[str, Any]) -> None:
    response = client.get(f"/api/snapshots/{document['snapshot_id']}/erp-export.zip")
    assert response.status_code == 409
    assert response.json()["detail"] == "noben popisni dokument še ni zaključen"


def test_export_of_closed_documents(client: TestClient, document: dict[str, Any]) -> None:
    close_b6(client, document)
    snapshot_id = document["snapshot_id"]

    response = client.get(f"/api/snapshots/{snapshot_id}/erp-export.zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"erp_izvoz_uvoz_{snapshot_id}.zip" in response.headers["content-disposition"]
    files = read_zip(response.content)
    reference = f"INV{snapshot_id:04d}-B6"
    # Screws from B6-1-1 and the found ones on B6-3-1 are one item: 120 + 5.
    assert rows(files["erp_kolicine.csv"]) == [
        [reference, "1", "0000001", "", "125", "kos", ""],
        [reference, "2", "0000002", "", "12,5", "m", ""],
        [reference, "3", "0000003", "L01", "0,0", "l", "X"],  # litres keep one decimal
    ]
    created = rows(files["erp_dokumenti.csv"])[0][2]
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", created)
    assert rows(files["erp_dokumenti.csv"]) == [
        [reference, "1", created, "B6", "0000001", "", "kos"],
        [reference, "2", created, "B6", "0000002", "", "m"],
        [reference, "3", created, "B6", "0000003", "L01", "l"],
    ]
    summary = files["povzetek.txt"]
    assert "Dokumenti v izvozu: 1, postavk: 3" in summary
    assert "Izpuščeni dokumenti (niso zaključeni): 1" in summary
    assert "regal K1" in summary


def test_export_errors(client: TestClient) -> None:
    data = "Šifra materiala;Opis materiala;ME;Lokacija;Zaloga;Cena na enoto\n1;V;kos;B1-1-1;1;1\n"
    snapshot = client.post("/api/snapshots", files={"file": ("s.csv", data.encode())}).json()
    response = client.get(f"/api/snapshots/{snapshot['id']}/erp-export.zip")
    assert response.status_code == 409
    assert "še nima popisnih dokumentov" in response.json()["detail"]
    assert client.get("/api/snapshots/999999/erp-export.zip").status_code == 404


def test_export_links_on_the_pages(client: TestClient, document: dict[str, Any]) -> None:
    snapshot_id = document["snapshot_id"]
    link = f"/api/snapshots/{snapshot_id}/erp-export.zip"
    assert link in client.get("/").text
    assert link not in client.get(f"/dashboard/{snapshot_id}").text  # nothing closed yet
    close_b6(client, document)
    assert link in client.get(f"/dashboard/{snapshot_id}").text


def test_cli_export_for_unknown_import(
    monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setenv("INVENTURA_DATABASE_URL", test_settings.database_url)
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(cli_app, ["erp-export", "999999"])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 2
    assert "Izvoza ni mogoče pripraviti: uvoz 999999 ne obstaja" in result.output


def test_cli_reports_an_unreachable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "INVENTURA_DATABASE_URL", "postgresql+psycopg://nobody:x@127.0.0.1:1/none?connect_timeout=2"
    )
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(cli_app, ["erp-export", "1"])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 2
    assert "Baza ni dosegljiva" in result.output
