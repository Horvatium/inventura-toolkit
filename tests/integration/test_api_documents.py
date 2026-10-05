from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

HEADER = "Šifra materiala;Opis materiala;ME;Lokacija;Šarža;Zaloga;Cena na enoto\n"
ROWS = [
    "0000003;Ležaj 6204;kos;B10-1-1;;4;6,40",
    "0000001;Vijak M8;kos;B2-1-2;;120;0,15",
    "0000002;Kabel NYM-J;m;B2-1-1;;12,5;0,80",
    "0000004;Olje HLP 46;l;B2-2-1;L01;20,0;3,50",
    "0000004;Olje HLP 46;l;B2-2-1;L02;5;3,50",
    "0000005;Filter;kos;K1-01-01;;2;40,00",
]


def import_rows(client: TestClient, rows: list[str], price: str | None = None) -> int:
    lines = [r if price is None else r.rsplit(";", 1)[0] + f";{price}" for r in rows]
    data = (HEADER + "\n".join(lines) + "\n").encode()
    response = client.post("/api/snapshots", files={"file": ("stock.csv", data)})
    assert response.status_code == 201, response.text
    snapshot_id: int = response.json()["id"]
    return snapshot_id


@pytest.fixture
def snapshot_id(client: TestClient) -> int:
    return import_rows(client, ROWS)


@pytest.fixture
def created(client: TestClient, snapshot_id: int) -> list[dict[str, Any]]:
    response = client.post(f"/api/snapshots/{snapshot_id}/documents")
    assert response.status_code == 201, response.text
    documents: list[dict[str, Any]] = response.json()
    return documents


def by_rack(documents: list[dict[str, Any]], rack: str) -> dict[str, Any]:
    return next(d for d in documents if d["regal"] == rack)


def test_one_document_per_rack_in_natural_order(created: list[dict[str, Any]]) -> None:
    assert [(d["zaporedna_st"], d["regal"], d["stevilo_postavk"]) for d in created] == [
        (1, "B2", 4),
        (2, "B10", 1),
        (3, "K1", 1),
    ]
    assert all(d["status"] == "odprt" and d["presteto"] == 0 for d in created)


def test_documents_can_be_created_once(client: TestClient, created: list[dict[str, Any]]) -> None:
    response = client.post(f"/api/snapshots/{created[0]['snapshot_id']}/documents")
    assert response.status_code == 409
    assert "already has count documents" in response.json()["detail"]


def test_unknown_snapshot(client: TestClient) -> None:
    assert client.post("/api/snapshots/999999/documents").status_code == 404


def test_document_items_in_walking_order(client: TestClient, created: list[dict[str, Any]]) -> None:
    detail = client.get(f"/api/documents/{by_rack(created, 'B2')['id']}").json()
    assert [(i["lokacija"], i["sifra"], i["sarza"]) for i in detail["postavke"]] == [
        ("B2-1-1", "0000002", None),
        ("B2-1-2", "0000001", None),
        ("B2-2-1", "0000004", "L01"),
        ("B2-2-1", "0000004", "L02"),
    ]
    first = detail["postavke"][0]
    assert first["knjizena_kolicina"] == "12.500"
    assert first["cena_na_enoto"] == "0.80"
    assert first["presteta_kolicina"] is None
    assert first["krog"] == 1


def test_list_documents_by_snapshot(client: TestClient, created: list[dict[str, Any]]) -> None:
    other = import_rows(client, ROWS[:1])
    client.post(f"/api/snapshots/{other}/documents")

    mine = client.get("/api/documents", params={"snapshot_id": created[0]["snapshot_id"]})
    assert [d["regal"] for d in mine.json()] == ["B2", "B10", "K1"]
    assert len(client.get("/api/documents").json()) == 4
    assert client.get("/api/documents/999999").status_code == 404


def test_later_import_does_not_change_started_count(
    client: TestClient, created: list[dict[str, Any]]
) -> None:
    import_rows(client, ROWS, price="99,00")
    detail = client.get(f"/api/documents/{by_rack(created, 'K1')['id']}").json()
    assert detail["postavke"][0]["cena_na_enoto"] == "40.00"
    assert Decimal(detail["postavke"][0]["knjizena_kolicina"]) == 2


def test_count_sheet_xlsx(client: TestClient, created: list[dict[str, Any]]) -> None:
    response = client.get(f"/api/documents/{by_rack(created, 'B2')['id']}/count-sheet.xlsx")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="popisni_list_B2.xlsx"'
    )
    sheet = load_workbook(BytesIO(response.content))["B2"]
    assert str(sheet["A2"].value).startswith("Dokument 1 od 3")
    assert [sheet[f"B{r}"].value for r in range(6, 10)] == [
        "B2-1-1",
        "B2-1-2",
        "B2-2-1",
        "B2-2-1",
    ]


def test_count_sheet_html(client: TestClient, created: list[dict[str, Any]]) -> None:
    url = f"/api/documents/{by_rack(created, 'B2')['id']}/count-sheet.html"
    blind = client.get(url)
    assert blind.status_code == 200
    assert "Popisni list – regal B2" in blind.text
    assert "Knjižna količina" not in blind.text
    with_book = client.get(url, params={"book_quantities": True}).text
    assert '<td class="book">12,5</td>' in with_book
