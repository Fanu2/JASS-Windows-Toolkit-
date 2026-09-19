# JASS SQLite Explorer

**Version:** 1.7.0  
**Status:** Experimental Compatibility Baseline / Read-Only  
**Platform:** Linux / Windows / other platforms supported by PySide6  
**Framework:** Python + PySide6 + SQLite  
**Project:** JASS Tools

---

## Overview

**JASS SQLite Explorer** is a local, read-only desktop application for opening, inspecting, searching, profiling, and investigating SQLite databases.

The project is designed not only as a database browser, but also as a practical **SQLite compatibility laboratory**: real-world databases with different schemas, sizes, indexes, FTS structures, Unicode content, and data patterns can be opened and examined without modifying the original database.

The current milestone deliberately focuses on **inspection and compatibility testing**, rather than database editing.

---

## Current Compatibility Testing

During development, the Explorer has been tested with real databases including:

### Mizo corpus database

- Approximately **4,000,000 rows**
- `sentences` table
- `corpus_metadata` table
- FTS5 virtual table
- Unicode text
- Very large TEXT values
- External/recovered USB storage
- Read-only analysis

### Punjabi Aksharantar database

- **534,841 entries**
- Multiple indexes
- FTS5 virtual table
- Several TEXT columns
- NULL values
- Numeric and REAL columns
- Dataset split information
- Unicode Punjabi/Gurmukhi text

These databases exposed several practical compatibility issues during development and helped improve the Explorer's handling of real-world SQLite structures.

---

# Main Features

## 1. Dashboard

Provides an overview of the currently opened database.

Displays information such as:

- Database path
- Database size
- Modification time
- Number of tables
- Views
- Indexes
- Triggers
- Estimated row count
- FTS tables
- Foreign-key definitions
- SQLite integrity status
- Page size
- Page count
- Journal mode
- Encoding
- Read-only status

---

## 2. Data Browser

Browse table contents without modifying the database.

Features include:

- Table selection
- Pagination
- Configurable rows per page
- Column display
- WHERE filtering
- Large-table browsing
- Horizontal and vertical scrolling
- Unicode text display
- NULL handling
- Basic result inspection

The browser is intended to remain safe for exploratory work.

---

## 3. FTS Search

Provides full-text searching where an FTS5 virtual table is available.

Useful for:

- Large text corpora
- Language datasets
- Document databases
- Search indexes
- Content exploration

The Explorer detects available FTS structures rather than assuming that every database contains FTS.

---

## 4. Statistics

The Statistics workspace examines individual tables and their columns.

Depending on the database, it can show:

- Column name
- SQLite type
- Primary-key status
- NOT NULL status
- NULL count
- Distinct-value information
- Average text length
- Maximum text length
- Column profiling
- Top-value/frequency information

### Large database handling

Large databases require different treatment from small databases.

The Explorer therefore uses deferred/fast analysis in situations where an exact:

```text
COUNT(DISTINCT ...)
GROUP BY ...
```

operation could become unnecessarily expensive.

For example, with a 4-million-row text table, exact distinct-value analysis may be deferred while inexpensive structural and length statistics are still displayed.

An optional **Deep exact analysis** mode can be used when exact calculations are specifically required.

---

# 5. Schema Inspector

Displays the SQLite schema, including:

- CREATE TABLE statements
- CREATE INDEX statements
- CREATE VIEW statements
- CREATE TRIGGER statements
- Virtual-table definitions
- FTS5 structures
- Internal FTS tables

This is particularly useful for understanding databases that contain automatically generated SQLite/FTS objects.

---

# 6. SQL Console

Provides a read-only SQL environment for custom investigation.

Typical examples:

```sql
SELECT * FROM sentences LIMIT 20;
```

```sql
SELECT COUNT(*) FROM sentences;
```

```sql
SELECT line_no, text
FROM sentences
WHERE text LIKE '%hmang%'
LIMIT 20;
```

```sql
SELECT split, COUNT(*)
FROM entries
GROUP BY split;
```

The application is designed to prevent destructive database operations.

---

# 7. Investigation

The Investigation workspace provides targeted ways to examine unusual records.

Examples include:

- Longest records
- Search-target investigation
- Record-length investigation
- Targeted text investigation
- Limited result sets
- Exportable investigation results

The purpose is to help answer questions such as:

> "Why is this database so large?"

or:

> "Which records contain unusually large amounts of text?"

---

# 8. Corpus Lab

The Corpus Lab is specialized functionality developed while testing language and text databases.

It can inspect:

- Record counts
- NULL records
- Empty records
- Average text length
- Minimum/maximum text length
- Total characters
- Sample records
- Token counts
- Unique sample tokens
- Average tokens per record
- Sample lexical ratio
- Character classes
- Unicode characteristics
- Vocabulary statistics
- Sentence-length characteristics
- Anomalies
- Duplicate candidates
- Investigation results

The analysis is intended as a **diagnostic tool**, not as a linguistic gold-standard tokenizer.

---

# 9. Corpus Quality Investigator

The Quality Investigator identifies records that deserve manual review.

Available investigation modes include:

- Quality scan — sample
- Longest records
- Most repetitive records
- Web / SEO pattern candidates
- Very long records

The investigator can consider signals such as:

- Extreme repetition
- Adjacent repeated terms
- Unusually long records
- URL patterns
- Other suspicious text patterns

Results can include:

- Record length
- Repetition percentage
- URL count
- Detected signals
- Preview
- Quality score

### Important

A quality finding is **not proof that a record is incorrect, unwanted, or contaminated**.

It is a review candidate.

For example, during testing of the Mizo corpus, a record with approximately 85.7% repetition was detected. Inspection showed repeated material such as:

```text
TUR TUR TUR TUR ...
```

This demonstrated that the quality investigator was capable of surfacing unusual records.

---

# 10. Unicode Analysis

Unicode inspection is important for multilingual databases.

The Explorer can examine:

- Unicode characters
- Character classes
- Unicode block hints
- Latin characters
- Devanagari
- CJK
- Other detected ranges
- Whitespace
- Digits
- Punctuation

This is particularly useful for:

- Mizo
- Punjabi/Gurmukhi
- Shahmukhi
- Hindi
- Multilingual corpora
- Transliteration datasets

---

# 11. Duplicate Investigation

The Corpus Lab includes duplicate-oriented investigation.

This can help identify:

- Exact duplicate candidates
- Repeated records
- Highly repetitive records
- Potentially duplicated corpus material

An **Exact Duplicate Check** is available for more targeted verification.

---

# 12. Reports

Reports can document database and analysis results.

Supported report outputs include formats such as:

- TXT
- CSV
- JSON

Reports are useful for:

- Dataset documentation
- Corpus audits
- Database comparison
- Research notes
- Compatibility testing
- Reproducible investigations

---

# Read-Only Design

JASS SQLite Explorer is intentionally designed around a **read-only philosophy**.

The application is intended to:

- Open databases
- Inspect databases
- Query databases
- Analyze databases
- Search databases
- Export analysis results

It is **not intended to edit the original database**.

This makes it suitable for inspecting:

- Existing datasets
- Recovered databases
- Research databases
- Language corpora
- Backup databases
- Databases that should not be modified during investigation

The application displays:

```text
READ-ONLY
```

when a database is open.

---

# Why Test With Different Databases?

A SQLite application that works perfectly with one database may fail with another.

Real-world SQLite databases can differ substantially.

For example:

```text
Database A
├── 2 tables
├── simple TEXT data
└── no indexes

Database B
├── 1 million rows
├── several indexes
├── NULL values
└── mixed numeric/text fields

Database C
├── FTS5
├── virtual tables
├── Unicode corpus
└── millions of records

Database D
├── views
├── triggers
├── foreign keys
├── BLOBs
└── application-specific schema
```

The goal of JASS SQLite Explorer is therefore not merely:

> "Can it open my database?"

but:

> **"How reliably does it behave across different SQLite databases?"**

---

# Compatibility Matrix

The current development/testing baseline is:

| Database feature | Status |
|---|---|
| Small SQLite database | Tested |
| Large SQLite database | Tested |
| 500K+ rows | Tested |
| 4M rows | Tested |
| FTS5 | Tested |
| Multiple indexes | Tested |
| Unicode-heavy text | Tested |
| Key/value metadata | Tested |
| NULL-containing columns | Tested |
| Very long TEXT values | Tested |
| External USB database | Tested |
| Read-only database | Tested |
| Multiple tables | Tested |
| Virtual tables | Tested |
| No indexes | Not yet systematically tested |
| Views | Not yet systematically tested |
| Triggers | Not yet systematically tested |
| Foreign keys | Not yet systematically tested |
| WITHOUT ROWID | Not yet systematically tested |
| WAL-mode database | Not yet systematically tested |
| BLOB-heavy database | Not yet systematically tested |
| Numeric/scientific database | Not yet systematically tested |
| Damaged/incomplete database | Not yet systematically tested |

This matrix is intentionally a **living test plan**.

---

# Performance Philosophy

Large SQLite databases should not automatically be treated like small databases.

For example:

```text
50 rows
```

and:

```text
4,000,000 rows
```

require different strategies.

JASS SQLite Explorer therefore attempts to:

- avoid unnecessary full-table operations
- defer expensive DISTINCT/GROUP BY analysis
- use bounded samples for linguistic analysis
- provide progress indicators
- avoid freezing the interface where possible
- allow cancellation for long-running operations
- preserve responsiveness during analysis

The application should favor:

> **Useful information quickly, exact analysis when explicitly requested.**

---

# Example: Mizo Corpus

The Explorer successfully opened:

```text
JASS_Mizo_Corpus_4M.db
```

with:

```text
4,000,000 records
```

The database contained:

```text
corpus_metadata
sentences
sentences_fts
sentences_fts_config
sentences_fts_data
sentences_fts_docsize
sentences_fts_idx
```

Corpus analysis reported approximately:

```text
Average characters: 97.46
Minimum characters: 9
Maximum characters: 87,767
Total characters: 389,821,646
```

A bounded linguistic sample could also be examined without attempting expensive full-corpus tokenization.

---

# Example: Punjabi Aksharantar

The Explorer also successfully handled:

```text
JASS_Punjabi_Aksharantar.db
```

with:

```text
534,841 rows
```

The database included fields such as:

```text
id
unique_identifier
native_word
romanized_word
source
score
split
```

and indexes such as:

```text
idx_native
idx_romanized
idx_source
idx_split
```

This provided a useful contrast with the Mizo sentence corpus.

---

# Installation

## Requirements

- Python 3
- PySide6
- SQLite support included with Python

Install PySide6:

```bash
python3 -m pip install PySide6
```

On Debian/MX Linux, Python and pip may be installed with:

```bash
sudo apt update
sudo apt install python3 python3-pip
```

---

# Running

From the directory containing the application:

```bash
python3 JASS_SQLite_Explorer_v1.7.0.py
```

Or:

```bash
python3 JASS_SQLite_Explorer_v1.7.0_fixed.py
```

if using the fixed distribution file.

---

# Recommended Testing Procedure

When testing a new SQLite database:

### 1. Open the database

Use:

```text
File → Open Database
```

### 2. Check Dashboard

Look at:

- table count
- row estimates
- indexes
- FTS
- journal mode
- integrity status

### 3. Inspect Schema

Confirm that the schema is represented correctly.

### 4. Open Data Browser

Select a normal user table rather than an internal SQLite/FTS table.

### 5. Run Statistics

Test:

- column overview
- NULL handling
- text lengths
- numeric fields
- distinct values

### 6. Test FTS

If the database contains FTS5, test its search functionality.

### 7. Test SQL Console

Run simple read-only queries.

### 8. Test specialized tools

For text databases:

```text
Corpus Lab
Quality Investigator
Investigation
```

### 9. Export a report

Check that report generation works.

### 10. Record compatibility findings

Add the database type and any unusual behavior to the compatibility matrix.

---

# Safety

JASS SQLite Explorer is designed for inspection, but users should still work carefully with important databases.

Recommended practice:

- Keep backups of important databases.
- Prefer opening a copy of a critical database.
- Do not experiment with unknown destructive SQL.
- Remember that SQL extensions and SQLite features can vary.
- Treat recovered databases as potentially damaged until integrity has been checked.

The application itself is intended to remain read-only.

---

# Known Limitations

The current version is an exploratory compatibility baseline.

Some SQLite features have not yet been systematically tested, including:

- complex views
- triggers
- WAL databases
- BLOB-heavy databases
- WITHOUT ROWID tables
- unusual collations
- attached databases
- encrypted SQLite databases
- corrupted database files
- extremely large BLOB values
- application-specific virtual tables
- specialized SQLite extensions

Corpus analysis is also intentionally diagnostic.

It should not be interpreted as:

- a linguistic gold standard
- a language-quality certification
- a corpus contamination proof
- a replacement for expert linguistic analysis

---

# Development Lessons

The real-world databases used during development revealed several important engineering requirements.

### Never assume table names

A query designed for:

```text
entries
```

must not be blindly executed against:

```text
sentences
```

The Explorer should always use the currently selected table and its actual schema.

### Do not assume DISTINCT is cheap

On millions of rows:

```sql
SELECT COUNT(DISTINCT text) FROM sentences;
```

can be expensive.

Large-table handling therefore needs a distinction between:

```text
FAST / DEFERRED
```

and:

```text
DEEP / EXACT
```

analysis.

### Do not assume every column has exact distinct statistics

For large databases, a column profile may legitimately report:

```text
Distinct: deferred
```

rather than freezing the application while calculating it.

### Unicode matters

A database can contain multilingual data even when the schema itself is completely ordinary SQLite.

SQLite Explorer therefore treats Unicode as a first-class inspection concern.

---

# Roadmap

Future development should prioritize compatibility rather than endless feature expansion.

Possible future test stages:

## Compatibility Stage

- Views
- Triggers
- Foreign keys
- WITHOUT ROWID
- WAL
- BLOBs
- numeric datasets
- empty databases
- databases containing only indexes
- databases with unusual schemas

## Investigation Stage

- Database comparison
- Schema comparison
- Query execution timing
- Index effectiveness inspection
- Query plan viewer
- `EXPLAIN QUERY PLAN`
- SQLite pragma inspector
- page-level diagnostics

## Data Quality Stage

- Missing-value analysis
- Duplicate analysis
- Outlier detection
- Encoding anomalies
- suspicious text patterns
- BLOB statistics
- date/time detection
- numeric distribution

## Reporting Stage

- HTML reports
- PDF reports
- database compatibility reports
- machine-readable audit reports
- comparison reports

---

# Project Philosophy

JASS SQLite Explorer follows a simple principle:

> **Explore first. Modify never. Understand before acting.**

The application is intended to be a practical instrument for understanding SQLite databases encountered in real projects rather than being tied to one particular dataset.

The current 1.7.x milestone should therefore be considered a **compatibility and investigation baseline**.

---

## License

Choose a project license before publishing the repository publicly.

MIT is a practical option for a small standalone utility if you want broad reuse:

```text
MIT License
Copyright (c) JASS Tools
```

Add the complete license text to a separate `LICENSE` file before release.

---

## Status

**JASS SQLite Explorer 1.7.0**

Current status:

**Functional — Compatibility Testing Baseline**

The application has successfully been exercised against substantially different SQLite databases, including a 4-million-row multilingual corpus and a 534K-row transliteration dataset.

The next major milestone should be broader **SQLite compatibility testing**, not simply adding more UI features.
