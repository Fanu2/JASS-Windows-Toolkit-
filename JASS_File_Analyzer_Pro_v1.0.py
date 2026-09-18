import os
import sys
import csv
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QProgressBar,
    QFrame, QAbstractItemView, QMenu, QTabWidget, QSpinBox, QDoubleSpinBox,
    QGroupBox
)


APP_NAME = "JASS File Analyzer Pro"
VERSION = "1.0"


def human_size(value):
    value = float(value)
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:,.1f} {unit}"
        value /= 1024


def extension_of(name):
    # Correctly handles multi-dot filenames and extensionless files.
    ext = os.path.splitext(name)[1]
    return ext.lower() if ext else "[No extension]"


class ScanWorker(QThread):
    file_found = Signal(str, int, float)
    folder_found = Signal(str)
    progress = Signal(int)
    status = Signal(str)
    finished_scan = Signal(dict)
    error = Signal(str)

    def __init__(self, root, include_hidden=True, case_sensitive=False):
        super().__init__()
        self.root = root
        self.include_hidden = include_hidden
        self.case_sensitive = case_sensitive
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def run(self):
        started = time.time()
        files = 0
        folders = 0
        total_size = 0
        extension_counts = Counter()
        extension_sizes = defaultdict(int)
        largest = []
        errors = 0

        try:
            for current, dirs, names in os.walk(self.root):
                if self.stop_requested:
                    break

                if not self.include_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    names = [n for n in names if not n.startswith(".")]

                folders += len(dirs)
                self.folder_found.emit(current)

                for name in names:
                    if self.stop_requested:
                        break

                    path = os.path.join(current, name)
                    try:
                        size = os.path.getsize(path)
                        mtime = os.path.getmtime(path)
                    except (OSError, PermissionError):
                        errors += 1
                        continue

                    ext = extension_of(name)
                    files += 1
                    total_size += size
                    extension_counts[ext] += 1
                    extension_sizes[ext] += size

                    largest.append((size, path, mtime))
                    if len(largest) > 100:
                        largest.sort(reverse=True, key=lambda x: x[0])
                        largest = largest[:100]

                    self.file_found.emit(path, size, mtime)

                if folders % 10 == 0:
                    self.status.emit(f"Scanning: {current}")
                    self.progress.emit(0)

            largest.sort(reverse=True, key=lambda x: x[0])
            elapsed = time.time() - started
            result = {
                "files": files,
                "folders": folders,
                "size": total_size,
                "extensions": dict(extension_counts),
                "extension_sizes": dict(extension_sizes),
                "largest": largest,
                "errors": errors,
                "elapsed": elapsed,
                "stopped": self.stop_requested,
            }
            self.finished_scan.emit(result)

        except Exception as e:
            self.error.emit(str(e))


class FinderWorker(QThread):
    result = Signal(str, int, float)
    status = Signal(str)
    finished_search = Signal(int, int, float)
    error = Signal(str)

    def __init__(self, root, extensions, case_sensitive, include_hidden, min_bytes, max_bytes):
        super().__init__()
        self.root = root
        self.extensions = extensions
        self.case_sensitive = case_sensitive
        self.include_hidden = include_hidden
        self.min_bytes = min_bytes
        self.max_bytes = max_bytes
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def run(self):
        count = 0
        total = 0
        started = time.time()

        try:
            for current, dirs, names in os.walk(self.root):
                if self.stop_requested:
                    break

                if not self.include_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    names = [n for n in names if not n.startswith(".")]

                for name in names:
                    if self.stop_requested:
                        break

                    compare = name if self.case_sensitive else name.lower()
                    if not any(compare.endswith(e if self.case_sensitive else e.lower())
                               for e in self.extensions):
                        continue

                    path = os.path.join(current, name)
                    try:
                        size = os.path.getsize(path)
                        mtime = os.path.getmtime(path)
                    except (OSError, PermissionError):
                        continue

                    if size < self.min_bytes:
                        continue
                    if self.max_bytes is not None and size > self.max_bytes:
                        continue

                    count += 1
                    total += size
                    self.result.emit(path, size, mtime)

                if count % 500 == 0 and count:
                    self.status.emit(f"Found {count:,} matching files…")

            self.finished_search.emit(count, total, time.time() - started)

        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scan_worker = None
        self.finder_worker = None
        self.inventory = []
        self.finder_results = []
        self.current_root = ""

        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1380, 820)
        self.setMinimumSize(1050, 680)
        self.build_ui()
        self.apply_style()

    # ---------- Common ----------
    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Search files • analyze directories • understand your storage")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.global_stat = QLabel("Ready")
        self.global_stat.setObjectName("stat")
        header.addWidget(self.global_stat)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_finder_tab(), "🔎  File Finder")
        self.tabs.addTab(self.build_analyzer_tab(), "📊  Directory Analyzer")
        self.tabs.addTab(self.build_largest_tab(), "🏆  Largest Files")
        root.addWidget(self.tabs, 1)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("status")
        root.addWidget(self.status_label)

    def folder_row(self, label_text):
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        edit = QLineEdit()
        edit.setPlaceholderText("Choose a folder…")
        row.addWidget(edit, 1)
        button = QPushButton("Browse…")
        row.addWidget(button)
        return row, edit, button

    # ---------- Finder ----------
    def build_finder_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        panel = QFrame()
        panel.setObjectName("panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setSpacing(10)

        grid.addWidget(QLabel("Search folder"), 0, 0)
        self.find_path = QLineEdit()
        self.find_path.setPlaceholderText("Search recursively in this folder…")
        grid.addWidget(self.find_path, 0, 1, 1, 4)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self.choose_folder(self.find_path))
        grid.addWidget(browse, 0, 5)

        grid.addWidget(QLabel("Extensions"), 1, 0)
        self.find_ext = QLineEdit()
        self.find_ext.setPlaceholderText("pdf, docx, jpg  •  or  *.pdf, *.jpg")
        grid.addWidget(self.find_ext, 1, 1, 1, 4)

        start = QPushButton("▶  Search")
        start.setObjectName("primary")
        start.clicked.connect(self.start_finder)
        grid.addWidget(start, 1, 5)
        self.find_start = start

        grid.addWidget(QLabel("Min size"), 2, 0)
        self.find_min = QSpinBox()
        self.find_min.setRange(0, 999999)
        self.find_min.setSuffix(" MB")
        grid.addWidget(self.find_min, 2, 1)

        grid.addWidget(QLabel("Max size"), 2, 2)
        self.find_max = QSpinBox()
        self.find_max.setRange(0, 999999)
        self.find_max.setSpecialValueText("No limit")
        self.find_max.setSuffix(" MB")
        grid.addWidget(self.find_max, 2, 3)

        self.find_case = QCheckBox("Case sensitive")
        grid.addWidget(self.find_case, 2, 4)
        self.find_hidden = QCheckBox("Include hidden")
        self.find_hidden.setChecked(True)
        grid.addWidget(self.find_hidden, 2, 5)

        layout.addWidget(panel)

        controls = QHBoxLayout()
        self.find_filter = QLineEdit()
        self.find_filter.setPlaceholderText("Filter displayed results…")
        self.find_filter.textChanged.connect(self.filter_finder)
        controls.addWidget(self.find_filter, 1)

        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_finder)
        controls.addWidget(clear)

        stop = QPushButton("Stop")
        stop.clicked.connect(self.stop_finder)
        controls.addWidget(stop)

        export = QPushButton("Export CSV")
        export.clicked.connect(self.export_finder_csv)
        controls.addWidget(export)
        layout.addLayout(controls)

        self.find_progress = QProgressBar()
        self.find_progress.setRange(0, 0)
        self.find_progress.hide()
        layout.addWidget(self.find_progress)

        self.find_table = QTableWidget(0, 4)
        self.find_table.setHorizontalHeaderLabels(["Name", "Location", "Size", "Modified"])
        self.setup_table(self.find_table)
        self.find_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.find_table.customContextMenuRequested.connect(
            lambda pos: self.table_context(self.find_table, pos)
        )
        layout.addWidget(self.find_table, 1)

        return page

    def start_finder(self):
        if self.finder_worker and self.finder_worker.isRunning():
            return

        root = self.find_path.text().strip()
        if not os.path.isdir(root):
            QMessageBox.warning(self, "Invalid folder", "Please select a valid search folder.")
            return

        extensions = self.parse_extensions(self.find_ext.text())
        if not extensions:
            QMessageBox.warning(self, "Missing extension", "Enter at least one extension.")
            return

        self.clear_finder()
        self.finder_results = []

        max_mb = self.find_max.value()
        max_bytes = None if max_mb == 0 else max_mb * 1024 * 1024

        self.finder_worker = FinderWorker(
            root, extensions, self.find_case.isChecked(),
            self.find_hidden.isChecked(),
            self.find_min.value() * 1024 * 1024,
            max_bytes
        )
        self.finder_worker.result.connect(self.add_finder_result)
        self.finder_worker.status.connect(self.status_label.setText)
        self.finder_worker.finished_search.connect(self.finder_finished)
        self.finder_worker.error.connect(self.worker_error)
        self.find_progress.show()
        self.find_start.setEnabled(False)
        self.status_label.setText("Searching…")
        self.finder_worker.start()

    def add_finder_result(self, path, size, mtime):
        self.finder_results.append((path, size, mtime))
        r = self.find_table.rowCount()
        self.find_table.insertRow(r)
        self.find_table.setItem(r, 0, QTableWidgetItem(os.path.basename(path)))
        self.find_table.setItem(r, 1, QTableWidgetItem(os.path.dirname(path)))
        item = QTableWidgetItem(human_size(size))
        item.setData(Qt.UserRole, size)
        self.find_table.setItem(r, 2, item)
        self.find_table.setItem(r, 3, QTableWidgetItem(
            datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        ))
        self.global_stat.setText(f"{len(self.finder_results):,} matches")

    def finder_finished(self, count, total, elapsed):
        self.find_progress.hide()
        self.find_start.setEnabled(True)
        self.status_label.setText(
            f"Search complete • {count:,} files • {human_size(total)} • {elapsed:.2f}s"
        )

    def stop_finder(self):
        if self.finder_worker and self.finder_worker.isRunning():
            self.finder_worker.stop()
            self.finder_worker.wait(2000)
            self.find_progress.hide()
            self.find_start.setEnabled(True)
            self.status_label.setText("Search stopped")

    def clear_finder(self):
        self.find_table.setRowCount(0)
        self.finder_results = []
        self.global_stat.setText("Ready")

    def filter_finder(self, text):
        text = text.lower().strip()
        for r in range(self.find_table.rowCount()):
            values = [self.find_table.item(r, c).text().lower()
                      for c in range(4)]
            self.find_table.setRowHidden(r, bool(text and text not in " ".join(values)))

    # ---------- Analyzer ----------
    def build_analyzer_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        panel = QFrame()
        panel.setObjectName("panel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(16, 14, 16, 14)

        grid.addWidget(QLabel("Directory to analyze"), 0, 0)
        self.analyze_path = QLineEdit()
        self.analyze_path.setPlaceholderText("Choose a directory…")
        grid.addWidget(self.analyze_path, 0, 1, 1, 4)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self.choose_folder(self.analyze_path))
        grid.addWidget(browse, 0, 5)

        self.analyze_hidden = QCheckBox("Include hidden files/folders")
        self.analyze_hidden.setChecked(True)
        grid.addWidget(self.analyze_hidden, 1, 1, 1, 2)

        start = QPushButton("▶  Analyze Directory")
        start.setObjectName("primary")
        start.clicked.connect(self.start_analysis)
        grid.addWidget(start, 1, 5)
        self.analyze_start = start

        layout.addWidget(panel)

        cards = QGridLayout()
        self.card_files = self.make_card("TOTAL FILES", "0")
        self.card_folders = self.make_card("FOLDERS", "0")
        self.card_size = self.make_card("TOTAL SIZE", "0 B")
        self.card_types = self.make_card("FILE TYPES", "0")
        cards.addWidget(self.card_files, 0, 0)
        cards.addWidget(self.card_folders, 0, 1)
        cards.addWidget(self.card_size, 0, 2)
        cards.addWidget(self.card_types, 0, 3)
        layout.addLayout(cards)

        split = QHBoxLayout()

        self.ext_table = QTableWidget(0, 4)
        self.ext_table.setHorizontalHeaderLabels(
            ["Extension", "Files", "% of Files", "Total Size"]
        )
        self.setup_table(self.ext_table)
        split.addWidget(self.ext_table, 3)

        self.info_box = QGroupBox("Scan information")
        info_layout = QVBoxLayout(self.info_box)
        self.info_text = QLabel("No analysis yet.")
        self.info_text.setWordWrap(True)
        self.info_text.setAlignment(Qt.AlignTop)
        info_layout.addWidget(self.info_text)
        info_layout.addStretch()
        split.addWidget(self.info_box, 1)

        layout.addLayout(split, 1)

        bottom = QHBoxLayout()
        self.analyze_filter = QLineEdit()
        self.analyze_filter.setPlaceholderText("Filter extension list…")
        self.analyze_filter.textChanged.connect(self.filter_extensions)
        bottom.addWidget(self.analyze_filter)
        export = QPushButton("Export Analysis JSON")
        export.clicked.connect(self.export_analysis)
        bottom.addWidget(export)
        stop = QPushButton("Stop")
        stop.clicked.connect(self.stop_analysis)
        bottom.addWidget(stop)
        layout.addLayout(bottom)

        return page

    def make_card(self, heading, value):
        frame = QFrame()
        frame.setObjectName("card")
        lay = QVBoxLayout(frame)
        h = QLabel(heading)
        h.setObjectName("cardHeading")
        v = QLabel(value)
        v.setObjectName("cardValue")
        lay.addWidget(h)
        lay.addWidget(v)
        frame.value_label = v
        return frame

    def start_analysis(self):
        if self.scan_worker and self.scan_worker.isRunning():
            return

        root = self.analyze_path.text().strip()
        if not os.path.isdir(root):
            QMessageBox.warning(self, "Invalid folder", "Please select a valid directory.")
            return

        self.clear_analysis()
        self.current_root = root
        self.inventory = []

        self.scan_worker = ScanWorker(root, self.analyze_hidden.isChecked())
        self.scan_worker.file_found.connect(self.add_inventory_file)
        self.scan_worker.status.connect(self.status_label.setText)
        self.scan_worker.finished_scan.connect(self.analysis_finished)
        self.scan_worker.error.connect(self.worker_error)
        self.analyze_start.setEnabled(False)
        self.status_label.setText("Analyzing directory…")
        self.scan_worker.start()

    def add_inventory_file(self, path, size, mtime):
        self.inventory.append((path, size, mtime))

    def analysis_finished(self, data):
        self.analyze_start.setEnabled(True)

        self.card_files.value_label.setText(f"{data['files']:,}")
        self.card_folders.value_label.setText(f"{data['folders']:,}")
        self.card_size.value_label.setText(human_size(data["size"]))
        self.card_types.value_label.setText(f"{len(data['extensions']):,}")

        self.ext_table.setRowCount(0)
        total_files = data["files"] or 1
        sorted_ext = sorted(data["extensions"].items(), key=lambda x: x[1], reverse=True)

        for ext, count in sorted_ext:
            r = self.ext_table.rowCount()
            self.ext_table.insertRow(r)
            self.ext_table.setItem(r, 0, QTableWidgetItem(ext))
            self.ext_table.setItem(r, 1, QTableWidgetItem(f"{count:,}"))
            self.ext_table.setItem(r, 2, QTableWidgetItem(f"{count * 100 / total_files:.2f}%"))
            self.ext_table.setItem(
                r, 3, QTableWidgetItem(human_size(data["extension_sizes"].get(ext, 0)))
            )

        stopped = "Stopped early • " if data["stopped"] else ""
        self.info_text.setText(
            f"<b>Path:</b> {self.current_root}<br><br>"
            f"<b>Files:</b> {data['files']:,}<br>"
            f"<b>Folders:</b> {data['folders']:,}<br>"
            f"<b>Total size:</b> {human_size(data['size'])}<br>"
            f"<b>Unreadable/skipped:</b> {data['errors']:,}<br>"
            f"<b>Elapsed:</b> {data['elapsed']:.2f} seconds<br><br>"
            f"{stopped}"
        )

        # Populate largest-files page.
        self.populate_largest(data["largest"])
        self.global_stat.setText(f"{data['files']:,} files • {human_size(data['size'])}")
        self.status_label.setText(
            f"Analysis complete • {data['files']:,} files • {data['folders']:,} folders"
        )

    def stop_analysis(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.stop()
            self.scan_worker.wait(2000)
            self.analyze_start.setEnabled(True)
            self.status_label.setText("Analysis stopped")

    def clear_analysis(self):
        self.ext_table.setRowCount(0)
        self.inventory = []
        for card, value in [
            (self.card_files, "0"), (self.card_folders, "0"),
            (self.card_size, "0 B"), (self.card_types, "0")
        ]:
            card.value_label.setText(value)
        self.info_text.setText("No analysis yet.")

    def filter_extensions(self, text):
        text = text.lower().strip()
        for r in range(self.ext_table.rowCount()):
            ext = self.ext_table.item(r, 0).text().lower()
            self.ext_table.setRowHidden(r, bool(text and text not in ext))

    # ---------- Largest files ----------
    def build_largest_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        intro = QLabel("Largest files from the most recent directory analysis")
        intro.setObjectName("section")
        layout.addWidget(intro)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Show top"))
        self.largest_count = QComboBox()
        self.largest_count.addItems(["10", "25", "50", "100"])
        self.largest_count.currentTextChanged.connect(self.refresh_largest)
        controls.addWidget(self.largest_count)
        controls.addStretch()
        controls.addWidget(QLabel("These are informational only — nothing is deleted."))
        layout.addLayout(controls)

        self.largest_table = QTableWidget(0, 4)
        self.largest_table.setHorizontalHeaderLabels(["Rank", "File", "Size", "Modified"])
        self.setup_table(self.largest_table)
        self.largest_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.largest_table.customContextMenuRequested.connect(
            lambda pos: self.table_context(self.largest_table, pos)
        )
        layout.addWidget(self.largest_table, 1)
        self.largest_data = []
        return page

    def populate_largest(self, data):
        self.largest_data = data
        self.refresh_largest()

    def refresh_largest(self):
        if not hasattr(self, "largest_table"):
            return
        n = int(self.largest_count.currentText())
        self.largest_table.setRowCount(0)
        for rank, (size, path, mtime) in enumerate(self.largest_data[:n], 1):
            r = self.largest_table.rowCount()
            self.largest_table.insertRow(r)
            self.largest_table.setItem(r, 0, QTableWidgetItem(str(rank)))
            self.largest_table.setItem(r, 1, QTableWidgetItem(path))
            item = QTableWidgetItem(human_size(size))
            item.setData(Qt.UserRole, size)
            self.largest_table.setItem(r, 2, item)
            self.largest_table.setItem(
                r, 3, QTableWidgetItem(datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"))
            )

    # ---------- Utilities ----------
    def setup_table(self, table):
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, table.columnCount()):
            table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)

    def choose_folder(self, edit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            edit.setText(folder)

    @staticmethod
    def parse_extensions(text):
        result = []
        for item in text.replace(";", ",").split(","):
            item = item.strip()
            if not item:
                continue
            if item.startswith("*."):
                item = item[1:]
            elif not item.startswith("."):
                item = "." + item
            result.append(item)
        return result

    def table_context(self, table, pos):
        item = table.itemAt(pos)
        if not item:
            return
        row = item.row()

        if table is self.largest_table:
            path = table.item(row, 1).text()
        else:
            path = os.path.join(table.item(row, 1).text(), table.item(row, 0).text())

        menu = QMenu(self)
        open_file = menu.addAction("Open File")
        open_folder = menu.addAction("Open Containing Folder")
        copy = menu.addAction("Copy Full Path")
        chosen = menu.exec(table.viewport().mapToGlobal(pos))

        if chosen == open_file:
            self.open_path(path)
        elif chosen == open_folder:
            self.open_path(os.path.dirname(path))
        elif chosen == copy:
            QApplication.clipboard().setText(path)

    def open_path(self, path):
        if not os.path.exists(path):
            QMessageBox.warning(self, "Not found", "The path no longer exists.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "Cannot open", str(e))

    def export_finder_csv(self):
        if not self.finder_results:
            QMessageBox.information(self, "Nothing to export", "Run a search first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Finder Results", "finder_results.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "Location", "Size", "Modified", "Full Path"])
            for p, size, mtime in self.finder_results:
                writer.writerow([
                    os.path.basename(p), os.path.dirname(p), human_size(size),
                    datetime.fromtimestamp(mtime).isoformat(sep=" "),
                    p
                ])
        self.status_label.setText(f"Exported {len(self.finder_results):,} finder results")

    def export_analysis(self):
        if not self.inventory:
            QMessageBox.information(self, "Nothing to export", "Run a directory analysis first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Analysis", "directory_analysis.json", "JSON Files (*.json)"
        )
        if not path:
            return

        ext_counts = Counter(extension_of(os.path.basename(p)) for p, _, _ in self.inventory)
        ext_sizes = defaultdict(int)
        for p, size, _ in self.inventory:
            ext_sizes[extension_of(os.path.basename(p))] += size

        data = {
            "application": APP_NAME,
            "version": VERSION,
            "root": self.current_root,
            "generated": datetime.now().isoformat(),
            "files": len(self.inventory),
            "folders": self.count_folders(self.current_root),
            "total_size_bytes": sum(x[1] for x in self.inventory),
            "extensions": {
                ext: {"files": count, "size_bytes": ext_sizes[ext]}
                for ext, count in sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)
            },
            "largest_files": [
                {"path": p, "size_bytes": size, "modified": datetime.fromtimestamp(m).isoformat()}
                for size, p, m in sorted(
                    ((s, p, m) for p, s, m in self.inventory),
                    reverse=True
                )[:100]
            ]
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.status_label.setText("Analysis exported successfully")

    @staticmethod
    def count_folders(root):
        total = 0
        try:
            for _, dirs, _ in os.walk(root):
                total += len(dirs)
        except OSError:
            pass
        return total

    def worker_error(self, message):
        self.find_progress.hide()
        self.find_start.setEnabled(True)
        self.analyze_start.setEnabled(True)
        QMessageBox.critical(self, "Operation error", message)
        self.status_label.setText("Operation failed")

    def closeEvent(self, event):
        for worker in (self.scan_worker, self.finder_worker):
            if worker and worker.isRunning():
                worker.stop()
                worker.wait(2000)
        event.accept()

    def apply_style(self):
        self.setStyleSheet("""
        QWidget {
            font-family: "Noto Sans", "Segoe UI", sans-serif;
            font-size: 13px;
        }
        QMainWindow, QWidget {
            background: #f5f7fb;
            color: #1f2937;
        }
        QLabel#title {
            font-size: 27px;
            font-weight: 700;
            color: #111827;
        }
        QLabel#subtitle, QLabel#status {
            color: #667085;
        }
        QLabel#stat {
            background: #e8eefc;
            border-radius: 18px;
            padding: 9px 16px;
            font-weight: 600;
        }
        QTabWidget::pane {
            border: 1px solid #dfe4ec;
            background: white;
            border-radius: 10px;
            top: -1px;
        }
        QTabBar::tab {
            background: #e9edf4;
            padding: 10px 18px;
            margin-right: 3px;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
        }
        QTabBar::tab:selected {
            background: white;
            font-weight: 600;
        }
        QFrame#panel, QFrame#card {
            background: white;
            border: 1px solid #e0e5ee;
            border-radius: 11px;
        }
        QFrame#card {
            padding: 4px;
        }
        QLabel#cardHeading {
            color: #667085;
            font-size: 11px;
            font-weight: 700;
        }
        QLabel#cardValue {
            color: #111827;
            font-size: 24px;
            font-weight: 700;
        }
        QLabel#section {
            font-size: 16px;
            font-weight: 600;
        }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background: white;
            border: 1px solid #cfd6e2;
            border-radius: 7px;
            padding: 8px 10px;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
            border: 1px solid #637ff5;
        }
        QPushButton {
            background: white;
            border: 1px solid #cfd6e2;
            border-radius: 7px;
            padding: 8px 14px;
        }
        QPushButton:hover {
            background: #eef2ff;
        }
        QPushButton#primary {
            background: #4f63d8;
            color: white;
            border: none;
            font-weight: 600;
        }
        QPushButton#primary:hover {
            background: #4053c5;
        }
        QTableWidget {
            background: white;
            border: 1px solid #e0e5ee;
            border-radius: 9px;
            gridline-color: #edf0f5;
            selection-background-color: #dfe6ff;
            selection-color: #111827;
        }
        QHeaderView::section {
            background: #f0f3f8;
            border: none;
            border-bottom: 1px solid #dfe4ec;
            padding: 9px;
            font-weight: 600;
        }
        QProgressBar {
            border: none;
            background: #e7ebf2;
            border-radius: 5px;
            height: 8px;
        }
        QProgressBar::chunk {
            background: #637ff5;
            border-radius: 5px;
        }
        QGroupBox {
            background: white;
            border: 1px solid #e0e5ee;
            border-radius: 9px;
            margin-top: 10px;
            padding: 12px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 5px;
        }
        """)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
