#!/usr/bin/env python3
"""
JASS Archive Explorer v1.0
Lightweight, local-first PySide6 archive browser.

Supports inspection of ZIP/TAR-family archives using Python's standard library.
7z/RAR are detected and can be opened with an installed external utility.
Read-only by default: no archive is modified.
"""

import sys
import os
import json
import csv
import mimetypes
import shutil
import subprocess
import zipfile
import tarfile
import gzip
import bz2
import lzma
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QTabWidget, QProgressBar, QGroupBox, QFormLayout, QPlainTextEdit,
    QAbstractItemView, QMenu, QTreeWidget, QTreeWidgetItem, QDialog,
    QDialogButtonBox
)

ARCHIVE_EXTS = {
    ".zip": "ZIP", ".tar": "TAR", ".tgz": "TAR.GZ", ".tar.gz": "TAR.GZ",
    ".tbz": "TAR.BZ2", ".tbz2": "TAR.BZ2", ".tar.bz2": "TAR.BZ2",
    ".txz": "TAR.XZ", ".tar.xz": "TAR.XZ", ".gz": "GZIP",
    ".bz2": "BZIP2", ".xz": "XZ", ".7z": "7-Zip", ".rar": "RAR"
}

TEXT_EXTS = {
    ".txt", ".md", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".html",
    ".css", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".sql", ".sh", ".bash", ".ps1", ".bat", ".csv", ".log"
}


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            return f"{n:,.1f} {unit}"
        n /= 1024
    return "0 B"


def archive_type(path):
    name = str(path).lower()
    for ext in sorted(ARCHIVE_EXTS, key=len, reverse=True):
        if name.endswith(ext):
            return ARCHIVE_EXTS[ext]
    return "Unknown"


def external_tool(kind):
    if kind == "7-Zip":
        return shutil.which("7z") or shutil.which("7zz")
    if kind == "RAR":
        return shutil.which("unrar")
    return None


def kind_for_name(name):
    ext = Path(name).suffix.lower()
    if ext in TEXT_EXTS:
        return "Text / Code"
    if ext in {".jpg",".jpeg",".png",".gif",".bmp",".webp",".tif",".tiff",".svg",".ico"}:
        return "Image"
    if ext in {".mp3",".wav",".flac",".ogg",".opus",".m4a",".aac",".wma"}:
        return "Audio"
    if ext in {".mp4",".mkv",".avi",".mov",".webm",".m4v",".mpeg",".mpg"}:
        return "Video"
    if ext in {".pdf",".doc",".docx",".odt",".rtf"}:
        return "Document"
    if ext in {".zip",".7z",".rar",".tar",".gz",".bz2",".xz"}:
        return "Archive"
    return "Other"


def open_system(path):
    if sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", str(path)])
    elif sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])


def zip_entries(path):
    with zipfile.ZipFile(path, "r") as z:
        return [
            {"name": i.filename, "size": i.file_size, "compressed": i.compress_size,
             "is_dir": i.is_dir(), "modified": datetime(*i.date_time).isoformat(sep=" "),
             "method": i.compress_type, "crc": f"{i.CRC:08X}"}
            for i in z.infolist()
        ]


def tar_entries(path):
    mode = "r:*"
    with tarfile.open(path, mode) as t:
        out = []
        for i in t.getmembers():
            out.append({
                "name": i.name, "size": i.size, "compressed": 0,
                "is_dir": i.isdir(), "modified": datetime.fromtimestamp(i.mtime).isoformat(sep=" "),
                "method": i.type.decode(errors="replace") if isinstance(i.type, bytes) else str(i.type),
                "crc": ""
            })
        return out


class ArchiveWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            kind = archive_type(self.path)
            if kind == "ZIP":
                entries = zip_entries(self.path)
                backend = "Python zipfile"
            elif kind.startswith("TAR"):
                entries = tar_entries(self.path)
                backend = "Python tarfile"
            elif kind == "GZIP":
                entries = [{"name": Path(self.path).stem, "size": os.path.getsize(self.path),
                            "compressed": os.path.getsize(self.path), "is_dir": False,
                            "modified": "", "method": "GZIP", "crc": ""}]
                backend = "Python gzip"
            elif kind == "BZIP2":
                entries = [{"name": Path(self.path).stem, "size": os.path.getsize(self.path),
                            "compressed": os.path.getsize(self.path), "is_dir": False,
                            "modified": "", "method": "BZIP2", "crc": ""}]
                backend = "Python bz2"
            elif kind == "XZ":
                entries = [{"name": Path(self.path).stem, "size": os.path.getsize(self.path),
                            "compressed": os.path.getsize(self.path), "is_dir": False,
                            "modified": "", "method": "XZ", "crc": ""}]
                backend = "Python lzma"
            else:
                tool = external_tool("7-Zip" if kind == "7-Zip" else "RAR")
                if not tool:
                    raise RuntimeError(
                        f"{kind} archives require an external tool. "
                        f"Install {'p7zip-full' if kind == '7-Zip' else 'unrar'} and try again."
                    )
                if kind == "7-Zip":
                    proc = subprocess.run([tool, "l", "-slt", self.path],
                                          capture_output=True, text=True, errors="replace")
                    if proc.returncode != 0:
                        raise RuntimeError(proc.stderr.strip() or "7z could not read the archive.")
                    entries = []
                    current = None
                    for line in proc.stdout.splitlines():
                        if line.startswith("Path = "):
                            if current:
                                entries.append(current)
                            current = {"name": line[7:], "size": 0, "compressed": 0,
                                       "is_dir": False, "modified": "", "method": "", "crc": ""}
                        elif current is not None:
                            if line.startswith("Size = "):
                                try: current["size"] = int(line[7:])
                                except ValueError: pass
                            elif line.startswith("Packed Size = "):
                                try: current["compressed"] = int(line[14:])
                                except ValueError: pass
                            elif line.startswith("Folder = "):
                                current["is_dir"] = line[9:].strip() == "+"
                            elif line.startswith("Modified = "):
                                current["modified"] = line[11:]
                    if current: entries.append(current)
                    backend = tool
                else:
                    proc = subprocess.run([tool, "-tv", self.path],
                                          capture_output=True, text=True, errors="replace")
                    if proc.returncode != 0:
                        raise RuntimeError(proc.stderr.strip() or "unrar could not read the archive.")
                    entries = []
                    for line in proc.stdout.splitlines():
                        if "  " in line and len(line) > 30:
                            parts = line.split()
                            if len(parts) >= 6:
                                try:
                                    size = int(parts[2])
                                except ValueError:
                                    continue
                                name = " ".join(parts[5:])
                                entries.append({"name": name, "size": size, "compressed": 0,
                                                "is_dir": False, "modified": " ".join(parts[0:2]),
                                                "method": "", "crc": ""})
                    backend = tool
            self.finished.emit({"path": self.path, "kind": kind, "entries": entries, "backend": backend})
        except Exception as e:
            self.error.emit(str(e))


class TextPreview(QDialog):
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.setWindowTitle(title); self.resize(850, 650)
        v = QVBoxLayout(self)
        edit = QPlainTextEdit(); edit.setReadOnly(True); edit.setPlainText(text); v.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(self.reject); v.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JASS Archive Explorer v1.0")
        self.resize(1400, 900)
        self.data = None
        self.worker = None
        self.current_path = ""
        self.build_ui()

    def build_ui(self):
        root = QWidget(); self.setCentralWidget(root); outer = QVBoxLayout(root)
        title = QLabel("JASS Archive Explorer"); title.setObjectName("Title"); outer.addWidget(title)
        sub = QLabel("Browse • Inspect • Search • Preview — archive contents without extracting everything")
        sub.setObjectName("Subtitle"); outer.addWidget(sub)

        controls = QGroupBox("Archive")
        f = QGridLayout(controls)
        self.archive_path = QLineEdit(); self.archive_path.setPlaceholderText("Choose ZIP, TAR, 7Z, RAR, GZ, BZ2 or XZ archive…")
        browse = QPushButton("Browse…"); browse.clicked.connect(self.browse)
        open_btn = QPushButton("📂 Open Archive"); open_btn.clicked.connect(self.open_archive)
        f.addWidget(QLabel("File"),0,0); f.addWidget(self.archive_path,0,1,1,4); f.addWidget(browse,0,5); f.addWidget(open_btn,0,6)
        outer.addWidget(controls)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.dashboard(), "🏠 Dashboard")
        self.tabs.addTab(self.contents(), "📦 Contents")
        self.tabs.addTab(self.tree_tab(), "🌳 Structure")
        self.tabs.addTab(self.search_tab(), "🔎 Search")
        self.tabs.addTab(self.preview_tab(), "👁 Preview")
        self.tabs.addTab(self.report_tab(), "📋 Report")
        outer.addWidget(self.tabs,1)
        self.statusBar().showMessage("Choose an archive and click Open Archive.")

    def dashboard(self):
        w=QWidget(); v=QVBoxLayout(w); grid=QGridLayout(); self.cards={}
        for i,(k,l) in enumerate([("name","Archive"),("type","Format"),("size","Archive Size"),("entries","Entries"),("files","Files"),("dirs","Directories"),("stored","Stored Size"),("compressed","Packed Size")]):
            box=QGroupBox(l); bv=QVBoxLayout(box); val=QLabel("—"); val.setObjectName("CardValue"); bv.addWidget(val); self.cards[k]=val; grid.addWidget(box,i//4,i%4)
        v.addLayout(grid); self.dashboard_text=QPlainTextEdit(); self.dashboard_text.setReadOnly(True); v.addWidget(self.dashboard_text,1); return w

    def make_table(self, headers):
        t=QTableWidget(0,len(headers)); t.setHorizontalHeaderLabels(headers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows); t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers); t.setAlternatingRowColors(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive); t.horizontalHeader().setStretchLastSection(True)
        t.setContextMenuPolicy(Qt.CustomContextMenu); t.customContextMenuRequested.connect(lambda p,tab=t:self.menu(tab,p))
        return t

    def contents(self):
        w=QWidget(); v=QVBoxLayout(w); bar=QHBoxLayout()
        self.filter=QLineEdit(); self.filter.setPlaceholderText("Filter filename/path…"); self.filter.textChanged.connect(self.populate_contents)
        self.file_filter=QComboBox(); self.file_filter.addItems(["All","Files","Directories"]); self.file_filter.currentTextChanged.connect(self.populate_contents)
        self.sort=QComboBox(); self.sort.addItems(["Name A–Z","Size ↓","Packed Size ↓"]); self.sort.currentTextChanged.connect(self.populate_contents)
        bar.addWidget(self.filter,2); bar.addWidget(self.file_filter); bar.addWidget(self.sort); v.addLayout(bar)
        self.content_table=self.make_table(["Name","Type","Size","Packed","Ratio","Modified"]); self.content_table.cellDoubleClicked.connect(self.preview_selected)
        v.addWidget(self.content_table,1); return w

    def tree_tab(self):
        w=QWidget(); v=QVBoxLayout(w); self.tree=QTreeWidget(); self.tree.setHeaderLabels(["Path","Type","Size"]); v.addWidget(self.tree); return w

    def search_tab(self):
        w=QWidget(); v=QVBoxLayout(w)
        self.search=QLineEdit(); self.search.setPlaceholderText("Search inside archive by filename…"); self.search.textChanged.connect(self.populate_search); v.addWidget(self.search)
        self.search_table=self.make_table(["Name","Type","Size","Packed","Modified"]); self.search_table.cellDoubleClicked.connect(self.preview_selected_search); v.addWidget(self.search_table,1); return w

    def preview_tab(self):
        w=QWidget(); v=QVBoxLayout(w)
        self.preview_info=QLabel("Select a text file in Contents or Search to preview it."); v.addWidget(self.preview_info)
        self.preview_text=QPlainTextEdit(); self.preview_text.setReadOnly(True); v.addWidget(self.preview_text,1); return w

    def report_tab(self):
        w=QWidget(); v=QVBoxLayout(w)
        row=QHBoxLayout()
        for text,fn in [("Export JSON",self.export_json),("Export CSV",self.export_csv),("Save TXT Report",self.export_txt)]:
            b=QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch(); v.addLayout(row)
        self.report=QPlainTextEdit(); self.report.setReadOnly(True); v.addWidget(self.report,1); return w

    def browse(self):
        p,_=QFileDialog.getOpenFileName(self,"Choose Archive","",
            "Archives (*.zip *.tar *.tgz *.tar.gz *.tbz *.tbz2 *.tar.bz2 *.txz *.tar.xz *.gz *.bz2 *.xz *.7z *.rar);;All Files (*)")
        if p:self.archive_path.setText(p)

    def open_archive(self):
        p=self.archive_path.text().strip()
        if not p or not os.path.isfile(p):
            QMessageBox.warning(self,"Archive Required","Choose a valid archive file first."); return
        self.current_path=p; self.statusBar().showMessage("Reading archive…")
        self.worker=ArchiveWorker(p); self.worker.finished.connect(self.loaded); self.worker.error.connect(self.failed); self.worker.start()

    def failed(self,msg): QMessageBox.critical(self,"Archive Error",msg); self.statusBar().showMessage("Archive could not be opened.")

    def loaded(self,d):
        self.data=d; self.populate_all()
        self.statusBar().showMessage(f"Opened {Path(d['path']).name}: {len(d['entries']):,} entries using {d['backend']}.")

    def populate_all(self):
        d=self.data; entries=d["entries"]; files=[x for x in entries if not x["is_dir"]]; dirs=[x for x in entries if x["is_dir"]]
        stored=sum(x["size"] for x in files); packed=sum(x["compressed"] for x in files)
        self.cards["name"].setText(Path(d["path"]).name); self.cards["type"].setText(d["kind"])
        self.cards["size"].setText(human(os.path.getsize(d["path"]))); self.cards["entries"].setText(f"{len(entries):,}")
        self.cards["files"].setText(f"{len(files):,}"); self.cards["dirs"].setText(f"{len(dirs):,}")
        self.cards["stored"].setText(human(stored)); self.cards["compressed"].setText(human(packed))
        ratio=f"{stored/packed:.2f}×" if packed else "n/a"
        self.dashboard_text.setPlainText(
            f"Archive: {d['path']}\nFormat: {d['kind']}\nBackend: {d['backend']}\n"
            f"Entries: {len(entries):,}\nFiles: {len(files):,}\nDirectories: {len(dirs):,}\n"
            f"Stored content: {human(stored)}\nPacked content: {human(packed)}\n"
            f"Expansion ratio: {ratio}\n\n"
            "Safety: this application reads archive metadata/content but does not modify the archive."
        )
        self.populate_contents(); self.populate_search(); self.populate_tree(); self.report.setPlainText(self.build_report())

    def populate_contents(self):
        if not self.data:return
        rows=list(self.data["entries"]); q=self.filter.text().lower(); mode=self.file_filter.currentText()
        if q: rows=[x for x in rows if q in x["name"].lower()]
        if mode=="Files": rows=[x for x in rows if not x["is_dir"]]
        elif mode=="Directories": rows=[x for x in rows if x["is_dir"]]
        sm=self.sort.currentText()
        if sm=="Size ↓": rows.sort(key=lambda x:x["size"],reverse=True)
        elif sm=="Packed Size ↓": rows.sort(key=lambda x:x["compressed"],reverse=True)
        else: rows.sort(key=lambda x:x["name"].lower())
        self.content_table.setRowCount(0)
        for x in rows[:10000]:
            r=self.content_table.rowCount(); self.content_table.insertRow(r)
            typ="Directory" if x["is_dir"] else kind_for_name(x["name"])
            ratio=(x["compressed"]/x["size"]*100) if x["size"] else 0
            vals=[x["name"],typ,human(x["size"]),human(x["compressed"]),f"{ratio:.1f}%" if x["compressed"] else "—",x["modified"]]
            for c,val in enumerate(vals):self.content_table.setItem(r,c,QTableWidgetItem(str(val)))
        self.content_table.resizeColumnsToContents(); self.content_table.setColumnWidth(0,600)

    def populate_search(self):
        if not self.data:return
        q=self.search.text().strip().lower(); rows=[x for x in self.data["entries"] if q in x["name"].lower()] if q else []
        self.search_table.setRowCount(0)
        for x in rows[:10000]:
            r=self.search_table.rowCount(); self.search_table.insertRow(r)
            vals=[x["name"],"Directory" if x["is_dir"] else kind_for_name(x["name"]),human(x["size"]),human(x["compressed"]),x["modified"]]
            for c,val in enumerate(vals):self.search_table.setItem(r,c,QTableWidgetItem(str(val)))
        self.search_table.resizeColumnsToContents(); self.search_table.setColumnWidth(0,650)

    def populate_tree(self):
        self.tree.clear()
        if not self.data:return
        root=QTreeWidgetItem([Path(self.data["path"]).name,self.data["kind"],human(os.path.getsize(self.data["path"]))]); self.tree.addTopLevelItem(root)
        nodes={"":root}
        for x in sorted(self.data["entries"],key=lambda z:z["name"].lower()):
            parts=[p for p in x["name"].replace("\\","/").split("/") if p]
            if not parts:continue
            parent=""; parent_item=root
            for part in parts[:-1]:
                key=(parent+"/"+part).strip("/")
                if key not in nodes:
                    item=QTreeWidgetItem([part,"Directory",""]); parent_item.addChild(item); nodes[key]=item
                parent_item=nodes[key]; parent=key
            QTreeWidgetItem(parent_item,[parts[-1],"Directory" if x["is_dir"] else kind_for_name(x["name"]),human(x["size"])])
        root.setExpanded(True)

    def selected_name(self,table,col=0):
        rows=table.selectionModel().selectedRows()
        return table.item(rows[0].row(),col).text() if rows else None

    def preview_selected(self,row,col):
        self.preview_entry(self.content_table.item(row,0).text())
    def preview_selected_search(self,row,col):
        self.preview_entry(self.search_table.item(row,0).text())

    def preview_entry(self,name):
        if not self.data:return
        e=next((x for x in self.data["entries"] if x["name"]==name),None)
        if not e or e["is_dir"]:return
        if not Path(name).suffix.lower() in TEXT_EXTS:
            self.preview_info.setText(f"{name}\nBinary/non-text file — metadata is available in Contents.")
            self.preview_text.clear(); self.tabs.setCurrentIndex(4); return
        try:
            if self.data["kind"]=="ZIP":
                with zipfile.ZipFile(self.data["path"]) as z:
                    raw=z.read(name)
            elif self.data["kind"].startswith("TAR"):
                with tarfile.open(self.data["path"],"r:*") as t:
                    member=t.getmember(name); f=t.extractfile(member); raw=f.read() if f else b""
            else:
                self.preview_info.setText("Text preview is available for ZIP/TAR-family members in v1.0.")
                self.preview_text.clear(); self.tabs.setCurrentIndex(4); return
            text=raw[:2_000_000].decode("utf-8",errors="replace")
            self.preview_info.setText(f"{name} — showing up to 2 MB")
            self.preview_text.setPlainText(text); self.tabs.setCurrentIndex(4)
        except Exception as e:
            QMessageBox.warning(self,"Preview Failed",str(e))

    def menu(self,table,pos):
        item=table.itemAt(pos)
        if not item:return
        name=item.text()
        menu=QMenu(self); copy=menu.addAction("Copy Archive Path"); opena=menu.addAction("Open Archive Location")
        act=menu.exec(table.viewport().mapToGlobal(pos))
        if act==copy: QApplication.clipboard().setText(self.current_path)
        elif act==opena:
            try: open_system(os.path.dirname(self.current_path))
            except Exception as e: QMessageBox.warning(self,"Open Failed",str(e))

    def build_report(self):
        if not self.data:return "No archive loaded."
        d=self.data; es=d["entries"]; files=[x for x in es if not x["is_dir"]]; stored=sum(x["size"] for x in files); packed=sum(x["compressed"] for x in files)
        lines=["JASS ARCHIVE EXPLORER — REPORT","="*64,f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",f"Archive: {d['path']}",f"Format: {d['kind']}",f"Backend: {d['backend']}",f"Entries: {len(es):,}",f"Files: {len(files):,}",f"Directories: {len(es)-len(files):,}",f"Stored size: {human(stored)}",f"Packed size: {human(packed)}","", "LARGEST MEMBERS","-"*64]
        for i,x in enumerate(sorted(files,key=lambda z:z["size"],reverse=True)[:30],1):lines.append(f"{i:3}. {human(x['size']):>12}  {x['name']}")
        return "\n".join(lines)

    def export_json(self):
        if not self.data:return
        p,_=QFileDialog.getSaveFileName(self,"Export JSON","archive_report.json","JSON (*.json)")
        if p:
            Path(p).write_text(json.dumps(self.data,indent=2),encoding="utf-8"); QMessageBox.information(self,"Saved",f"Saved:\n{p}")
    def export_csv(self):
        if not self.data:return
        p,_=QFileDialog.getSaveFileName(self,"Export CSV","archive_contents.csv","CSV (*.csv)")
        if p:
            with open(p,"w",newline="",encoding="utf-8") as f:
                w=csv.writer(f); w.writerow(["name","size","compressed","is_dir","modified","method","crc"])
                for x in self.data["entries"]:w.writerow([x["name"],x["size"],x["compressed"],x["is_dir"],x["modified"],x["method"],x["crc"]])
            QMessageBox.information(self,"Saved",f"Saved:\n{p}")
    def export_txt(self):
        if not self.data:return
        p,_=QFileDialog.getSaveFileName(self,"Save Report","archive_report.txt","Text (*.txt)")
        if p:Path(p).write_text(self.build_report(),encoding="utf-8"); QMessageBox.information(self,"Saved",f"Saved:\n{p}")


def main():
    app=QApplication(sys.argv); app.setApplicationName("JASS Archive Explorer")
    app.setStyleSheet("""
        QWidget{font-size:13px} QLineEdit,QComboBox,QSpinBox,QPlainTextEdit{padding:6px}
        QPushButton{padding:8px 12px;font-weight:600} QGroupBox{font-weight:700}
        #Title{font-size:25px;font-weight:800} #Subtitle{color:#64748b}
        #CardValue{font-size:21px;font-weight:800}
    """)
    w=MainWindow(); w.show(); sys.exit(app.exec())

if __name__=="__main__": main()
