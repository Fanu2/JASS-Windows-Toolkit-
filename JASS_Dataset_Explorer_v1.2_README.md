# JASS Dataset Explorer v1.2

JASS Dataset Explorer is a **read-only, local-first PySide6 dataset inspection and data-quality workbench**.

Version 1.2 strengthens the **Data Preview** tab so it can be used as a practical lightweight dataset browser without turning the application into a spreadsheet editor.

## Supported Formats

- CSV
- TSV
- JSON
- JSONL / NDJSON
- Parquet — optional PyArrow support

## v1.2 Highlights

### Enhanced Data Preview

The Data Preview tab now provides:

- bounded row preview
- displayed-row text filtering
- column-specific filtering
- sortable columns
- row numbers
- auto-fit columns
- hide individual columns
- show all columns
- copy selected cell
- copy selected row
- double-click row details
- right-click context menu
- Unicode information for the selected cell
- export of currently displayed/filtered rows
- sensitive-column masking during preview and export
- full long-text inspection in the row-details dialog

### Copyable Search Results

Search results are now directly copyable:

- select one or more cells
- press **Ctrl+C**
- use **Copy Selected**
- use **Copy All Results**
- right-click the result table for copy actions
- copied values retain the same sensitive-data masking used by the display

### Unicode Intelligence

The Unicode inspector reports:

- character count
- UTF-8 byte count
- unique-character count
- whitespace count
- Unicode general categories
- script/name hints for common scripts
- a readable sample of the selected value

This is particularly useful for multilingual corpora such as Bengali, Punjabi/Gurmukhi, Shahmukhi, Mizo and other Unicode-heavy datasets.

### Existing v1.1 Intelligence

The application retains:

- unique-value ratio
- repeated-value surplus
- column quality score
- type evidence
- exact duplicate-row analysis within the bounded sample
- sensitive-column candidate detection
- masked sensitive values
- missing/empty analysis
- URL/email detection
- very-long-value detection
- mixed-type detection
- column profiles
- Quality Investigator
- bounded search
- TXT report export
- background analysis
- read-only operation

## Read-Only Philosophy

JASS Dataset Explorer does not modify the source dataset.

Exporting filtered preview rows creates a **new CSV file**; it never changes the original dataset.

Potentially sensitive columns are masked in the UI and exported preview.

## Performance Model

Analysis is deliberately bounded:

- the configured sample is kept in memory
- CSV/TSV/JSONL scanning is streamed
- JSON is loaded according to its structure
- Parquet uses PyArrow when available
- expensive analysis runs in a background thread

The Data Preview only displays the current analysis sample, not the entire dataset.

## Important Limitation

Search, Quality analysis and Data Preview operate on the bounded sample loaded during analysis.

For very large datasets, increase the **Sample** value when you need broader inspection, while remembering that a larger sample consumes more memory and takes longer to analyze.

## Running

```bash
python3 JASS_Dataset_Explorer_v1.2.py
```

PySide6 is required:

```bash
python3 -m pip install PySide6
```

For Parquet:

```bash
python3 -m pip install pyarrow
```

## Example Workflow

1. Open a CSV, TSV, JSON, JSONL or Parquet file.
2. Choose an appropriate sample size.
3. Review Dashboard.
4. Inspect Schema & Types.
5. Open Column Profiles.
6. Use Data Preview for sorting/filtering.
7. Select a multilingual cell and use **Unicode Info**.
8. Double-click a row for detailed inspection.
9. Run Quality checks.
10. Export only the displayed preview rows if required.

## Safety

JASS Dataset Explorer is intended for inspection, profiling and research.

It does not:

- delete data
- rename source files
- modify source rows
- upload data
- send data to a cloud service
- require an AI service
- require a database server

Always treat datasets containing passwords, tokens, credentials or personal information as sensitive.

## Roadmap

Possible future directions:

- visual frequency charts
- missing-value heatmap
- richer pattern detection
- date/time profiling
- numeric distribution analysis
- duplicate-row drill-down
- approximate cardinality for huge datasets
- sampling strategies beyond first-N rows
- random/stratified sampling
- data dictionary generation
- HTML/PDF reports
- archive inspection
- database-table import
- multilingual normalization diagnostics
- script detection improvements
- dataset comparison
- schema-drift comparison
- persistent project/session files
- optional local AI assistance through Ollama/LM Studio

## Status

**v1.2 — Data Preview & Unicode Intelligence checkpoint**

The project remains intentionally lightweight, local-first and read-only.
