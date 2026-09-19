# JASS Healthspan Explorer v1.0

An offline-first PySide6 research explorer for the **frozen JASS Healthspan Research 2011–2014 dataset**.

## Dataset

Built from:

- NHANES 2011–2012
- NHANES 2013–2014

Current frozen baseline:

- 19,931 records
- 80 variables
- no duplicate `SEQN`
- no residual SAS-missing sentinel
- official and independently derived grip measurements agree
- source XPT files preserved

## Features

### Dashboard

Displays:

- participant count
- variable count
- age range
- grip records
- BMI records
- activity records
- cycle counts
- dataset provenance

### Analysis

Research views for:

- Grip strength
- BMI
- Physical activity
- Blood pressure
- Sleep
- Metabolic markers

Includes:

- descriptive statistics
- age-group summaries
- ranges
- available-record counts
- quality-flag counts
- optional age-trend charts when QtCharts is available

### Records

Interactive record explorer with:

- age filtering
- text search
- sortable table
- bounded display of the first 5,000 matching records
- CSV export

The source dataset is never modified.

### Schema

Shows every variable with:

- name
- dtype
- non-null count
- missing percentage

### Quality

Reports:

- duplicate SEQN
- quality flags
- official-vs-derived grip agreement
- selected missingness indicators

### Research Notes

Session notes can be exported as Markdown.

## Installation

From your project directory:

```bash
cd ~/Projects/JASS_Healthspan_Research
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pandas numpy pyarrow PySide6
```

For charts, your PySide6 installation should include QtCharts. If it does not, all numerical analysis still works.

## Run

Place the application anywhere convenient, then:

```bash
python3 JASS_Healthspan_Explorer_v1.0.py
```

It automatically looks for:

```text
~/Projects/JASS_Healthspan_Research/
└── JASS_Healthspan_Research_2011_2014/
    └── processed/
        └── JASS_Healthspan_Research_2011_2014_v1.2.parquet
```

You can also open the CSV manually.

## Design principles

- Offline-first
- Local-only
- Read-only source dataset
- No cloud services
- No AI
- No modification of NHANES/JASS source records
- Explicit population-level interpretation
- Research rather than diagnosis

## Important interpretation boundary

The Explorer provides descriptive and exploratory analysis of a survey-derived population dataset.

It does **not**:

- diagnose disease
- calculate an individual's medical risk
- predict lifespan
- provide treatment advice
- establish causation from correlations

Survey weights, strata, PSU design, and complex-sample inference are visible source variables but are not automatically applied to every displayed descriptive statistic in v1.0. Researchers should account for the NHANES survey design when doing formal population inference.

## Roadmap

Potential future versions:

### v1.1 — Advanced filtering
- sex
- age bands
- cycle
- race/ethnicity
- education
- BMI categories
- grip availability
- activity availability

### v1.2 — Relationship explorer
- correlation matrix
- scatter plots
- trend lines
- subgroup comparison
- distribution plots

### v1.3 — NHANES survey-aware analysis
- MEC weights
- fasting subsample weights
- strata
- PSU
- survey-weighted descriptive estimates
- confidence intervals

### v1.4 — Healthspan research workspace
- saved analyses
- named research questions
- reproducible analysis definitions
- persistent SQLite research notebook
- citations/provenance

### v2.0 — JASS Healthspan Research Studio
- cohort builder
- analysis pipelines
- statistical tests
- publication-ready figures
- reproducible reports
- benchmark datasets
- integration with the broader JASS/Athena research ecosystem

## License / source

This application is a research utility built around public-use NHANES data. Consult the CDC/NCHS NHANES documentation and data-use terms for the underlying source data.

The JASS application itself is provided as a local research tool.
