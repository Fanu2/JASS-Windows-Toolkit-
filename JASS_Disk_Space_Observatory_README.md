# JASS Disk Space Observatory v1.0

A local-first PySide6 disk-usage analyzer for Linux. It helps answer: **where is my disk space going?**

## Highlights

- Beautiful desktop dashboard
- Mounted-filesystem overview
- Folder/file analysis
- Recursive scanning
- Optional hidden-file inclusion
- Unlimited or controlled scan depth
- Background scanning with Stop
- Largest files
- File-type/storage breakdown
- Search and filtering
- Sorting by size, name or modified time
- Folder hierarchy view
- Treemap visualization
- Percentage of analyzed storage
- Modified timestamps
- Read-only context actions
- Copy path
- Open containing directory
- CSV export
- JSON export
- Human-readable report
- No database
- No cloud services
- No deletion/move/rename operations

## Safety

This application is deliberately **read-only**.

It does not delete, move, rename, compress, modify or clean files. It only reads filesystem metadata and directory entries.

Symlinks are skipped to avoid accidentally following links outside the selected tree.

## Requirements

- Linux
- Python 3.10+
- PySide6

Install PySide6:

```bash
python3 -m pip install PySide6
```

Run:

```bash
python3 JASS_Disk_Space_Observatory_v1.0.py
```

## Main views

### Dashboard
Shows mounted filesystems and their total/used/free space.

### Explorer
Search, filter and sort every discovered file/folder.

### Hierarchy
Displays the scanned directory structure with aggregate sizes.

### Treemap
Visualizes the largest top-level items. Larger rectangles represent more storage.

### File Types
Groups files by extension and reports file count and storage percentage.

### Largest Files
Quickly locate the largest files in the scanned tree.

### Report
Produces a concise text report and supports CSV/JSON export.

## Recommended first scan on MX Linux

For a quick look at your home directory:

```text
/home/jasvir
```

For the entire root filesystem, use:

```text
/
```

The root scan may encounter protected directories and therefore can produce warnings or skip inaccessible locations.

## Design philosophy

JASS Disk Space Observatory is intended to be a safe diagnostic companion to file-management tools. It answers **what is consuming space** without making changes to the filesystem.

Future releases can add:

- true proportional nested treemap layouts
- duplicate-file analysis
- extension heatmaps
- directory age analysis
- cache/temp detection
- Docker storage inspection
- Flatpak/AppImage/storage analysis
- mount/device health panels
- inode usage
- hard-link awareness
- permissions/error reporting
- filesystem comparison
- historical snapshots
- scan caching
- interactive drill-down treemap
- safe cleanup suggestions (still requiring explicit confirmation)
