# JASS Folder Intelligence Studio v1.0

**Inspect • Understand • Measure • Report**

JASS Folder Intelligence Studio is a lightweight, local-first PySide6 application for understanding what is consuming space inside a folder.

It is deliberately **read-only**. The scanner does not delete, move, rename or modify files.

## Features

### 🔎 Folder Scanner
- Choose any folder
- Recursive or non-recursive analysis
- Include/exclude hidden files
- Maximum scan depth
- Background scanning
- Stop button
- Permission/error handling
- Symlinks skipped to avoid recursive surprises
- Common generated/dependency directories skipped during recursive scans

### 🏠 Dashboard
Shows:
- Total files
- Directories discovered
- Total storage
- Average file size
- Number of file types
- Largest file
- Text/code file count
- Access errors
- Storage by category

### 📄 File Explorer
Search/filter by:
- filename
- path
- extension
- file category

Categories:
- Text / Code
- Image
- Audio
- Video
- Document
- Archive
- Executable
- Other

Sort by:
- Size
- Name
- Modified time
- Extension

Double-click opens a file. Context menu provides:
- Open
- Open containing folder
- Copy path

### 📊 File Type Analysis
Displays:
- extension
- file count
- total size
- percentage of scanned storage

### 📦 Largest Files
Top:
- 25
- 50
- 100
- 250
- 500

Shows filename, size, type, modified time and full path.

### 🌳 Structure
Tree view of discovered directories with depth, modification time and path.

### 📋 Reports
Export:
- JSON
- CSV
- readable TXT report

## Safety

This application is designed as an **analysis tool**, not a cleanup tool.

It does not:
- delete files
- move files
- rename files
- overwrite files
- change permissions
- follow symbolic links
- modify the scanned folder

The only write operations are the reports/projects that you explicitly choose to export.

## Installation — MX Linux / Debian

```bash
sudo apt update
sudo apt install python3 python3-pip
python3 -m pip install PySide6
```

Run:

```bash
python3 JASS_Folder_Intelligence_Studio_v1.0.py
```

## Recommended Usage

Start with a normal user-owned directory:

```text
/home/jasvir/Downloads
/home/jasvir/Documents
/home/jasvir/Projects
```

For very large filesystems, begin with a smaller directory and then expand the scan.

Scanning `/` can encounter virtual filesystems such as `/proc`, `/sys` and `/run`, as well as restricted directories. Permission errors are recorded rather than treated as fatal.

## Performance

The scanner uses `os.scandir()` and a background `QThread` so the GUI remains responsive.

For very large trees, the Files and Largest tabs intentionally display a manageable subset of rows while the complete scan information remains available for reports.

## Roadmap — v2.0

Potential upgrades:

- True storage treemap
- Folder size aggregation
- Folder-to-folder comparison
- Duplicate file detection
- Empty folder detection
- Old/stale file analysis
- File age distribution
- Size distribution charts
- Extension heatmap
- Interactive directory hierarchy
- Mount/filesystem awareness
- Exclude/include pattern editor
- Custom skip lists
- Scan profiles
- Saved scan snapshots
- Compare two snapshots
- Growth/change analysis
- SHA-256 duplicate verification
- Hard-link detection
- MIME detection
- Archive contents analysis
- CSV/JSON import
- HTML/PDF reports
- Dark theme
- Charts and visual dashboard
- Optional read-only disk overview

## Suggested Repository

```text
JASS-Folder-Intelligence-Studio/
├── JASS_Folder_Intelligence_Studio_v1.0.py
├── README.md
└── examples/
```

## License

Choose the license appropriate for your repository.

---

**JASS Folder Intelligence Studio**  
*Know your folders before you change them.*
