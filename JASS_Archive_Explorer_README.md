# JASS Archive Explorer v1.0

**Browse • Inspect • Search • Preview**

JASS Archive Explorer is a lightweight, local-first PySide6 application for examining archive contents without extracting an entire archive first.

## Features

### 📦 Supported archives

Built-in Python support:
- ZIP
- TAR
- TAR.GZ / TGZ
- TAR.BZ2 / TBZ / TBZ2
- TAR.XZ / TXZ
- GZIP
- BZIP2
- XZ

Optional external-tool support:
- 7-Zip (`7z` / `7zz`)
- RAR (`unrar`)

### 🏠 Dashboard

Displays:
- archive name
- format
- archive size
- entry count
- file count
- directory count
- stored content size
- packed size
- expansion ratio
- backend used

### 📦 Contents

- Full member listing
- filename/path filter
- Files / Directories filter
- sort by name
- sort by stored size
- sort by packed size
- file category detection
- modified time where available

### 🌳 Structure

Builds an interactive directory tree from archive member paths.

### 🔎 Search

Search archive members by filename/path.

### 👁 Text Preview

Double-click a text/code member in ZIP/TAR archives to preview it without extracting the whole archive.

The preview is capped at approximately 2 MB.

### 📋 Reports

Export:
- JSON
- CSV
- readable TXT report

## Installation — MX Linux / Debian

```bash
sudo apt update
sudo apt install python3 python3-pip
python3 -m pip install PySide6
```

Run:

```bash
python3 JASS_Archive_Explorer_v1.0.py
```

### Optional 7-Zip support

```bash
sudo apt install p7zip-full
```

Depending on your Debian/MX Linux repository version, the executable may be `7z` or `7zz`; the application detects either.

### Optional RAR support

```bash
sudo apt install unrar
```

## Safety

JASS Archive Explorer is **read-only** with respect to the archive.

It does not:
- modify archives
- delete members
- rename members
- overwrite archives
- automatically extract archives

Opening an archive reads its metadata and, for supported text previews, reads selected member content.

## Performance

ZIP and TAR archives are inspected using Python's standard library.

For very large archives, the application keeps the GUI responsive while the archive is being read.

The table displays up to 10,000 matching rows at once to keep the interface practical.

## Important v1.0 limitation

ZIP/TAR-family archives receive the richest inspection and text-preview support.

7-Zip and RAR support depends on external command-line tools and their installed versions. v1.0 focuses on listing/inspection rather than archive modification.

## Roadmap — v2.0

- Archive-to-archive comparison
- Nested archive detection
- Archive integrity/test operation
- Duplicate member detection
- Compression-ratio analysis
- File-type statistics
- Size distribution charts
- Search by extension/type/size
- Archive bookmarks
- Recent archives
- Persistent history
- Safe selective extraction
- Extract selected files
- Extract to chosen folder
- Conflict preview before extraction
- Password-protected archive detection
- Password prompt for supported formats
- Checksums
- MIME detection
- Embedded archive inspection
- TAR permissions/owner/group display
- ZIP compression method names
- HTML/PDF reports
- Drag-and-drop archive opening
- Dark theme
- Archive creation as a separate explicit workflow

## Suggested Repository

```text
JASS-Archive-Explorer/
├── JASS_Archive_Explorer_v1.0.py
├── README.md
└── examples/
```

**JASS Archive Explorer**  
*Open the archive. Understand what is inside.*
