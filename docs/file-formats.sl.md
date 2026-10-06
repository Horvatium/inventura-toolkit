# Oblike datotek

*[English](file-formats.md)*

Vsi primeri uporabljajo izmišljene podatke iz `src/inventura/generator.py`.

## Izvoz zalog (vhod)

CSV (podpičje, UTF-8) ali XLSX (prvi list). Stolpci se povežejo po naslovih prek
`config/column_mapping.yaml`; vsako polje sprejme več imen, velike in male črke ter
presledki okoli imena ne štejejo, ostali stolpci se ne upoštevajo.

| Polje | Privzeti naslovi | Obvezno | Pravilo |
|---|---|---|---|
| `sifra` | Šifra materiala, Material | da | besedilo do 40 znakov; vodilne ničle ostanejo |
| `opis` | Opis materiala, Material description | da | besedilo do 200 znakov |
| `merska_enota` | ME, Merska enota, Unit | da | isti material ima vedno isto ME |
| `lokacija` | Lokacija, Storage bin | da | `REGAL-NIVO-POLOŽAJ`, npr. `B6-1-1` ali `K2-03-11` |
| `sarza` | Šarža, Batch | ne | prazno pomeni brez šarže |
| `kolicina` | Zaloga, Quantity | da | 0 ali več; cela števila, pri `m` in `l` ena decimalka |
| `cena_na_enoto` | Cena na enoto, Unit price | da | 0 ali več, največ 2 decimalki |

```text
Šifra materiala;Opis materiala;ME;Lokacija;Šarža;Zaloga;Cena na enoto
0010002;Vijak šestrobi DIN 933 M10x20 INOX A2;kos;K2-02-09;;817;0,04
0010025;Olje hidravlično HLP 100;l;K3-02-14;L10-4332;289,5;2,93
```

- Števila v besedilnih celicah uporabljajo zapis iz nastavitvene datoteke (privzeto
  `1.234,5`). Pika je tedaj ločilo tisočic, zato se `1.5` zavrne in ne prebere kot 15.
  Številske celice v XLSX se preberejo kot števila.
- Vrstica, ki ponovi isti material, lokacijo in šaržo, je napaka; vodilne ničle v lokaciji
  je ne naredijo drugačne (`K2-03-11` = `K2-3-11`).
- Ena sama napaka zavrne celotno datoteko. Napake se izpišejo po številkah vrstic kot v
  Excelu, `inventura import --errors-csv napake.csv` pa jih zapiše v datoteko.

## Popisni listi (izhod in vhod)

En list na regal, v vrstnem redu hoje: Excel (en delovni list na regal, glava se ponovi na
vsaki natisnjeni strani, preverjanje vnosa v stolpcu za štetje) in stran HTML za tisk na
A4. Knjižne količine privzeto niso prikazane (slepo štetje); `--book-quantities` ali
`?book_quantities=true` jih doda. Med ponovnim štetjem list vsebuje samo postavke za
ponovno štetje.

**Izpolnjen Excel popisni list** se lahko uvozi nazaj v njegov dokument:

- uporabi se list z imenom regala (ali edini list v datoteki); stolpci se poiščejo po
  naslovih, zato vrstice nad glavo niso pomembne;
- vrstica s količino posodobi svojo postavko, prazna količina ne spremeni ničesar,
  količina pa nadomesti tisto, ki je bila prej vnesena na tablici;
- vrstica, ki jo števec ročno dopiše na konec, postane najdeno blago, če je material v
  šifrantu;
- ena sama napaka zavrne celoten list.

## Poročilo v Excelu

`GET /api/snapshots/{id}/report.xlsx` ali `inventura report <id>`.

| List | Vsebina |
|---|---|
| Povzetek | vrstica na regal in skupna vrstica: postavke, prešteto, neprešteto, z razliko, višek, manjko, neto in absolutna vrednost |
| Razlike | vsaka prešteta postavka z razliko: knjižna, prešteta, razlika, cena, vrednost, odstotek, krog, najdeno blago; filter na vseh stolpcih |
| Neprešteto | postavke, ki še niso preštete |

Vrednosti so števila, ne formule. Pogojno oblikovanje obarva manjko rdeče, višek zeleno
in označi postavke, preštete v drugem krogu.

## Paketni vnos v ERP (simulacija oblike)

`GET /api/snapshots/{id}/erp-export.zip` ali `inventura erp-export <id>`. Orodje nima
povezave z ERP (na primer SAP MM); datoteke le posnemajo obliko paketnega vnosa.
Izvozijo se samo zaključeni dokumenti; en ERP dokument na regal, količine istega materiala
in šarže z različnih lokacij pa se seštejejo.

`erp_dokumenti.csv` ustvari popisne dokumente:

```text
Referenca;Postavka;Datum popisa;Regal;Material;Šarža;ME
INV0001-B1;1;06.10.2026;B1;0010011;;kos
INV0001-B1;3;06.10.2026;B1;0010122;L39-5376;kg
```

`erp_kolicine.csv` vnese preštete količine:

```text
Referenca;Postavka;Material;Šarža;Prešteta količina;ME;Nič
INV0001-B1;1;0010011;;28;kos;
INV0001-B1;10;0010604;L12-8059;176,8;l;
INV0001-B1;18;0011294;L77-5204;0;kos;X
```

- ločilo podpičje, UTF-8 z BOM, decimalna vejica brez ločila tisočic, decimalke po merski
  enoti (`12,5` m, `0,0` l, `28` kos), datumi `DD.MM.LLLL`;
- `Referenca` je `INV` + številka uvoza + regal, zato se ERP dokument da izslediti nazaj;
- `Nič` = `X` označi prešteto ničlo, da je ERP ne razume kot prazen vnos;
- `povzetek.txt` našteje izvožene dokumente in izpuščene (še nezaključene) regale.
