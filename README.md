# Inventura Toolkit

*[Slovenščina](README.sl.md)*

Warehouse stock counts still run through spreadsheets and manual re-keying. This tool
splits a stock export into one count document per rack, collects counts on a tablet and
flags variances for recount.

It covers the part of a physical inventory that happens outside the ERP: from the stock
export to count sheets, counting, variances and a recount, to a report, a dashboard and
a CSV file for a batch upload back into the ERP (for example SAP MM).

![From the stock export to counting on a tablet, variances and the dashboard](docs/demo.gif)

*All data in this repository is fictional, produced by the project's own generator.*

## What it does

1. **Import the stock export** (CSV or XLSX). Columns are matched through a YAML mapping,
   every row is validated and errors are reported by row number.
2. **Split by rack.** One count document per rack, racks in natural order (B2 before B10),
   items in walking order. Book quantity and unit price are frozen at this point.
3. **Count sheets** in Excel and as a page to print on A4, blind by default.
4. **Count on a tablet.** Large fields, every quantity saved on its own, Enter moves to
   the next item; goods found on a shelf without a book entry can be added. A filled
   Excel sheet can be imported instead.
5. **Variances and recount.** Every difference goes to a second count round; after the
   last round the counts are accepted and the rack is closed.
6. **Results:** an Excel report with conditional formatting, a dashboard (progress by rack,
   largest variances, total value) and a CSV batch upload for the ERP.

| Counting on a tablet | Variances | Dashboard |
|---|---|---|
| ![Count page](docs/images/stetje.png) | ![Variances](docs/images/razlike.png) | ![Dashboard](docs/images/nadzorna_plosca.png) |

The user interface is in Slovenian, the language of the warehouse it was built for.

## Quick start

Needs Docker.

```bash
docker compose up --build
```

Open <http://localhost:8000>. On the first start the database is migrated and filled with
a fictional inventory in progress: some racks closed, some in a recount, some still being
counted. There is no login (see [Limitations](#limitations)). The API documentation is at
<http://localhost:8000/docs>.

<details>
<summary>Behind a proxy or an antivirus that inspects HTTPS</summary>

If the build cannot download packages (`invalid peer certificate: UnknownIssuer`), pass the
root certificate of the proxy or antivirus. It is trusted only while the image is built:

```bash
docker build --secret id=extra_ca,src=root-ca.pem -t inventura-toolkit .
docker compose up
```
</details>

## Design decisions

- **One rack is one document.** A rack is what one counter covers in one walk; progress,
  recounts and closing all happen per rack, and the ERP gets one document per rack.
- **Book quantity and price are frozen** when the count starts. A later import must not
  change a count that is under way, and the variance must be measured against what the
  counter was counting.
- **`Numeric`, never `float`.** Quantities are `Numeric(14,3)` and money `Numeric(14,2)`,
  `Decimal` in Python, read from files as text. That is why the project uses only
  PostgreSQL, also in the tests: SQLite has no decimal type.
- **Not counted is not zero.** An empty count means "not counted yet", 0 means "counted,
  nothing there"; progress and variances keep the two apart.
- **Every round is a row, variances are never stored.** A recount adds a row; the variance
  is computed from the latest round on every read, so it cannot drift from the counts.
- **`NULLS NOT DISTINCT`** on the unique key of count items: the batch is often empty, and
  two rows without a batch must still count as the same position.
- **Locations are parsed.** `K2-03-11` and `K2-3-11` are the same location; racks sort
  naturally; the original text is kept for display.
- **Every difference is recounted.** The price does not decide what is counted again; it
  only gives the variance its value in the report.
- **HTMX instead of React.** Server-rendered pages need no separate frontend build and work
  on any tablet browser. htmx and Chart.js are served by the application itself, so
  counting works in a warehouse network without internet access.
- **All or nothing.** A stock export or a filled count sheet with any error is rejected
  as a whole, with the errors listed by row; nothing is half imported.
- **Business rules in `core/`**, a package without files, network or database, so they are
  tested with plain unit tests and property-based tests.

More in [architecture](docs/architecture.md), [data model](docs/data-model.md) and
[file formats](docs/file-formats.md).

## Limitations

- **The ERP export simulates a format.** It imitates a batch input for creating physical
  inventory documents and entering counts; there is no connection to any ERP.
- **No login or roles.** Everyone with access sees everything, including the variance
  pages that counters should not need. Roles (count manager, counter) are a planned
  extension.
- **One warehouse, one currency (EUR).** Plants and storage locations are not modelled.
- **Count sheets are Excel and HTML.** A PDF from the same template is a planned extension.

## Development

Python 3.12 with [uv](https://docs.astral.sh/uv/), PostgreSQL 16 in Docker.

```bash
uv sync
docker compose up -d db          # PostgreSQL on localhost:5433
uv run alembic upgrade head
uv run inventura demo            # optional: a fictional inventory
uv run inventura serve           # http://localhost:8000
```

Checks (the same as in CI):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

The tests use a separate database `inventura_test` in the same container; every test
runs in a transaction that is rolled back.

| Command | What it does |
|---|---|
| `inventura generate -o stock.csv` | fictional stock export (CSV or XLSX), same seed same data |
| `inventura import stock.csv` | validate an export and list row errors |
| `inventura sheets stock.csv` | count sheets (Excel + print page) without the database |
| `inventura demo` | fill an empty database with a fictional inventory |
| `inventura report <id>` | Excel variance report of an import |
| `inventura erp-export <id>` | ERP batch upload (ZIP) of the closed documents |
| `inventura serve` | run the web application |

Settings are environment variables with the prefix `INVENTURA_`: `DATABASE_URL`,
`TEST_DATABASE_URL`, `COLUMN_MAPPING`, `VARIANCE_RULES`, `MAX_UPLOAD_BYTES`. The
configuration files are `config/column_mapping.yaml` and `config/variance_rules.yaml`.

Screenshots and the GIF are produced from a running demo with
`uv run --with playwright --with pillow python scripts/docs_media.py`.

### Project structure

```text
src/inventura/
  core/        business rules, no I/O: locations, stock rows, documents, counting,
               variances, ERP aggregation
  io/          files: import, count sheets, filled sheet reader, report, ERP export
  db/          SQLAlchemy models and sessions
  services/    use cases on the database
  web/         FastAPI: JSON API, Jinja2 + HTMX pages, static files
  cli.py       Typer commands
  generator.py fictional stock data
  demo.py      demo inventory
config/        column mapping and recount rules (YAML)
migrations/    Alembic
tests/         unit (core), io, integration (PostgreSQL), CLI
docs/          architecture, data model, file formats; English and Slovenian
```

## Built with

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL 16, pandas,
openpyxl, PyYAML, Jinja2, HTMX, Chart.js, Typer, pytest, Hypothesis, Faker, ruff, mypy,
uv, Docker Compose, GitHub Actions.

## License

[MIT](LICENSE)
