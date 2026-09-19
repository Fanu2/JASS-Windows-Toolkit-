# JASS Document Laboratory v1.1

JASS Document Laboratory v1.1 adds a **persistent local research workspace** to the v1.0 document inspection foundation.

## Major v1.1 addition

A small SQLite database is created inside the selected document folder:

```text
.jass_document_laboratory.sqlite3
```

The database stores the document inventory, notes, bookmarks, quotations and an FTS5 search index.

The source documents themselves remain untouched.

## Persistent Library

The SQLite catalog stores:

- document path
- filename
- extension
- size
- modified time
- word count
- character count
- paragraph count
- heading count
- extraction status
- last-opened time

Repeated scans update the catalog rather than creating duplicate document rows.

## SQLite FTS5 Search

Search now uses a local SQLite FTS5 index.

Benefits:

- fast repeated searches
- context snippets
- Unicode-aware tokenization
- local-only processing
- no cloud service
- no AI model

The FTS index is rebuilt/updated during scanning.

## Persistent Research Notes

Notes are now stored in SQLite rather than being session-only.

Each document can have its own persistent research note.

## Bookmarks

Save:

- label
- page/chapter/location

Bookmarks are stored persistently and displayed in a copyable table.

## Quotations

Save quotations with:

- source document
- quotation
- page/chapter/location
- timestamp

The quotation library is persistent and copyable.

## Reader

The v1.0 reader remains available:

- PDF
- EPUB
- TXT
- Markdown
- HTML
- DOCX
- font sizing
- copy all text
- export extracted text

## Reports

Document inventory can still be exported as:

- CSV
- JSON
- TXT

## Read-only source policy

JASS Document Laboratory does not modify the source document collection.

It does create its own local SQLite research database in the selected folder.

It does not:

- rename source documents
- move source documents
- delete source documents
- overwrite source documents
- upload documents
- use cloud services
- require an AI model

## Installation

```bash
python3 -m pip install PySide6
```

Optional PDF:

```bash
python3 -m pip install PyMuPDF
```

Optional DOCX:

```bash
python3 -m pip install python-docx
```

## Run

```bash
python3 JASS_Document_Laboratory_v1.1.py
```

## v1.1 Architecture

```text
Document Files
     │
     ▼
Document Extractors
     │
     ▼
Document Statistics
     │
     ├── Library Catalog ── SQLite
     ├── FTS5 Search Index
     ├── Research Notes
     ├── Bookmarks
     └── Quotations
```

## Current limitations

- Search is lexical FTS5, not semantic search.
- Research notes are plain text.
- Bookmarks do not yet jump to exact PDF/EPUB positions.
- PDF rendering/page thumbnails are not included.
- EPUB TOC/metadata browser is not yet included.
- No OCR.
- No vector database.
- No AI dependency.

## Roadmap

### v1.2 — Advanced Research Workspace

- true document/page navigation
- EPUB TOC
- PDF page thumbnails
- reading progress
- favorites/tags
- saved searches
- quotation editor
- citation styles
- Markdown research export

### v1.3 — Corpus Intelligence

- word frequencies
- n-grams
- concordance
- duplicate passages
- near-duplicate documents
- multilingual normalization
- language detection
- Unicode diagnostics

### Future

- citation resolver
- chunking
- retrieval preparation
- local embeddings
- optional Ollama/LM Studio providers
- Athena document-import integration

## Status

**v1.1 — Persistent Research Workspace checkpoint**

Local-first • privacy-conscious • read-only source handling • SQLite-backed research
