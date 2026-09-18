# 🏺 JASS Project Archaeologist

**JASS Project Archaeologist** is a beautiful, read-only PySide6 desktop workbench for understanding an existing software project.

It is designed for the moment when a project has accumulated years of code, experiments, generated files, old folders, Git history, and forgotten components — and you want to **excavate the project before changing it**.

> **Archaeology before reconstruction.**

## ✨ What it does

### 📊 Project Overview
After a scan it summarizes:

- Total files
- Directories encountered
- Total disk footprint
- Source-file count
- Text-readable file count
- Number of extensions
- Largest file
- Access errors
- Scan duration
- File-type distribution

### 🧭 Project Explorer

Search and filter the complete scan by:

- Filename/path
- Source files
- Text files
- Large files (>10 MB)

Sort by:

- Path
- Size ascending
- Size descending
- Modified time
- Name

Right-click a file to:

- Copy its path
- Open its containing folder
- Inspect readable text

### 🌳 Structure View

Reconstructs the discovered project hierarchy as an expandable tree.

### 💻 Code Archaeology

Focuses on source files and shows:

- Filename
- Detected language/extension
- Approximate line count
- Size
- Full path

Double-click a source file to inspect its contents locally.

### ⛏ Git History

If the project contains `.git`, the application can inspect:

- Current branch
- HEAD commit
- Working-tree status
- Recent commits
- Remotes
- Tags
- Contributors

The Git inspection is read-only.

### 🕰 Timeline

Shows the most recently modified files, helping answer:

> What parts of this project are still alive?

### 📑 Reports

Generate a human-readable archaeology report and export raw scan data as:

- JSON
- CSV

## 🔐 Safety

JASS Project Archaeologist is intentionally **read-only**.

It does **not**:

- delete files
- rename files
- move files
- rewrite source code
- alter Git history
- run project code
- install dependencies
- upload project contents
- contact a cloud service

Git commands used by the Git History tab are informational commands only.

## 🧠 Why “Archaeologist”?

A mature project often contains several layers:

1. **Living code** — actively maintained components
2. **Legacy code** — old but still important components
3. **Experiments** — prototypes and trials
4. **Artifacts** — generated output and temporary material
5. **Dependencies** — environments and vendor trees
6. **History** — decisions preserved in Git
7. **Forgotten structures** — files nobody remembers creating

The goal is to make those layers visible before you begin refactoring.

## 🚀 Installation

On MX Linux / Debian:

```bash
sudo apt update
sudo apt install python3 python3-pyside6
```

If your distribution does not provide PySide6 through apt:

```bash
python3 -m pip install PySide6
```

## ▶️ Run

```bash
python3 JASS_Project_Archaeologist_v1.0.py
```

Or from Geany, open the `.py` file and run it.

## 🔎 Recommended first scan

For a very large project, start with:

- Depth: **3–5**
- Skip generated/dependency folders: **ON**

Then perform a deeper scan after understanding the first result.

## 📁 Files intentionally skipped

When **Skip generated / dependency folders** is enabled, common directories such as:

```text
.git
.venv
venv
node_modules
__pycache__
dist
build
.pytest_cache
.mypy_cache
.vscode
.idea
coverage
```

are excluded from traversal.

Turn the option off when you specifically want to investigate these areas.

## ⚙️ Technical design

- Python 3
- PySide6
- Standard library for scanning and reporting
- `os.walk()` for efficient recursive traversal
- Background `QThread` for scanning
- Optional local Git CLI inspection
- No database
- No cloud service
- No AI dependency
- No OpenCV
- No PyTorch

## ⚠️ Large projects

Scanning millions of files can consume considerable time and memory because the current release keeps file records in memory for interactive exploration.

For very large repositories, begin with a limited depth and excluded generated/dependency folders.

## 🗺️ Future roadmap

Potential future releases can add:

- Duplicate-file archaeology
- Empty-directory archaeology
- Dead-code indicators
- TODO/FIXME extraction
- Import/dependency graph
- Python module/class/function inventory
- Project health dashboard
- Git churn analysis
- Commit archaeology
- “Last touched” component analysis
- Stale-file detection
- Large-file hotspots
- Build-artifact detection
- Configuration inventory
- Documentation coverage
- Test-suite discovery
- Project fingerprinting
- Technology-stack detection
- Dependency manifests
- Virtual-environment detection
- Architecture map
- Interactive treemap
- “What changed?” snapshots
- Before/after project comparisons
- Markdown/HTML/PDF reports
- Optional local LLM analysis through Ollama/LM Studio

## 🧭 Philosophy

JASS Project Archaeologist follows a simple rule:

> **Understand the project before changing the project.**

It is intended to complement engineering workflows such as architecture reviews, repository audits, stabilization sprints, refactoring, migration planning, and project recovery.

---

**JASS Project Archaeologist v1.0**  
Local-first • Read-only • Privacy-conscious • PySide6
