# JASS Quote Harvester v1.0

**JASS Quote Harvester** is a local-first PySide6 application for discovering, reviewing, curating and exporting potentially quotable passages from your own local books, documents and notes.

It is designed as a companion to a personal literature/research collection.

> **Harvest broadly → Verify the source → Curate deliberately**

## What it does

JASS Quote Harvester scans:

- TXT
- Markdown
- HTML
- EPUB
- PDF (optional PyMuPDF)

It detects two broad classes of material:

1. **Explicit quotations** — text enclosed in common quotation marks.
2. **Quote candidates** — sentences that meet conservative length and linguistic heuristics.

The application does **not** claim that a candidate is an authentic quotation or identify an author unless that information is present in the source metadata.

---

## Features

### 📚 Source harvesting

- Select a single document or a folder
- Recursive folder scanning
- Maximum file limit
- Candidate-score threshold
- Explicit-quotation-only mode
- Background processing
- Stop button
- Error counting
- Duplicate suppression within each source

### 📖 Supported formats

| Format | Support |
|---|---|
| TXT | Native |
| Markdown | Native |
| HTML | Native |
| EPUB | Native stdlib ZIP/XML |
| PDF | Optional PyMuPDF |

PDF support:

```bash
python3 -m pip install PyMuPDF
```

No OCR is required in v1.0.

---

## 🔎 Quote detection

### Explicit quotations

The scanner recognizes common forms such as:

```text
“Knowledge is power.”
"Knowledge is power."
‘Knowledge is power.’
```

Longer quoted passages are also recognized.

### Candidate extraction

Unquoted sentences receive a heuristic score based on factors such as:

- Reasonable sentence length
- Quote-like wording
- Reflective language
- Advice or imperative language
- Rhetorical punctuation
- Questions/exclamations
- Words associated with themes such as life, love, truth, hope and freedom

The score is **not an AI confidence score**.

It simply helps prioritize material for human review.

---

## ⭐ Quote Library

Every harvested quote can be:

- Searched
- Filtered by score
- Filtered to favorites
- Viewed
- Edited
- Tagged
- Annotated with notes
- Copied
- Exported individually

Columns:

```text
Favorite
Score
Quote
Author
Source
Location
Tags
Notes
```

---

## ✍️ Quote Card / Editor

For each selected passage you can edit:

- Quote text
- Author
- Tags
- Notes
- Favorite status

The source path and extraction location remain visible.

This makes the tool useful not only for harvesting but also for building a curated quotation collection.

---

## 📊 Dashboard

The dashboard provides:

- Sources processed
- Quotes harvested
- Favorites
- Total quote words
- Errors
- Average quote score
- Source distribution
- Quote-signal categories

---

## 🗂️ Collections

Starter views include:

- Favorites
- Explicit Quotations
- High Score (80+)
- Wisdom / Reflection
- Love / Relationships
- Life / Time
- Hope / Freedom

These are lightweight discovery views rather than authoritative literary classifications.

---

## 📄 Reports

Export your quote library as:

### JSON

Best for:

- Programmatic processing
- Future database import
- RAG pipelines
- Backup

### CSV

Best for:

- Excel/LibreOffice
- Filtering
- Sorting
- Spreadsheet workflows

### TXT

Best for:

- Human reading
- Simple archives
- Sharing a curated selection

Individual quotes can also be exported.

---

# Installation

On MX Linux / Debian:

```bash
sudo apt update
sudo apt install python3 python3-pip
python3 -m pip install PySide6
```

Optional PDF support:

```bash
python3 -m pip install PyMuPDF
```

Run:

```bash
python3 JASS_Quote_Harvester_v1.0.py
```

---

# Recommended workflow

For a large literature collection:

### Step 1 — Start small

Test with:

```text
~/Documents/Books/Test
```

### Step 2 — Harvest explicit quotations

Enable:

```text
Explicit quotations only
```

This produces a high-precision starting collection.

### Step 3 — Broaden discovery

Turn explicit-only off and lower/raise the candidate threshold.

For example:

```text
Candidate score: 38
```

### Step 4 — Review

Open the Quote Library and inspect:

- wording
- source
- location
- author
- context

### Step 5 — Curate

Add:

- tags
- notes
- favorites

### Step 6 — Export

Save JSON/CSV for future processing.

---

# Important accuracy limitation

JASS Quote Harvester is **not an attribution engine**.

For example, if a sentence looks like a famous quotation, JASS does not automatically claim:

```text
— Albert Einstein
```

unless that information comes from the source.

Similarly, a sentence that looks quotable may simply be ordinary prose.

Always verify:

1. Exact wording
2. Source
3. Location
4. Author
5. Context

before publishing or attributing a quotation.

---

# Copyright consideration

Quote harvesting can surface copyrighted passages.

Use the application primarily with material you are entitled to process.

The software does not determine whether a particular quotation or amount of quoted text is legally permissible to reproduce.

The safest workflow is to use it as a **research and personal curation tool**, retaining provenance back to the original source.

---

# Privacy / local-first model

The application:

- Does not upload documents
- Does not contact quotation websites
- Does not use cloud APIs
- Does not require an account
- Does not modify source documents
- Does not delete source documents
- Does not require an AI model

Your source books and documents remain on your machine.

---

# Architecture

```text
                 JASS Quote Harvester
                         │
          ┌──────────────┴──────────────┐
          │                             │
     Source Readers                Quote Engine
          │                             │
   ┌──────┼──────┐                ┌─────┴─────┐
   │      │      │                │           │
  TXT   EPUB   HTML              Explicit   Candidate
   │      │      │               Quotes      Scoring
   └──────┼──────┘                    │
          │                           │
         PDF                    Deduplication
          │                           │
          └────────────┬──────────────┘
                       │
                 Quote Library
                       │
          ┌────────────┼────────────┐
          │            │            │
       Search       Curate       Export
          │            │            │
          └────────────┼────────────┘
                       │
                 JSON / CSV / TXT
```

---

# Roadmap

## v1.1 — Persistent Quote Library

- SQLite database
- Persistent favorites
- Persistent tags
- Persistent notes
- Collections
- Quote IDs
- Import existing JSON/CSV
- Backup/restore

## v1.2 — Provenance

- Book title
- Author
- Publisher
- ISBN
- Language
- Chapter
- Page
- EPUB spine position
- PDF page number
- Source hash
- Citation fields

## v1.3 — Multilingual Harvesting

Especially useful for a multilingual literature collection:

- English
- Punjabi Gurmukhi
- Punjabi Shahmukhi
- Mizo
- Hindi
- Assamese
- Bengali
- Tamil
- Telugu

Improvements would include language-aware sentence segmentation and Unicode-aware rules.

## v1.4 — Quote Studio

- Beautiful quote cards
- Background templates
- Typography
- Author styling
- Multiple export sizes
- PNG/JPEG
- Batch quote-card generation

This could integrate naturally with **JASS Quote & Poster Studio**.

## v1.5 — Research Tools

- Context window around quote
- Concordance
- Keyword-in-context
- Source comparison
- Duplicate/similar quote detection
- Quote provenance viewer
- Citation generator
- Bibliography export

## v2.0 — Local Semantic Quote Intelligence

Optional integration with:

- Ollama
- LM Studio
- Local embeddings
- Semantic search
- RAG
- Theme discovery
- Similar quotation search
- Context-aware quote discovery

The AI layer would remain optional; the core harvester remains usable without it.

---

# Safety principle

JASS Quote Harvester is intentionally built around:

> **Harvest → Verify → Curate → Cite**

It should help you discover useful passages without pretending that heuristic extraction is authoritative literary attribution.

---

## License

Choose the license appropriate for your JASS repository, such as MIT, before publishing.
