# 🧰 JASS Developer Toolbox

**JASS Developer Toolbox** is a lightweight, local-first PySide6 developer workbench that gathers frequently needed development utilities into one desktop application.

It is designed for everyday work on Linux/MX Linux and other desktop environments.

## ✨ Modules

### 🏠 Dashboard
Quick environment overview:

- operating system
- Python version
- PySide6
- CPU
- RAM
- shell
- working directory
- hostname
- common developer tools

Detected tools include:

- Git
- Python
- pip
- FFmpeg
- ADB
- Docker
- Ollama

### 📄 File Inspector
Inspect an individual file:

- filename
- path
- extension
- size
- modification time
- Unix permissions
- read/write/execute access
- text preview

Large files are not automatically loaded into the preview.

### 🔤 Text Lab
Analyze text:

- characters
- non-whitespace characters
- words
- lines
- paragraphs
- unique words
- average word length

Transform text:

- uppercase
- lowercase
- trim lines
- sort lines
- unique lines

### {} JSON Lab
Tools for:

- pretty formatting
- minification
- validation
- copying formatted output

### 🔎 Regex Lab
Test regular expressions locally.

Supports common flags:

```text
i = ignore case
m = multiline
s = dot matches newline
```

Displays:

- match count
- matched text
- match spans

### 🔐 Hash Lab
Calculate:

- MD5
- SHA-1
- SHA-256

Useful for comparing downloaded files, backups and build artifacts.

> MD5 and SHA-1 are included for compatibility/fingerprinting. SHA-256 should be preferred for modern integrity verification.

### ⌨ Command Runner
Execute a command entered by the user and display:

- stdout
- stderr
- exit code

Commands run in a background thread so the GUI remains responsive.

**Important:** this is a real shell command runner. Only enter commands you understand and trust.

### 🗂 Project Inspector
Quickly inspect a project directory.

Reports:

- file count
- total size
- Git detection
- file-extension distribution
- largest files

Common generated/dependency directories are skipped:

```text
.git
node_modules
.venv
venv
__pycache__
build
dist
```

### 🖥 System Diagnostics
Shows:

- platform
- machine architecture
- processor
- Python installation
- Python executable
- working directory
- hostname
- user
- shell
- available developer commands

### 🔄 Converters
Currently includes:

- CSV → JSON
- JSON → CSV

## 🔐 Privacy

JASS Developer Toolbox is local-first.

It does not:

- upload source code
- send files to an API
- require an account
- use cloud AI
- phone home

All inspection and transformation utilities operate locally.

The **Command Runner** is different: it executes commands on your own computer because that is its explicit purpose.

## 🚀 Installation

On MX Linux / Debian:

```bash
sudo apt update
sudo apt install python3 python3-pyside6
```

Alternatively:

```bash
python3 -m pip install PySide6
```

## ▶️ Run

```bash
python3 JASS_Developer_Toolbox_v1.0.py
```

## 🧭 Typical workflows

### Verify a downloaded file

1. Open Hash Lab.
2. Select the file.
3. Calculate SHA-256.
4. Compare the displayed hash with the publisher's expected value.

### Inspect a project

1. Open Project Inspector.
2. Select the project root.
3. Inspect file distribution and largest files.
4. Use the system diagnostics tab to check available development tools.

### Clean up text data

1. Paste text into Text Lab.
2. Analyze it.
3. Trim, sort or deduplicate lines.
4. Copy the resulting text.

### Validate JSON

1. Paste JSON into JSON Lab.
2. Click Validate.
3. Format it if valid.

### Test a regex

1. Enter the pattern.
2. Add flags if required.
3. Paste test data.
4. Click Test Regex.

## 🛠 Design

The application intentionally avoids large frameworks and heavy dependencies.

Core stack:

- Python 3
- PySide6
- Python standard library

Optional external programs are detected rather than bundled:

- Git
- FFmpeg
- ADB
- Docker
- Ollama

## ⚠️ Command Runner

The Command Runner uses the system shell.

Examples of harmless diagnostic commands include:

```bash
pwd
python3 --version
git --version
ffmpeg -version
df -h
```

Commands that modify files, install packages, delete data or change system configuration should only be executed when you deliberately intend to do so.

## 🗺️ Future roadmap

### Developer utilities
- YAML/TOML/XML formatter
- Base64 encoder/decoder
- URL encoder/decoder
- JWT inspector
- Unix timestamp converter
- UUID generator
- random token generator
- checksum comparison
- binary/hex viewer

### File tools
- directory size analyzer
- duplicate finder
- batch rename preview
- file comparison
- folder comparison
- archive inspector
- permissions analyzer

### Code intelligence
- Python AST explorer
- imports/dependency graph
- classes/functions/method inventory
- TODO/FIXME scanner
- complexity indicators
- documentation coverage
- test discovery
- project fingerprint

### Git utilities
- repository status dashboard
- branch viewer
- commit browser
- changed-file explorer
- diff viewer
- commit archaeology
- churn analysis

### Local AI integration
Optional integrations could eventually support:

- Ollama
- LM Studio
- local embeddings
- codebase RAG
- local code explanation
- local documentation generation

These would remain optional so the toolbox stays useful without AI.

### JASS ecosystem

The toolbox can eventually complement:

- **JASS Project Archaeologist**
- **JASS Disk Space Observatory**
- **JASS File Analyzer**
- **JASS AppImage Manager**
- **JASS Media Laboratory**
- **JASS Literature Explorer**
- **JASS Android Transfer Manager**

## 🧭 Philosophy

> **Small utilities. One workbench. Local control.**

JASS Developer Toolbox is intended to be a practical Swiss-army knife for development rather than another large IDE.

---

**JASS Developer Toolbox v1.0**  
Local-first • Lightweight • PySide6 • Developer-focused
