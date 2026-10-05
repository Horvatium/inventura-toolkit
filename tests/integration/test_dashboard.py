"""Dashboard: progress by rack, largest variances by value and their total value.

Uses the shared B6 document: 0000001 vijak 120 kos at 0,15 €, 0000002 kabel 12,5 m at
0,80 €, 0000003 olje 20 l at 3,50 €; material 0000009 (2 kos at 40 €) is on rack K1.
"""

import json
import re
from typing import Any

from fastapi.testclient import TestClient


def count(client: TestClient, document: dict[str, Any], quantities: dict[str, str]) -> None:
    for item in document["postavke"]:
        if item["sifra"] in quantities:
            body = {"presteta_kolicina": quantities[item["sifra"]]}
            assert client.patch(f"/api/items/{item['id']}", json=body).status_code == 200


def test_dashboard_api(client: TestClient, document: dict[str, Any]) -> None:
    count(client, document, {"0000001": "100", "0000003": "21"})  # -3,00 € and +3,50 €

    body = client.get(f"/api/snapshots/{document['snapshot_id']}/dashboard").json()

    assert (body["uvoz_id"], body["dokumentov"], body["zakljucenih"]) == (
        document["snapshot_id"],
        2,
        0,
    )
    assert body["po_statusu"] == {"v_stetju": 1, "odprt": 1}
    totals = body["povzetek"]
    assert (totals["postavk"], totals["presteto"], totals["z_razliko"]) == (4, 2, 2)
    assert (totals["visek"], totals["manjko"], totals["neto"]) == ("3.50", "-3.00", "0.50")
    racks = {rack["regal"]: rack for rack in body["regali"]}
    assert (racks["B6"]["postavk"], racks["B6"]["presteto"], racks["B6"]["neto"]) == (3, 2, "0.50")
    assert (racks["K1"]["postavk"], racks["K1"]["presteto"]) == (1, 0)
    assert [(v["sifra"], v["razlika_vrednost"]) for v in body["najvecje_razlike"]] == [
        ("0000003", "3.50"),
        ("0000001", "-3.00"),
    ]


def test_dashboard_api_unknown_import(client: TestClient) -> None:
    assert client.get("/api/snapshots/999999/dashboard").status_code == 404


def test_dashboard_without_inventory(client: TestClient) -> None:
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Inventura še ni začeta" in page.text


def test_dashboard_page(client: TestClient, document: dict[str, Any]) -> None:
    count(client, document, {"0000001": "100", "0000002": "12.5", "0000003": "20"})
    snapshot_id = document["snapshot_id"]

    latest = client.get("/dashboard", follow_redirects=False)
    assert latest.status_code == 303
    assert latest.headers["location"] == f"/dashboard/{snapshot_id}"

    page = client.get(f"/dashboard/{snapshot_id}").text
    assert "75 %" in page  # 3 of 4 items counted
    assert "3 od 4 postavk" in page
    assert "-3,00 €" in page
    assert 'id="chart-progress"' in page and 'id="chart-net"' in page
    assert "chart.umd.min.js" in page and "dashboard.js" in page
    assert f'hx-get="/dashboard/{snapshot_id}/content" hx-trigger="every 30s"' in page

    match = re.search(r'id="dashboard-data">(.*?)</script>', page, re.S)
    assert match is not None
    data = json.loads(match[1])
    assert [rack["regal"] for rack in data["regali"]] == ["B6", "K1"]


def test_dashboard_refresh_returns_only_the_content(
    client: TestClient, document: dict[str, Any]
) -> None:
    content = client.get(f"/dashboard/{document['snapshot_id']}/content").text
    assert content.lstrip().startswith('<div id="dashboard"')
    assert "<html" not in content
    assert "Ni še preštetih postavk z razliko." in content


def test_chart_library_is_served_locally(client: TestClient) -> None:
    script = client.get("/static/chart.umd.min.js")
    assert script.status_code == 200
    assert "Chart.js v4.5.1" in script.text[:200]
