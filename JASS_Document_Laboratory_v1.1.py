#!/usr/bin/env python3
"""
JASS Document Laboratory v1.0
Local-first, read-only document inspection and research workstation.
"""

import csv
import html
import json
import os
import re
import sys
import sqlite3
import datetime
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QStatusBar, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget, QComboBox
)

APP_VERSION = "1.1.0"
SUPPORTED = {".pdf", ".epub", ".txt", ".md", ".markdown", ".html", ".htm", ".docx"}
TEXT_EXTS = {".txt", ".md", ".markdown", ".html", ".htm"}
MAX_PREVIEW = 200_000
MAX_SEARCH_RESULTS = 500


def safe_text(value):
    if value is None:
        return ""
    return str(value)


def html_to_text(text):
    text = re.sub(r"(?is)<script.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def normalize_text(text):
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def language_hints(text):
    counts = Counter()
    for ch in text:
        name = ""
        try:
            import unicodedata
            name = unicodedata.name(ch, "")
        except Exception:
            pass
        for script in ("LATIN", "BENGALI", "GURMUKHI", "DEVANAGARI",
                       "ARABIC", "CYRILLIC", "GREEK", "MIZO"):
            if script in name:
                counts[script.title()] += 1
                break
        else:
            if ch.isalpha():
                counts["Other"] += 1
    return counts


def extract_text_file(path):
    data = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        data = html_to_text(data)
    return normalize_text(data)


def extract_pdf(path):
    try:
        import fitz
    except ImportError:
        raise RuntimeError("PDF support requires PyMuPDF: python3 -m pip install PyMuPDF")
    doc = fitz.open(str(path))
    pages = []
    for i, page in enumerate(doc):
        pages.append(f"\n--- PAGE {i + 1} ---\n{page.get_text('text')}")
    return normalize_text("\n".join(pages)), len(doc)


def epub_spine_items(path):
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = container.find(".//c:rootfile", ns)
        if rootfile is None:
            raise RuntimeError("EPUB container.xml has no rootfile.")
        opf_path = rootfile.attrib["full-path"]
        opf_dir = str(Path(opf_path).parent).replace("\\", "/")
        opf = ET.fromstring(z.read(opf_path))
        nsuri = opf.tag.split("}")[0].strip("{")
        n = {"o": nsuri}
        manifest = {}
        for item in opf.findall(".//o:manifest/o:item", n):
            manifest[item.attrib.get("id")] = item.attrib.get("href", "")
        spine = []
        for itemref in opf.findall(".//o:spine/o:itemref", n):
            ident = itemref.attrib.get("idref")
            href = manifest.get(ident)
            if href:
                target = str(Path(opf_dir) / href).replace("\\", "/")
                spine.append(target)
        return spine


def extract_epub(path):
    parts = []
    with zipfile.ZipFile(path) as z:
        for i, member in enumerate(epub_spine_items(path), 1):
            try:
                raw = z.read(member)
                text = raw.decode("utf-8", errors="replace")
                text = html_to_text(text)
                if text.strip():
                    parts.append(f"\n--- CHAPTER {i} ---\n{text}")
            except KeyError:
                continue
    return normalize_text("\n".join(parts))


def extract_docx(path):
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError("DOCX support requires python-docx: python3 -m pip install python-docx")
    doc = Document(str(path))
    blocks = []
    for p in doc.paragraphs:
        if p.text.strip():
            blocks.append(p.text)
    for table in doc.tables:
        blocks.append("\n--- TABLE ---")
        for row in table.rows:
            blocks.append("\t".join(cell.text for cell in row.cells))
    return normalize_text("\n".join(blocks))


def extract_document(path):
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return extract_text_file(path), None
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".epub":
        return extract_epub(path), None
    if ext == ".docx":
        return extract_docx(path), None
    raise RuntimeError(f"Unsupported document type: {ext}")


def document_stats(text):
    words = re.findall(r"\S+", text)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    lines = text.splitlines()
    headings = [
        x.strip() for x in lines
        if re.match(r"^\s{0,3}(#{1,6}\s+|[A-Z][A-Z0-9 .,:;!?'-]{5,})$", x.strip())
    ]
    urls = re.findall(r"https?://\S+", text, re.I)
    emails = re.findall(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b", text)
    repeated_lines = sum(
        n - 1 for n in Counter(x.strip() for x in lines if x.strip()).values() if n > 1
    )
    hints = language_hints(text)
    return {
        "characters": len(text),
        "words": len(words),
        "lines": len(lines),
        "paragraphs": len(paragraphs),
        "headings": len(headings),
        "urls": len(urls),
        "emails": len(emails),
        "repeated_line_surplus": repeated_lines,
        "languages": ", ".join(f"{k} ({v:,})" for k, v in hints.most_common(8)),
        "max_line_length": max((len(x) for x in lines), default=0),
        "empty_lines": sum(1 for x in lines if not x.strip()),
    }


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    extension TEXT,
    size INTEGER,
    modified REAL,
    words INTEGER,
    characters INTEGER,
    paragraphs INTEGER,
    headings INTEGER,
    error TEXT DEFAULT '',
    added_at TEXT NOT NULL,
    last_opened TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(document_id),
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    location TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS quotations (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    quote TEXT NOT NULL,
    location TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(
    document_id UNINDEXED,
    content,
    tokenize='unicode61 remove_diacritics 0'
);
"""


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def connect_db(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(DB_SCHEMA)
    return conn


class ResearchDB:
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / ".jass_document_laboratory.sqlite3"
        self.conn = connect_db(self.path)

    def upsert_records(self, records):
        cur = self.conn.cursor()
        for rec in records:
            cur.execute("""
                INSERT INTO documents
                (path,name,extension,size,modified,words,characters,paragraphs,headings,error,added_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                    name=excluded.name, extension=excluded.extension, size=excluded.size,
                    modified=excluded.modified, words=excluded.words,
                    characters=excluded.characters, paragraphs=excluded.paragraphs,
                    headings=excluded.headings, error=excluded.error
            """, (
                rec.path, rec.name, rec.extension, rec.size, rec.modified,
                rec.words, rec.characters, rec.paragraphs, rec.headings,
                rec.error, now_iso()
            ))
            doc_id = cur.execute(
                "SELECT id FROM documents WHERE path=?", (rec.path,)
            ).fetchone()[0]
            if not rec.error:
                try:
                    content, _ = extract_document(Path(rec.path))
                    cur.execute("DELETE FROM document_search WHERE document_id=?", (doc_id,))
                    cur.execute(
                        "INSERT INTO document_search(document_id,content) VALUES (?,?)",
                        (doc_id, content)
                    )
                except Exception:
                    pass
        self.conn.commit()

    def all_documents(self):
        return self.conn.execute("""
            SELECT id,path,name,extension,size,modified,words,characters,paragraphs,headings,error
            FROM documents ORDER BY name COLLATE NOCASE
        """).fetchall()

    def document_id(self, path):
        row = self.conn.execute("SELECT id FROM documents WHERE path=?", (path,)).fetchone()
        return row[0] if row else None

    def set_last_opened(self, path):
        self.conn.execute(
            "UPDATE documents SET last_opened=? WHERE path=?", (now_iso(), path)
        )
        self.conn.commit()

    def get_note(self, path):
        did = self.document_id(path)
        if did is None:
            return ""
        row = self.conn.execute(
            "SELECT body FROM notes WHERE document_id=?", (did,)
        ).fetchone()
        return row[0] if row else ""

    def set_note(self, path, body):
        did = self.document_id(path)
        if did is None:
            return
        self.conn.execute("""
            INSERT INTO notes(document_id,body,updated_at) VALUES (?,?,?)
            ON CONFLICT(document_id) DO UPDATE SET
                body=excluded.body, updated_at=excluded.updated_at
        """, (did, body, now_iso()))
        self.conn.commit()

    def add_bookmark(self, path, label, location, note):
        did = self.document_id(path)
        if did is None:
            return
        self.conn.execute(
            "INSERT INTO bookmarks(document_id,label,location,note,created_at) VALUES (?,?,?,?,?)",
            (did, label, location, note, now_iso())
        )
        self.conn.commit()

    def bookmarks(self, path=None):
        if path:
            did = self.document_id(path)
            return self.conn.execute("""
                SELECT id,label,location,note,created_at FROM bookmarks
                WHERE document_id=? ORDER BY id DESC
            """, (did,)).fetchall()
        return self.conn.execute("""
            SELECT b.id,d.name,b.label,b.location,b.note,b.created_at
            FROM bookmarks b JOIN documents d ON d.id=b.document_id
            ORDER BY b.id DESC
        """).fetchall()

    def add_quote(self, path, quote, location, note):
        did = self.document_id(path)
        if did is None:
            return
        self.conn.execute(
            "INSERT INTO quotations(document_id,quote,location,note,created_at) VALUES (?,?,?,?,?)",
            (did, quote, location, note, now_iso())
        )
        self.conn.commit()

    def quotes(self):
        return self.conn.execute("""
            SELECT q.id,d.name,q.quote,q.location,q.note,q.created_at
            FROM quotations q JOIN documents d ON d.id=q.document_id
            ORDER BY q.id DESC
        """).fetchall()

    def search(self, query, limit=500):
        return self.conn.execute("""
            SELECT d.path,d.name,
                   snippet(document_search,1,'[',']',' … ',24),
                   bm25(document_search)
            FROM document_search
            JOIN documents d ON d.id=document_search.document_id
            WHERE document_search MATCH ?
            ORDER BY bm25(document_search)
            LIMIT ?
        """, (query, limit)).fetchall()

    def close(self):
        self.conn.close()


@dataclass
class DocRecord:
    path: str
    name: str
    extension: str
    size: int
    modified: float
    words: int
    characters: int
    paragraphs: int
    headings: int
    error: str = ""


class ScanWorker(QThread):
    progress = Signal(int, str)
    finished_data = Signal(object)
    failed = Signal(str)

    def __init__(self, root, recursive=True, max_docs=10000):
        super().__init__()
        self.root = Path(root)
        self.recursive = recursive
        self.max_docs = max_docs
        self.stop_event = Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        records = []
        errors = 0
        try:
            iterator = self.root.rglob("*") if self.recursive else self.root.glob("*")
            candidates = []
            for p in iterator:
                if self.stop_event.is_set():
                    return
                if p.is_file() and p.suffix.lower() in SUPPORTED:
                    candidates.append(p)
                    if len(candidates) >= self.max_docs:
                        break
            total = len(candidates)
            for i, path in enumerate(candidates, 1):
                if self.stop_event.is_set():
                    return
                self.progress.emit(int(i / max(1, total) * 100), f"Reading {path.name}")
                try:
                    text, _ = extract_document(path)
                    st = document_stats(text)
                    records.append(DocRecord(
                        str(path), path.name, path.suffix.lower(),
                        path.stat().st_size, path.stat().st_mtime,
                        st["words"], st["characters"], st["paragraphs"], st["headings"]
                    ))
                except Exception as exc:
                    errors += 1
                    records.append(DocRecord(
                        str(path), path.name, path.suffix.lower(),
                        path.stat().st_size if path.exists() else 0,
                        path.stat().st_mtime if path.exists() else 0,
                        0, 0, 0, 0, str(exc)
                    ))
            self.finished_data.emit({"records": records, "errors": errors})
        except Exception as exc:
            self.failed.emit(str(exc))


class CopyTable(QTableWidget):
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected()
            return
        super().keyPressEvent(event)

    def copy_selected(self):
        ranges = self.selectedRanges()
        if not ranges:
            item = self.currentItem()
            if item:
                QApplication.clipboard().setText(item.text())
            return
        out = []
        for rg in ranges:
            for r in range(rg.topRow(), rg.bottomRow() + 1):
                out.append("\t".join(
                    self.item(r, c).text() if self.item(r, c) else ""
                    for c in range(rg.leftColumn(), rg.rightColumn() + 1)
                ))
        QApplication.clipboard().setText("\n".join(out))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"JASS Document Laboratory v{APP_VERSION}")
        self.resize(1450, 900)
        self.records = []
        self.current_text = ""
        self.current_path = None
        self.notes = {}
        self.db = None
        self.worker = None
        self.build_ui()
        self.statusBar().showMessage("Ready — local-first • read-only")

    def build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        self.setCentralWidget(central)

        bar = QHBoxLayout()
        self.open_btn = QPushButton("Open Folder")
        self.open_btn.clicked.connect(self.open_folder)
        bar.addWidget(self.open_btn)

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self.scan_folder)
        bar.addWidget(self.scan_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_scan)
        bar.addWidget(self.stop_btn)

        self.recursive = QComboBox()
        self.recursive.addItems(["Recursive scan", "Current folder only"])
        bar.addWidget(self.recursive)

        self.export_btn = QPushButton("Export Report")
        self.export_btn.clicked.connect(self.export_report)
        bar.addWidget(self.export_btn)
        bar.addStretch()
        root.addLayout(bar)

        self.path_label = QLabel("No folder selected")
        root.addWidget(self.path_label)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.build_library_tab()
        self.build_reader_tab()
        self.build_search_tab()
        self.build_stats_tab()
        self.build_notes_tab()

    def build_library_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        top = QHBoxLayout()
        self.library_filter = QLineEdit()
        self.library_filter.setPlaceholderText("Filter documents by name/path...")
        self.library_filter.textChanged.connect(self.filter_library)
        top.addWidget(self.library_filter, 1)
        self.format_filter = QComboBox()
        self.format_filter.addItems(["All formats", ".pdf", ".epub", ".txt", ".md", ".html", ".docx"])
        self.format_filter.currentTextChanged.connect(self.filter_library)
        top.addWidget(self.format_filter)
        lay.addLayout(top)

        self.library = CopyTable(0, 9)
        self.library.setHorizontalHeaderLabels([
            "Document", "Format", "Size", "Words", "Characters",
            "Paragraphs", "Headings", "Modified", "Status"
        ])
        self.library.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.library.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.library.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.library.itemDoubleClicked.connect(self.open_record)
        self.library.itemSelectionChanged.connect(self.library_selection_changed)
        self.library.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.library)
        self.tabs.addTab(tab, "Library")

    def build_reader_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        top = QHBoxLayout()
        self.reader_title = QLabel("No document selected")
        self.reader_title.setFont(QFont("Sans Serif", 13, QFont.Weight.Bold))
        top.addWidget(self.reader_title, 1)
        self.reader_font = QSpinBox()
        self.reader_font.setRange(8, 36)
        self.reader_font.setValue(12)
        self.reader_font.valueChanged.connect(lambda v: self.reader.setFontPointSize(v))
        top.addWidget(QLabel("Font"))
        top.addWidget(self.reader_font)
        self.copy_doc_btn = QPushButton("Copy All Text")
        self.copy_doc_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.current_text))
        top.addWidget(self.copy_doc_btn)
        self.save_text_btn = QPushButton("Export Text")
        self.save_text_btn.clicked.connect(self.export_current_text)
        top.addWidget(self.save_text_btn)
        lay.addLayout(top)

        self.reader = QTextBrowser()
        self.reader.setOpenExternalLinks(False)
        lay.addWidget(self.reader)
        self.tabs.addTab(tab, "Reader")

    def build_search_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search across indexed document text...")
        top.addWidget(self.search_edit, 1)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.search_documents)
        top.addWidget(self.search_btn)
        self.search_limit = QSpinBox()
        self.search_limit.setRange(10, MAX_SEARCH_RESULTS)
        self.search_limit.setValue(100)
        top.addWidget(self.search_limit)
        lay.addLayout(top)

        self.search_info = QLabel("Search uses the persistent local SQLite FTS5 index after a scan.")
        lay.addWidget(self.search_info)

        self.search_results = CopyTable(0, 4)
        self.search_results.setHorizontalHeaderLabels(["Document", "Match / Context", "Path", "Rank"])
        self.search_results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.search_results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.search_results.itemDoubleClicked.connect(self.open_search_result)
        lay.addWidget(self.search_results)
        self.tabs.addTab(tab, "Search")

    def build_stats_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        self.stats = QTableWidget(0, 2)
        self.stats.setHorizontalHeaderLabels(["Metric", "Value"])
        self.stats.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.stats)
        self.tabs.addTab(tab, "Statistics")

    def build_notes_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.research_tabs = QTabWidget()
        layout.addWidget(self.research_tabs)

        notes_tab = QWidget()
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Documents"))
        self.note_list = QListWidget()
        self.note_list.currentRowChanged.connect(self.load_note)
        ll.addWidget(self.note_list)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.note_title = QLabel("Select a document")
        rl.addWidget(self.note_title)
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("Persistent research notes for the selected document...")
        self.note_edit.textChanged.connect(self.save_note)
        rl.addWidget(self.note_edit)
        split.addWidget(right)
        split.setSizes([350, 900])
        nl = QVBoxLayout(notes_tab)
        nl.addWidget(split)
        self.research_tabs.addTab(notes_tab, "Notes")

        bookmarks_tab = QWidget()
        bl = QVBoxLayout(bookmarks_tab)
        bbar = QHBoxLayout()
        self.bookmark_label = QLineEdit()
        self.bookmark_label.setPlaceholderText("Bookmark label")
        bbar.addWidget(self.bookmark_label)
        self.bookmark_location = QLineEdit()
        self.bookmark_location.setPlaceholderText("Page / chapter / location")
        bbar.addWidget(self.bookmark_location)
        add_b = QPushButton("Add Bookmark")
        add_b.clicked.connect(self.add_bookmark)
        bbar.addWidget(add_b)
        bl.addLayout(bbar)
        self.bookmarks_table = CopyTable(0, 5)
        self.bookmarks_table.setHorizontalHeaderLabels(["ID","Document","Label","Location","Note"])
        self.bookmarks_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        bl.addWidget(self.bookmarks_table)
        self.research_tabs.addTab(bookmarks_tab, "Bookmarks")

        quotes_tab = QWidget()
        ql = QVBoxLayout(quotes_tab)
        self.quote_edit = QPlainTextEdit()
        self.quote_edit.setPlaceholderText("Paste or compose a quotation to save...")
        ql.addWidget(self.quote_edit)
        qbar = QHBoxLayout()
        self.quote_location = QLineEdit()
        self.quote_location.setPlaceholderText("Page / chapter / location")
        qbar.addWidget(self.quote_location)
        add_q = QPushButton("Save Quotation")
        add_q.clicked.connect(self.add_quote)
        qbar.addWidget(add_q)
        ql.addLayout(qbar)
        self.quotes_table = CopyTable(0, 5)
        self.quotes_table.setHorizontalHeaderLabels(["ID","Document","Quotation","Location","Note"])
        self.quotes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ql.addWidget(self.quotes_table)
        self.research_tabs.addTab(quotes_tab, "Quotations")

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Document Folder")
        if folder:
            self.path_label.setText(folder)
            self.scan_folder()

    def scan_folder(self):
        folder = self.path_label.text()
        if not folder or not Path(folder).is_dir():
            QMessageBox.information(self, "Folder", "Select a valid document folder first.")
            return
        self.stop_scan()
        recursive = self.recursive.currentIndex() == 0
        self.worker = ScanWorker(folder, recursive)
        self.worker.progress.connect(self.scan_progress)
        self.worker.finished_data.connect(self.scan_finished)
        self.worker.failed.connect(self.scan_failed)
        self.open_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        self.worker = None
        self.open_btn.setEnabled(True)
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def scan_progress(self, value, message):
        self.statusBar().showMessage(f"{message} ({value}%)")

    def scan_failed(self, message):
        self.stop_scan()
        QMessageBox.critical(self, "Scan Error", message)

    def scan_finished(self, data):
        self.records = data["records"]
        try:
            if self.db:
                self.db.close()
            self.db = ResearchDB(self.path_label.text())
            self.db.upsert_records(self.records)
        except Exception as exc:
            self.db = None
            QMessageBox.warning(self, "Library Database", f"Persistent research database could not be created:\n{exc}")
        self.stop_scan()
        self.populate_library()
        self.populate_stats(data["errors"])
        self.populate_notes()
        self.statusBar().showMessage(
            f"Indexed {len(self.records):,} documents • {data['errors']:,} extraction errors • persistent SQLite library ready"
        )

    def populate_library(self):
        self.library.setRowCount(0)
        for rec in self.records:
            r = self.library.rowCount()
            self.library.insertRow(r)
            vals = [
                rec.name, rec.extension, self.human_size(rec.size),
                f"{rec.words:,}", f"{rec.characters:,}",
                f"{rec.paragraphs:,}", f"{rec.headings:,}",
                self.format_time(rec.modified), "ERROR" if rec.error else "OK"
            ]
            for c, value in enumerate(vals):
                item = QTableWidgetItem(value)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, rec.path)
                self.library.setItem(r, c, item)
        self.library.resizeRowsToContents()
        self.filter_library()
        self.update_note_list()

    def filter_library(self):
        q = self.library_filter.text().casefold().strip()
        fmt = self.format_filter.currentText()
        for r in range(self.library.rowCount()):
            name = self.library.item(r, 0).text().casefold()
            path = self.records[r].path.casefold() if r < len(self.records) else ""
            ext = self.library.item(r, 1).text()
            visible = (not q or q in name or q in path) and (fmt == "All formats" or ext == fmt)
            self.library.setRowHidden(r, not visible)

    def library_selection_changed(self):
        rows = self.library.selectionModel().selectedRows()
        if rows:
            r = rows[0].row()
            if 0 <= r < len(self.records):
                self.load_document(self.records[r].path)

    def open_record(self, item):
        path = item.data(Qt.ItemDataRole.UserRole) or self.records[item.row()].path
        self.load_document(path)

    def load_document(self, path):
        try:
            text, page_count = extract_document(Path(path))
            self.current_path = path
            self.current_text = text
            if self.db:
                self.db.set_last_opened(path)
            self.reader_title.setText(Path(path).name)
            self.reader.setPlainText(text[:MAX_PREVIEW])
            self.reader.setFontPointSize(self.reader_font.value())
            self.populate_current_stats(text, page_count)
            self.tabs.setCurrentIndex(1)
        except Exception as exc:
            QMessageBox.critical(self, "Document Error", str(exc))

    def populate_current_stats(self, text, page_count=None):
        st = document_stats(text)
        rows = [
            ("Path", self.current_path or ""),
            ("Format", Path(self.current_path).suffix.lower() if self.current_path else ""),
            ("Characters", f"{st['characters']:,}"),
            ("Words", f"{st['words']:,}"),
            ("Lines", f"{st['lines']:,}"),
            ("Paragraphs", f"{st['paragraphs']:,}"),
            ("Headings", f"{st['headings']:,}"),
            ("URLs", f"{st['urls']:,}"),
            ("Emails", f"{st['emails']:,}"),
            ("Repeated-line surplus", f"{st['repeated_line_surplus']:,}"),
            ("Maximum line length", f"{st['max_line_length']:,}"),
            ("Language/script hints", st["languages"] or "None detected"),
        ]
        if page_count:
            rows.insert(2, ("PDF pages", f"{page_count:,}"))
        self.stats.setRowCount(0)
        for k, v in rows:
            r = self.stats.rowCount()
            self.stats.insertRow(r)
            self.stats.setItem(r, 0, QTableWidgetItem(k))
            self.stats.setItem(r, 1, QTableWidgetItem(v))

    def search_documents(self):
        q = self.search_edit.text().strip()
        if not q:
            self.search_results.setRowCount(0)
            return
        if not self.db:
            QMessageBox.information(self, "Search", "Scan a document folder first.")
            return
        try:
            results = self.db.search(q, self.search_limit.value())
        except sqlite3.Error as exc:
            QMessageBox.warning(
                self, "Search syntax",
                f"SQLite FTS5 could not parse the query.\n\n{exc}\n\n"
                "Try a simple word or phrase."
            )
            return
        self.search_results.setRowCount(0)
        for path, name, snippet, rank in results:
            r = self.search_results.rowCount()
            self.search_results.insertRow(r)
            for c, value in enumerate([name, snippet, path, f"{rank:.4f}"]):
                self.search_results.setItem(r, c, QTableWidgetItem(str(value)))
        self.search_info.setText(
            f"{len(results):,} indexed matches • SQLite FTS5 • local only"
        )

    def open_search_result(self, item):
        r = item.row()
        if r < 0:
            return
        path_item = self.search_results.item(r, 2)
        if path_item:
            self.load_document(path_item.text())

    def populate_stats(self, errors):
        total_size = sum(x.size for x in self.records)
        words = sum(x.words for x in self.records)
        chars = sum(x.characters for x in self.records)
        formats = Counter(x.extension for x in self.records)
        rows = [
            ("Documents", f"{len(self.records):,}"),
            ("Total size", self.human_size(total_size)),
            ("Total words", f"{words:,}"),
            ("Total characters", f"{chars:,}"),
            ("Extraction errors", f"{errors:,}"),
            ("Formats", ", ".join(f"{k}: {v}" for k, v in formats.most_common())),
        ]
        self.stats.setRowCount(0)
        for k, v in rows:
            r = self.stats.rowCount()
            self.stats.insertRow(r)
            self.stats.setItem(r, 0, QTableWidgetItem(k))
            self.stats.setItem(r, 1, QTableWidgetItem(v))

    def populate_notes(self):
        self.note_list.clear()
        for rec in self.records:
            self.note_list.addItem(rec.name)
        self.refresh_research_tables()

    def update_note_list(self):
        self.populate_notes()

    def load_note(self, row):
        self.note_edit.blockSignals(True)
        if 0 <= row < len(self.records):
            path = self.records[row].path
            self.note_title.setText(Path(path).name)
            self.note_edit.setPlainText(self.db.get_note(path) if self.db else "")
        else:
            self.note_title.setText("Select a document")
            self.note_edit.clear()
        self.note_edit.blockSignals(False)

    def save_note(self):
        row = self.note_list.currentRow()
        if 0 <= row < len(self.records) and self.db:
            self.db.set_note(self.records[row].path, self.note_edit.toPlainText())

    def add_bookmark(self):
        if not self.db or not self.current_path:
            QMessageBox.information(self, "Bookmark", "Open a document first.")
            return
        label = self.bookmark_label.text().strip() or Path(self.current_path).name
        location = self.bookmark_location.text().strip() or "Current document"
        self.db.add_bookmark(self.current_path, label, location, "")
        self.bookmark_label.clear()
        self.bookmark_location.clear()
        self.refresh_research_tables()
        self.statusBar().showMessage("Bookmark saved.")

    def add_quote(self):
        if not self.db or not self.current_path:
            QMessageBox.information(self, "Quotation", "Open a document first.")
            return
        quote = self.quote_edit.toPlainText().strip()
        if not quote:
            QMessageBox.information(self, "Quotation", "Enter a quotation first.")
            return
        location = self.quote_location.text().strip() or "Document"
        self.db.add_quote(self.current_path, quote, location, "")
        self.quote_edit.clear()
        self.quote_location.clear()
        self.refresh_research_tables()
        self.statusBar().showMessage("Quotation saved.")

    def refresh_research_tables(self):
        if not self.db:
            return
        rows = self.db.bookmarks()
        self.bookmarks_table.setRowCount(0)
        for row in rows:
            r = self.bookmarks_table.rowCount()
            self.bookmarks_table.insertRow(r)
            for c, value in enumerate(row):
                self.bookmarks_table.setItem(r, c, QTableWidgetItem(str(value)))

        rows = self.db.quotes()
        self.quotes_table.setRowCount(0)
        for row in rows:
            r = self.quotes_table.rowCount()
            self.quotes_table.insertRow(r)
            for c, value in enumerate(row):
                self.quotes_table.setItem(r, c, QTableWidgetItem(str(value)))

    def export_current_text(self):
        if not self.current_text:
            return
        default = Path(self.current_path).stem + ".txt" if self.current_path else "document.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Export Extracted Text", default, "Text Files (*.txt)")
        if path:
            Path(path).write_text(self.current_text, encoding="utf-8")
            self.statusBar().showMessage(f"Exported text to {path}")

    def export_report(self):
        if not self.records:
            QMessageBox.information(self, "Report", "No indexed documents.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Document Report", "document_laboratory_report.csv",
            "CSV Files (*.csv);;JSON Files (*.json);;Text Files (*.txt)"
        )
        if not path:
            return
        suffix = Path(path).suffix.lower()
        payload = [asdict(x) for x in self.records]
        try:
            if suffix == ".json":
                Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            elif suffix == ".txt":
                lines = ["JASS DOCUMENT LABORATORY REPORT", ""]
                for x in self.records:
                    lines.append(
                        f"{x.name} | {x.extension} | {x.words:,} words | "
                        f"{x.characters:,} chars | {x.path}"
                    )
                Path(path).write_text("\n".join(lines), encoding="utf-8")
            else:
                with open(path, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=payload[0].keys())
                    writer.writeheader()
                    writer.writerows(payload)
            self.statusBar().showMessage(f"Report exported: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    @staticmethod
    def human_size(n):
        value = float(n)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}"
            value /= 1024

    @staticmethod
    def format_time(ts):
        import datetime
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    def closeEvent(self, event):
        self.stop_scan()
        if self.db:
            self.db.close()
            self.db = None
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JASS Document Laboratory")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
