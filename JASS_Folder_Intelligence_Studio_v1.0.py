#!/usr/bin/env python3
"""
JASS Folder Intelligence Studio v1.0
Local-first PySide6 folder intelligence and storage analysis tool.
Read-only: never deletes, moves, renames, or modifies scanned files.
"""

import sys
import os
import json
import csv
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QTabWidget, QProgressBar, QSplitter, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QFormLayout, QPlainTextEdit, QAbstractItemView, QMenu
)


SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".cache", ".npm", ".cargo", ".rustup",
    "dist", "build", ".pytest_cache", ".mypy_cache"
}

TEXT_EXTS = {
    ".txt", ".md", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".html",
    ".css", ".scss", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".sql", ".sh", ".bash", ".ps1", ".bat", ".csv", ".log"
}


def human(n):
    n = float(n or 0)
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    for u in units:
        if n < 1024 or u == units[-1]:
            return f"{n:,.1f} {u}"
        n /= 1024
    return "0 B"


def safe_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def file_kind(path):
    ext = Path(path).suffix.lower()
    if ext in TEXT_EXTS:
        return "Text / Code"
    if ext in {".jpg",".jpeg",".png",".gif",".bmp",".webp",".tif",".tiff",".svg",".ico"}:
        return "Image"
    if ext in {".mp3",".wav",".flac",".ogg",".opus",".m4a",".aac",".wma"}:
        return "Audio"
    if ext in {".mp4",".mkv",".avi",".mov",".webm",".m4v",".mpeg",".mpg",".ts",".mts",".m2ts"}:
        return "Video"
    if ext in {".pdf",".doc",".docx",".odt",".rtf"}:
        return "Document"
    if ext in {".zip",".7z",".rar",".tar",".gz",".bz2",".xz",".iso"}:
        return "Archive"
    if ext in {".exe",".msi",".deb",".rpm",".appimage",".bin"}:
        return "Executable"
    return "Other"


class ScanWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, root, recursive=True, hidden=False, max_depth=0):
        super().__init__()
        self.root = root
        self.recursive = recursive
        self.hidden = hidden
        self.max_depth = max_depth
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True

    def run(self):
        try:
            files, dirs, errors = [], [], 0
            ext_stats = {}
            kind_stats = {}
            total_size = 0
            largest = []
            depth_map = {}
            stack = [(self.root, 0)]
            while stack and not self.stop_requested:
                current, depth = stack.pop()
                try:
                    entries = list(os.scandir(current))
                except (OSError, PermissionError):
                    errors += 1
                    continue

                depth_map[depth] = depth_map.get(depth, 0) + 1
                for entry in entries:
                    if self.stop_requested:
                        break
                    try:
                        if not self.hidden and entry.name.startswith("."):
                            continue
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            dirs.append({
                                "name": entry.name, "path": entry.path,
                                "depth": depth, "mtime": safe_mtime(entry.path)
                            })
                            if self.recursive and (self.max_depth == 0 or depth < self.max_depth):
                                if entry.name not in SKIP_DIRS:
                                    stack.append((entry.path, depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            size = entry.stat().st_size
                            ext = Path(entry.name).suffix.lower() or "[no extension]"
                            kind = file_kind(entry.name)
                            rec = {
                                "name": entry.name, "path": entry.path, "size": size,
                                "mtime": safe_mtime(entry.path), "extension": ext,
                                "kind": kind, "depth": depth
                            }
                            files.append(rec)
                            total_size += size
                            ext_stats[ext] = ext_stats.get(ext, 0) + size
                            kind_stats[kind] = kind_stats.get(kind, 0) + size
                            largest.append(rec)
                    except (OSError, PermissionError):
                        errors += 1

                self.progress.emit(len(files), current)

            largest.sort(key=lambda x: x["size"], reverse=True)
            result = {
                "root": self.root, "files": files, "dirs": dirs,
                "errors": errors, "total_size": total_size,
                "ext_stats": ext_stats, "kind_stats": kind_stats,
                "largest": largest[:500], "depth_map": depth_map,
                "stopped": self.stop_requested,
                "duration": 0
            }
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JASS Folder Intelligence Studio v1.0")
        self.resize(1400, 900)
        self.data = None
        self.worker = None
        self.build_ui()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        title = QLabel("JASS Folder Intelligence Studio")
        title.setObjectName("Title")
        outer.addWidget(title)
        subtitle = QLabel("Inspect • Understand • Measure • Report — read-only")
        subtitle.setObjectName("Subtitle")
        outer.addWidget(subtitle)

        controls = QGroupBox("Scan Controls")
        cf = QGridLayout(controls)
        self.path = QLineEdit()
        self.path.setPlaceholderText("Choose a folder to analyze…")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        self.recursive = QCheckBox("Recursive")
        self.recursive.setChecked(True)
        self.hidden = QCheckBox("Include hidden")
        self.depth = QSpinBox()
        self.depth.setRange(0, 999)
        self.depth.setValue(0)
        self.depth.setSpecialValueText("Unlimited")
        self.scan_btn = QPushButton("🔎 Analyze Folder")
        self.scan_btn.clicked.connect(self.start_scan)
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.clicked.connect(self.stop_scan)
        self.stop_btn.setEnabled(False)
        cf.addWidget(QLabel("Folder"), 0, 0)
        cf.addWidget(self.path, 0, 1, 1, 4)
        cf.addWidget(browse, 0, 5)
        cf.addWidget(self.recursive, 1, 1)
        cf.addWidget(self.hidden, 1, 2)
        cf.addWidget(QLabel("Max depth"), 1, 3)
        cf.addWidget(self.depth, 1, 4)
        cf.addWidget(self.scan_btn, 1, 5)
        cf.addWidget(self.stop_btn, 1, 6)
        outer.addWidget(controls)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.dashboard_tab(), "🏠 Dashboard")
        self.tabs.addTab(self.files_tab(), "📄 Files")
        self.tabs.addTab(self.types_tab(), "📊 File Types")
        self.tabs.addTab(self.largest_tab(), "📦 Largest")
        self.tabs.addTab(self.structure_tab(), "🌳 Structure")
        self.tabs.addTab(self.reports_tab(), "📋 Reports")
        outer.addWidget(self.tabs, 1)

        self.statusBar().showMessage("Choose a folder and click Analyze Folder.")

    def dashboard_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        grid = QGridLayout()
        self.cards = {}
        for i, (key, label) in enumerate([
            ("files","Files"), ("dirs","Directories"), ("size","Total Size"),
            ("avg","Average File"), ("ext","File Types"), ("largest","Largest File"),
            ("text","Text/Code"), ("errors","Access Errors")
        ]):
            box = QGroupBox(label)
            v = QVBoxLayout(box)
            val = QLabel("—")
            val.setObjectName("CardValue")
            v.addWidget(val)
            self.cards[key] = val
            grid.addWidget(box, i // 4, i % 4)
        layout.addLayout(grid)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setPlaceholderText("Folder intelligence summary will appear here.")
        layout.addWidget(self.summary, 1)
        return w

    def make_table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        t.horizontalHeader().setStretchLastSection(True)
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(lambda pos, table=t: self.table_menu(table, pos))
        return t

    def files_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.file_search = QLineEdit(); self.file_search.setPlaceholderText("Filter by name, path, extension or type…")
        self.file_search.textChanged.connect(self.filter_files)
        self.kind_filter = QComboBox(); self.kind_filter.addItems(["All types","Text / Code","Image","Audio","Video","Document","Archive","Executable","Other"])
        self.kind_filter.currentTextChanged.connect(self.filter_files)
        self.sort_files = QComboBox(); self.sort_files.addItems(["Size ↓","Name A–Z","Modified ↓","Extension"])
        self.sort_files.currentTextChanged.connect(self.populate_files)
        bar.addWidget(self.file_search, 2); bar.addWidget(self.kind_filter); bar.addWidget(self.sort_files)
        v.addLayout(bar)
        self.file_table = self.make_table(["Name","Type","Extension","Size","Modified","Path"])
        self.file_table.cellDoubleClicked.connect(self.open_selected_file)
        v.addWidget(self.file_table,1)
        return w

    def types_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.type_table = self.make_table(["Extension / Type","Files","Total Size","Share"])
        v.addWidget(self.type_table)
        return w

    def largest_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        bar = QHBoxLayout(); bar.addWidget(QLabel("Show"))
        self.topn = QComboBox(); self.topn.addItems(["25","50","100","250","500"]); self.topn.setCurrentText("100")
        self.topn.currentTextChanged.connect(self.populate_largest)
        bar.addWidget(self.topn); bar.addWidget(QLabel("largest files")); bar.addStretch()
        v.addLayout(bar)
        self.large_table = self.make_table(["Rank","Name","Size","Type","Modified","Path"])
        self.large_table.cellDoubleClicked.connect(self.open_selected_large)
        v.addWidget(self.large_table,1)
        return w

    def structure_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Folder","Depth","Modified","Path"])
        self.tree.setAlternatingRowColors(True)
        v.addWidget(self.tree)
        return w

    def reports_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        info = QLabel("Export the current analysis without modifying the scanned folder.")
        info.setWordWrap(True); v.addWidget(info)
        row = QHBoxLayout()
        for text, fn in [("Export JSON", self.export_json), ("Export CSV", self.export_csv), ("Readable Report", self.export_report)]:
            b=QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        v.addLayout(row)
        self.report_preview = QPlainTextEdit(); self.report_preview.setReadOnly(True)
        v.addWidget(self.report_preview,1)
        return w

    def browse(self):
        p = QFileDialog.getExistingDirectory(self, "Choose Folder")
        if p: self.path.setText(p)

    def start_scan(self):
        root = self.path.text().strip()
        if not root or not os.path.isdir(root):
            QMessageBox.warning(self, "Folder Required", "Choose a valid folder first.")
            return
        self.scan_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.progress.setVisible(True); self.progress.setRange(0,0)
        self.statusBar().showMessage("Analyzing…")
        self.worker = ScanWorker(root, self.recursive.isChecked(), self.hidden.isChecked(), self.depth.value())
        self.worker.progress.connect(lambda n,p: self.statusBar().showMessage(f"Scanning: {n:,} files — {p}"))
        self.worker.finished.connect(self.scan_finished)
        self.worker.error.connect(self.scan_error)
        self.worker.start()

    def stop_scan(self):
        if self.worker:
            self.worker.stop()
            self.statusBar().showMessage("Stopping scan…")

    def scan_error(self, msg):
        self.scan_btn.setEnabled(True); self.stop_btn.setEnabled(False); self.progress.setVisible(False)
        QMessageBox.critical(self, "Scan Error", msg)

    def scan_finished(self, data):
        self.data = data
        self.scan_btn.setEnabled(True); self.stop_btn.setEnabled(False); self.progress.setVisible(False)
        self.populate_all()
        state = "stopped" if data["stopped"] else "complete"
        self.statusBar().showMessage(f"Analysis {state}: {len(data['files']):,} files, {len(data['dirs']):,} directories.")

    def populate_all(self):
        d=self.data; files=d["files"]
        size=d["total_size"]; count=len(files)
        largest=d["largest"][0] if d["largest"] else None
        self.cards["files"].setText(f"{count:,}")
        self.cards["dirs"].setText(f"{len(d['dirs']):,}")
        self.cards["size"].setText(human(size))
        self.cards["avg"].setText(human(size/count) if count else "0 B")
        self.cards["ext"].setText(f"{len(d['ext_stats']):,}")
        self.cards["largest"].setText(human(largest["size"]) if largest else "—")
        self.cards["text"].setText(f"{sum(1 for x in files if x['kind']=='Text / Code'):,}")
        self.cards["errors"].setText(f"{d['errors']:,}")
        lines=[
            f"Root: {d['root']}",
            f"Status: {'Stopped by user' if d['stopped'] else 'Complete'}",
            f"Files: {count:,}",
            f"Directories discovered: {len(d['dirs']):,}",
            f"Total file size: {human(size)}",
            f"Average file size: {human(size/count) if count else '0 B'}",
            f"Distinct extensions: {len(d['ext_stats']):,}",
            f"Access/read errors: {d['errors']:,}",
            "",
            "Storage by category:"
        ]
        for k,v in sorted(d["kind_stats"].items(), key=lambda x:x[1], reverse=True):
            lines.append(f"  {k}: {human(v)} ({v/size*100:.1f}%)" if size else f"  {k}: {human(v)}")
        if largest:
            lines += ["","Largest file:",f"  {largest['path']}",f"  {human(largest['size'])}"]
        self.summary.setPlainText("\n".join(lines))
        self.populate_files(); self.populate_types(); self.populate_largest(); self.populate_tree()
        self.report_preview.setPlainText(self.build_report())

    def populate_files(self):
        if not self.data:return
        rows=list(self.data["files"])
        mode=self.sort_files.currentText()
        if mode=="Name A–Z": rows.sort(key=lambda x:x["name"].lower())
        elif mode=="Modified ↓": rows.sort(key=lambda x:x["mtime"],reverse=True)
        elif mode=="Extension": rows.sort(key=lambda x:x["extension"].lower())
        else: rows.sort(key=lambda x:x["size"],reverse=True)
        q=self.file_search.text().lower()
        kind=self.kind_filter.currentText()
        if q: rows=[x for x in rows if q in x["name"].lower() or q in x["path"].lower() or q in x["extension"].lower() or q in x["kind"].lower()]
        if kind!="All types": rows=[x for x in rows if x["kind"]==kind]
        self.file_table.setRowCount(0)
        for x in rows[:5000]:
            r=self.file_table.rowCount(); self.file_table.insertRow(r)
            vals=[x["name"],x["kind"],x["extension"],human(x["size"]),datetime.fromtimestamp(x["mtime"]).strftime("%Y-%m-%d %H:%M"),x["path"]]
            for c,val in enumerate(vals): self.file_table.setItem(r,c,QTableWidgetItem(str(val)))
        self.file_table.resizeColumnsToContents()
        if self.file_table.columnCount(): self.file_table.setColumnWidth(5,500)

    def filter_files(self):
        self.populate_files()

    def populate_types(self):
        if not self.data:return
        counts={}
        for f in self.data["files"]: counts[f["extension"]]=counts.get(f["extension"],0)+1
        total=self.data["total_size"]
        rows=sorted(self.data["ext_stats"].items(),key=lambda x:x[1],reverse=True)
        self.type_table.setRowCount(0)
        for ext,size in rows:
            r=self.type_table.rowCount(); self.type_table.insertRow(r)
            vals=[ext,counts.get(ext,0),human(size),f"{size/total*100:.1f}%" if total else "0%"]
            for c,v in enumerate(vals): self.type_table.setItem(r,c,QTableWidgetItem(str(v)))
        self.type_table.resizeColumnsToContents()

    def populate_largest(self):
        if not self.data:return
        n=int(self.topn.currentText()); self.large_table.setRowCount(0)
        for i,x in enumerate(self.data["largest"][:n],1):
            r=self.large_table.rowCount(); self.large_table.insertRow(r)
            vals=[i,x["name"],human(x["size"]),x["kind"],datetime.fromtimestamp(x["mtime"]).strftime("%Y-%m-%d %H:%M"),x["path"]]
            for c,v in enumerate(vals): self.large_table.setItem(r,c,QTableWidgetItem(str(v)))
        self.large_table.resizeColumnsToContents()
        self.large_table.setColumnWidth(5,500)

    def populate_tree(self):
        self.tree.clear()
        if not self.data:return
        root=QTreeWidgetItem([Path(self.data["root"]).name or self.data["root"],"0","",self.data["root"]])
        self.tree.addTopLevelItem(root)
        nodes={self.data["root"]:root}
        for x in sorted(self.data["dirs"],key=lambda z:z["path"].lower()):
            parent=os.path.dirname(x["path"])
            # If an ancestor was skipped from the discovered list, attach upward to nearest known node.
            while parent not in nodes and parent and parent != os.path.dirname(parent):
                parent=os.path.dirname(parent)
            par=nodes.get(parent,root)
            item=QTreeWidgetItem([x["name"],str(x["depth"]),datetime.fromtimestamp(x["mtime"]).strftime("%Y-%m-%d %H:%M"),x["path"]])
            par.addChild(item); nodes[x["path"]]=item
        root.setExpanded(True)

    def selected_path(self, table, path_col):
        rows=table.selectionModel().selectedRows()
        if not rows:return None
        return table.item(rows[0].row(),path_col).text()

    def open_path(self,path):
        if not path:return
        try:
            if sys.platform.startswith("linux"): subprocess.Popen(["xdg-open",path])
            elif sys.platform=="win32": os.startfile(path)
            elif sys.platform=="darwin": subprocess.Popen(["open",path])
        except Exception as e: QMessageBox.warning(self,"Open Failed",str(e))

    def open_selected_file(self,row,col):
        self.open_path(self.file_table.item(row,5).text())

    def open_selected_large(self,row,col):
        self.open_path(self.large_table.item(row,5).text())

    def table_menu(self,table,pos):
        item=table.itemAt(pos)
        if not item:return
        menu=QMenu(self)
        openact=menu.addAction("Open")
        folder=menu.addAction("Open Containing Folder")
        copy=menu.addAction("Copy Path")
        act=menu.exec(table.viewport().mapToGlobal(pos))
        if not act:return
        path=self.selected_path(table,5)
        if act==openact:self.open_path(path)
        elif act==folder:self.open_path(os.path.dirname(path))
        elif act==copy: QApplication.clipboard().setText(path)

    def build_report(self):
        if not self.data:return "No analysis available."
        d=self.data; total=d["total_size"]; files=d["files"]
        out=[
            "JASS FOLDER INTELLIGENCE STUDIO — REPORT",
            "="*60,
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Root: {d['root']}",
            f"Files: {len(files):,}",
            f"Directories: {len(d['dirs']):,}",
            f"Total size: {human(total)}",
            f"Average file: {human(total/len(files)) if files else '0 B'}",
            f"Access errors: {d['errors']:,}",
            "",
            "TOP FILE TYPES BY STORAGE",
            "-"*60
        ]
        for k,v in sorted(d["ext_stats"].items(),key=lambda x:x[1],reverse=True)[:30]:
            out.append(f"{k:20} {human(v):>12}  {(v/total*100):6.2f}%" if total else f"{k:20} {human(v):>12}")
        out += ["","LARGEST FILES","-"*60]
        for i,x in enumerate(d["largest"][:25],1): out.append(f"{i:3}. {human(x['size']):>12}  {x['path']}")
        return "\n".join(out)

    def export_json(self):
        if not self.data:return QMessageBox.information(self,"Nothing to Export","Analyze a folder first.")
        p,_=QFileDialog.getSaveFileName(self,"Export JSON","folder_intelligence.json","JSON (*.json)")
        if not p:return
        export={k:v for k,v in self.data.items() if k!="largest"}
        export["files"]=self.data["files"]; export["dirs"]=self.data["dirs"]; export["largest"]=self.data["largest"]
        Path(p).write_text(json.dumps(export,indent=2),encoding="utf-8")
        QMessageBox.information(self,"Export Complete",f"Saved:\n{p}")

    def export_csv(self):
        if not self.data:return QMessageBox.information(self,"Nothing to Export","Analyze a folder first.")
        p,_=QFileDialog.getSaveFileName(self,"Export CSV","folder_files.csv","CSV (*.csv)")
        if not p:return
        with open(p,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(["name","path","size_bytes","modified","extension","kind","depth"])
            for x in self.data["files"]:
                w.writerow([x["name"],x["path"],x["size"],datetime.fromtimestamp(x["mtime"]).isoformat(),x["extension"],x["kind"],x["depth"]])
        QMessageBox.information(self,"Export Complete",f"Saved:\n{p}")

    def export_report(self):
        if not self.data:return QMessageBox.information(self,"Nothing to Export","Analyze a folder first.")
        p,_=QFileDialog.getSaveFileName(self,"Save Report","folder_intelligence_report.txt","Text (*.txt)")
        if not p:return
        Path(p).write_text(self.build_report(),encoding="utf-8")
        QMessageBox.information(self,"Export Complete",f"Saved:\n{p}")


def main():
    app=QApplication(sys.argv)
    app.setApplicationName("JASS Folder Intelligence Studio")
    app.setStyleSheet("""
        QWidget { font-size: 13px; }
        QMainWindow { background: #f4f6f8; }
        QLineEdit,QComboBox,QSpinBox,QPlainTextEdit { padding: 6px; }
        QPushButton { padding: 8px 12px; font-weight: 600; }
        QGroupBox { font-weight: 700; }
        #Title { font-size: 25px; font-weight: 800; }
        #Subtitle { color: #64748b; margin-bottom: 5px; }
        #CardValue { font-size: 22px; font-weight: 800; }
        QTableWidget { gridline-color: #d7dce2; }
    """)
    w=MainWindow(); w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()
