# JASS Windows Toolkit

A collection of practical **Python desktop utilities, file-management tools, developer helpers, privacy tools, research utilities, and personal productivity applications** developed under the JASS project.

The repository is intended primarily for **Windows users**, with many applications built using **Python and PySide6**. Most tools are standalone scripts and can be used independently.

> **JASS** is a personal software toolkit focused on practical, lightweight utilities rather than a single large application.

---

## 📦 What's in the Toolkit

The repository contains a growing collection of independent applications.

### 📁 File & Folder Management

| Application | Purpose |
|---|---|
| **JASS File Organizer Pro** | Organize files into structured folders |
| **JASS Duplicate File Remover** | Find and remove duplicate files |
| **JASS Big File Duplicate Cleaner** | Locate large duplicate files |
| **JASS Empty Folder Remover** | Find and remove empty folders |
| **JASS Nested Folder Updater** | Update or reorganize nested folder structures |
| **JASS Subfolder Consolidator** | Consolidate subfolders into a cleaner structure |
| **JASS Folder Intelligence Studio** | Inspect and understand folder structures |
| **JASS File Analyzer Pro** | Analyze files and their properties |
| **JASS Disk Space Observatory** | Examine disk-space usage |
| **JASS Archive Explorer** | Explore archive contents |

### 🗄️ Database & Data Tools

| Application | Purpose |
|---|---|
| **JASS SQLite Explorer** | Explore and inspect SQLite databases |
| **JASS Dataset Explorer** | Inspect datasets and tabular data |
| **JASS Document Laboratory** | Work with and inspect documents |
| **JASS Healthspan Explorer** | Explore healthspan-related research data |
| **JASS Literature Explorer** | Explore literature collections |

### 🖼️ Images & Creative Tools

| Application | Purpose |
|---|---|
| **JASS Image Viewer Pro** | View images in a desktop interface |
| **JASS Image Vault Pro** | Organize and manage image collections |
| **JASS Quote & Poster Studio** | Create quote/poster-style graphics |
| **JASS TextLab Studio** | Create and work with formatted text content |

### 📱 Android & Device Utilities

| Application | Purpose |
|---|---|
| **JASS Android File Commander** | Manage Android files |
| **JASS Android Transfer Manager** | Assist with Android file transfers |
| **JASS AppImage Manager** | Manage AppImage applications |

### 🔐 Privacy & Security Utilities

| Application | Purpose |
|---|---|
| **JASS Privacy Scanner** | Scan files/projects for potential privacy issues |
| **JASS Password Generator Vault** | Generate and manage password-related vault data |
| **JASS Offline Facebook** | Offline-oriented personal/archive utility |

> Security-related applications should be used carefully. Always keep backups of important files and never treat a utility as a substitute for a proper backup or security strategy.

### 🧰 Developer & Project Utilities

| Application | Purpose |
|---|---|
| **JASS Developer Toolbox** | Collection of developer-oriented utilities |
| **JASS Project Archaeologist** | Inspect and understand existing projects |
| **JASS Quote Harvester** | Extract/collect quotations |
| **JASS Archive Explorer** | Inspect archived project/data files |

---

## 📚 Additional Files

The repository also contains supporting README files and application/data files, including:

- `JASS_Vault.jassvault`
- `rosa.jassvault`
- `jass_book_reader_pro.py`
- `README(JASS Image Vault Pro).md`
- Other application-specific README files

The `.jassvault` files are application data/vault files and are not Python source code.

---

## 🖥️ Technology

Most GUI applications in this repository are written in:

- **Python 3**
- **PySide6 / Qt**
- SQLite where database storage is appropriate
- Standard Python libraries where possible

Individual applications may have additional dependencies.

---

## 🚀 Getting Started

### 1. Install Python

Install a current Python 3 release for Windows.

Verify:

```powershell
python --version
```

or:

```powershell
py --version
```

### 2. Clone the repository

```powershell
git clone https://github.com/Fanu2/JASS-Windows-Toolkit.git
cd JASS-Windows-Toolkit
```

### 3. Create a virtual environment

Recommended:

```powershell
py -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

### 4. Install PySide6

For applications using PySide6:

```powershell
python -m pip install PySide6
```

Individual applications may require additional packages. Check the corresponding README or the imports in the Python file before running them.

---

## ▶️ Running an Application

Most programs can be started directly:

```powershell
python JASS_File_Organizer_Pro_v1.0.2.py
```

or:

```powershell
py JASS_File_Organizer_Pro_v1.0.2.py
```

For another application:

```powershell
python JASS_SQLite_Explorer_v1.7.0_fixed.py
```

The exact filename and version may change as applications are improved.

---

## 🧪 Versioning

Many applications use versioned filenames, for example:

```text
JASS_Document_Laboratory_v1.0.py
JASS_Document_Laboratory_v1.1.py
```

and:

```text
JASS_SQLite_Explorer_v1.7.0_fixed.py
```

This reflects the development history of individual utilities.

Where a dedicated README exists, it should be treated as the primary documentation for that application.

---

## 🛡️ Safety & Backups

Several utilities in this repository can **move, rename, delete, consolidate, or modify files and folders**.

Before using file-management utilities:

1. Make a backup of important data.
2. Test the application on a small sample directory.
3. Review the preview/results before destructive operations.
4. Avoid running cleanup utilities against system directories unless you fully understand the operation.
5. Keep important data on a separate backup drive.

For duplicate removal and folder-cleaning utilities in particular, **verify the selected files before deletion**.

---

## 🧩 Design Philosophy

The JASS Windows Toolkit follows a simple philosophy:

> **Build small, useful tools for real-world work.**

The applications are generally designed to:

- solve a specific practical problem;
- provide a graphical interface where useful;
- work locally/offline where possible;
- avoid unnecessary complexity;
- preserve user control over files and data;
- evolve through small, versioned improvements.

The toolkit is intentionally a collection of independent applications rather than one monolithic program.

---

## 📂 Repository Organization

The repository currently keeps applications largely as individual Python files:

```text
JASS-Windows-Toolkit/
│
├── JASS_Android_File_Commander_v1.py
├── JASS_Android_Transfer_Manager_v1.0.py
├── JASS_AppImage_Manager_v1.0.py
├── JASS_Archive_Explorer_v1.0.py
│
├── JASS_File_Organizer_Pro_v1.0.2.py
├── JASS_File_Analyzer_Pro_v1.0.py
├── JASS_Duplicate_File_Remover_v1.2.py
├── JASS_Empty_Folder_Remover_v1.0.py
├── JASS_Folder_Intelligence_Studio_v1.0.py
│
├── JASS_SQLite_Explorer_v1.7.0_fixed.py
├── JASS_Dataset_Explorer_v1.2_copyable.py
├── JASS_Document_Laboratory_v1.1.py
│
├── JASS_Image_Viewer_Pro_v1.0.py
├── JASS_Image_Vault_Pro_v2.0.py
├── JASS_Quote_and_Poster_Studio_v1.0.py
├── JASS_TextLab_Studio_v2.0.py
│
├── JASS_Privacy_Scanner_v1.0.py
├── JASS_Password_Generator_Vault_v1.0.py
├── JASS_Developer_Toolbox_v1.0.py
├── JASS_Project_Archaeologist_v1.0.py
│
├── ... additional JASS utilities ...
│
└── README.md
```

This is a representative structure; filenames and versions may change as the toolkit evolves.

---

## 🔄 Development Status

The toolkit is under active development.

Applications may be at different stages of maturity:

- stable personal utilities;
- experimental tools;
- versioned development releases;
- utilities undergoing refinement.

A higher version number does not necessarily mean that one application is more stable than another.

Always check the application's own README, filename/version, and recent repository commit history before relying on it for important work.

---

## 🤝 Contributions

This repository is primarily a personal development and utility collection.

Suggestions, bug reports, improvements, and useful ideas are welcome.

When reporting an issue, include:

- application name;
- version;
- Windows version;
- Python version;
- exact error message/traceback;
- steps needed to reproduce the problem.

---

## 📄 License

Unless a separate license file or application-specific notice states otherwise, the repository should be considered **personal-use / source-available software** and not assumed to be freely redistributable.

Check the repository's license information before redistributing or incorporating any component into another project.

---

## 👤 Author

**Fanu2 / JASS**

A collection of practical Windows utilities developed for file management, research, productivity, privacy, data exploration, and everyday computing.

---

## ⭐ Repository

**JASS-Windows-Toolkit**

A growing toolbox of small applications — built one useful problem at a time.
