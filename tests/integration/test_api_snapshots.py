from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from inventura.db.models import Material, StockItem, StockSnapshot
from inventura.generator import generate_stock, write_csv, write_xlsx


@pytest.fixture(scope="module")
def export_csv(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    path = tmp_path_factory.mktemp("export") / "stock.csv"
    write_csv(generate_stock(materials=60, seed=3), path)
    return path.read_bytes()


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_import_csv_stores_snapshot(
    client: TestClient, session: Session, export_csv: bytes
) -> None:
    response = client.post("/api/snapshots", files={"file": ("zaloga.csv", export_csv)})

    assert response.status_code == 201, response.text
    body = response.json()
    rows = len(generate_stock(materials=60, seed=3))
    assert body["izvorna_datoteka"] == "zaloga.csv"
    assert body["stevilo_vrstic"] == body["stevilo_postavk"] == rows
    assert body["stevilo_dokumentov"] == 0
    assert session.scalar(select(func.count()).select_from(Material)) == 60


def test_import_xlsx(client: TestClient, tmp_path: Path) -> None:
    path = tmp_path / "stock.xlsx"
    write_xlsx(generate_stock(materials=10, seed=1), path)
    response = client.post("/api/snapshots", files={"file": ("stock.xlsx", path.read_bytes())})
    assert response.status_code == 201, response.text


def test_stored_values_are_exact(client: TestClient, session: Session) -> None:
    data = (
        "Šifra materiala;Opis materiala;ME;Lokacija;Šarža;Zaloga;Cena na enoto\n"
        "0000007;Kabel NYM-J 3x1,5;m;K2-03-11;;1.250,5;0,80\n"
    ).encode("utf-8-sig")
    response = client.post("/api/snapshots", files={"file": ("stock.csv", data)})
    assert response.status_code == 201, response.text

    item = session.scalars(select(StockItem)).one()
    assert (item.lokacija, item.regal, item.nivo, item.polozaj, item.sarza) == (
        "K2-03-11",
        "K2",
        3,
        11,
        None,
    )
    assert (item.kolicina, item.cena_na_enoto, item.vrstica) == (
        Decimal("1250.500"),
        Decimal("0.80"),
        2,
    )


def test_file_with_row_errors_is_rejected_and_nothing_stored(
    client: TestClient, session: Session, fixtures_dir: Path
) -> None:
    data = (fixtures_dir / "stock_errors.csv").read_bytes()
    response = client.post("/api/snapshots", files={"file": ("stock_errors.csv", data)})

    assert response.status_code == 422
    body = response.json()
    assert body["vrstic_z_napakami"] == 10
    assert body["napake"][0] == {
        "vrstica": 4,
        "polje": "opis",
        "vrednost": "",
        "sporocilo": "vrednost je obvezna",
    }
    assert session.scalar(select(func.count()).select_from(StockSnapshot)) == 0


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("stock.txt", b"x", "nepodprta vrsta datoteke '.txt'"),
        ("stock.csv", b"A;B\n1;2\n", "manjkajo stolpci"),
        ("stock.xlsx", b"not a zip file", "ni mogoče prebrati"),
        ("stock.csv", "Šifra;x\n".encode("cp1250"), "ni mogoče prebrati"),
    ],
)
def test_unreadable_files_are_bad_requests(
    client: TestClient, name: str, data: bytes, message: str
) -> None:
    response = client.post("/api/snapshots", files={"file": (name, data)})
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_header_only_file_is_a_bad_request(client: TestClient) -> None:
    data = "Šifra materiala;Opis materiala;ME;Lokacija;Zaloga;Cena na enoto\n".encode()
    response = client.post("/api/snapshots", files={"file": ("stock.csv", data)})
    assert response.status_code == 400
    assert response.json()["detail"] == "datoteka nima vrstic z zalogo"


def test_file_too_large(client: TestClient, export_csv: bytes) -> None:
    client.app.state.settings = client.app.state.settings.model_copy(
        update={"max_upload_bytes": 100}
    )
    response = client.post("/api/snapshots", files={"file": ("stock.csv", export_csv)})
    assert response.status_code == 413


def test_list_and_get_snapshots(client: TestClient, export_csv: bytes) -> None:
    first = client.post("/api/snapshots", files={"file": ("a.csv", export_csv)}).json()
    second = client.post("/api/snapshots", files={"file": ("b.csv", export_csv)}).json()

    listed = client.get("/api/snapshots").json()
    assert [s["id"] for s in listed] == [second["id"], first["id"]]
    assert client.get(f"/api/snapshots/{first['id']}").json() == first
    assert client.get("/api/snapshots/999999").status_code == 404


def test_reimport_updates_material_master_data(client: TestClient, session: Session) -> None:
    header = "Šifra materiala;Opis materiala;ME;Lokacija;Zaloga;Cena na enoto\n"
    for price in ("1,00", "1,50"):
        data = (header + f"0000009;Vijak M8;kos;B1-1-1;5;{price}\n").encode()
        assert client.post("/api/snapshots", files={"file": ("s.csv", data)}).status_code == 201
    material = session.scalars(select(Material).where(Material.sifra == "0000009")).one()
    assert material.cena_na_enoto == Decimal("1.50")
