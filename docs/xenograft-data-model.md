# Xenograft data model

## SLIMS hierarchy

```
Project
  └─ Experiment            xprm_pk, xprm_fk_project, xprm_name
       └─ ExperimentRun     xprn_pk, xprn_fk_experiment
            └─ ExperimentRunStep   xprs_pk, xprs_fk_experimentRun
                 └─ ExperimentRunStepContent   xrsc_fk_experimentRunStep,
                                               xrsc_fk_content
                      └─ Content   cntn_pk
```

**A record from the `Content` table carries no back-reference to the MINDs
project.** If the join table is not walked and stored at snapshot time, the
provenance is not recoverable without re-walking SLIMS. This is why
`snapshot.py` fetches the whole structure before fetching any content.
`ExperimentRunStepContent` is a pure join table: one row per (run step, content)
pair.

Stored locally as `experiment`, `exp_run`, `exp_runstep`, `runstep_content`, and
`content`. `runstep_content` denormalises `exp_run_pk` and `experiment_pk` onto
each edge so "all content in experiment X" is one indexed lookup rather than a
four-table join.

## Data model

### Base content model

One generic `content` row per SLIMS record. Type-specific fields stay in the raw
column dump; the row itself carries only identity, type and derivation.

| column             | source                    | note                                 |
| ------------------ | ------------------------- | ------------------------------------ |
| `pk`               | `cntn_pk`                 |                                      |
| `slims_id`         | `cntn_barCode`            |                                      |
| `content_type`     | `cntn_fk_contentType`     | resolved display label, not the fk   |
| `mammoid`          | `cntn_cf_mammoid`         | optional, unreliable outside tumours |
| `original_content` | `cntn_fk_originalContent` | derivation link                      |
| `raw_json`         | all non-empty columns     | `{name: [title, display]}`           |

### Typed tables

After fetching, specific types tables are constructed for the data type `Mouse`,
`Tumor` and `Assay`. It carries the `pk`, `type` and `raw_json` from the base
content table + additional and specifc information to each type. These pieces of
information can come from slims columns or derived from the project structure.

**all_content** is a hidden fallback over every type, so content outside the
three kinds above still renders a detail page.

#### Tumors

| key                        | meaning                                                                   |
| -------------------------- | ------------------------------------------------------------------------- |
| `slims_id`                 | SLIMS barcode                                                             |
| `mammoid`                  | tumor identifier; the key the experiment is matched on                    |
| `exp_name`                 | experiment name this tumour corresponds to                                |
| `tumor_type`               | tumour type                                                               |
| `subtype`                  | histological subtype                                                      |
| `grade`                    | tumour grade                                                              |
| `er`, `pr`, `her2`, `ki67` | tumor-specific information                                                |
| `on_omero`                 | whether an omero link is provided on slims for this experiment/tumor      |
| `omero_link`               | actual URL to OMERO                                                       |
| `exp_guid`                 | unique identifier provided by slims, used to build the SLIMS deep link    |
| `rna_sequenced`            | whether the experiment has at least one Tissue for RNA associated content |
| `n_xenografts`             | number of mice in the same experiment                                     |

`exp_name`, `n_xenografts`, `rna_sequenced`, `on_omero`, `omero_link` and
`exp_guid` are derived: they resolve through linked tables rather than reading a
column.

#### Mice

| key            | meaning                                              |
| -------------- | ---------------------------------------------------- |
| `slims_id`     | SLIMS barcode                                        |
| `mammoid`      | free text here, not a reliable link back to a tumour |
| `exp_name`     | experiment the mouse belongs to                      |
| `mouse_exp_nb` | mouse number within the experiment                   |
| `generation`   | which run of the same experiment                     |
| `strain`       | mouse strain                                         |
| `sex`          | sex                                                  |
| `treatment`    | treatment received                                   |

#### Assays

Currently only content of type: `Slide`, `Blood Sample`, `Tissue for RNA`,
`Blood for analysis` are included as displayed assays.

| key                | meaning                                                         |
| ------------------ | --------------------------------------------------------------- |
| `slims_id`         | SLIMS barcode                                                   |
| `assay_type`       | which kind of assay this row is                                 |
| `mammoid`          | sample identifier, when populated                               |
| `exp_name`         | experiment the assay belongs to                                 |
| `original_content` | the content it was physically derived from, referenced on slims |

### Linked tables

Linked tables are created to store the relational link between experiment
(experiment name) and tumor (mammoid). A one-to-one correspondance is assumed
between experiment and tumor entries. This facilitates the computation of
derived values. Another linked table is created to store the link between
content derived from an experiment via the walk experiment -> run -> runstep ->
runstep content.

| `via`     | rule                                                                       |
| --------- | -------------------------------------------------------------------------- |
| `mammoid` | tumour types only: experiment name matched against `content.mammoid`       |
| `runstep` | everything else: the `experiment_pk` already on the `runstep_content` edge |

Tumour → experiment is therefore a **name match**, assumed one-to-one. At
fetching time, the count of these two events:
`tumor_without_matching_experiment` and `experiment_without_matching_tumor` are
reported.

`original_content` is the separate, physical derivation link (mouse → organ →
block → slide). It is stored but not currently traversed.

## Both axes together

```mermaid
flowchart TD
    subgraph
        EXP["Experiment"]
        Run["ExperimentRun<br/>"]
        Step["ExperimentRunStep<br/>"]
        Link["RunStepContent<br/>(join table)"]
        Content["Content<br/>"]
        EXP --> Run --> Step --> Link --> Content
        Tumor ---|mammoid| EXP
    end

    Tumor["Tumour / Mets"]
    Mouse["Mouse"]
    Sample["Assays"]

    Content -.- Tumor
    Content --- Mouse
    Content --- Sample

```
