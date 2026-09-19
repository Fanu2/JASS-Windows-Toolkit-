# JASS Document Laboratory v1.0

**JASS Document Laboratory** is a local-first, read-only PySide6 workstation for investigating document collections.

It is designed as a practical bridge between file inspection, literature research and future Athena document-ingestion workflows.

## Supported formats

- PDF — optional PyMuPDF
- EPUB — standard-library ZIP/XML/HTML processing
- TXT
- Markdown / MD
- HTML / HTM
- DOCX — optional python-docx

## Features

### Library

- Recursive document scanning
- Current-folder-only scanning
- Format filtering
- Name/path filtering
- File size
- Word count
- Character count
- Paragraph count
- Heading count
- Modified time
- Extraction-error reporting
- Background scanning
- Stop operation

### Reader

- Local text extraction
- Large-text preview
- Font-size control
- Copy all extracted text
- Export extracted text
- PDF page markers
- EPUB chapter markers
- DOCX paragraph/table extraction

### Search

- Search across indexed documents
- Context snippets
- Match position
- Bounded result count
- Copyable results
- Double-click result to open the document

### Statistics

Per-document and collection-level statistics include:

- words
- characters
- lines
- paragraphs
- headings
- URLs
- email addresses
- repeated-line surplus
- maximum line length
- language/script hints

### Research Notes

Session-local notes can be associated with individual documents.

v1.0 intentionally does **not** modify the source documents or maintain a permanent notes database.

### Reports

Export the document inventory as:

- CSV
- JSON
- TXT

## Read-only design

The source collection is never modified.

The application does not:

- rename documents
- move documents
- delete documents
- overwrite source documents
- upload documents
- use cloud services
- require an AI model
- require a database server

Export operations create new files.

## Installation

Basic:

```bash
python3 -m pip install PySide6
```

PDF support:

```bash
python3 -m pip install PyMuPDF
```

DOCX support:

```bash
python3 -m pip install python-docx
```

## Run

```bash
python3 JASS_Document_Laboratory_v1.0.py
```

## Important performance note

Library scanning extracts document text to calculate statistics. Very large PDF/EPUB/DOCX collections can therefore take time.

Search also extracts documents locally when a search is executed. v1.0 deliberately favors correctness and simple local operation over a permanent full-text index.

## Current limitations

- Research notes are session-local.
- Search is not backed by SQLite/FTS yet.
- PDF rendering is not included; extracted text is used.
- EPUB covers and metadata are not yet catalogued.
- DOCX tables are extracted as text.
- No persistent bookmarks or reading progress.
- No semantic/vector search.
- No OCR.
- No cloud synchronization.

## Roadmap

Potential future versions:

### v1.1 — Document Intelligence

- persistent SQLite document catalog
- persistent notes
- bookmarks
- reading progress
- document metadata
- page/section navigation
- better EPUB metadata
- PDF page thumbnails
- table detection
- document comparison

### v1.2 — Research Workspace

- saved searches
- quotation extraction
- citations
- annotations
- collections
- tags
- bibliography export
- Markdown/HTML research reports

### v1.3 — Corpus Intelligence

- multilingual normalization
- character/script analysis
- duplicate document detection
- near-duplicate detection
- repeated passage detection
- concordance
- n-grams
- frequency analysis

### Future — Athena Integration

- document ingestion service
- chunking
- metadata extraction
- citation resolver
- retrieval preparation
- local embedding providers
- optional Ollama/LM Studio integration

## Status

**v1.0 — Document Laboratory Foundation**

Local-first • privacy-conscious • read-only • modular
