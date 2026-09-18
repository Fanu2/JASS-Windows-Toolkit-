# JASS Privacy Scanner v1.0

**JASS Privacy Scanner** is a local-first, read-only privacy and sensitive-data auditing application for Linux, built with Python and PySide6.

It is designed to help answer:

> **“What privacy-sensitive material might be sitting in this folder?”**

The scanner searches for privacy-relevant filenames, possible secrets in text, browser artifacts, risky filesystem permissions, and media files that may contain privacy-bearing metadata.

## Design principles

- 🔒 **Local-first**
- 🛡️ **Read-only scanning**
- 🚫 **No cloud**
- 🚫 **No AI/API calls**
- 🚫 **No automatic deletion**
- 🚫 **No automatic quarantine**
- 🔐 **Detected secret evidence is masked**
- 🧩 **Heuristic rules rather than destructive assumptions**

A finding means **“review this”**, not “this file is definitely dangerous.”

---

## Features

### 1. Privacy Dashboard

The dashboard summarizes:

- Files scanned
- Data scanned
- Total findings
- Critical findings
- High findings
- Medium findings
- Low findings
- Filesystem access errors
- Privacy-relevant categories
- Highest-scoring locations

It also shows:

- Text files scanned
- Media candidates
- Scan duration
- Scan root

---

## 2. Folder Scanner

Choose any directory and configure:

- Recursive scanning
- Include hidden files/directories
- Scan text content
- Check media metadata
- Maximum directory depth
- Skip common generated/dependency folders

Common skipped directories include:

```text
.git
.svn
.hg
__pycache__
.venv
venv
node_modules
.npm
.cache
.cargo
.rustup
dist
build
.gradle
.idea
.vscode
```

Skipping is configurable.

---

## 3. Credential & Secret Filename Detection

The scanner recognizes filenames that deserve inspection, including patterns associated with:

```text
password
passwd
credential
secret
token
apikey
api-key
private-key
wallet
seed
mnemonic
```

It also recognizes common SSH key filenames such as:

```text
id_rsa
id_ed25519
id_ecdsa
```

Example:

```text
.env
credentials.json
my_api_key.txt
id_ed25519
wallet_backup.txt
```

The scanner does **not** automatically open or display these files as secrets.

---

## 4. Text Content Scanner

For supported text-like files, the scanner searches for patterns associated with:

- Private-key blocks
- AWS-style access keys
- GitHub tokens
- API-key assignments
- Access tokens
- Bearer tokens
- JWTs
- Password assignments
- Email addresses
- IPv4 addresses
- Phone-like numbers
- Credit-card-like number patterns
- Cloud/storage URLs

Supported text extensions include common:

```text
TXT MD RST LOG CSV TSV
JSON JSONL XML YAML YML TOML
INI CFG CONF ENV
PY JS TS JSX TSX
JAVA C H CPP HPP CS GO RS
PHP RB SH BAT PS1 SQL
HTML HTM CSS SCSS
SRT VTT
```

Text scanning is deliberately limited to **512 KB per file** in v1.0 to avoid unexpectedly reading very large files into memory.

---

## 5. Masked Evidence

The scanner deliberately does not expose full secret-like values.

For example, instead of displaying:

```text
AKIAxxxxxxxxxxxxxxxx
```

the application displays a masked representation such as:

```text
AKI••••••••••••xxx
```

This principle also applies to exported reports.

### Important

The report itself can still contain:

- File paths
- Rule names
- Finding categories
- Masked evidence

Therefore, save reports only in a location you trust.

---

## 6. Browser & Profile Artifact Detection

The scanner looks for path/name indicators associated with browser data, such as:

```text
cookies
history
Login Data
Web Data
key4.db
places.sqlite
session
local storage
```

It also recognizes common browser-profile locations under Linux.

These files can contain highly privacy-sensitive information, so the scanner flags them for review rather than attempting to read or modify them.

---

## 7. Filesystem Permission Audit

The scanner checks for:

### World-writable files

Example:

```text
-rw-rw-rw-
```

These can allow other local users to modify the file.

### World-executable files

The scanner flags files executable by other users.

### World-writable directories without sticky bit

This can be especially important on shared Linux systems.

The scanner reports the filesystem mode, for example:

```text
0o777
```

No permissions are changed.

---

## 8. Media Privacy Audit

The scanner recognizes common media that may contain metadata:

```text
JPG
JPEG
TIFF
PNG
WEBP
HEIC
MOV
MP4
M4V
```

It does not claim that every file contains GPS information.

Instead it reports:

> Media file may contain EXIF/XMP/QuickTime metadata such as location, device, or timestamps.

This is intentionally conservative.

---

## 9. Findings Explorer

The Findings tab provides:

- Severity
- Score
- Category
- Rule
- Path
- Detail
- Masked evidence

Filters include:

- Search
- Severity
- Category

You can double-click a finding or select it and choose **View Finding**.

---

## 10. Privacy Rules

The application includes a visible rule inventory showing:

- Rule name
- Rule type
- Score
- Regular-expression pattern

This makes the scanner auditable rather than hiding its detection logic.

---

## 11. Reports

Export:

### JSON

Contains:

- Scan information
- Statistics
- Findings
- Masked evidence
- Scanner version

### CSV

Useful for:

- Spreadsheet analysis
- Filtering
- Sorting
- Further processing

### TXT

A human-readable report.

---

# Severity model

The scanner uses a simple heuristic score.

| Score | Severity |
|---:|---|
| 45+ | Critical |
| 30–44 | High |
| 15–29 | Medium |
| 0–14 | Low |

The score describes the **rule's potential privacy significance**, not the importance of the person or file.

---

# What JASS Privacy Scanner does NOT do

v1.0 intentionally does not:

- Delete files
- Move files
- Rename files
- Encrypt files
- Upload files
- Contact external services
- Modify permissions
- Modify EXIF metadata
- Automatically quarantine files
- Automatically remove secrets
- Follow symlinks during traversal
- Attempt to authenticate to services
- Recover passwords
- Crack encrypted files

This makes the first version suitable as an **audit and discovery tool**.

---

# Installation on MX Linux / Debian

Install Python and PySide6:

```bash
sudo apt update
sudo apt install python3 python3-pip
python3 -m pip install PySide6
```

If your system uses a Python virtual environment, that is also recommended.

Run:

```bash
python3 JASS_Privacy_Scanner_v1.0.py
```

---

# Example workflow

Start with a small directory:

```text
/home/jasvir/Documents
```

Then:

1. Choose the folder.
2. Enable **Recursive**.
3. Enable **Scan text content**.
4. Enable **Check media metadata**.
5. Leave **Skip generated/dependency folders** enabled.
6. Start the scan.
7. Review Critical and High findings.
8. Inspect the original files manually.
9. Export a report if useful.

Do **not** delete something merely because JASS flagged it.

---

# Privacy model

JASS Privacy Scanner is designed to perform its work locally.

The scanner itself does not use:

- Internet access
- Cloud APIs
- AI models
- Remote databases
- Analytics services

All scanning occurs on the machine running the program.

---

# Limitations

This is a heuristic scanner.

It can produce:

### False positives

For example:

```text
password = "example"
```

may be a documentation example rather than a real credential.

An email address may be public information.

A media file may contain only harmless metadata.

A filename containing `backup` does not prove that sensitive information exists inside it.

### False negatives

A secret may be:

- Encoded
- Obfuscated
- Split across files
- Stored in binary format
- Hidden in an unsupported file type
- Larger than the content scan limit
- Written in an unexpected syntax

Therefore this application should **not** be treated as a complete security scanner or DLP system.

---

# Roadmap

## v1.1 — Metadata Intelligence

- Optional ExifTool integration
- EXIF field inventory
- GPS detection
- Camera/device detection
- Software/application metadata
- Timestamp analysis

## v1.2 — Browser Privacy

- Browser discovery
- Chrome/Chromium profile inventory
- Firefox profile inventory
- Edge profile inventory
- Cookie database detection
- History database detection
- Saved-login database detection
- Browser artifact report

## v1.3 — Secret Intelligence

- Entropy analysis
- More provider-specific token patterns
- Custom regular-expression rules
- `.git` secret detection
- Git history secret scanning
- Ignore lists
- False-positive suppression

## v1.4 — File Privacy Intelligence

- Duplicate sensitive-file detection
- Sensitive directory analysis
- Empty sensitive folders
- Old backup detection
- Archive inspection
- Database detection
- Document metadata analysis

## v1.5 — Privacy Baselines

- Scan snapshots
- Before/after comparison
- New sensitive-file detection
- Changed permissions
- New browser artifacts
- Privacy baseline reports

## v2.0 — Privacy Workspace

Potential future architecture:

```text
JASS Privacy Scanner
        │
        ├── File Privacy Engine
        ├── Secret Detection Engine
        ├── Metadata Engine
        ├── Browser Artifact Engine
        ├── Permission Auditor
        ├── Archive Inspector
        ├── Git History Scanner
        ├── Baseline Engine
        └── Privacy Report Engine
```

Possible outputs:

- HTML report
- PDF report
- Privacy inventory
- Sensitive-data map
- Remediation checklist
- Before/after privacy comparison

---

# Safety philosophy

The core design principle is:

> **Discover first. Review second. Act last.**

JASS Privacy Scanner should never make an irreversible privacy decision on your behalf.

---

## License

Choose the license appropriate for your JASS repository, such as MIT, before publishing.
