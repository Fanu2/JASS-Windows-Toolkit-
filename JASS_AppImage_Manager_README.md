# 📦 JASS AppImage Manager

**JASS AppImage Manager** is a local-first PySide6 desktop application for discovering, cataloguing, inspecting, launching and integrating AppImage applications on Linux.

It is designed especially for users who keep portable applications in folders such as `~/Applications`, `~/AppImages`, `~/Downloads` or `~/.local/bin`.

## ✨ Features

### 📊 Dashboard
Shows:

- AppImage count
- Total storage consumed
- Executable vs non-executable files
- Files with recognizable version strings
- Number of locations
- Potential duplicate application names

### 📦 AppImage Library
Scan one or more directories and build an interactive inventory.

Search by:

- application name
- filename
- version
- path

Filter:

- all
- executable
- not executable

Sort by:

- name
- size
- modification time
- version

Double-click an item to launch it.

### 🔍 Inspector
Inspect:

- application name
- filename
- guessed version
- complete path
- file size
- modification time
- executable status
- Unix permissions
- detected file type

Actions:

- Launch
- Open containing folder
- Calculate SHA-256
- Make executable

### 🧬 Duplicate Analysis
Groups AppImages by normalized application name to help discover:

- multiple versions
- copies in different directories
- old downloads
- parallel portable installations

This is **analysis only**. The application does not automatically delete anything.

### 🖥 Desktop Integration
Create a `.desktop` launcher under:

```text
~/.local/share/applications/
```

This allows an AppImage to appear in the Linux desktop application menu.

The launcher action is explicit; scanning itself never creates desktop files.

### 📑 Reports
Export:

- JSON inventory
- CSV inventory
- readable report

## 🔐 Safety model

JASS AppImage Manager is intentionally conservative.

### Scanning does not modify files

The scanner only reads:

- filenames
- file size
- modification time
- permissions
- executable bit

### Launching is explicit

An AppImage is never launched automatically.

You must explicitly:

- double-click an AppImage, or
- choose Launch.

### Permission changes are explicit

**Make Executable** changes only the Unix executable bits of the selected file.

Use it only for an AppImage you trust.

### Desktop integration is explicit

Creating a `.desktop` launcher is the only other normal file-writing operation.

The application does not:

- delete AppImages
- rename AppImages
- move AppImages
- extract AppImages
- update applications
- install packages
- upload files
- use cloud services

## 🚀 Installation

On MX Linux / Debian:

```bash
sudo apt update
sudo apt install python3 python3-pyside6
```

Or, where appropriate:

```bash
python3 -m pip install PySide6
```

## ▶️ Run

```bash
python3 JASS_AppImage_Manager_v1.0.py
```

## 📁 Suggested AppImage organization

A clean structure could be:

```text
~/Applications/
├── Browsers/
├── Editors/
├── Multimedia/
├── Graphics/
├── Utilities/
├── Development/
└── Other/
```

The manager does not require this structure.

## 🔎 Recommended workflow

1. Put AppImages in one or more folders.
2. Select the folder in JASS AppImage Manager.
3. Enable **Recursive** if subfolders should be scanned.
4. Click **Scan**.
5. Review the Dashboard.
6. Inspect individual AppImages.
7. Use SHA-256 when you need a file fingerprint.
8. Make trusted files executable when necessary.
9. Create desktop launchers for applications you want integrated into the menu.
10. Export JSON/CSV for archival or inventory purposes.

## ⚠️ Important security note

An AppImage is executable software.

Only launch AppImages from sources you trust and verify downloads when appropriate.

JASS AppImage Manager does not attempt to determine whether an AppImage is safe.

## 🧠 Why build this?

AppImages are convenient, but collections can quickly become messy:

```text
Firefox.AppImage
Firefox-120.AppImage
Firefox-121.AppImage
Firefox-latest.AppImage
Firefox (1).AppImage
old/Firefox.AppImage
Downloads/Firefox.AppImage
```

The manager turns that collection into an observable inventory.

It is particularly useful for:

- portable application collections
- offline software archives
- testing multiple versions
- maintaining an application library
- identifying redundant copies
- creating desktop integration

## 🗺️ Future roadmap

### AppImage intelligence

- AppImage Type 1 / Type 2 identification
- embedded AppImage metadata
- desktop-file extraction
- icon extraction
- application ID detection
- embedded version detection
- architecture detection
- runtime information
- AppImageKit metadata
- signature/hash verification helpers

### Library management

- persistent SQLite database
- categories
- tags
- favorites
- notes
- application icons
- version history
- update tracking
- archive locations
- broken-file detection
- missing-file detection

### Version archaeology

- group versions of the same application
- compare file hashes
- identify identical copies
- identify probable old versions
- side-by-side version comparison

### Desktop integration

- update existing launchers
- remove manager-created launchers
- icon extraction
- category selection
- application menu refresh
- portable launcher profiles

### Advanced Linux integration

- AppImageLauncher-compatible workflows
- MIME associations
- terminal launch
- environment-variable profiles
- working-directory profiles
- sandbox/policy inspection
- architecture compatibility checks

### JASS ecosystem

Potential integration with:

- **JASS Disk Space Observatory**
- **JASS Project Archaeologist**
- **JASS File Analyzer**
- **JASS Linux System Observatory**
- **JASS Downloads Intelligence**

This would eventually allow an AppImage to be traced from:

**download → storage → application → disk footprint → project/library inventory**

## 🧭 Philosophy

> **Inventory first. Understand second. Integrate third.**

The manager deliberately avoids becoming an automatic package installer or cleaner.

You remain in control of every meaningful action.

---

**JASS AppImage Manager v1.0**  
Local-first • Linux-focused • PySide6 • Safety-conscious
