# File formats

*[Slovenščina](file-formats.sl.md)*

All examples use fictional data from `src/inventura/generator.py`.

## Stock export (input)

CSV (semicolon, UTF-8) or XLSX (first sheet). Columns are matched by header through
`config/column_mapping.yaml`; each field accepts several header names, matching ignores
case and surrounding spaces, and other columns are ignored.

| Field | Default headers | Required | Rule |
|---|---|---|---|
| `sifra` | Šifra materiala, Material | yes | text, up to 40 characters; leading zeros are kept |
| `opis` | Opis materiala, Material description | yes | text, up to 200 characters |
| `merska_enota` | ME, Merska enota, Unit | yes | the same material always has the same unit |
| `lokacija` | Lokacija, Storage bin | yes | `RACK-LEVEL-POSITION`, e.g. `B6-1-1` or `K2-03-11` |
| `sarza` | Šarža, Batch | no | empty means no batch |
| `kolicina` | Zaloga, Quantity | yes | 0 or more; whole numbers, one decimal for `m` and `l` |
| `cena_na_enoto` | Cena na enoto, Unit price | yes | 0 or more, at most 2 decimals |

```text
Šifra materiala;Opis materiala;ME;Lokacija;Šarža;Zaloga;Cena na enoto
0010002;Vijak šestrobi DIN 933 M10x20 INOX A2;kos;K2-02-09;;817;0,04
0010025;Olje hidravlično HLP 100;l;K3-02-14;L10-4332;289,5;2,93
```

- Numbers in text cells use the format from the mapping file (by default `1.234,5`).
  A dot is then a thousands separator, so `1.5` is rejected rather than read as 15.
  Numeric XLSX cells are read as numbers.
- A row repeating the same material, location and batch is an error; leading zeros in
  the location do not make it different (`K2-03-11` = `K2-3-11`).
- Any error rejects the whole file. Errors are reported by row number as in Excel, and
  `inventura import --errors-csv errors.csv` writes them to a file.

## Count sheets (output and input)

One sheet per rack, in walking order: Excel (one worksheet per rack, header repeated on
every printed page, an input check on the count column) and an HTML page for printing
on A4. Book quantities are left out by default (a blind count); `--book-quantities` or
`?book_quantities=true` adds them. During a recount the sheet lists only the items sent
to the recount.

A **filled Excel sheet** can be imported back into its document:

- the worksheet named after the rack is used (or the only one in the file); columns are
  found by their titles, so rows above the header do not matter;
- a row with a quantity updates its item, an empty quantity changes nothing, and a
  quantity replaces one entered earlier on the tablet;
- a row written by hand at the end becomes found goods, if the material is in the
  master data;
- any error rejects the whole sheet.

## Excel report

`GET /api/snapshots/{id}/report.xlsx` or `inventura report <id>`.

| Sheet | Contents |
|---|---|
| Povzetek | one row per rack plus a total: items, counted, uncounted, items with a difference, surplus, shortage, net and absolute value |
| Razlike | every counted item with a difference: book, counted, difference, unit price, value, percentage, round, found goods; filter on every column |
| Neprešteto | items not counted yet |

Values are numbers, not formulas. Conditional formatting colours shortages red and
surpluses green and marks items counted in a second round.

## ERP batch upload (simulated format)

`GET /api/snapshots/{id}/erp-export.zip` or `inventura erp-export <id>`. The toolkit
has no connection to an ERP (for example SAP MM); the files only imitate a batch input
format. Only closed documents are exported; one ERP document per rack, with quantities
of the same material and batch from different locations added up.

`erp_dokumenti.csv` creates the physical inventory documents:

```text
Referenca;Postavka;Datum popisa;Regal;Material;Šarža;ME
INV0001-B1;1;06.10.2026;B1;0010011;;kos
INV0001-B1;3;06.10.2026;B1;0010122;L39-5376;kg
```

`erp_kolicine.csv` enters the counted quantities:

```text
Referenca;Postavka;Material;Šarža;Prešteta količina;ME;Nič
INV0001-B1;1;0010011;;28;kos;
INV0001-B1;10;0010604;L12-8059;176,8;l;
INV0001-B1;18;0011294;L77-5204;0;kos;X
```

- semicolon separated, UTF-8 with BOM, decimal comma without a thousands separator,
  decimals as the unit allows (`12,5` m, `0,0` l, `28` kos), dates `DD.MM.YYYY`;
- `Referenca` is `INV` + import number + rack, so the ERP document can be traced back;
- `Nič` = `X` marks a counted zero, so the ERP does not take it for an empty entry;
- `povzetek.txt` lists the exported documents and the racks left out (not closed yet).
