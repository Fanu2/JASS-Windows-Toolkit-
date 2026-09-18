# 📖 JASS Literature Explorer

**JASS Literature Explorer** is a local-first PySide6 desktop application for building, browsing, reading, searching and researching a personal literature collection.

It is designed for large collections of EPUBs, PDFs, TXT files, Markdown books and HTML literature.

## ✨ Features

### 🏠 Dashboard
- Library item count
- Total library size
- Format count
- Favorite count
- Supported-format summary

### 📚 Library
Recursively scan a literature folder and discover:

- EPUB
- PDF
- TXT
- Markdown
- HTML

Features:

- Search by filename/path
- Format filter
- Favorites-only view
- Sortable library table
- Right-click actions
- Open containing folder

### 📖 Reader
Local reading view with:

- TXT / Markdown
- HTML text extraction
- EPUB chapter extraction
- PDF text extraction when PyMuPDF is installed
- Adjustable font size
- Favorite books

### 🔎 Full-Text Search
Search inside readable books and display:

- Matching book
- Search term
- Surrounding context
- Full path

The search is performed locally.

### 📝 Research Notes
Attach notes to individual books during the current session.

Useful for:

- Themes
- Quotations
- Characters
- Research observations
- Questions
- Reading notes

### 🗂 Collections
Starter collection categories are included for organizing a literature workflow:

- Romance
- Poetry
- Classics
- Philosophy
- History
- Punjabi
- Shahmukhi
- Mizo
- Hindi
- Research

### ℹ️ Book Details
Shows:

- filename
- path
- format
- size
- modified time
- character count
- word count
- paragraph count
- EPUB/PDF details when available

### 📑 Reports
Export library information to:

- JSON
- CSV
- readable report

## 🔐 Privacy & safety

JASS Literature Explorer is deliberately local-first.

It does not:

- upload books
- use cloud APIs
- modify your books
- rename files
- move files
- delete files
- modify EPUB/PDF contents
- require an online account

Scanning is read-only.

## 🚀 Installation

### MX Linux / Debian

```bash
sudo apt update
sudo apt install python3 python3-pyside6
```

If PySide6 is unavailable through your distribution:

```bash
python3 -m pip install PySide6
```

### Optional PDF support

For extracting text from PDFs:

```bash
python3 -m pip install PyMuPDF
```

EPUB support in v1.0 uses Python's standard library, so no EPUB-specific dependency is required.

## ▶️ Run

```bash
python3 JASS_Literature_Explorer_v1.0.py
```

## 📁 Recommended library layout

For example:

```text
Literature/
├── English/
│   ├── Classics/
│   ├── Romance/
│   └── Poetry/
├── Punjabi/
│   ├── Gurmukhi/
│   └── Shahmukhi/
├── Mizo/
├── Hindi/
└── Research/
```

The application does not require this structure; it is simply a useful organization scheme.

## 🧭 Suggested workflow

1. Create or select your literature root folder.
2. Click **Scan Library**.
3. Review the Dashboard.
4. Use Library filters to narrow the collection.
5. Double-click a book.
6. Read it in the Reader.
7. Search important phrases in Full-Text Search.
8. Record observations in Research Notes.
9. Export a JSON/CSV inventory when required.

## ⚠️ Large collections

The first release keeps discovered files in memory for interactive browsing.

For extremely large collections:

- scan a parent category separately
- keep generated/dependency-folder skipping enabled
- avoid scanning unrelated system directories
- split very large collections into logical libraries

## 🛠 Technical design

- Python 3
- PySide6
- Standard library for scanning
- Standard-library EPUB ZIP/XML/HTML processing
- Optional PyMuPDF for PDFs
- Background QThread library scan
- Local text search
- No database required
- No AI dependency
- No cloud service

## 🗺️ Future roadmap

The project is deliberately positioned to grow into a serious literature research environment.

### v1.x
- persistent library database
- persistent favorites
- persistent notes
- reading progress
- bookmarks
- recent books
- table-of-contents navigation
- EPUB chapter navigation
- PDF page navigation
- cover extraction
- thumbnail grid
- duplicate-book detection
- metadata editing

### v2.x
- author/title/year metadata extraction
- ISBN detection
- language detection
- genre tagging
- advanced collections
- smart collections
- saved searches
- reading statistics
- quotation manager
- annotation system
- bibliography generation
- citation export
- Markdown research notebooks

### Research Intelligence
Possible integration with the wider JASS/Athena ecosystem:

- semantic search
- local embeddings
- RAG
- citation resolver
- passage-level citations
- cross-book thematic search
- multilingual search
- Punjabi/Gurmukhi/Shahmukhi support
- Mizo literature corpus exploration
- concordance
- frequency analysis
- collocations
- named-entity extraction
- literary timeline
- character index
- local Ollama/LM Studio integration

## 🧠 Design philosophy

JASS Literature Explorer follows:

> **Library first. Reading second. Research third. Intelligence only when useful.**

The application is intended to remain useful as a conventional offline literature manager even if AI features are never enabled.

---

**JASS Literature Explorer v1.0**  
Local-first • Offline-friendly • Read-only • PySide6
