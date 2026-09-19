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

APP_VERSION = "1.0.0"
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

        self.search_info = QLabel("Search uses the selected library documents and extracts text locally.")
        lay.addWidget(self.search_info)

        self.search_results = CopyTable(0, 4)
        self.search_results.setHorizontalHeaderLabels(["Document", "Match", "Context", "Position"])
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
        self.note_edit.setPlaceholderText("Session research notes for the selected document...")
        self.note_edit.textChanged.connect(self.save_note)
        rl.addWidget(self.note_edit)
        split.addWidget(right)
        split.setSizes([350, 900])
        layout = QVBoxLayout(tab)
        layout.addWidget(split)
        self.tabs.addTab(tab, "Research Notes")

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
        self.stop_scan()
        self.populate_library()
        self.populate_stats(data["errors"])
        self.populate_notes()
        self.statusBar().showMessage(
            f"Indexed {len(self.records):,} documents • {data['errors']:,} extraction errors"
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
        qf = q.casefold()
        results = []
        for rec in self.records:
            if rec.error:
                continue
            try:
                text, _ = extract_document(Path(rec.path))
            except Exception:
                continue
            low = text.casefold()
            start = 0
            while len(results) < self.search_limit.value():
                pos = low.find(qf, start)
                if pos < 0:
                    break
                context_start = max(0, pos - 100)
                context_end = min(len(text), pos + len(q) + 160)
                context = text[context_start:context_end].replace("\n", " ")
                results.append((rec.path, text[pos:pos+len(q)], context, str(pos)))
                start = pos + max(1, len(q))
        self.search_results.setRowCount(0)
        for path, match, context, pos in results:
            r = self.search_results.rowCount()
            self.search_results.insertRow(r)
            for c, value in enumerate([Path(path).name, match, context, pos]):
                self.search_results.setItem(r, c, QTableWidgetItem(value))
        self.search_info.setText(f"{len(results):,} matches shown.")
        self.search_results.resizeRowsToContents()

    def open_search_result(self, item):
        r = item.row()
        if r < 0:
            return
        name = self.search_results.item(r, 0).text()
        candidates = [x.path for x in self.records if x.name == name]
        if candidates:
            self.load_document(candidates[0])

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

    def update_note_list(self):
        self.populate_notes()

    def load_note(self, row):
        self.note_edit.blockSignals(True)
        if 0 <= row < len(self.records):
            path = self.records[row].path
            self.note_title.setText(Path(path).name)
            self.note_edit.setPlainText(self.notes.get(path, ""))
        else:
            self.note_title.setText("Select a document")
            self.note_edit.clear()
        self.note_edit.blockSignals(False)

    def save_note(self):
        row = self.note_list.currentRow()
        if 0 <= row < len(self.records):
            self.notes[self.records[row].path] = self.note_edit.toPlainText()

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
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JASS Document Laboratory")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
