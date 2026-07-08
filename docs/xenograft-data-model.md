## Data model

Target shape for the xenograft export, expressed in the actual SLIMS `Content`
columns (verified against the live API). Everything lives in the `Content`
table, split by `cntn_fk_contentType`; the join key across all three entities is
`cntn_cf_mammoid`. Derived values (no single column) are given as expressions.

```jsonc
{
  "Tumors": [                                            // cntn_fk_contentType == 10
    {
      "cntn_id": "TUMOR_00000001",
      "cntn_cf_mammoid": "T-050",
      "treatments": "unique(linked Mouse.cntn_cf_fk_treatment -> Treatment)",
      "rna_sequenced": "exists(linked content of type 5 'Tissue for RNA')",
      "dna_sequenced": "exists(linked content of type 24 'DNA')",
      "number_of_experiments": "count(distinct linked Assay.cntn_cf_mouseExpNb)"
    }
  ],
  "Mouse": [                                             // cntn_fk_contentType == 19
    {
      "cntn_id": "00001167",
      "cntn_cf_mouseExpNb": "12",
      "cntn_cf_mammoid": "T-099",
      "cntn_cf_generation": "G7(5)",
      "cntn_cf_fk_treatment": "tamoxifen (chow)"
    }
  ],
  "Assay": [                                             // cntn_fk_contentType 21 (Blood), 5 (Tissue for RNA), ...
    {
      "cntn_fk_contentType": "Blood Sample",
      "cntn_cf_mouseExpNb": "12",
      "cntn_cf_mammoid": "M-37",
      "cntn_cf_organ": null
    },
    {
      "cntn_fk_contentType": "Tissue for RNA",
      "cntn_cf_mouseExpNb": "12",
      "cntn_cf_mammoid": "T-099",
      "cntn_cf_organ": "3L"
    }
  ]
}
```

## Column coverage

Counted across the whole `Content` table (9 201 Mouse, 299 Tumor, 5 347 Blood
Sample, 6 999 Tissue for RNA records).

| Column | Meaning | Populated |
| --- | --- | --- |
| `cntn_id` | UID / Slims ID | 100% |
| `cntn_cf_mammoid` | Mammo/Tumor/Mets/Cell line (join key) | Tumor 299/299, Mouse 7 920/9 201, Blood 5 347/5 347, RNA 6 975/6 999 |
| `cntn_cf_mouseExpNb` | Mouse exp # | Mouse 8 126/9 201, RNA 5 262/6 999 |
| `cntn_cf_generation` | Generation (Pyrat), `G…` | Mouse 1 403/9 201 |
| `cntn_cf_generationMm` | Generation, `P…` (alt.) | Mouse 7 956/9 201 |
| `cntn_cf_fk_treatment` | Treatment (FK → type 41) | Mouse 2 748/9 201 |
| `cntn_cf_organ` | Organ | RNA 5 254/6 999; null on blood |
| `cntn_fk_contentType` | content type = assay type | always |

## Caveats

- **`dna_sequenced`**: the `DNA` content type (24) has **0 records**, so with
  today's data this is always `false`. Confirm with the lab whether DNA samples
  are tracked under another type.
- **`generation`**: two columns. `cntn_cf_generationMm` is better populated
  (7 956) but holds `P…` values; `cntn_cf_generation` (1 403) holds the `G…`
  values matching `G7(5)`. Pick per the series you want.
- **`cntn_cf_mammoid` on Mouse**: clean on tumors (`T-050`) but free text on mice
  (e.g. `850-9 MCF7 shHR + Treatments`), so a Mouse→Tumor join on it is
  unreliable for some rows; the derivation chain (`cntn_fk_originalContent`) may
  be sturdier.
- **`cntn_cf_fk_treatment`**: a foreign key (Treatment content pk); resolve the
  label with `record.follow("cntn_cf_fk_treatment")` or the column `displayValue`.
