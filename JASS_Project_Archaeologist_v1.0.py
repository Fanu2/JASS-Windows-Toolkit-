#!/usr/bin/env python3
"""
JASS Project Archaeologist v1.0
A read-only PySide6 project intelligence and archaeology workbench.
"""

import sys, os, re, json, csv, hashlib, subprocess, datetime, traceback
from pathlib import Path
from collections import Counter, defaultdict

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QAction, QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QTextEdit, QPlainTextEdit, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QSplitter, QFrame, QMenu, QDialog,
    QDialogButtonBox, QListWidget, QListWidgetItem
)

APP_NAME = "JASS Project Archaeologist"
VERSION = "1.0"

TEXT_EXTS = {
    ".py",".pyw",".js",".jsx",".ts",".tsx",".java",".c",".h",".cpp",".hpp",
    ".cc",".cs",".go",".rs",".rb",".php",".swift",".kt",".kts",".sh",".bash",
    ".zsh",".fish",".ps1",".bat",".cmd",".sql",".html",".htm",".css",".scss",
    ".json",".yaml",".yml",".toml",".ini",".cfg",".conf",".xml",".md",".rst",
    ".txt",".tex",".csv",".tsv",".vue",".svelte"
}
SOURCE_EXTS = {
    ".py",".pyw",".js",".jsx",".ts",".tsx",".java",".c",".h",".cpp",".hpp",
    ".cc",".cs",".go",".rs",".rb",".php",".swift",".kt",".kts",".sh",".ps1",
    ".bat",".cmd",".sql",".html",".htm",".css",".scss",".vue",".svelte"
}
IGNORE_DIRS = {
    ".git",".hg",".svn",".venv","venv","env","node_modules","__pycache__",
    ".pytest_cache",".mypy_cache",".ruff_cache","dist","build",".tox",
    ".idea",".vscode",".coverage","coverage","site-packages"
}

def human(n):
    if n is None: return "—"
    n=float(n)
    for u in ("B","KB","MB","GB","TB"):
        if n < 1024: return f"{n:.1f} {u}"
        n/=1024
    return f"{n:.1f} PB"

def fmt_dt(ts):
    try: return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except: return "—"

def is_text_file(path):
    return path.suffix.lower() in TEXT_EXTS

def safe_read(path, limit=300000):
    try:
        with open(path, "rb") as f:
            data=f.read(limit)
        if b"\x00" in data[:4096]:
            return None
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None

def git_cmd(root, args):
    try:
        p=subprocess.run(["git","-C",str(root),*args], capture_output=True,
                         text=True, timeout=20)
        if p.returncode == 0:
            return p.stdout.strip()
    except Exception:
        pass
    return ""

class ScanWorker(QThread):
    item = Signal(dict)
    progress = Signal(int, str)
    finished_scan = Signal(dict)
    failed = Signal(str)

    def __init__(self, root, max_depth=30, skip_ignored=True):
        super().__init__()
        self.root=Path(root)
        self.max_depth=max_depth
        self.skip_ignored=skip_ignored
        self.stop_requested=False
        self.count=0

    def stop(self): self.stop_requested=True

    def run(self):
        stats=Counter()
        ext=Counter()
        largest=[]
        errors=[]
        start=datetime.datetime.now()
        try:
            for base, dirs, files in os.walk(self.root, topdown=True, followlinks=False):
                if self.stop_requested: break
                basep=Path(base)
                try: depth=len(basep.relative_to(self.root).parts)
                except: depth=0
                if depth >= self.max_depth:
                    dirs[:] = []
                if self.skip_ignored:
                    dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for name in files:
                    if self.stop_requested: break
                    p=basep/name
                    try:
                        st=p.stat()
                        size=st.st_size
                        suffix=p.suffix.lower() or "[no extension]"
                        stats["files"]+=1; stats["bytes"]+=size
                        ext[suffix]+=1
                        if p.is_symlink(): stats["symlinks"]+=1
                        largest.append((size,str(p),fmt_dt(st.st_mtime)))
                        if len(largest)>120: largest.sort(reverse=True); largest=largest[:120]
                        self.count+=1
                        self.item.emit({
                            "kind":"file","path":str(p),"name":name,"size":size,
                            "ext":suffix,"modified":st.st_mtime,"depth":depth
                        })
                    except Exception as e:
                        stats["errors"]+=1; errors.append(f"{p}: {e}")
                stats["dirs"] += len(dirs)
                self.progress.emit(self.count, str(basep))
            largest.sort(reverse=True)
            info={
                "root":str(self.root),"files":stats["files"],"dirs":stats["dirs"],
                "bytes":stats["bytes"],"errors":stats["errors"],
                "symlinks":stats["symlinks"],"extensions":dict(ext),
                "largest":largest[:100],
                "duration":(datetime.datetime.now()-start).total_seconds(),
                "stopped":self.stop_requested,"errors_sample":errors[:100]
            }
            self.finished_scan.emit(info)
        except Exception:
            self.failed.emit(traceback.format_exc())

class GitWorker(QThread):
    finished_git=Signal(dict)
    def __init__(self, root): super().__init__(); self.root=root
    def run(self):
        r=Path(self.root)
        out={}
        out["is_git"]= (r/".git").exists()
        if not out["is_git"]:
            self.finished_git.emit(out); return
        out["branch"]=git_cmd(r,["branch","--show-current"])
        out["commit"]=git_cmd(r,["rev-parse","--short","HEAD"])
        out["status"]=git_cmd(r,["status","--short"])
        out["log"]=git_cmd(r,["log","--oneline","--decorate","-25"])
        out["remotes"]=git_cmd(r,["remote","-v"])
        out["tags"]=git_cmd(r,["tag","--sort=-creatordate"])[:4000]
        out["contributors"]=git_cmd(r,["shortlog","-sne","--all"])[:5000]
        self.finished_git.emit(out)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1450,900)
        self.root=None
        self.records=[]
        self.scan_info={}
        self.filtered=[]
        self.worker=None
        self.git_worker=None
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        central=QWidget(); self.setCentralWidget(central)
        main=QVBoxLayout(central); main.setContentsMargins(14,14,14,14); main.setSpacing(10)

        top=QFrame(); top.setObjectName("hero")
        tl=QVBoxLayout(top)
        title=QLabel("🏺  JASS Project Archaeologist")
        title.setObjectName("title")
        sub=QLabel("Excavate a project, reconstruct its structure, inspect its history, and discover what has been forgotten.")
        sub.setObjectName("subtitle")
        tl.addWidget(title); tl.addWidget(sub)

        controls=QHBoxLayout()
        self.path_edit=QLineEdit()
        self.path_edit.setPlaceholderText("Choose a project directory…")
        browse=QPushButton("📂 Browse")
        browse.clicked.connect(self.choose_root)
        self.depth=QSpinBox(); self.depth.setRange(1,99); self.depth.setValue(30)
        self.depth.setPrefix("Depth: ")
        self.skip=QCheckBox("Skip generated / dependency folders"); self.skip.setChecked(True)
        scan=QPushButton("🔎 Start Archaeology"); scan.setObjectName("primary")
        scan.clicked.connect(self.start_scan)
        stop=QPushButton("⏹ Stop"); stop.clicked.connect(self.stop_scan)
        controls.addWidget(self.path_edit,1); controls.addWidget(browse); controls.addWidget(self.depth)
        controls.addWidget(self.skip); controls.addWidget(scan); controls.addWidget(stop)
        tl.addLayout(controls); main.addWidget(top)

        self.progress=QProgressBar(); self.progress.setTextVisible(True)
        self.progress.setFormat("Ready")
        main.addWidget(self.progress)

        self.tabs=QTabWidget(); main.addWidget(self.tabs,1)
        self.build_dashboard()
        self.build_explorer()
        self.build_structure()
        self.build_code()
        self.build_git()
        self.build_timeline()
        self.build_reports()

        status=QLabel("Read-only • Local analysis • No files are modified")
        status.setObjectName("status")
        main.addWidget(status)

    def metric_card(self, title):
        f=QFrame(); f.setObjectName("card")
        l=QVBoxLayout(f)
        a=QLabel(title); a.setObjectName("cardTitle")
        b=QLabel("—"); b.setObjectName("cardValue")
        l.addWidget(a); l.addWidget(b)
        return f,b

    def build_dashboard(self):
        w=QWidget(); l=QVBoxLayout(w)
        grid=QGridLayout()
        self.cards={}
        for i,(k,t) in enumerate([
            ("files","Files"),("dirs","Directories"),("bytes","Total Size"),
            ("source","Source Files"),("text","Text Files"),("ext","Extensions"),
            ("largest","Largest File"),("errors","Access Errors")
        ]):
            c,v=self.metric_card(t); self.cards[k]=v; grid.addWidget(c,i//4,i%4)
        l.addLayout(grid)
        split=QSplitter(Qt.Horizontal)
        self.summary=QTextEdit(); self.summary.setReadOnly(True)
        self.type_table=QTableWidget(0,3)
        self.type_table.setHorizontalHeaderLabels(["Extension","Files","Share"])
        self.type_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        split.addWidget(self.summary); split.addWidget(self.type_table); split.setSizes([700,600])
        l.addWidget(split,1)
        self.tabs.addTab(w,"📊 Overview")

    def build_explorer(self):
        w=QWidget(); l=QVBoxLayout(w)
        bar=QHBoxLayout()
        self.search=QLineEdit(); self.search.setPlaceholderText("Search path or filename…")
        self.kind=QComboBox(); self.kind.addItems(["All","Source","Text","Large (>10 MB)"])
        self.sort=QComboBox(); self.sort.addItems(["Path","Size ↓","Size ↑","Modified ↓","Name"])
        self.search.textChanged.connect(self.refresh_explorer)
        self.kind.currentTextChanged.connect(self.refresh_explorer)
        self.sort.currentTextChanged.connect(self.refresh_explorer)
        bar.addWidget(self.search,1); bar.addWidget(self.kind); bar.addWidget(self.sort)
        l.addLayout(bar)
        self.table=QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(["Name","Type","Size","Modified","Path"])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)
        l.addWidget(self.table)
        self.tabs.addTab(w,"🧭 Explorer")

    def build_structure(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.tree=QTreeWidget(); self.tree.setHeaderLabels(["Project Structure","Kind","Size"])
        self.tree.header().setSectionResizeMode(0,QHeaderView.Stretch)
        l.addWidget(self.tree)
        self.tabs.addTab(w,"🌳 Structure")

    def build_code(self):
        w=QWidget(); l=QVBoxLayout(w)
        top=QHBoxLayout()
        self.code_filter=QLineEdit(); self.code_filter.setPlaceholderText("Filter source files…")
        self.code_filter.textChanged.connect(self.refresh_code)
        top.addWidget(self.code_filter,1)
        l.addLayout(top)
        split=QSplitter(Qt.Horizontal)
        self.code_table=QTableWidget(0,5)
        self.code_table.setHorizontalHeaderLabels(["File","Language","Lines","Size","Path"])
        self.code_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch)
        self.code_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.code_table.doubleClicked.connect(self.open_code)
        self.code_preview=QPlainTextEdit(); self.code_preview.setReadOnly(True)
        split.addWidget(self.code_table); split.addWidget(self.code_preview); split.setSizes([700,700])
        l.addWidget(split,1)
        self.tabs.addTab(w,"💻 Code Archaeology")

    def build_git(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.git_header=QLabel("Git repository: not inspected")
        self.git_header.setObjectName("section")
        l.addWidget(self.git_header)
        self.git_text=QPlainTextEdit(); self.git_text.setReadOnly(True)
        l.addWidget(self.git_text)
        btn=QPushButton("⛏ Inspect Git History"); btn.clicked.connect(self.inspect_git)
        l.addWidget(btn)
        self.tabs.addTab(w,"⛏ Git History")

    def build_timeline(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.timeline=QTableWidget(0,4)
        self.timeline.setHorizontalHeaderLabels(["Modified","File","Size","Path"])
        self.timeline.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.timeline.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        l.addWidget(self.timeline)
        self.tabs.addTab(w,"🕰 Timeline")

    def build_reports(self):
        w=QWidget(); l=QVBoxLayout(w)
        row=QHBoxLayout()
        for text,fn in [("💾 Export JSON",self.export_json),("📄 Export CSV",self.export_csv),
                        ("📝 Project Report",self.project_report),("📋 Copy Summary",self.copy_summary)]:
            b=QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row)
        self.report=QPlainTextEdit(); self.report.setReadOnly(True)
        l.addWidget(self.report)
        self.tabs.addTab(w,"📑 Reports")

    def _apply_style(self):
        self.setStyleSheet("""
        QMainWindow,QWidget { background:#11151b; color:#e8edf2; font-size:13px; }
        #hero { background:#1a2230; border:1px solid #2e3a4d; border-radius:16px; }
        #title { font-size:27px; font-weight:700; color:#f3f6fa; }
        #subtitle { color:#aeb9c7; font-size:14px; }
        #primary { background:#2d8cff; color:white; font-weight:700; padding:9px 16px; border-radius:8px; }
        QPushButton { background:#202936; border:1px solid #354255; padding:8px 12px; border-radius:7px; }
        QPushButton:hover { background:#2a3545; }
        QLineEdit,QComboBox,QSpinBox,QTextEdit,QPlainTextEdit,QTableWidget,QTreeWidget {
            background:#0d1117; border:1px solid #303b4b; border-radius:7px; }
        QTabWidget::pane { border:1px solid #2c3746; border-radius:8px; }
        QTabBar::tab { padding:10px 15px; background:#18202b; border:1px solid #293546; }
        QTabBar::tab:selected { background:#263348; }
        #card { background:#18202b; border:1px solid #2c3746; border-radius:12px; }
        #cardTitle { color:#8f9baa; }
        #cardValue { font-size:22px; font-weight:700; }
        #section { font-size:18px; font-weight:700; padding:8px; }
        #status { color:#7f8b99; padding:4px; }
        QHeaderView::section { background:#202936; padding:7px; border:0; }
        QProgressBar { border:1px solid #303b4b; border-radius:7px; text-align:center; height:22px; }
        QProgressBar::chunk { background:#2d8cff; border-radius:6px; }
        """)

    def choose_root(self):
        p=QFileDialog.getExistingDirectory(self,"Choose Project Directory",str(Path.home()))
        if p: self.path_edit.setText(p)

    def start_scan(self):
        p=self.path_edit.text().strip()
        if not p or not Path(p).is_dir():
            QMessageBox.warning(self,"Project Archaeologist","Please choose a valid project directory.")
            return
        self.root=Path(p); self.records=[]; self.scan_info={}
        self.table.setRowCount(0); self.tree.clear(); self.code_table.setRowCount(0)
        self.progress.setRange(0,0); self.progress.setFormat("Excavating…")
        self.worker=ScanWorker(self.root,self.depth.value(),self.skip.isChecked())
        self.worker.item.connect(self.on_item)
        self.worker.progress.connect(lambda n,path:self.progress.setFormat(f"Examined {n:,} files • {path}"))
        self.worker.finished_scan.connect(self.scan_done)
        self.worker.failed.connect(lambda e: QMessageBox.critical(self,"Scan failed",e))
        self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.progress.setFormat("Stopping…")

    def on_item(self,r):
        self.records.append(r)
        if len(self.records)%250==0: self.refresh_explorer()

    def scan_done(self,info):
        self.scan_info=info
        self.progress.setRange(0,100); self.progress.setValue(100)
        self.progress.setFormat(f"Completed • {info['files']:,} files • {human(info['bytes'])}")
        self.refresh_all()

    def refresh_all(self):
        info=self.scan_info
        if not info:return
        src=sum(1 for r in self.records if Path(r["path"]).suffix.lower() in SOURCE_EXTS)
        txt=sum(1 for r in self.records if is_text_file(Path(r["path"])))
        largest=max((r for r in self.records),key=lambda x:x["size"],default=None)
        self.cards["files"].setText(f"{info['files']:,}")
        self.cards["dirs"].setText(f"{info['dirs']:,}")
        self.cards["bytes"].setText(human(info["bytes"]))
        self.cards["source"].setText(f"{src:,}")
        self.cards["text"].setText(f"{txt:,}")
        self.cards["ext"].setText(f"{len(info['extensions']):,}")
        self.cards["largest"].setText(human(largest["size"]) if largest else "—")
        self.cards["errors"].setText(str(info["errors"]))
        self.summary.setPlainText(self.make_summary())
        self.refresh_types()
        self.refresh_explorer()
        self.refresh_structure()
        self.refresh_code()
        self.refresh_timeline()
        self.report.setPlainText(self.make_report())

    def make_summary(self):
        i=self.scan_info
        lines=[
            f"PROJECT ROOT\n{i.get('root','—')}",
            "",
            "ARCHAEOLOGY FINDINGS",
            f"Files: {i.get('files',0):,}",
            f"Directories encountered: {i.get('dirs',0):,}",
            f"Disk footprint: {human(i.get('bytes',0))}",
            f"Source files: {sum(Path(r['path']).suffix.lower() in SOURCE_EXTS for r in self.records):,}",
            f"Text-readable files: {sum(is_text_file(Path(r['path'])) for r in self.records):,}",
            f"Access errors: {i.get('errors',0):,}",
            f"Scan time: {i.get('duration',0):.2f}s",
            "",
            "INTERPRETATION",
            "This report is observational. It does not alter, rename, delete, or migrate project files."
        ]
        if (self.root/".git").exists():
            lines += ["","VERSION CONTROL","Git repository detected."]
        return "\n".join(lines)

    def refresh_types(self):
        d=sorted(self.scan_info.get("extensions",{}).items(),key=lambda x:x[1],reverse=True)
        total=max(1,self.scan_info.get("files",1))
        self.type_table.setRowCount(len(d))
        for row,(e,n) in enumerate(d):
            self.type_table.setItem(row,0,QTableWidgetItem(e))
            self.type_table.setItem(row,1,QTableWidgetItem(f"{n:,}"))
            self.type_table.setItem(row,2,QTableWidgetItem(f"{n/total*100:.1f}%"))

    def refresh_explorer(self):
        q=self.search.text().lower()
        k=self.kind.currentText()
        rows=[]
        for r in self.records:
            p=Path(r["path"]); ext=p.suffix.lower()
            if q and q not in r["path"].lower(): continue
            if k=="Source" and ext not in SOURCE_EXTS: continue
            if k=="Text" and not is_text_file(p): continue
            if k=="Large (>10 MB)" and r["size"]<=10*1024*1024: continue
            rows.append(r)
        s=self.sort.currentText()
        if s=="Size ↓": rows.sort(key=lambda x:x["size"],reverse=True)
        elif s=="Size ↑": rows.sort(key=lambda x:x["size"])
        elif s=="Modified ↓": rows.sort(key=lambda x:x["modified"],reverse=True)
        elif s=="Name": rows.sort(key=lambda x:x["name"].lower())
        else: rows.sort(key=lambda x:x["path"].lower())
        self.filtered=rows
        self.table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            vals=[r["name"],r["ext"],human(r["size"]),fmt_dt(r["modified"]),r["path"]]
            for j,v in enumerate(vals): self.table.setItem(i,j,QTableWidgetItem(str(v)))

    def refresh_structure(self):
        self.tree.clear()
        rootitem=QTreeWidgetItem([self.root.name if self.root else "Project","Root",""])
        self.tree.addTopLevelItem(rootitem)
        nodes={str(self.root):rootitem} if self.root else {}
        for r in sorted(self.records,key=lambda x:x["path"]):
            p=Path(r["path"]); parent=p.parent
            parent_item=nodes.get(str(parent),rootitem)
            it=QTreeWidgetItem([p.name,r["ext"],human(r["size"])])
            parent_item.addChild(it)
            nodes[str(p)]=it
        rootitem.setExpanded(True)

    def refresh_code(self):
        q=self.code_filter.text().lower()
        rows=[]
        for r in self.records:
            p=Path(r["path"])
            if p.suffix.lower() not in SOURCE_EXTS: continue
            if q and q not in r["path"].lower(): continue
            txt=safe_read(p,1000000)
            lines=txt.count("\n")+1 if txt is not None else 0
            rows.append((r,lines))
        rows.sort(key=lambda x:x[0]["path"].lower())
        self.code_table.setRowCount(len(rows))
        for i,(r,lines) in enumerate(rows):
            vals=[r["name"],r["ext"].lstrip(".").upper(),f"{lines:,}",human(r["size"]),r["path"]]
            for j,v in enumerate(vals): self.code_table.setItem(i,j,QTableWidgetItem(str(v)))

    def open_code(self,index):
        row=index.row()
        path=self.code_table.item(row,4).text()
        txt=safe_read(Path(path),2000000)
        self.code_preview.setPlainText(txt or "[Unable to decode/read file]")

    def refresh_timeline(self):
        rows=sorted(self.records,key=lambda x:x["modified"],reverse=True)[:500]
        self.timeline.setRowCount(len(rows))
        for i,r in enumerate(rows):
            vals=[fmt_dt(r["modified"]),r["name"],human(r["size"]),r["path"]]
            for j,v in enumerate(vals): self.timeline.setItem(i,j,QTableWidgetItem(v))

    def inspect_git(self):
        if not self.root:return
        self.git_header.setText(f"Git repository: {self.root}")
        self.git_text.setPlainText("Inspecting Git history…")
        self.git_worker=GitWorker(self.root)
        self.git_worker.finished_git.connect(self.git_done)
        self.git_worker.start()

    def git_done(self,d):
        if not d.get("is_git"):
            self.git_text.setPlainText("No .git directory detected at the selected project root.")
            return
        text=(
            f"Branch: {d.get('branch') or '(detached/unknown)'}\n"
            f"HEAD: {d.get('commit') or '—'}\n\n"
            f"WORKTREE STATUS\n{d.get('status') or '(clean / no short-status output)'}\n\n"
            f"RECENT COMMITS\n{d.get('log') or '—'}\n\n"
            f"REMOTES\n{d.get('remotes') or '—'}\n\n"
            f"TAGS\n{d.get('tags') or '—'}\n\n"
            f"CONTRIBUTORS\n{d.get('contributors') or '—'}"
        )
        self.git_text.setPlainText(text)

    def make_report(self):
        if not self.scan_info:return "No archaeology run yet."
        i=self.scan_info
        ext=sorted(i.get("extensions",{}).items(),key=lambda x:x[1],reverse=True)
        largest=sorted(self.records,key=lambda x:x["size"],reverse=True)[:15]
        lines=[
            "JASS PROJECT ARCHAEOLOGIST REPORT",
            "="*70,
            f"Generated: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Root: {i['root']}",
            "",
            "PROJECT METRICS",
            f"Files: {i['files']:,}",
            f"Directories: {i['dirs']:,}",
            f"Size: {human(i['bytes'])}",
            f"Access errors: {i['errors']:,}",
            f"Scan duration: {i['duration']:.2f}s",
            "",
            "FILE TYPE DISTRIBUTION"
        ]
        for e,n in ext: lines.append(f"{e:20} {n:8,}  {n/max(1,i['files'])*100:6.2f}%")
        lines += ["","LARGEST FILES"]
        for n,r in enumerate(largest,1):
            lines.append(f"{n:2}. {human(r['size']):>12}  {r['path']}")
        if i.get("errors_sample"):
            lines += ["","ACCESS ERROR SAMPLE"]+i["errors_sample"][:20]
        return "\n".join(lines)

    def project_report(self):
        self.tabs.setCurrentWidget(self.tabs.widget(6))
        self.report.setPlainText(self.make_report())
        return True

    def copy_summary(self):
        QApplication.clipboard().setText(self.make_report())
        QMessageBox.information(self,"Copied","Project report copied to clipboard.")

    def export_json(self):
        if not self.records:return
        p,_=QFileDialog.getSaveFileName(self,"Export JSON",str(self.root/"project_archaeology.json"),"JSON (*.json)")
        if not p:return
        data={"application":APP_NAME,"version":VERSION,"scan":self.scan_info,"records":self.records}
        try:
            Path(p).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
            QMessageBox.information(self,"Export complete",p)
        except Exception as e: QMessageBox.critical(self,"Export failed",str(e))

    def export_csv(self):
        if not self.records:return
        p,_=QFileDialog.getSaveFileName(self,"Export CSV",str(self.root/"project_files.csv"),"CSV (*.csv)")
        if not p:return
        try:
            with open(p,"w",newline="",encoding="utf-8") as f:
                wr=csv.writer(f); wr.writerow(["name","extension","size","modified","path"])
                for r in self.records: wr.writerow([r["name"],r["ext"],r["size"],fmt_dt(r["modified"]),r["path"]])
            QMessageBox.information(self,"Export complete",p)
        except Exception as e: QMessageBox.critical(self,"Export failed",str(e))

    def table_menu(self,pos):
        row=self.table.rowAt(pos.y())
        if row<0:return
        path=self.table.item(row,4).text()
        menu=QMenu(self)
        copy=menu.addAction("📋 Copy Path")
        openf=menu.addAction("📂 Open Containing Folder")
        menu.addSeparator()
        inspect=menu.addAction("🔍 Inspect File")
        act=menu.exec(self.table.viewport().mapToGlobal(pos))
        if act==copy: QApplication.clipboard().setText(path)
        elif act==openf:
            subprocess.Popen(["xdg-open",str(Path(path).parent)])
        elif act==inspect:
            txt=safe_read(Path(path),500000)
            dlg=QDialog(self); dlg.setWindowTitle(Path(path).name); dlg.resize(900,650)
            lay=QVBoxLayout(dlg)
            ed=QPlainTextEdit(); ed.setReadOnly(True); ed.setPlainText(txt or "[Binary, unreadable, or unsupported text file]")
            lay.addWidget(ed)
            dlg.exec()

def main():
    app=QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w=MainWindow(); w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()
