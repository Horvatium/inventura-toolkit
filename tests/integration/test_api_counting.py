from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from inventura.core.counting import DocumentStatus
from inventura.db.models import CountDocument, CountItem

HEADER = "Šifra materiala;Opis materiala;ME;Lokacija;Šarža;Zaloga;Cena na enoto\n"
ROWS = "0000001;Vijak M8;kos;B6-1-1;;120;0,15\n0000002;Kabel NYM-J;m;B6-1-2;;12,5;0,80\n"


@pytest.fixture
def document(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/snapshots", files={"file": ("s.csv", (HEADER + ROWS).encode())})
    snapshot_id = response.json()["id"]
    (created,) = client.post(f"/api/snapshots/{snapshot_id}/documents").json()
    detail: dict[str, Any] = client.get(f"/api/documents/{created['id']}").json()
    return detail


def item(document: dict[str, Any], sifra: str) -> int:
    item_id: int = next(i["id"] for i in document["postavke"] if i["sifra"] == sifra)
    return item_id


def count(client: TestClient, item_id: int, quantity: object, counter: str | None = "Ana") -> Any:
    body = {"presteta_kolicina": quantity, "stevec": counter}
    return client.patch(f"/api/items/{item_id}", json=body)


def test_recording_a_count(client: TestClient, document: dict[str, Any]) -> None:
    response = count(client, item(document, "0000001"), "118")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["presteta_kolicina"] == "118.000"
    assert body["stevec"] == "Ana"
    assert body["presteto_ob"] is not None
    progress = client.get(f"/api/documents/{document['id']}").json()
    assert (progress["status"], progress["presteto"], progress["stevilo_postavk"]) == (
        "v_stetju",
        1,
        2,
    )


def test_zero_is_a_count_and_null_clears_it(client: TestClient, document: dict[str, Any]) -> None:
    item_id = item(document, "0000001")
    assert count(client, item_id, "0").json()["presteta_kolicina"] == "0.000"
    assert client.get(f"/api/documents/{document['id']}").json()["presteto"] == 1

    cleared = count(client, item_id, None).json()
    assert (cleared["presteta_kolicina"], cleared["stevec"], cleared["presteto_ob"]) == (
        None,
        None,
        None,
    )
    assert client.get(f"/api/documents/{document['id']}").json()["presteto"] == 0


@pytest.mark.parametrize(
    ("sifra", "quantity", "status", "expected"),
    [
        ("0000002", 12.5, 200, "12.500"),
        ("0000002", "12.5", 200, "12.500"),
        ("0000002", "12.55", 422, "quantity in 'm' may have at most 1 decimal"),
        ("0000001", "1.5", 422, "quantity in 'kos' must be a whole number"),
        ("0000001", "-1", 422, "quantity must not be negative"),
    ],
)
def test_quantity_rules(
    client: TestClient,
    document: dict[str, Any],
    sifra: str,
    quantity: object,
    status: int,
    expected: str,
) -> None:
    response = count(client, item(document, sifra), quantity)
    assert response.status_code == status
    body = response.json()
    assert (body["presteta_kolicina"] if status == 200 else body["detail"]) == expected


def test_not_a_number(client: TestClient, document: dict[str, Any]) -> None:
    assert count(client, item(document, "0000001"), "veliko").status_code == 422


def test_closed_document_cannot_be_changed(
    client: TestClient, session: Session, document: dict[str, Any]
) -> None:
    session.execute(
        update(CountDocument)
        .where(CountDocument.id == document["id"])
        .values(status=DocumentStatus.ZAKLJUCEN)
    )
    response = count(client, item(document, "0000001"), "5")
    assert response.status_code == 409
    assert response.json()["detail"] == "document is closed"


def test_earlier_round_cannot_be_changed(
    client: TestClient, session: Session, document: dict[str, Any]
) -> None:
    first_round = session.get(CountItem, item(document, "0000001"))
    assert first_round is not None
    session.execute(
        insert(CountItem).values(
            document_id=first_round.document_id,
            material_id=first_round.material_id,
            lokacija=first_round.lokacija,
            nivo=first_round.nivo,
            polozaj=first_round.polozaj,
            sarza=None,
            knjizena_kolicina=first_round.knjizena_kolicina,
            cena_na_enoto=first_round.cena_na_enoto,
            krog=2,
        )
    )

    response = count(client, first_round.id, "5")
    assert response.status_code == 409

    detail = client.get(f"/api/documents/{document['id']}").json()
    rounds = {i["sifra"]: i["krog"] for i in detail["postavke"]}
    assert rounds == {"0000001": 2, "0000002": 1}
    second_round = session.scalar(select(CountItem.id).where(CountItem.krog == 2))
    assert count(client, second_round, "5").status_code == 200


def test_unknown_item(client: TestClient) -> None:
    assert count(client, 999999, "1").status_code == 404


def test_unknown_fields_are_rejected(client: TestClient, document: dict[str, Any]) -> None:
    response = client.patch(
        f"/api/items/{item(document, '0000001')}",
        json={"presteta_kolicina": "1", "knjizena_kolicina": "1"},
    )
    assert response.status_code == 422
