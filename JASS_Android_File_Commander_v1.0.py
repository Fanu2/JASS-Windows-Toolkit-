#!/usr/bin/env python3
"""
JASS Android File Commander v1.0
Dual-pane Linux <-> Android file manager using ADB, with KDE Connect
quick-send integration.

Read-only browsing by default. Transfers are explicit.
"""

import sys
import os
import subprocess
import shlex
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QGroupBox, QSplitter, QProgressBar,
    QAbstractItemView, QMenu, QInputDialog
)

QUICK_ANDROID = {
    "Downloads": "/sdcard/Download",
    "Pictures": "/sdcard/Pictures",
    "DCIM": "/sdcard/DCIM",
    "Movies": "/sdcard/Movies",
    "Music": "/sdcard/Music",
    "Documents": "/sdcard/Documents",
}


def human(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:,.1f} {u}"
        n /= 1024
    return "0 B"


def run_cmd(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True,
                          errors="replace", timeout=timeout)


class AdbWorker(QThread):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, args, operation="command", timeout=60):
        super().__init__()
        self.args = args
        self.operation = operation
        self.timeout = timeout

    def run(self):
        try:
            p = run_cmd(self.args, self.timeout)
            if p.returncode != 0:
                self.failed.emit(p.stderr.strip() or p.stdout.strip() or
                                 f"Command failed with exit code {p.returncode}.")
            else:
                self.finished.emit({"stdout": p.stdout, "stderr": p.stderr,
                                    "operation": self.operation})
        except FileNotFoundError:
            self.failed.emit("ADB is not installed or is not in PATH.")
        except subprocess.TimeoutExpired:
            self.failed.emit("ADB operation timed out.")
        except Exception as e:
            self.failed.emit(str(e))


class TransferWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, args, label):
        super().__init__()
        self.args = args
        self.label = label

    def run(self):
        try:
            p = subprocess.run(self.args, capture_output=True, text=True,
                               errors="replace")
            if p.returncode == 0:
                self.finished.emit(True, p.stdout.strip() or f"{self.label} complete.")
            else:
                self.finished.emit(False, p.stderr.strip() or p.stdout.strip() or
                                   f"{self.label} failed.")
        except FileNotFoundError:
            self.finished.emit(False, "ADB is not installed or is not in PATH.")
        except Exception as e:
            self.finished.emit(False, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JASS Android File Commander v1.0")
        self.resize(1450, 900)
        self.devices = []
        self.device = None
        self.left_path = str(Path.home())
        self.right_path = "/sdcard"
        self.left_rows = []
        self.right_rows = []
        self.worker = None
        self.transfer = None
        self.build_ui()
        self.refresh_devices()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        title = QLabel("JASS Android File Commander")
        title.setObjectName("Title")
        outer.addWidget(title)
        sub = QLabel("Linux ↔ Android • Dual Pane • ADB + KDE Connect")
        sub.setObjectName("Subtitle")
        outer.addWidget(sub)

        top = QGroupBox("Device Connection")
        g = QGridLayout(top)
        self.device_combo = QComboBox()
        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.connect_btn = QPushButton("Connect / Select")
        self.connect_btn.clicked.connect(self.select_device)
        self.status_label = QLabel("No Android device selected")
        self.adb_status = QLabel("ADB: checking…")
        g.addWidget(QLabel("ADB device"), 0, 0)
        g.addWidget(self.device_combo, 0, 1, 1, 3)
        g.addWidget(self.refresh_btn, 0, 4)
        g.addWidget(self.connect_btn, 0, 5)
        g.addWidget(self.adb_status, 1, 1)
        g.addWidget(self.status_label, 1, 2, 1, 4)
        outer.addWidget(top)

        quick = QHBoxLayout()
        quick.addWidget(QLabel("Android quick folders:"))
        for name, path in QUICK_ANDROID.items():
            b = QPushButton(name)
            b.clicked.connect(lambda checked=False, p=path: self.set_android_path(p))
            quick.addWidget(b)
        quick.addStretch()
        outer.addLayout(quick)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.build_linux_pane())
        split.addWidget(self.build_android_pane())
        split.setSizes([650, 650])
        outer.addWidget(split, 1)

        actions = QHBoxLayout()
        self.copy_to_android = QPushButton("→  Copy to Android")
        self.copy_to_android.clicked.connect(self.send_to_android)
        self.copy_to_linux = QPushButton("←  Copy to Linux")
        self.copy_to_linux.clicked.connect(self.receive_from_android)
        self.mkdir_android = QPushButton("＋ Android Folder")
        self.mkdir_android.clicked.connect(self.make_android_folder)
        self.open_linux = QPushButton("Open Linux Folder")
        self.open_linux.clicked.connect(self.open_linux_folder)
        for b in [self.copy_to_android, self.copy_to_linux, self.mkdir_android,
                  self.open_linux]:
            actions.addWidget(b)
        actions.addStretch()
        outer.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)
        self.statusBar().showMessage("Select an Android device.")

    def build_linux_pane(self):
        box = QGroupBox("🐧 Linux")
        v = QVBoxLayout(box)
        row = QHBoxLayout()
        self.linux_path = QLineEdit(self.left_path)
        self.linux_path.returnPressed.connect(self.browse_linux)
        b = QPushButton("Browse")
        b.clicked.connect(self.choose_linux)
        up = QPushButton("↑")
        up.clicked.connect(self.linux_up)
        row.addWidget(self.linux_path, 1)
        row.addWidget(up)
        row.addWidget(b)
        v.addLayout(row)
        self.linux_table = self.make_table(["Name", "Type", "Size", "Modified"])
        self.linux_table.cellDoubleClicked.connect(self.linux_double)
        v.addWidget(self.linux_table, 1)
        self.populate_linux()
        return box

    def build_android_pane(self):
        box = QGroupBox("📱 Android")
        v = QVBoxLayout(box)
        row = QHBoxLayout()
        self.android_path = QLineEdit("/sdcard")
        self.android_path.returnPressed.connect(self.populate_android)
        up = QPushButton("↑")
        up.clicked.connect(self.android_up)
        refresh = QPushButton("↻")
        refresh.clicked.connect(self.populate_android)
        row.addWidget(self.android_path, 1)
        row.addWidget(up)
        row.addWidget(refresh)
        v.addLayout(row)
        self.android_table = self.make_table(["Name", "Type", "Size", "Modified"])
        self.android_table.cellDoubleClicked.connect(self.android_double)
        v.addWidget(self.android_table, 1)
        return box

    def make_table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        t.horizontalHeader().setStretchLastSection(True)
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        return t

    def refresh_devices(self):
        self.device_combo.clear()
        p = shutil_which("adb")
        if not p:
            self.adb_status.setText("ADB: not installed")
            self.status_label.setText("Install adb to use the dual-pane commander.")
            return
        self.adb_status.setText(f"ADB: {p}")
        try:
            r = run_cmd(["adb", "devices", "-l"])
            rows = []
            for line in r.stdout.splitlines()[1:]:
                line = line.strip()
                if not line or line.startswith("*"):
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    model = ""
                    for x in parts[2:]:
                        if x.startswith("model:"):
                            model = x.split(":", 1)[1]
                    rows.append((serial, model or serial))
            self.devices = rows
            for serial, name in rows:
                self.device_combo.addItem(f"{name} [{serial}]", serial)
            if rows:
                self.device_combo.setCurrentIndex(0)
                self.select_device()
            else:
                self.status_label.setText("No authorized Android device found.")
        except Exception as e:
            self.status_label.setText(str(e))

    def select_device(self):
        if self.device_combo.count() == 0:
            return
        self.device = self.device_combo.currentData()
        self.status_label.setText(f"Connected: {self.device}")
        self.populate_android()

    def adb_base(self):
        return ["adb", "-s", self.device] if self.device else ["adb"]

    def set_android_path(self, path):
        self.android_path.setText(path)
        self.populate_android()

    def populate_linux(self):
        path = Path(self.linux_path.text() or self.left_path).expanduser()
        try:
            rows = []
            for x in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                try:
                    if x.is_dir():
                        typ, size = "Folder", ""
                    else:
                        typ, size = "File", human(x.stat().st_size)
                    mod = datetime.fromtimestamp(x.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    rows.append((x.name, typ, size, mod, str(x)))
                except OSError:
                    continue
            self.left_rows = rows
            self.linux_table.setRowCount(0)
            for row in rows:
                r = self.linux_table.rowCount()
                self.linux_table.insertRow(r)
                for c, val in enumerate(row[:4]):
                    self.linux_table.setItem(r, c, QTableWidgetItem(str(val)))
            self.linux_table.resizeColumnsToContents()
            self.linux_table.setColumnWidth(0, 350)
        except Exception as e:
            QMessageBox.warning(self, "Linux Folder Error", str(e))

    def choose_linux(self):
        p = QFileDialog.getExistingDirectory(self, "Choose Linux Folder", self.linux_path.text())
        if p:
            self.linux_path.setText(p)
            self.populate_linux()

    def browse_linux(self):
        self.populate_linux()

    def linux_up(self):
        p = Path(self.linux_path.text()).expanduser()
        self.linux_path.setText(str(p.parent))
        self.populate_linux()

    def linux_double(self, row, col):
        item = self.left_rows[row]
        if item[1] == "Folder":
            self.linux_path.setText(item[4])
            self.populate_linux()

    def selected_linux(self):
        rows = self.linux_table.selectionModel().selectedRows()
        return [self.left_rows[x.row()][4] for x in rows]

    def populate_android(self):
        if not self.device:
            self.status_label.setText("Select an Android device first.")
            return
        path = self.android_path.text().strip() or "/sdcard"
        self.status_label.setText(f"Reading Android: {path}")
        args = self.adb_base() + ["shell", "ls", "-l", path]
        self.worker = AdbWorker(args, "list")
        self.worker.finished.connect(lambda d: self.android_loaded(path, d["stdout"]))
        self.worker.failed.connect(self.adb_failed)
        self.worker.start()

    def android_loaded(self, path, output):
        rows = []
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("total "):
                continue
            parts = line.split(maxsplit=7)
            if len(parts) < 7:
                continue
            perm = parts[0]
            if perm.startswith("l"):
                continue
            typ = "Folder" if perm.startswith("d") else "File"
            size = parts[4] if typ == "File" and parts[4].isdigit() else ""
            if size:
                size = human(int(size))
            name = parts[-1]
            modified = " ".join(parts[5:7]) if len(parts) >= 7 else ""
            rows.append((name, typ, size, modified, name))
        self.right_rows = rows
        self.android_table.setRowCount(0)
        for row in rows:
            r = self.android_table.rowCount()
            self.android_table.insertRow(r)
            for c, val in enumerate(row[:4]):
                self.android_table.setItem(r, c, QTableWidgetItem(str(val)))
        self.android_table.resizeColumnsToContents()
        self.android_table.setColumnWidth(0, 350)
        self.status_label.setText(f"Android: {path} • {len(rows)} items")

    def adb_failed(self, msg):
        self.status_label.setText("ADB error")
        QMessageBox.warning(self, "ADB Error", msg)

    def android_up(self):
        p = self.android_path.text().rstrip("/")
        if p in ("", "/"):
            self.android_path.setText("/")
        else:
            parent = p.rsplit("/", 1)[0]
            self.android_path.setText(parent or "/")
        self.populate_android()

    def android_double(self, row, col):
        item = self.right_rows[row]
        if item[1] == "Folder":
            base = self.android_path.text().rstrip("/")
            self.android_path.setText((base + "/" + item[0]) if base else "/" + item[0])
            self.populate_android()
        else:
            self.preview_android_file(item[0])

    def selected_android(self):
        rows = self.android_table.selectionModel().selectedRows()
        return [self.right_rows[x.row()][4] for x in rows]

    def preview_android_file(self, name):
        base = self.android_path.text().rstrip("/")
        remote = f"{base}/{name}" if base else "/" + name
        args = self.adb_base() + ["shell", "sh", "-c",
                                  f"if [ -f {shlex.quote(remote)} ]; then head -c 200000 {shlex.quote(remote)}; fi"]
        self.worker = AdbWorker(args, "preview")
        self.worker.finished.connect(lambda d: self.show_preview(remote, d["stdout"]))
        self.worker.failed.connect(self.adb_failed)
        self.worker.start()

    def show_preview(self, path, text):
        if not text:
            QMessageBox.information(self, "Preview", f"No text preview available:\n{path}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Android Preview — {Path(path).name}")
        dlg.resize(850, 650)
        v = QVBoxLayout(dlg)
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text)
        v.addWidget(edit)
        b = QPushButton("Close")
        b.clicked.connect(dlg.accept)
        v.addWidget(b)
        dlg.exec()

    def send_to_android(self):
        if not self.device:
            QMessageBox.warning(self, "No Device", "Select an Android device first."); return
        items = self.selected_linux()
        if not items:
            QMessageBox.information(self, "Nothing Selected", "Select one or more Linux files/folders.")
            return
        dest = self.android_path.text().strip() or "/sdcard"
        # adb push handles files and directories.
        args = self.adb_base() + ["push"] + items + [dest]
        self.start_transfer(args, "Linux → Android")

    def receive_from_android(self):
        if not self.device:
            QMessageBox.warning(self, "No Device", "Select an Android device first."); return
        items = self.selected_android()
        if not items:
            QMessageBox.information(self, "Nothing Selected", "Select one or more Android files/folders.")
            return
        dest = QFileDialog.getExistingDirectory(self, "Choose Linux Destination", str(Path.home()))
        if not dest: return
        base = self.android_path.text().rstrip("/")
        remote = [f"{base}/{x}" if base else "/" + x for x in items]
        args = self.adb_base() + ["pull"] + remote + [dest]
        self.start_transfer(args, "Android → Linux")

    def start_transfer(self, args, label):
        self.progress.setVisible(True)
        self.statusBar().showMessage(f"{label} in progress…")
        self.set_transfer_buttons(False)
        self.transfer = TransferWorker(args, label)
        self.transfer.finished.connect(lambda ok, msg: self.transfer_done(ok, msg, label))
        self.transfer.start()

    def transfer_done(self, ok, msg, label):
        self.progress.setVisible(False)
        self.set_transfer_buttons(True)
        self.statusBar().showMessage(msg)
        if ok:
            QMessageBox.information(self, "Transfer Complete", f"{label}\n\n{msg}")
            self.populate_linux()
            self.populate_android()
        else:
            QMessageBox.critical(self, "Transfer Failed", msg)

    def set_transfer_buttons(self, enabled):
        for b in [self.copy_to_android, self.copy_to_linux, self.mkdir_android]:
            b.setEnabled(enabled)

    def make_android_folder(self):
        if not self.device: return
        name, ok = QInputDialog.getText(self, "New Android Folder", "Folder name:")
        if not ok or not name.strip(): return
        base = self.android_path.text().rstrip("/")
        remote = f"{base}/{name.strip()}" if base else "/" + name.strip()
        args = self.adb_base() + ["shell", "mkdir", "-p", remote]
        self.worker = AdbWorker(args, "mkdir")
        self.worker.finished.connect(lambda d: self.populate_android())
        self.worker.failed.connect(self.adb_failed)
        self.worker.start()

    def open_linux_folder(self):
        try:
            p = self.linux_path.text()
            if sys.platform.startswith("linux"): subprocess.Popen(["xdg-open", p])
            elif sys.platform == "win32": os.startfile(p)
            elif sys.platform == "darwin": subprocess.Popen(["open", p])
        except Exception as e:
            QMessageBox.warning(self, "Open Failed", str(e))


def shutil_which(name):
    import shutil
    return shutil.which(name)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JASS Android File Commander")
    app.setStyleSheet("""
        QWidget { font-size: 13px; }
        QLineEdit, QComboBox { padding: 7px; }
        QPushButton { padding: 8px 13px; font-weight: 600; }
        QGroupBox { font-weight: 700; }
        #Title { font-size: 26px; font-weight: 800; }
        #Subtitle { color: #64748b; margin-bottom: 5px; }
        QTableWidget { gridline-color: #d7dce2; }
    """)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
