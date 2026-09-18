#!/usr/bin/env python3
"""
JASS Privacy Scanner v1.0
Local-first privacy and sensitive-data audit tool for Linux.

Read-only by design:
- Scans files and folders for privacy-relevant artifacts.
- Does not delete, move, upload, or modify files.
- Secret/content matches are masked in the UI and reports.
"""

import csv
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QStatusBar, QTableWidget,
    QTableWidgetItem, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget, QHeaderView
)

APP_NAME = "JASS Privacy Scanner"
VERSION = "1.0"

TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonl",
    ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".h", ".cpp",
    ".hpp", ".cs", ".go", ".rs", ".php", ".rb", ".sh", ".bat", ".ps1",
    ".sql", ".html", ".htm", ".css", ".scss", ".tex", ".srt", ".vtt",
    ".properties", ".desktop"
}

SKIP_DIRS_DEFAULT = {
    ".git", ".svn", ".hg", "__pycache__", ".venv", "venv", "node_modules",
    ".npm", ".cache", ".cargo", ".rustup", "dist", "build", ".gradle",
    ".idea", ".vscode"
}

FILENAME_RULES = [
    ("Credential-looking filename", re.compile(
        r"(?i)(^|[._-])(password|passwd|pwd|credential|credentials|secret|secrets|token|tokens|apikey|api[_-]?key|private[_-]?key|wallet|seed|mnemonic)([._-]|$)"
    ), 30),
    ("Environment/config file", re.compile(
        r"(?i)(^|[._-])(\.env|env|config|settings|credentials)([._-]|$)"
    ), 18),
    ("SSH/private-key filename", re.compile(
        r"(?i)(id_rsa|id_ed25519|id_ecdsa|private.*key|authorized_keys)"
    ), 35),
    ("Browser/profile artifact", re.compile(
        r"(?i)(cookies|web data|login data|history|places\.sqlite|session|local storage|key4\.db)"
    ), 20),
    ("Backup/archive with possible sensitive contents", re.compile(
        r"(?i)(backup|dump|export|database|\.sql|\.bak|\.old|\.tar|\.zip|\.7z|\.rar)"
    ), 10),
]

CONTENT_RULES = [
    ("Private key material", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), 50),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), 45),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), 45),
    ("Generic API key assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|apikey|access[_-]?token|secret[_-]?key)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{12,}"
    ), 40),
    ("Bearer token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"), 40),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"), 40),
    ("Password assignment", re.compile(
        r"(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"]{6,}"
    ), 35),
    ("Email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 8),
    ("IPv4 address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), 5),
    ("Phone-like number", re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{8,}\d)(?!\d)"), 8),
    ("Credit-card-like number", re.compile(
        r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"
    ), 35),
    ("Cloud/storage URL", re.compile(
        r"(?i)\b(?:s3://|gs://|az://|https?://(?:drive|dropbox|onedrive)\.[^\s]+)"
    ), 12),
]

SENSITIVE_DIR_NAMES = re.compile(
    r"(?i)(password|secret|credential|private|wallet|backup|finance|tax|passport|identity|medical|personal|keys?)"
)

BROWSER_PATH_HINTS = re.compile(
    r"(?i)(\.config/(google-chrome|chromium|mozilla|microsoft-edge)|"
    r"\.mozilla/firefox|cookies|history|login data|web data|key4\.db)"
)

@dataclass
class Finding:
    severity: str
    score: int
    category: str
    rule: str
    path: str
    detail: str
    evidence: str = ""
    source: str = "filename"

def human_size(n):
    n = float(n or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    for u in units:
        if n < 1024 or u == units[-1]:
            return f"{n:.1f} {u}" if u != "B" else f"{int(n)} B"
        n /= 1024

def severity_for(score):
    if score >= 45:
        return "Critical"
    if score >= 30:
        return "High"
    if score >= 15:
        return "Medium"
    return "Low"

def mask_secret(s):
    if not s:
        return ""
    s = s.strip()
    if len(s) <= 8:
        return "••••"
    return s[:3] + "••••" + s[-3:]

def safe_rel(path, root):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except Exception:
        return str(path)

def readable_text(path, max_bytes=512 * 1024):
    try:
        if path.stat().st_size > max_bytes:
            return None
        data = path.read_bytes()
        if b"\x00" in data[:8192]:
            return None
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None

def permission_findings(path):
    out = []
    try:
        st = path.stat()
        mode = stat.S_IMODE(st.st_mode)
        if stat.S_ISREG(st.st_mode):
            if mode & stat.S_IWOTH:
                out.append(Finding("High", 32, "Permissions",
                    "World-writable file", str(path),
                    f"Mode {oct(mode)} allows other users to write this file.",
                    oct(mode), "permissions"))
            if mode & stat.S_IROTH and mode & stat.S_IWUSR:
                # Not inherently unsafe; flag only credential-looking files elsewhere.
                pass
            if mode & stat.S_IXOTH:
                out.append(Finding("Medium", 18, "Permissions",
                    "World-executable file", str(path),
                    f"Mode {oct(mode)} allows other users to execute this file.",
                    oct(mode), "permissions"))
        if stat.S_ISDIR(st.st_mode) and (mode & stat.S_IWOTH) and not (mode & stat.S_ISVTX):
            out.append(Finding("High", 30, "Permissions",
                "World-writable directory without sticky bit", str(path),
                f"Directory mode {oct(mode)} is writable by other users without a sticky bit.",
                oct(mode), "permissions"))
    except Exception:
        pass
    return out

def scan_file(path, root, content_scan, metadata_scan):
    findings = []
    name = path.name
    rel = safe_rel(path, root)

    for rule, rx, score in FILENAME_RULES:
        if rx.search(name):
            cat = "Browser Artifact" if "Browser" in rule else (
                "Credentials" if "Credential" in rule or "SSH" in rule else "File Pattern"
            )
            findings.append(Finding(
                severity_for(score), score, cat, rule, str(path),
                f"Filename matches a privacy-sensitive pattern: {name}",
                name, "filename"
            ))

    if BROWSER_PATH_HINTS.search(str(path)):
        findings.append(Finding(
            "Medium", 20, "Browser Artifact", "Browser/profile path",
            str(path), "Path resembles a browser profile or browsing-data location.",
            rel, "path"
        ))

    if content_scan and path.suffix.lower() in TEXT_EXTENSIONS:
        text = readable_text(path)
        if text is not None:
            for rule, rx, score in CONTENT_RULES:
                m = rx.search(text)
                if m:
                    evidence = mask_secret(m.group(0))
                    # Email/phone/IP are less secret than credential material.
                    findings.append(Finding(
                        severity_for(score), score, "Content",
                        rule, str(path),
                        f"Possible {rule.lower()} detected in text content.",
                        evidence, "content"
                    ))

    findings.extend(permission_findings(path))

    # Metadata without third-party Python libraries: report only the existence
    # of common metadata-bearing media. Optional ExifTool adds richer metadata.
    if metadata_scan and path.suffix.lower() in {
        ".jpg", ".jpeg", ".tif", ".tiff", ".png", ".webp", ".heic", ".mov", ".mp4", ".m4v"
    }:
        findings.append(Finding(
            "Low", 8, "Metadata", "Metadata-bearing media",
            str(path),
            "Media file may contain EXIF/XMP/QuickTime metadata such as location, device, or timestamps.",
            path.suffix.lower(), "metadata"
        ))

    return findings

class ScanWorker(QThread):
    progress = Signal(int, str)
    finding = Signal(object)
    finished_scan = Signal(object)
    error = Signal(str)

    def __init__(self, root, recursive=True, include_hidden=False, max_depth=0,
                 content_scan=True, metadata_scan=True, skip_generated=True):
        super().__init__()
        self.root = Path(root).expanduser()
        self.recursive = recursive
        self.include_hidden = include_hidden
        self.max_depth = max_depth
        self.content_scan = content_scan
        self.metadata_scan = metadata_scan
        self.skip_generated = skip_generated
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def should_skip_dir(self, p):
        if self.skip_generated and p.name in SKIP_DIRS_DEFAULT:
            return True
        if not self.include_hidden and p.name.startswith("."):
            return True
        return False

    def run(self):
        start = time.time()
        stats = {
            "files": 0, "dirs": 0, "errors": 0, "bytes": 0,
            "findings": 0, "critical": 0, "high": 0, "medium": 0, "low": 0,
            "scanned_text": 0, "metadata": 0
        }
        try:
            if not self.root.exists() or not self.root.is_dir():
                raise RuntimeError(f"Folder does not exist or is not a directory: {self.root}")

            stack = [(self.root, 0)]
            while stack and not self.stop_requested:
                current, depth = stack.pop()
                self.progress.emit(-1, str(current))
                try:
                    entries = list(os.scandir(current))
                except (PermissionError, OSError):
                    stats["errors"] += 1
                    continue

                stats["dirs"] += 1
                for entry in entries:
                    if self.stop_requested:
                        break
                    p = Path(entry.path)
                    if not self.include_hidden and p.name.startswith("."):
                        continue
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        if is_dir:
                            if self.recursive and not self.should_skip_dir(p):
                                if self.max_depth == 0 or depth + 1 < self.max_depth:
                                    stack.append((p, depth + 1))
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            continue

                        stats["files"] += 1
                        try:
                            size = entry.stat(follow_symlinks=False).st_size
                            stats["bytes"] += size
                        except OSError:
                            size = 0

                        fs = scan_file(p, self.root, self.content_scan, self.metadata_scan)
                        for f in fs:
                            stats["findings"] += 1
                            stats[f.severity.lower()] += 1
                            self.finding.emit(f)
                        if self.content_scan and p.suffix.lower() in TEXT_EXTENSIONS:
                            stats["scanned_text"] += 1
                        if self.metadata_scan and p.suffix.lower() in {
                            ".jpg", ".jpeg", ".tif", ".tiff", ".png", ".webp", ".heic", ".mov", ".mp4", ".m4v"
                        }:
                            stats["metadata"] += 1
                    except (PermissionError, OSError):
                        stats["errors"] += 1

                # Approximate progress by file count is intentionally not used:
                # filesystem totals are expensive to calculate before scanning.
                self.progress.emit(-1, str(current))

            stats["duration"] = time.time() - start
            stats["stopped"] = self.stop_requested
            self.finished_scan.emit(stats)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1500, 920)
        self.findings = []
        self.stats = {}
        self.worker = None
        self.root = str(Path.home())
        self.setStatusBar(QStatusBar())
        self.build_ui()
        self.apply_style()
        self.refresh_dashboard()

    def build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        subtitle = QLabel("Local-first privacy audit • Sensitive files • Secrets • Metadata • Permissions")
        subtitle.setObjectName("Subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        controls = QGroupBox("Scan Configuration")
        grid = QGridLayout(controls)

        self.path_edit = QLineEdit(self.root)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_folder)

        grid.addWidget(QLabel("Folder:"), 0, 0)
        grid.addWidget(self.path_edit, 0, 1, 1, 4)
        grid.addWidget(browse, 0, 5)

        self.recursive = QCheckBox("Recursive")
        self.recursive.setChecked(True)
        self.hidden = QCheckBox("Include hidden")
        self.content = QCheckBox("Scan text content")
        self.content.setChecked(True)
        self.metadata = QCheckBox("Check media metadata")
        self.metadata.setChecked(True)
        self.skip_generated = QCheckBox("Skip generated/dependency folders")
        self.skip_generated.setChecked(True)

        grid.addWidget(self.recursive, 1, 0)
        grid.addWidget(self.hidden, 1, 1)
        grid.addWidget(self.content, 1, 2)
        grid.addWidget(self.metadata, 1, 3)
        grid.addWidget(self.skip_generated, 1, 4, 1, 2)

        grid.addWidget(QLabel("Max depth (0 = unlimited):"), 2, 0)
        self.depth = QSpinBox()
        self.depth.setRange(0, 999)
        self.depth.setValue(0)
        grid.addWidget(self.depth, 2, 1)

        self.scan_btn = QPushButton("🔍 Start Privacy Scan")
        self.scan_btn.setObjectName("Primary")
        self.scan_btn.clicked.connect(self.start_scan)
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_scan)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        grid.addWidget(self.scan_btn, 2, 2)
        grid.addWidget(self.stop_btn, 2, 3)
        grid.addWidget(self.progress, 2, 4, 1, 2)
        outer.addWidget(controls)

        self.tabs = QTabWidget()
        self.dashboard_tab = self.make_dashboard()
        self.findings_tab = self.make_findings()
        self.patterns_tab = self.make_patterns()
        self.reports_tab = self.make_reports()
        self.help_tab = self.make_help()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.findings_tab, "Findings")
        self.tabs.addTab(self.patterns_tab, "Privacy Rules")
        self.tabs.addTab(self.reports_tab, "Reports")
        self.tabs.addTab(self.help_tab, "Help")
        outer.addWidget(self.tabs, 1)

        self.setCentralWidget(central)
        self.make_menu()

    def make_menu(self):
        file_menu = self.menuBar().addMenu("File")
        a = QAction("Choose Folder…", self)
        a.triggered.connect(self.choose_folder)
        file_menu.addAction(a)
        a = QAction("Export JSON…", self)
        a.triggered.connect(self.export_json)
        file_menu.addAction(a)
        a = QAction("Export CSV…", self)
        a.triggered.connect(self.export_csv)
        file_menu.addAction(a)
        file_menu.addSeparator()
        a = QAction("Quit", self)
        a.triggered.connect(self.close)
        file_menu.addAction(a)

        scan_menu = self.menuBar().addMenu("Scan")
        a = QAction("Start Scan", self)
        a.triggered.connect(self.start_scan)
        scan_menu.addAction(a)
        a = QAction("Stop Scan", self)
        a.triggered.connect(self.stop_scan)
        scan_menu.addAction(a)

    def make_dashboard(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        cards = QGridLayout()
        self.card_files = self.card("Files Scanned", "0")
        self.card_size = self.card("Data Scanned", "0 B")
        self.card_findings = self.card("Findings", "0")
        self.card_critical = self.card("Critical", "0")
        self.card_high = self.card("High", "0")
        self.card_medium = self.card("Medium", "0")
        self.card_low = self.card("Low", "0")
        self.card_errors = self.card("Access Errors", "0")
        cards.addWidget(self.card_files, 0, 0)
        cards.addWidget(self.card_size, 0, 1)
        cards.addWidget(self.card_findings, 0, 2)
        cards.addWidget(self.card_critical, 0, 3)
        cards.addWidget(self.card_high, 1, 0)
        cards.addWidget(self.card_medium, 1, 1)
        cards.addWidget(self.card_low, 1, 2)
        cards.addWidget(self.card_errors, 1, 3)
        lay.addLayout(cards)

        split = QSplitter(Qt.Horizontal)
        self.category_list = QListWidget()
        self.top_paths = QTreeWidget()
        self.top_paths.setHeaderLabels(["Privacy-relevant location", "Severity", "Rule"])
        self.top_paths.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.top_paths.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.top_paths.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        split.addWidget(self.category_list)
        split.addWidget(self.top_paths)
        split.setSizes([320, 900])
        lay.addWidget(split, 1)

        self.dashboard_note = QLabel("Run a scan to build a privacy inventory. This application is read-only.")
        self.dashboard_note.setWordWrap(True)
        lay.addWidget(self.dashboard_note)
        return w

    def card(self, label, value):
        f = QFrame()
        f.setObjectName("Card")
        l = QVBoxLayout(f)
        a = QLabel(label)
        a.setObjectName("CardLabel")
        b = QLabel(value)
        b.setObjectName("CardValue")
        l.addWidget(a)
        l.addWidget(b)
        return f

    def make_findings(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.finding_search = QLineEdit()
        self.finding_search.setPlaceholderText("Filter path, rule, category, detail…")
        self.finding_search.textChanged.connect(self.filter_findings)
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All severities", "Critical", "High", "Medium", "Low"])
        self.severity_filter.currentTextChanged.connect(self.filter_findings)
        self.category_filter = QComboBox()
        self.category_filter.addItem("All categories")
        self.category_filter.currentTextChanged.connect(self.filter_findings)
        bar.addWidget(self.finding_search, 1)
        bar.addWidget(self.severity_filter)
        bar.addWidget(self.category_filter)
        lay.addLayout(bar)

        self.finding_table = QTableWidget(0, 7)
        self.finding_table.setHorizontalHeaderLabels(
            ["Severity", "Score", "Category", "Rule", "Path", "Detail", "Evidence (masked)"]
        )
        self.finding_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.finding_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.finding_table.setAlternatingRowColors(True)
        h = self.finding_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        h.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.finding_table.doubleClicked.connect(self.show_finding)
        lay.addWidget(self.finding_table, 1)

        btns = QHBoxLayout()
        details = QPushButton("View Finding")
        details.clicked.connect(self.show_finding)
        export = QPushButton("Export Current Results")
        export.clicked.connect(self.export_json)
        btns.addWidget(details)
        btns.addWidget(export)
        btns.addStretch()
        lay.addLayout(btns)
        return w

    def make_patterns(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel(
            "The scanner uses conservative local heuristics. Content evidence is masked. "
            "A finding means 'needs review', not proof that a secret or personal datum is exposed."
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        table = QTableWidget(len(FILENAME_RULES) + len(CONTENT_RULES), 4)
        table.setHorizontalHeaderLabels(["Type", "Rule", "Score", "What it looks for"])
        rows = []
        for name, rx, score in FILENAME_RULES:
            rows.append(("Filename/path", name, score, rx.pattern))
        for name, rx, score in CONTENT_RULES:
            rows.append(("Content", name, score, rx.pattern))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(str(value)))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(table, 1)
        return w

    def make_reports(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        note = QLabel(
            "Reports contain file paths and masked evidence. They do not intentionally write detected "
            "secret values to disk. Export only to a location you trust."
        )
        note.setWordWrap(True)
        lay.addWidget(note)
        self.report_preview = QPlainTextEdit()
        self.report_preview.setReadOnly(True)
        lay.addWidget(self.report_preview, 1)
        row = QHBoxLayout()
        b1 = QPushButton("Export JSON…")
        b1.clicked.connect(self.export_json)
        b2 = QPushButton("Export CSV…")
        b2.clicked.connect(self.export_csv)
        b3 = QPushButton("Export Text…")
        b3.clicked.connect(self.export_text)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        row.addStretch()
        lay.addLayout(row)
        return w

    def make_help(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("""JASS Privacy Scanner v1.0

PURPOSE
-------
A local-first, read-only privacy audit for Linux files and folders.

WHAT IT CHECKS
--------------
• Credential-looking filenames (.env, password, secret, token, private keys)
• SSH/private-key filenames
• Browser/profile artifacts
• Backup/export/database/archive naming patterns
• Possible API keys, bearer tokens, JWTs and private-key blocks in text
• Password-like assignments
• Email, phone-like, IPv4 and credit-card-like patterns
• Cloud/storage URLs
• World-writable files
• World-executable files
• World-writable directories without a sticky bit
• Media files that may contain EXIF/XMP/QuickTime metadata

IMPORTANT
---------
This is a heuristic scanner. It can produce false positives and false negatives.
A finding should be reviewed before any action is taken.

PRIVACY DESIGN
--------------
• No network access is used by the scanner.
• No cloud services or AI APIs.
• No deletion, moving, renaming or modification of scanned files.
• Secret-like evidence is masked in the UI and exported reports.
• Text scanning is limited to configured text extensions and 512 KB per file.
• Symlinks are not followed during directory traversal.

MEDIA METADATA
--------------
The scanner identifies media that may contain privacy-bearing metadata. It does
not remove metadata. Future versions can optionally integrate ExifTool for
detailed EXIF/XMP inspection.

SAFE WORKFLOW
-------------
1. Start with a small folder.
2. Review findings.
3. Treat Critical/High results as items requiring manual verification.
4. Export a report if required.
5. Do not delete a file merely because it was flagged.

OPTIONAL FUTURE FEATURES
------------------------
• ExifTool metadata viewer
• Detailed EXIF GPS detection
• Browser-artifact inventory
• Git secret history checks
• Duplicate sensitive-file detection
• Entropy analysis
• Custom rules
• Exclusion lists
• Baseline/snapshot comparison
• HTML/PDF reports
• Secure redaction workflow
• File quarantine with explicit confirmation
• Password-protected report export
""")
        lay.addWidget(text, 1)
        return w

    def choose_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Choose folder", self.path_edit.text())
        if p:
            self.path_edit.setText(p)

    def start_scan(self):
        if self.worker and self.worker.isRunning():
            return
        root = self.path_edit.text().strip()
        if not root or not Path(root).is_dir():
            QMessageBox.warning(self, APP_NAME, "Please choose a valid folder.")
            return

        self.findings.clear()
        self.stats = {}
        self.finding_table.setRowCount(0)
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All categories")
        self.category_filter.blockSignals(False)
        self.report_preview.clear()
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.statusBar().showMessage("Starting privacy scan…")
        self.tabs.setCurrentWidget(self.dashboard_tab)

        self.worker = ScanWorker(
            root,
            self.recursive.isChecked(),
            self.hidden.isChecked(),
            self.depth.value(),
            self.content.isChecked(),
            self.metadata.isChecked(),
            self.skip_generated.isChecked()
        )
        self.worker.progress.connect(self.scan_progress)
        self.worker.finding.connect(self.add_finding)
        self.worker.finished_scan.connect(self.scan_finished)
        self.worker.error.connect(self.scan_error)
        self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.statusBar().showMessage("Stopping scan…")

    def scan_progress(self, _, path):
        self.statusBar().showMessage(f"Scanning: {path}")

    def add_finding(self, f):
        self.findings.append(f)
        self.insert_finding_row(f)
        self.update_category_filter(f.category)

    def update_category_filter(self, category):
        if self.category_filter.findText(category) < 0:
            self.category_filter.addItem(category)

    def insert_finding_row(self, f):
        row = self.finding_table.rowCount()
        self.finding_table.insertRow(row)
        vals = [f.severity, f.score, f.category, f.rule, f.path, f.detail, f.evidence]
        for c, v in enumerate(vals):
            self.finding_table.setItem(row, c, QTableWidgetItem(str(v)))
        item = self.finding_table.item(row, 0)
        if f.severity == "Critical":
            item.setForeground(QColor("#b00020"))
        elif f.severity == "High":
            item.setForeground(QColor("#c65d00"))
        elif f.severity == "Medium":
            item.setForeground(QColor("#8a6d00"))
        else:
            item.setForeground(QColor("#406080"))

    def filter_findings(self):
        needle = self.finding_search.text().lower().strip()
        sev = self.severity_filter.currentText()
        cat = self.category_filter.currentText()
        for r in range(self.finding_table.rowCount()):
            values = [
                self.finding_table.item(r, c).text().lower()
                if self.finding_table.item(r, c) else ""
                for c in range(self.finding_table.columnCount())
            ]
            match_text = not needle or any(needle in v for v in values)
            match_sev = sev == "All severities" or values[0] == sev.lower()
            match_cat = cat == "All categories" or values[2] == cat.lower()
            self.finding_table.setRowHidden(r, not (match_text and match_sev and match_cat))

    def show_finding(self):
        rows = self.finding_table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        vals = [self.finding_table.item(r, c).text() for c in range(7)]
        dlg = QDialog(self)
        dlg.setWindowTitle("Privacy Finding")
        dlg.resize(850, 520)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        for label, value in zip(
            ["Severity", "Score", "Category", "Rule", "Path", "Detail", "Masked evidence"], vals
        ):
            edit = QLineEdit(value)
            edit.setReadOnly(True)
            form.addRow(label + ":", edit)
        lay.addLayout(form)
        note = QLabel(
            "Review the original file manually. JASS Privacy Scanner does not expose full detected secrets."
        )
        note.setWordWrap(True)
        lay.addWidget(note)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close)
        dlg.exec()

    def scan_finished(self, stats):
        self.stats = stats
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        self.refresh_dashboard()
        self.build_report_preview()
        elapsed = stats.get("duration", 0)
        state = "stopped" if stats.get("stopped") else "completed"
        self.statusBar().showMessage(
            f"Scan {state}: {stats['files']} files, {stats['findings']} findings in {elapsed:.1f}s"
        )

    def scan_error(self, message):
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        QMessageBox.critical(self, APP_NAME, message)
        self.statusBar().showMessage("Scan failed.")

    def refresh_dashboard(self):
        s = self.stats or {}
        self.card_files.findChildren(QLabel)[1].setText(str(s.get("files", 0)))
        self.card_size.findChildren(QLabel)[1].setText(human_size(s.get("bytes", 0)))
        self.card_findings.findChildren(QLabel)[1].setText(str(s.get("findings", len(self.findings))))
        self.card_critical.findChildren(QLabel)[1].setText(str(s.get("critical", sum(x.severity=="Critical" for x in self.findings))))
        self.card_high.findChildren(QLabel)[1].setText(str(s.get("high", sum(x.severity=="High" for x in self.findings))))
        self.card_medium.findChildren(QLabel)[1].setText(str(s.get("medium", sum(x.severity=="Medium" for x in self.findings))))
        self.card_low.findChildren(QLabel)[1].setText(str(s.get("low", sum(x.severity=="Low" for x in self.findings))))
        self.card_errors.findChildren(QLabel)[1].setText(str(s.get("errors", 0)))

        self.category_list.clear()
        counts = {}
        for f in self.findings:
            counts[f.category] = counts.get(f.category, 0) + 1
        for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            self.category_list.addItem(f"{k}: {v}")

        self.top_paths.clear()
        for f in sorted(self.findings, key=lambda x: (-x.score, x.path))[:40]:
            item = QTreeWidgetItem([f.path, f.severity, f.rule])
            self.top_paths.addTopLevelItem(item)

        self.dashboard_note.setText(
            f"Folder: {self.path_edit.text()}  •  Text files scanned: {s.get('scanned_text', 0)}  •  "
            f"Media candidates: {s.get('metadata', 0)}  •  "
            "Read-only scan; no files were changed."
        )

    def build_report_preview(self):
        s = self.stats
        lines = [
            f"{APP_NAME} v{VERSION}",
            "=" * 72,
            f"Scan root: {self.path_edit.text()}",
            f"Timestamp: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "SUMMARY",
            f"Files scanned: {s.get('files', 0)}",
            f"Directories visited: {s.get('dirs', 0)}",
            f"Data scanned: {human_size(s.get('bytes', 0))}",
            f"Findings: {s.get('findings', 0)}",
            f"Critical: {s.get('critical', 0)}",
            f"High: {s.get('high', 0)}",
            f"Medium: {s.get('medium', 0)}",
            f"Low: {s.get('low', 0)}",
            f"Access errors: {s.get('errors', 0)}",
            f"Duration: {s.get('duration', 0):.2f}s",
            "",
            "FINDINGS",
        ]
        for i, f in enumerate(self.findings, 1):
            lines.extend([
                f"{i}. [{f.severity}] {f.category} — {f.rule}",
                f"   Path: {f.path}",
                f"   Detail: {f.detail}",
                f"   Evidence: {f.evidence}",
            ])
        self.report_preview.setPlainText("\n".join(lines))

    def export_json(self):
        if not self.findings and not self.stats:
            QMessageBox.information(self, APP_NAME, "Run a scan first.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export JSON", "privacy_report.json", "JSON (*.json)")
        if not p:
            return
        data = {
            "application": APP_NAME,
            "version": VERSION,
            "scan_root": self.path_edit.text(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "stats": self.stats,
            "findings": [asdict(x) for x in self.findings],
            "privacy_note": "Evidence is masked; findings are heuristic and require review."
        }
        try:
            Path(p).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self.statusBar().showMessage(f"JSON report saved: {p}")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, str(e))

    def export_csv(self):
        if not self.findings:
            QMessageBox.information(self, APP_NAME, "No findings to export.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export CSV", "privacy_findings.csv", "CSV (*.csv)")
        if not p:
            return
        try:
            with open(p, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["Severity", "Score", "Category", "Rule", "Path", "Detail", "Masked Evidence", "Source"])
                for f in self.findings:
                    writer.writerow([f.severity, f.score, f.category, f.rule, f.path, f.detail, f.evidence, f.source])
            self.statusBar().showMessage(f"CSV report saved: {p}")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, str(e))

    def export_text(self):
        if not self.findings and not self.stats:
            QMessageBox.information(self, APP_NAME, "Run a scan first.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export Text", "privacy_report.txt", "Text (*.txt)")
        if not p:
            return
        try:
            Path(p).write_text(self.report_preview.toPlainText(), encoding="utf-8")
            self.statusBar().showMessage(f"Text report saved: {p}")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, str(e))

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { font-size: 13px; }
            #Title { font-size: 28px; font-weight: 700; padding: 2px 0; }
            #Subtitle { color: #5b7187; font-size: 14px; padding-bottom: 6px; }
            QGroupBox { font-weight: 700; border: 1px solid #cbd3dc; border-radius: 8px; margin-top: 8px; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QFrame#Card { border: 1px solid #d3dae2; border-radius: 10px; background: #f8fafc; min-height: 78px; }
            #CardLabel { color: #5f6f7f; font-weight: 600; }
            #CardValue { font-size: 24px; font-weight: 700; }
            QPushButton { padding: 7px 13px; border: 1px solid #b9c2cc; border-radius: 6px; }
            QPushButton:hover { background: #eef3f7; }
            QPushButton#Primary { font-weight: 700; padding: 8px 16px; }
            QLineEdit, QComboBox, QSpinBox { padding: 6px; }
            QTableWidget, QTreeWidget, QListWidget { gridline-color: #d8dee5; }
            QHeaderView::section { padding: 7px; font-weight: 700; }
            QTabBar::tab { padding: 8px 15px; }
        """)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
