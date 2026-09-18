#!/usr/bin/env python3
"""
JASS Quote Harvester v1.0
Local-first quotation extraction and curation tool.

Read-only source scanning. Supports TXT, MD, HTML, EPUB and optional PDF
(PyMuPDF). Extracts candidate quotations using conservative heuristics.
"""

import csv
import json
import re
import sys
import time
import zipfile
from dataclasses import dataclass, asdict
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QFrame,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QSplitter, QTabWidget, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    QHeaderView, QTextBrowser
)

APP_NAME = "JASS Quote Harvester"
VERSION = "1.0"

SUPPORTED = {".txt", ".md", ".markdown", ".html", ".htm", ".epub", ".pdf"}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm"}

# Conservative phrase indicators. They increase candidate score; they are
# not claims that a sentence is a quotation.
QUOTE_HINTS = [
    r"\bI think\b", r"\bI believe\b", r"\bwe must\b", r"\byou should\b",
    r"\bnever\b", r"\balways\b", r"\bremember\b", r"\bperhaps\b",
    r"\blove\b", r"\blife\b", r"\bdeath\b", r"\btime\b", r"\btruth\b",
    r"\bfreedom\b", r"\bhope\b", r"\bwisdom\b", r"\bbeautiful\b",
    r"\bthe world\b", r"\bhuman\b", r"\bpeople\b", r"\bheart\b"
]
QUOTE_HINT_RX = [re.compile(x, re.I) for x in QUOTE_HINTS]

@dataclass
class Quote:
    text: str
    source: str
    location: str = ""
    author: str = ""
    score: int = 0
    tags: str = ""
    favorite: bool = False
    notes: str = ""

def clean_text(s):
    s = unescape(s or "")
    s = s.replace("\u00ad", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    return s.strip()

def strip_html(s):
    s = re.sub(r"(?is)<script.*?</script>", " ", s)
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p\s*>", "\n", s)
    s = re.sub(r"(?i)</div\s*>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return clean_text(s)

def split_sentences(text):
    text = clean_text(text)
    if not text:
        return []
    # Handles common sentence endings without requiring external NLP.
    parts = re.split(r'(?<=[.!?。！？])\s+(?=[A-Z0-9"“‘\'(])', text)
    return [p.strip(" \t\r\n\"“”") for p in parts if p.strip()]

def candidate_score(sentence):
    words = re.findall(r"\b[\w’'-]+\b", sentence, re.UNICODE)
    n = len(words)
    if n < 5 or n > 80:
        return 0
    score = 20
    if 8 <= n <= 35:
        score += 15
    if 35 < n <= 55:
        score += 5
    for rx in QUOTE_HINT_RX:
        if rx.search(sentence):
            score += 4
    if "," in sentence:
        score += 2
    if ":" in sentence or ";" in sentence:
        score += 2
    if sentence.endswith("?") or sentence.endswith("!"):
        score += 3
    if sentence.startswith(("But ", "And ", "Yet ", "So ", "Because ")):
        score += 1
    if re.search(r"\b(?:shall|should|must|cannot|don't|doesn't|isn't|won't)\b", sentence, re.I):
        score += 3
    return min(score, 100)

def extract_quoted_strings(text):
    found = []
    # Straight and curly double quotes, then single quotes for longer spans.
    patterns = [
        r'“([^”]{12,500})”',
        r'"([^"\n]{12,500})"',
        r'‘([^’]{12,500})’',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            q = clean_text(m.group(1))
            if 5 <= len(q.split()) <= 120:
                found.append((q, "Explicit quotation"))
    return found

def read_epub(path):
    with zipfile.ZipFile(path, "r") as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = None
        for e in container.iter():
            if e.tag.lower().endswith("rootfile"):
                rootfile = e.attrib.get("full-path")
                break
        if not rootfile:
            raise ValueError("EPUB package file not found")
        opf = ET.fromstring(z.read(rootfile))
        base = str(Path(rootfile).parent)
        if base == ".":
            base = ""
        manifest = {}
        spine = []
        for e in opf.iter():
            tag = e.tag.lower().split("}")[-1]
            if tag == "item":
                manifest[e.attrib.get("id")] = e.attrib.get("href")
            elif tag == "itemref":
                spine.append(e.attrib.get("idref"))
        chunks = []
        for sid in spine:
            href = manifest.get(sid)
            if not href:
                continue
            target = str(Path(base) / href) if base else href
            target = target.replace("\\", "/")
            # Normalize ./ segments.
            while target.startswith("./"):
                target = target[2:]
            try:
                raw = z.read(target).decode("utf-8", errors="replace")
                chunks.append((target, strip_html(raw)))
            except KeyError:
                # Some EPUBs encode paths differently; try normalized path.
                alt = str(Path(target))
                try:
                    raw = z.read(alt).decode("utf-8", errors="replace")
                    chunks.append((alt, strip_html(raw)))
                except Exception:
                    pass
        metadata = {}
        for e in opf.iter():
            tag = e.tag.lower().split("}")[-1]
            if tag == "title" and e.text:
                metadata["title"] = clean_text(e.text)
            elif tag == "creator" and e.text:
                metadata["author"] = clean_text(e.text)
        return chunks, metadata

def read_source(path):
    ext = path.suffix.lower()
    if ext in {".txt", ".md", ".markdown"}:
        return [(path.name, path.read_text(encoding="utf-8", errors="replace"))], {}
    if ext in {".html", ".htm"}:
        return [(path.name, strip_html(path.read_text(encoding="utf-8", errors="replace")))], {}
    if ext == ".epub":
        return read_epub(path)
    if ext == ".pdf":
        try:
            import fitz
        except ImportError:
            raise RuntimeError("PDF support requires PyMuPDF: python3 -m pip install PyMuPDF")
        doc = fitz.open(path)
        chunks = []
        for i, page in enumerate(doc):
            chunks.append((f"Page {i + 1}", page.get_text("text")))
        return chunks, {}
    raise ValueError("Unsupported file type")

def source_author(path, metadata):
    return metadata.get("author", "") if metadata else ""

def harvest(path, min_score=30, explicit_only=False):
    chunks, metadata = read_source(path)
    author = source_author(path, metadata)
    out = []
    seen = set()
    for location, text in chunks:
        text = clean_text(text)
        if not text:
            continue
        explicit = extract_quoted_strings(text)
        for q, why in explicit:
            key = re.sub(r"\W+", " ", q.lower()).strip()
            if key and key not in seen:
                seen.add(key)
                out.append(Quote(q, str(path), location, author, min(100, 75), "explicit", False, why))
        if explicit_only:
            continue
        sentences = split_sentences(text)
        for sent in sentences:
            score = candidate_score(sent)
            if score < min_score:
                continue
            key = re.sub(r"\W+", " ", sent.lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(Quote(sent, str(path), location, author, score, "candidate"))
    return out

class HarvestWorker(QThread):
    progress = Signal(int, str)
    quote_found = Signal(object)
    finished_harvest = Signal(object)
    error = Signal(str)

    def __init__(self, root, recursive, min_score, explicit_only, max_files):
        super().__init__()
        self.root = Path(root).expanduser()
        self.recursive = recursive
        self.min_score = min_score
        self.explicit_only = explicit_only
        self.max_files = max_files
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def run(self):
        start = time.time()
        stats = {"files": 0, "quotes": 0, "errors": 0, "words": 0, "stopped": False}
        try:
            if self.root.is_file():
                files = [self.root]
            else:
                iterator = self.root.rglob("*") if self.recursive else self.root.glob("*")
                files = []
                for p in iterator:
                    if self.stop_requested:
                        break
                    if p.is_file() and p.suffix.lower() in SUPPORTED:
                        files.append(p)
                        if self.max_files and len(files) >= self.max_files:
                            break

            for i, path in enumerate(files, 1):
                if self.stop_requested:
                    break
                self.progress.emit(int(i * 100 / max(1, len(files))), str(path))
                try:
                    quotes = harvest(path, self.min_score, self.explicit_only)
                    stats["files"] += 1
                    for q in quotes:
                        stats["quotes"] += 1
                        stats["words"] += len(q.text.split())
                        self.quote_found.emit(q)
                except Exception:
                    stats["errors"] += 1
            stats["stopped"] = self.stop_requested
            stats["duration"] = time.time() - start
            self.finished_harvest.emit(stats)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1500, 920)
        self.quotes = []
        self.stats = {}
        self.worker = None
        self.build_ui()
        self.apply_style()

    def build_ui(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 10)

        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        subtitle = QLabel("Local quotation discovery • Books • Documents • Notes • Curated quote library")
        subtitle.setObjectName("Subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        cfg = QGroupBox("Harvest Configuration")
        g = QGridLayout(cfg)
        self.path_edit = QLineEdit(str(Path.home()))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_source)
        g.addWidget(QLabel("Source:"), 0, 0)
        g.addWidget(self.path_edit, 0, 1, 1, 4)
        g.addWidget(browse, 0, 5)

        self.recursive = QCheckBox("Recursive")
        self.recursive.setChecked(True)
        self.explicit = QCheckBox("Explicit quotations only")
        self.min_score = QSpinBox()
        self.min_score.setRange(0, 100)
        self.min_score.setValue(38)
        self.max_files = QSpinBox()
        self.max_files.setRange(0, 1000000)
        self.max_files.setValue(0)
        self.max_files.setSpecialValueText("Unlimited")

        g.addWidget(self.recursive, 1, 0)
        g.addWidget(self.explicit, 1, 1)
        g.addWidget(QLabel("Candidate score:"), 1, 2)
        g.addWidget(self.min_score, 1, 3)
        g.addWidget(QLabel("Max files:"), 1, 4)
        g.addWidget(self.max_files, 1, 5)

        self.start_btn = QPushButton("✦ Harvest Quotes")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self.start_harvest)
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_harvest)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        g.addWidget(self.start_btn, 2, 0, 1, 2)
        g.addWidget(self.stop_btn, 2, 2)
        g.addWidget(self.progress, 2, 3, 1, 3)
        outer.addWidget(cfg)

        self.tabs = QTabWidget()
        self.dashboard = self.make_dashboard()
        self.library = self.make_library()
        self.reader = self.make_reader()
        self.collections = self.make_collections()
        self.reports = self.make_reports()
        self.help = self.make_help()
        self.tabs.addTab(self.dashboard, "Dashboard")
        self.tabs.addTab(self.library, "Quote Library")
        self.tabs.addTab(self.reader, "Quote Card")
        self.tabs.addTab(self.collections, "Collections")
        self.tabs.addTab(self.reports, "Reports")
        self.tabs.addTab(self.help, "Help")
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        self.make_menu()

    def make_menu(self):
        m = self.menuBar().addMenu("File")
        for text, fn in [
            ("Choose Source…", self.choose_source),
            ("Export JSON…", self.export_json),
            ("Export CSV…", self.export_csv),
            ("Export TXT…", self.export_txt),
        ]:
            a = QAction(text, self)
            a.triggered.connect(fn)
            m.addAction(a)
        m.addSeparator()
        a = QAction("Quit", self)
        a.triggered.connect(self.close)
        m.addAction(a)
        m = self.menuBar().addMenu("Harvest")
        a = QAction("Harvest Quotes", self); a.triggered.connect(self.start_harvest); m.addAction(a)
        a = QAction("Stop", self); a.triggered.connect(self.stop_harvest); m.addAction(a)

    def card(self, label, value):
        f = QFrame()
        f.setObjectName("Card")
        l = QVBoxLayout(f)
        a = QLabel(label); a.setObjectName("CardLabel")
        b = QLabel(value); b.setObjectName("CardValue")
        l.addWidget(a); l.addWidget(b)
        return f

    def make_dashboard(self):
        w = QWidget(); lay = QVBoxLayout(w)
        cards = QGridLayout()
        self.c_files = self.card("Sources", "0")
        self.c_quotes = self.card("Quotes", "0")
        self.c_fav = self.card("Favorites", "0")
        self.c_words = self.card("Quote Words", "0")
        self.c_errors = self.card("Errors", "0")
        self.c_score = self.card("Average Score", "0")
        for i, c in enumerate([self.c_files, self.c_quotes, self.c_fav, self.c_words, self.c_errors, self.c_score]):
            cards.addWidget(c, i // 3, i % 3)
        lay.addLayout(cards)

        split = QSplitter(Qt.Horizontal)
        self.source_list = QListWidget()
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderLabels(["Collection / Signal", "Count"])
        self.category_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.category_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        split.addWidget(self.source_list); split.addWidget(self.category_tree)
        lay.addWidget(split, 1)
        self.dashboard_note = QLabel("Choose a folder or document and start harvesting.")
        self.dashboard_note.setWordWrap(True)
        lay.addWidget(self.dashboard_note)
        return w

    def make_library(self):
        w = QWidget(); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search quote text, source, author, tags, notes…")
        self.search.textChanged.connect(self.filter_library)
        self.score_filter = QComboBox()
        self.score_filter.addItems(["All scores", "80+","60+","40+","30+"])
        self.score_filter.currentTextChanged.connect(self.filter_library)
        self.fav_only = QCheckBox("Favorites only")
        self.fav_only.toggled.connect(self.filter_library)
        bar.addWidget(self.search, 1); bar.addWidget(self.score_filter); bar.addWidget(self.fav_only)
        lay.addLayout(bar)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["★", "Score", "Quote", "Author", "Source", "Location", "Tags", "Notes"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self.open_selected_quote)
        lay.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        for text, fn in [
            ("★ Favorite", self.toggle_favorite),
            ("View / Edit", self.open_selected_quote),
            ("Copy Quote", self.copy_quote),
            ("Export Selected", self.export_selected),
        ]:
            b = QPushButton(text); b.clicked.connect(fn); buttons.addWidget(b)
        buttons.addStretch()
        lay.addLayout(buttons)
        return w

    def make_reader(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self.quote_view = QTextBrowser()
        self.quote_view.setOpenExternalLinks(False)
        self.quote_view.setPlaceholderText("Select a quote from the library.")
        lay.addWidget(self.quote_view, 1)
        self.quote_meta = QLabel("")
        self.quote_meta.setWordWrap(True)
        lay.addWidget(self.quote_meta)
        return w

    def make_collections(self):
        w = QWidget(); lay = QVBoxLayout(w)
        info = QLabel(
            "Collections are lightweight session tags. Add your own tags in the Quote Card editor. "
            "Starter views below are derived from quote signals, not from a fixed genre classification."
        )
        info.setWordWrap(True); lay.addWidget(info)
        self.collection_list = QListWidget()
        self.collection_list.addItems([
            "Favorites", "Explicit Quotations", "High Score (80+)",
            "Wisdom / Reflection", "Love / Relationships",
            "Life / Time", "Hope / Freedom"
        ])
        self.collection_list.itemClicked.connect(self.collection_clicked)
        lay.addWidget(self.collection_list, 1)
        return w

    def make_reports(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self.report = QPlainTextEdit(); self.report.setReadOnly(True)
        lay.addWidget(self.report, 1)
        row = QHBoxLayout()
        for text, fn in [("JSON…", self.export_json), ("CSV…", self.export_csv), ("TXT…", self.export_txt)]:
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch(); lay.addLayout(row)
        return w

    def make_help(self):
        w = QWidget(); lay = QVBoxLayout(w)
        t = QPlainTextEdit(); t.setReadOnly(True)
        t.setPlainText("""JASS Quote Harvester v1.0

PURPOSE
-------
Find potentially quotable passages in your own local books, documents and notes,
then curate them into a searchable quote library.

SUPPORTED SOURCES
-----------------
TXT, Markdown, HTML, EPUB and PDF (PDF requires PyMuPDF).

HOW HARVESTING WORKS
--------------------
1. Explicit quotation marks are detected first.
2. Sentences are scored using length and conservative linguistic signals.
3. Candidates above the selected threshold are added.
4. Duplicate text is suppressed within each source.
5. You review and curate the results.

This is heuristic extraction, not literary attribution software.

READ-ONLY DESIGN
----------------
Source files are never modified. The application does not upload content or
contact a quote database.

COPYRIGHT / FAIR USE
--------------------
Use this tool primarily with material you are entitled to process. A quotation
harvester can surface copyrighted passages; exporting large portions of a book
may create copyright issues. JASS does not determine whether a use is lawful.

PDF
---
Install optional support:
    python3 -m pip install PyMuPDF

EPUB
----
EPUB parsing uses Python's standard library ZIP/XML support.

ROADMAP
-------
v1.1:
• Persistent SQLite quote library
• Better EPUB metadata and chapter handling
• Reading position / page context
• Custom extraction rules
• Import existing quote CSV/JSON
• Duplicate similarity detection

v1.2:
• Quote provenance and citation fields
• Book/author metadata
• Language-aware sentence splitting
• Punjabi Gurmukhi / Shahmukhi / Mizo support
• Multilingual quote search

v1.3:
• Cover thumbnails
• Quote cards
• Bulk tagging
• Collections and smart filters
• HTML/PDF quote books

v2.0:
• Local semantic search
• Optional Ollama / LM Studio integration
• RAG-assisted quote discovery
• Citation validation
• Research workspace integration

CORE PRINCIPLE
--------------
Harvest broadly. Verify the source. Curate deliberately.
""")
        lay.addWidget(t, 1)
        return w

    def choose_source(self):
        p = QFileDialog.getExistingDirectory(self, "Choose source folder", self.path_edit.text())
        if p:
            self.path_edit.setText(p)

    def start_harvest(self):
        if self.worker and self.worker.isRunning():
            return
        p = Path(self.path_edit.text().strip()).expanduser()
        if not p.exists():
            QMessageBox.warning(self, APP_NAME, "Choose an existing file or folder.")
            return
        self.quotes.clear()
        self.stats = {}
        self.table.setRowCount(0)
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.progress.setVisible(True); self.progress.setValue(0)
        self.statusBar().showMessage("Harvesting…")
        self.worker = HarvestWorker(
            p, self.recursive.isChecked(), self.min_score.value(),
            self.explicit.isChecked(), self.max_files.value()
        )
        self.worker.progress.connect(lambda pct, path: self.scan_progress(pct, path))
        self.worker.quote_found.connect(self.add_quote)
        self.worker.finished_harvest.connect(self.harvest_finished)
        self.worker.error.connect(self.harvest_error)
        self.worker.start()

    def stop_harvest(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.statusBar().showMessage("Stopping…")

    def scan_progress(self, pct, path):
        self.progress.setValue(pct)
        self.statusBar().showMessage(f"Harvesting: {path}")

    def add_quote(self, q):
        self.quotes.append(q)
        self.insert_quote(q)

    def insert_quote(self, q):
        row = self.table.rowCount()
        self.table.insertRow(row)
        vals = ["★" if q.favorite else "", q.score, q.text, q.author, q.source, q.location, q.tags, q.notes]
        for c, v in enumerate(vals):
            self.table.setItem(row, c, QTableWidgetItem(str(v)))
        self.table.item(row, 2).setToolTip(q.text)

    def rebuild_table(self):
        self.table.setRowCount(0)
        for q in self.quotes:
            self.insert_quote(q)
        self.filter_library()

    def selected_index(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        visible_row = rows[0].row()
        visible = []
        needle = self.search.text().lower().strip()
        sf = self.score_filter.currentText()
        fav = self.fav_only.isChecked()
        for q in self.quotes:
            vals = " ".join([q.text, q.author, q.source, q.location, q.tags, q.notes]).lower()
            ok = not needle or needle in vals
            if sf != "All scores":
                threshold = int(sf.replace("+", ""))
                ok = ok and q.score >= threshold
            if fav:
                ok = ok and q.favorite
            if ok:
                visible.append(q)
        return self.quotes.index(visible[visible_row]) if 0 <= visible_row < len(visible) else None

    def filter_library(self):
        needle = self.search.text().lower().strip()
        sf = self.score_filter.currentText()
        fav = self.fav_only.isChecked()
        threshold = int(sf.replace("+", "")) if sf != "All scores" else 0
        for r, q in enumerate(self.quotes):
            hay = " ".join([q.text, q.author, q.source, q.location, q.tags, q.notes]).lower()
            ok = (not needle or needle in hay) and q.score >= threshold and (not fav or q.favorite)
            self.table.setRowHidden(r, not ok)

    def current_quote(self):
        idx = self.selected_index()
        return self.quotes[idx] if idx is not None else None

    def toggle_favorite(self):
        q = self.current_quote()
        if not q:
            return
        q.favorite = not q.favorite
        self.rebuild_table()
        self.update_dashboard()

    def copy_quote(self):
        q = self.current_quote()
        if not q:
            return
        QApplication.clipboard().setText(q.text)
        self.statusBar().showMessage("Quote copied to clipboard.")

    def open_selected_quote(self):
        q = self.current_quote()
        if not q:
            QMessageBox.information(self, APP_NAME, "Select a quote first.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Quote Card / Editor")
        dlg.resize(850, 650)
        lay = QVBoxLayout(dlg)
        text = QPlainTextEdit(q.text)
        author = QLineEdit(q.author)
        tags = QLineEdit(q.tags)
        notes = QPlainTextEdit(q.notes)
        form = QFormLayout()
        form.addRow("Quote:", text)
        form.addRow("Author:", author)
        form.addRow("Tags:", tags)
        form.addRow("Notes:", notes)
        lay.addLayout(form)
        meta = QLabel(f"Score: {q.score}   •   Source: {q.source}   •   Location: {q.location}")
        meta.setWordWrap(True); lay.addWidget(meta)
        row = QHBoxLayout()
        fav = QPushButton("★ Favorite" if not q.favorite else "☆ Unfavorite")
        save = QPushButton("Save")
        close = QPushButton("Close")
        row.addWidget(fav); row.addStretch(); row.addWidget(save); row.addWidget(close)
        lay.addLayout(row)
        fav.clicked.connect(lambda: setattr(q, "favorite", not q.favorite))
        def save_and_close():
            q.text = text.toPlainText().strip()
            q.author = author.text().strip()
            q.tags = tags.text().strip()
            q.notes = notes.toPlainText().strip()
            self.rebuild_table()
            self.update_dashboard()
            self.show_quote(q)
            dlg.accept()
        save.clicked.connect(save_and_close)
        close.clicked.connect(dlg.reject)
        self.show_quote(q)
        dlg.exec()

    def show_quote(self, q):
        self.quote_view.setHtml(
            f'<div style="font-size:24px; line-height:1.5;">“{self.escape_html(q.text)}”</div>'
            f'<div style="font-size:16px; margin-top:24px;">— {self.escape_html(q.author or "Unknown")}</div>'
        )
        self.quote_meta.setText(f"Score {q.score}  •  {q.source}  •  {q.location}  •  Tags: {q.tags or '—'}")
        self.tabs.setCurrentWidget(self.reader)

    @staticmethod
    def escape_html(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))

    def collection_clicked(self, item):
        name = item.text()
        if name == "Favorites":
            self.fav_only.setChecked(True)
        elif name == "High Score (80+)":
            self.fav_only.setChecked(False); self.score_filter.setCurrentText("80+")
        else:
            self.fav_only.setChecked(False)
            self.score_filter.setCurrentText("All scores")
            mapping = {
                "Explicit Quotations": "explicit",
                "Wisdom / Reflection": "wisdom",
                "Love / Relationships": "love",
                "Life / Time": "life",
                "Hope / Freedom": "hope",
            }
            self.search.setText(mapping.get(name, ""))

    def update_dashboard(self):
        self.c_files.findChildren(QLabel)[1].setText(str(self.stats.get("files", 0)))
        self.c_quotes.findChildren(QLabel)[1].setText(str(len(self.quotes)))
        self.c_fav.findChildren(QLabel)[1].setText(str(sum(q.favorite for q in self.quotes)))
        self.c_words.findChildren(QLabel)[1].setText(str(sum(len(q.text.split()) for q in self.quotes)))
        self.c_errors.findChildren(QLabel)[1].setText(str(self.stats.get("errors", 0)))
        avg = sum(q.score for q in self.quotes) / len(self.quotes) if self.quotes else 0
        self.c_score.findChildren(QLabel)[1].setText(f"{avg:.1f}")
        self.source_list.clear()
        sources = {}
        for q in self.quotes:
            sources[q.source] = sources.get(q.source, 0) + 1
        for s, n in sorted(sources.items(), key=lambda x: (-x[1], x[0])):
            self.source_list.addItem(f"{n:>4}  {s}")
        self.category_tree.clear()
        groups = {
            "Explicit quotations": lambda q: "explicit" in q.tags,
            "High score": lambda q: q.score >= 80,
            "Love / relationships": lambda q: bool(re.search(r"\b(love|heart|relationship)\b", q.text, re.I)),
            "Life / time": lambda q: bool(re.search(r"\b(life|time|death)\b", q.text, re.I)),
            "Hope / freedom": lambda q: bool(re.search(r"\b(hope|freedom)\b", q.text, re.I)),
            "Wisdom / reflection": lambda q: bool(re.search(r"\b(remember|truth|wisdom|perhaps|always|never)\b", q.text, re.I)),
        }
        for name, fn in groups.items():
            n = sum(fn(q) for q in self.quotes)
            item = QTreeWidgetItem([name, str(n)])
            self.category_tree.addTopLevelItem(item)
        self.dashboard_note.setText(
            f"Sources processed: {self.stats.get('files', 0)}  •  Quotes harvested: {len(self.quotes)}  •  "
            f"Errors: {self.stats.get('errors', 0)}  •  Read-only source processing."
        )

    def harvest_finished(self, stats):
        self.stats = stats
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        self.update_dashboard()
        self.build_report()
        self.statusBar().showMessage(
            f"Harvest {'stopped' if stats['stopped'] else 'completed'}: "
            f"{len(self.quotes)} quotes from {stats['files']} sources in {stats['duration']:.1f}s"
        )

    def harvest_error(self, msg):
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self.progress.setVisible(False)
        QMessageBox.critical(self, APP_NAME, msg)

    def build_report(self):
        lines = [
            f"{APP_NAME} v{VERSION}", "=" * 72,
            f"Source: {self.path_edit.text()}",
            f"Files processed: {self.stats.get('files', 0)}",
            f"Quotes: {len(self.quotes)}",
            f"Errors: {self.stats.get('errors', 0)}",
            f"Duration: {self.stats.get('duration', 0):.2f}s", "",
            "QUOTES"
        ]
        for i, q in enumerate(self.quotes, 1):
            lines += [f"{i}. [{q.score}] {q.text}", f"   — {q.author or 'Unknown'}",
                      f"   {q.source} | {q.location}", f"   Tags: {q.tags or '—'}"]
        self.report.setPlainText("\n".join(lines))

    def export_data(self):
        return {
            "application": APP_NAME, "version": VERSION,
            "source": self.path_edit.text(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "stats": self.stats,
            "quotes": [asdict(q) for q in self.quotes],
            "note": "Quotes are heuristically harvested; verify wording and provenance against the source."
        }

    def export_json(self):
        if not self.quotes:
            QMessageBox.information(self, APP_NAME, "No quotes to export.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export JSON", "quotes.json", "JSON (*.json)")
        if not p: return
        Path(p).write_text(json.dumps(self.export_data(), indent=2, ensure_ascii=False), encoding="utf-8")
        self.statusBar().showMessage(f"Saved {p}")

    def export_csv(self):
        if not self.quotes:
            QMessageBox.information(self, APP_NAME, "No quotes to export.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export CSV", "quotes.csv", "CSV (*.csv)")
        if not p: return
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Quote", "Author", "Source", "Location", "Score", "Tags", "Favorite", "Notes"])
            for q in self.quotes:
                w.writerow([q.text, q.author, q.source, q.location, q.score, q.tags, q.favorite, q.notes])
        self.statusBar().showMessage(f"Saved {p}")

    def export_txt(self):
        if not self.quotes:
            QMessageBox.information(self, APP_NAME, "No quotes to export.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export TXT", "quotes.txt", "Text (*.txt)")
        if not p: return
        Path(p).write_text(self.report.toPlainText(), encoding="utf-8")
        self.statusBar().showMessage(f"Saved {p}")

    def export_selected(self):
        q = self.current_quote()
        if not q:
            QMessageBox.information(self, APP_NAME, "Select a quote first.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Export Quote", "quote.txt", "Text (*.txt)")
        if p:
            Path(p).write_text(f"“{q.text}”\n\n— {q.author or 'Unknown'}\n\nSource: {q.source}\nLocation: {q.location}\n", encoding="utf-8")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        event.accept()

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
    w = MainWindow()
    w.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
