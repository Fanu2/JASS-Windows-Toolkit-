#!/usr/bin/env python3
"""
JASS AppImage Manager v1.0
Local-first PySide6 manager for discovering, cataloguing, launching and inspecting
AppImage applications.

Read-only by default. File operations are limited to explicitly requested desktop
integration actions such as making a .desktop launcher.
"""

import sys, os, re, json, csv, hashlib, subprocess, shutil, stat, datetime
from pathlib import Path
from collections import Counter

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QTextEdit,
    QPlainTextEdit, QFileDialog, QMessageBox, QProgressBar, QFrame,
    QSplitter, QTreeWidget, QTreeWidgetItem, QMenu, QDialog, QDialogButtonBox,
    QFormLayout, QAbstractItemView
)

APP_NAME = "JASS AppImage Manager"
VERSION = "1.0"
DEFAULT_DIRS = [
    Path.home() / "Applications",
    Path.home() / "AppImages",
    Path.home() / "Downloads",
    Path.home() / "bin",
    Path.home() / ".local" / "bin",
]

def human(n):
    n = float(n)
    for u in ("B","KB","MB","GB","TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"

def fmt_dt(ts):
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"

def sha256(path, chunk=1024*1024):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        while True:
            b=f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def run_cmd(args, timeout=15):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except Exception as e:
        return -1,"",str(e)

def appimage_type(path):
    try:
        with open(path,"rb") as f:
            head=f.read(4096)
        if head.startswith(b"\x7fELF"):
            if b"AI\x02" in head or b"AI\x01" in head:
                return "AppImage"
            # Type 1/2 AppImages are ELF files; the marker may not be in first 4K.
            if b"AppImage" in head or b"FUSE" in head:
                return "AppImage"
    except Exception:
        pass
    return path.suffix.lower() in (".appimage",".appimage2") and "AppImage" or "Unknown"

def is_appimage(path):
    if path.suffix.lower() not in (".appimage",".appimage2") and not path.name.lower().endswith(".appimage"):
        return False
    return path.is_file()

def extract_version(name):
    stem=Path(name).stem
    patterns=[
        r'(?<![\w])v?(\d+(?:\.\d+){1,4})(?![\w])',
        r'(?<![\w])(\d{4}\.\d+)(?![\w])'
    ]
    for pat in patterns:
        m=re.search(pat,stem,re.I)
        if m:return m.group(1)
    return ""

def guess_name(path):
    s=path.stem
    s=re.sub(r'[-_]?v?\d+(?:\.\d+){1,4}$','',s,flags=re.I)
    s=s.replace("_"," ").replace("-"," ").strip()
    return s or path.stem

class ScanWorker(QThread):
    found=Signal(dict)
    progress=Signal(int,str)
    done=Signal(dict)
    failed=Signal(str)

    def __init__(self, roots, recursive=True):
        super().__init__()
        self.roots=roots
        self.recursive=recursive
        self.stop_requested=False

    def stop(self): self.stop_requested=True

    def run(self):
        count=0; total=0; errors=0; seen=set()
        start=datetime.datetime.now()
        try:
            for root in self.roots:
                if self.stop_requested: break
                if not root.exists(): continue
                iterator=os.walk(root) if self.recursive else [(str(root),[],os.listdir(root))]
                for base,dirs,files in iterator:
                    if self.stop_requested: break
                    for fn in files:
                        if self.stop_requested: break
                        p=Path(base)/fn
                        try:
                            rp=str(p.resolve())
                            if rp in seen: continue
                            seen.add(rp)
                            if not is_appimage(p): continue
                            st=p.stat()
                            r={"name":p.name,"path":str(p),"size":st.st_size,
                               "modified":st.st_mtime,"version":extract_version(p.name),
                               "app_name":guess_name(p)}
                            try:r["executable"]=os.access(p,os.X_OK)
                            except:r["executable"]=False
                            self.found.emit(r)
                            count+=1; total+=st.st_size
                        except Exception:
                            errors+=1
                    self.progress.emit(count,str(base))
            self.done.emit({"count":count,"bytes":total,"errors":errors,
                            "duration":(datetime.datetime.now()-start).total_seconds(),
                            "stopped":self.stop_requested})
        except Exception as e:
            self.failed.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1500,920)
        self.apps=[]
        self.filtered=[]
        self.current=None
        self.worker=None
        self._build()
        self._style()

    def _build(self):
        c=QWidget(); self.setCentralWidget(c)
        main=QVBoxLayout(c); main.setContentsMargins(14,14,14,14); main.setSpacing(10)

        hero=QFrame(); hero.setObjectName("hero")
        hl=QVBoxLayout(hero)
        title=QLabel("📦  JASS AppImage Manager"); title.setObjectName("title")
        sub=QLabel("Discover, catalogue, inspect, launch and organize your portable Linux applications.")
        sub.setObjectName("subtitle")
        hl.addWidget(title); hl.addWidget(sub)

        row=QHBoxLayout()
        self.root=QLineEdit(); self.root.setPlaceholderText("AppImage folder or search root…")
        browse=QPushButton("📂 Browse"); browse.clicked.connect(self.choose)
        add=QPushButton("➕ Add Folder"); add.clicked.connect(self.add_folder)
        self.rec=QCheckBox("Recursive"); self.rec.setChecked(True)
        scan=QPushButton("🔎 Scan"); scan.setObjectName("primary"); scan.clicked.connect(self.scan)
        stop=QPushButton("⏹ Stop"); stop.clicked.connect(self.stop)
        row.addWidget(self.root,1); row.addWidget(browse); row.addWidget(add)
        row.addWidget(self.rec); row.addWidget(scan); row.addWidget(stop)
        hl.addLayout(row); main.addWidget(hero)

        self.progress=QProgressBar(); self.progress.setTextVisible(True); self.progress.setFormat("Ready")
        main.addWidget(self.progress)

        self.tabs=QTabWidget(); main.addWidget(self.tabs,1)
        self.dashboard(); self.library(); self.inspector(); self.duplicates()
        self.launchers(); self.reports()

        st=QLabel("Local-first • AppImage files are not modified during scanning • Launches run only when you explicitly request them")
        st.setObjectName("status"); main.addWidget(st)

    def card(self,t):
        f=QFrame(); f.setObjectName("card"); l=QVBoxLayout(f)
        a=QLabel(t); a.setObjectName("cardTitle")
        v=QLabel("—"); v.setObjectName("cardValue")
        l.addWidget(a); l.addWidget(v); return f,v

    def dashboard(self):
        w=QWidget(); l=QVBoxLayout(w); g=QGridLayout(); self.cards={}
        for i,(k,t) in enumerate([
            ("apps","AppImages"),("size","Total Size"),("exec","Executable"),
            ("versions","Versioned"),("folders","Locations"),("duplicates","Duplicate Names")
        ]):
            f,v=self.card(t); self.cards[k]=v; g.addWidget(f,i//3,i%3)
        l.addLayout(g)
        split=QSplitter(Qt.Horizontal)
        self.summary=QTextEdit(); self.summary.setReadOnly(True)
        self.type_table=QTableWidget(0,2); self.type_table.setHorizontalHeaderLabels(["Status","Count"])
        self.type_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        split.addWidget(self.summary); split.addWidget(self.type_table)
        l.addWidget(split,1); self.tabs.addTab(w,"📊 Dashboard")

    def library(self):
        w=QWidget(); l=QVBoxLayout(w)
        bar=QHBoxLayout()
        self.search=QLineEdit(); self.search.setPlaceholderText("Search AppImage name, version or path…")
        self.sort=QComboBox(); self.sort.addItems(["Name","Size ↓","Size ↑","Modified ↓","Version"])
        self.status_filter=QComboBox(); self.status_filter.addItems(["All","Executable","Not Executable"])
        self.search.textChanged.connect(self.refresh); self.sort.currentTextChanged.connect(self.refresh)
        self.status_filter.currentTextChanged.connect(self.refresh)
        bar.addWidget(self.search,1); bar.addWidget(self.status_filter); bar.addWidget(self.sort)
        l.addLayout(bar)
        self.table=QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(["","Application","Version","Size","Executable","Modified","Path"])
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6,QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self.launch_selected)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.menu)
        l.addWidget(self.table)
        self.tabs.addTab(w,"📦 AppImage Library")

    def inspector(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.inspect_title=QLabel("Select an AppImage to inspect"); self.inspect_title.setObjectName("section")
        l.addWidget(self.inspect_title)
        self.details=QPlainTextEdit(); self.details.setReadOnly(True); l.addWidget(self.details,1)
        row=QHBoxLayout()
        for label,fn in [("🚀 Launch",self.launch_current),("📂 Open Folder",self.open_folder),
                         ("🔐 SHA-256",self.hash_current),("🔑 Make Executable",self.make_executable)]:
            b=QPushButton(label); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row)
        self.tabs.addTab(w,"🔍 Inspector")

    def duplicates(self):
        w=QWidget(); l=QVBoxLayout(w)
        l.addWidget(QLabel("Potential duplicates are grouped by normalized application name."))
        self.dup=QTableWidget(0,4)
        self.dup.setHorizontalHeaderLabels(["Application","Copies","Total Size","Locations"])
        self.dup.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        l.addWidget(self.dup,1)
        b=QPushButton("🔄 Analyze Duplicates"); b.clicked.connect(self.refresh_duplicates); l.addWidget(b)
        self.tabs.addTab(w,"🧬 Duplicates")

    def launchers(self):
        w=QWidget(); l=QVBoxLayout(w)
        l.addWidget(QLabel("Desktop integration creates a launcher under ~/.local/share/applications."))
        self.launcher_name=QLineEdit(); self.launcher_name.setPlaceholderText("Launcher name (optional)")
        l.addWidget(self.launcher_name)
        b=QPushButton("🖥 Create .desktop Launcher for Selected"); b.clicked.connect(self.create_launcher)
        l.addWidget(b)
        self.launcher_log=QPlainTextEdit(); self.launcher_log.setReadOnly(True); l.addWidget(self.launcher_log,1)
        self.tabs.addTab(w,"🖥 Desktop Integration")

    def reports(self):
        w=QWidget(); l=QVBoxLayout(w)
        row=QHBoxLayout()
        for label,fn in [("💾 JSON",self.export_json),("📄 CSV",self.export_csv),
                         ("📑 Report",self.report_text)]:
            b=QPushButton(label); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row)
        self.report=QPlainTextEdit(); self.report.setReadOnly(True); l.addWidget(self.report,1)
        self.tabs.addTab(w,"📑 Reports")

    def _style(self):
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#11151b;color:#e8edf2;font-size:13px}
        #hero{background:#1a2230;border:1px solid #304057;border-radius:16px}
        #title{font-size:28px;font-weight:700;color:#f4f7fa}
        #subtitle{font-size:14px;color:#aeb9c7}
        #primary{background:#2d8cff;color:white;font-weight:700;padding:9px 16px;border-radius:8px}
        QPushButton{background:#202936;border:1px solid #354255;padding:8px 12px;border-radius:7px}
        QPushButton:hover{background:#2b3748}
        QLineEdit,QComboBox,QSpinBox,QTextEdit,QPlainTextEdit,QTableWidget{
          background:#0d1117;border:1px solid #303b4b;border-radius:7px}
        QTabWidget::pane{border:1px solid #2c3746;border-radius:8px}
        QTabBar::tab{padding:10px 15px;background:#18202b;border:1px solid #293546}
        QTabBar::tab:selected{background:#263348}
        #card{background:#18202b;border:1px solid #2c3746;border-radius:12px}
        #cardTitle{color:#8f9baa}
        #cardValue{font-size:23px;font-weight:700}
        #section{font-size:18px;font-weight:700;padding:7px}
        #status{color:#7f8b99;padding:4px}
        QHeaderView::section{background:#202936;padding:7px;border:0}
        QProgressBar{border:1px solid #303b4b;border-radius:7px;text-align:center;height:22px}
        QProgressBar::chunk{background:#2d8cff;border-radius:6px}
        """)

    def choose(self):
        p=QFileDialog.getExistingDirectory(self,"Choose AppImage Folder",str(Path.home()))
        if p:self.root.setText(p)

    def add_folder(self):
        p=QFileDialog.getExistingDirectory(self,"Add Search Folder",str(Path.home()))
        if p:
            current=[x.strip() for x in self.root.text().split(os.pathsep) if x.strip()]
            if p not in current:current.append(p)
            self.root.setText(os.pathsep.join(current))

    def scan(self):
        raw=self.root.text().strip()
        roots=[Path(x) for x in raw.split(os.pathsep) if x.strip()]
        if not roots or not any(x.is_dir() for x in roots):
            QMessageBox.warning(self,"AppImage Manager","Choose at least one valid folder."); return
        self.apps=[]; self.progress.setRange(0,0); self.progress.setFormat("Discovering AppImages…")
        self.worker=ScanWorker([x for x in roots if x.is_dir()],self.rec.isChecked())
        self.worker.found.connect(lambda r:self.apps.append(r))
        self.worker.progress.connect(lambda n,p:self.progress.setFormat(f"Found {n:,} AppImages • {p}"))
        self.worker.done.connect(self.done)
        self.worker.failed.connect(lambda e:QMessageBox.critical(self,"Scan failed",e))
        self.worker.start()

    def stop(self):
        if self.worker and self.worker.isRunning():self.worker.stop()

    def done(self,info):
        self.progress.setRange(0,100);self.progress.setValue(100)
        self.progress.setFormat(f"Ready • {info['count']:,} AppImages • {human(info['bytes'])}")
        self.refresh();self.refresh_duplicates();self.make_report()

    def refresh(self):
        q=self.search.text().lower(); sf=self.status_filter.currentText()
        rows=[]
        for a in self.apps:
            if q and q not in (a["name"]+" "+a["path"]+" "+a["version"]).lower():continue
            if sf=="Executable" and not a["executable"]:continue
            if sf=="Not Executable" and a["executable"]:continue
            rows.append(a)
        s=self.sort.currentText()
        if s=="Size ↓":rows.sort(key=lambda x:x["size"],reverse=True)
        elif s=="Size ↑":rows.sort(key=lambda x:x["size"])
        elif s=="Modified ↓":rows.sort(key=lambda x:x["modified"],reverse=True)
        elif s=="Version":rows.sort(key=lambda x:x["version"])
        else:rows.sort(key=lambda x:(x["app_name"].lower(),x["name"].lower()))
        self.filtered=rows;self.table.setRowCount(len(rows))
        for i,a in enumerate(rows):
            vals=["●" if a["executable"] else "○",a["app_name"],a["version"] or "—",
                  human(a["size"]),"Yes" if a["executable"] else "No",fmt_dt(a["modified"]),a["path"]]
            for j,v in enumerate(vals):self.table.setItem(i,j,QTableWidgetItem(v))
        self.refresh_dashboard()

    def refresh_dashboard(self):
        n=len(self.apps); total=sum(a["size"] for a in self.apps)
        names=Counter(a["app_name"].lower() for a in self.apps)
        dup=sum(1 for v in names.values() if v>1)
        self.cards["apps"].setText(f"{n:,}");self.cards["size"].setText(human(total))
        self.cards["exec"].setText(str(sum(a["executable"] for a in self.apps)))
        self.cards["versions"].setText(str(sum(bool(a["version"]) for a in self.apps)))
        self.cards["folders"].setText(str(len({str(Path(a["path"]).parent) for a in self.apps})))
        self.cards["duplicates"].setText(str(dup))
        self.summary.setPlainText(
            f"Scanned AppImages: {n:,}\n"
            f"Total storage: {human(total)}\n"
            f"Executable: {sum(a['executable'] for a in self.apps):,}\n"
            f"Not executable: {sum(not a['executable'] for a in self.apps):,}\n"
            f"Versioned filenames: {sum(bool(a['version']) for a in self.apps):,}\n"
            f"Duplicate application names: {dup:,}\n\n"
            "The manager inventories AppImages without modifying them."
        )
        self.type_table.setRowCount(2)
        self.type_table.setItem(0,0,QTableWidgetItem("Executable"))
        self.type_table.setItem(0,1,QTableWidgetItem(str(sum(a["executable"] for a in self.apps))))
        self.type_table.setItem(1,0,QTableWidgetItem("Not executable"))
        self.type_table.setItem(1,1,QTableWidgetItem(str(sum(not a["executable"] for a in self.apps))))

    def selected(self):
        row=self.table.currentRow()
        return self.filtered[row] if 0<=row<len(self.filtered) else None

    def launch_selected(self):
        a=self.selected()
        if a:self.set_current(a);self.launch_current()

    def set_current(self,a):
        self.current=a
        p=Path(a["path"])
        self.inspect_title.setText(p.name)
        self.details.setPlainText(
            f"Application: {a['app_name']}\nFilename: {a['name']}\n"
            f"Version guess: {a['version'] or 'Not detected'}\n"
            f"Path: {a['path']}\nSize: {human(a['size'])}\n"
            f"Modified: {fmt_dt(a['modified'])}\n"
            f"Executable: {'Yes' if a['executable'] else 'No'}\n"
            f"Permissions: {oct(p.stat().st_mode & 0o777)}\n"
            f"File type: {appimage_type(p)}"
        )
        self.tabs.setCurrentIndex(2)

    def launch_current(self):
        if not self.current:return
        p=Path(self.current["path"])
        if not os.access(p,os.X_OK):
            QMessageBox.warning(self,"Not executable","This AppImage is not marked executable.\nUse “Make Executable” first if you trust the file.")
            return
        try:
            subprocess.Popen([str(p)],cwd=str(p.parent),start_new_session=True)
            self.launcher_log.appendPlainText(f"Launched: {p}")
        except Exception as e:QMessageBox.critical(self,"Launch failed",str(e))

    def open_folder(self):
        if self.current:subprocess.Popen(["xdg-open",str(Path(self.current["path"]).parent)])

    def hash_current(self):
        if not self.current:return
        self.progress.setRange(0,0);self.progress.setFormat("Calculating SHA-256…")
        try:
            h=sha256(self.current["path"])
            self.details.append(f"\nSHA-256:\n{h}")
            self.progress.setRange(0,100);self.progress.setValue(100);self.progress.setFormat("SHA-256 complete")
        except Exception as e:QMessageBox.critical(self,"Hash failed",str(e))

    def make_executable(self):
        if not self.current:return
        p=Path(self.current["path"])
        try:
            mode=p.stat().st_mode
            p.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            self.current["executable"]=True
            self.refresh();self.set_current(self.current)
            QMessageBox.information(self,"Executable bit set",f"Made executable:\n{p}")
        except Exception as e:QMessageBox.critical(self,"Permission change failed",str(e))

    def refresh_duplicates(self):
        groups={}
        for a in self.apps:groups.setdefault(a["app_name"].lower(),[]).append(a)
        groups={k:v for k,v in groups.items() if len(v)>1}
        self.dup.setRowCount(len(groups))
        for i,(k,items) in enumerate(sorted(groups.items())):
            self.dup.setItem(i,0,QTableWidgetItem(items[0]["app_name"]))
            self.dup.setItem(i,1,QTableWidgetItem(str(len(items))))
            self.dup.setItem(i,2,QTableWidgetItem(human(sum(x["size"] for x in items))))
            self.dup.setItem(i,3,QTableWidgetItem("\n".join(x["path"] for x in items)))

    def menu(self,pos):
        row=self.table.rowAt(pos.y())
        if row<0:return
        a=self.filtered[row];self.set_current(a)
        m=QMenu(self);op=m.addAction("🚀 Launch");ins=m.addAction("🔍 Inspect")
        cp=m.addAction("📋 Copy Path");fo=m.addAction("📂 Open Folder")
        m.addSeparator();ex=m.addAction("🔑 Make Executable")
        act=m.exec(self.table.viewport().mapToGlobal(pos))
        if act==op:self.launch_current()
        elif act==ins:self.tabs.setCurrentIndex(2)
        elif act==cp:QApplication.clipboard().setText(a["path"])
        elif act==fo:self.open_folder()
        elif act==ex:self.make_executable()

    def create_launcher(self):
        if not self.current:
            QMessageBox.warning(self,"Desktop Integration","Select an AppImage first.");return
        p=Path(self.current["path"])
        name=self.launcher_name.text().strip() or self.current["app_name"]
        safe=re.sub(r"[^A-Za-z0-9._-]+","-",name).strip("-") or "AppImage"
        target=Path.home()/".local/share/applications"/f"{safe}.desktop"
        target.parent.mkdir(parents=True,exist_ok=True)
        content=f"""[Desktop Entry]
Type=Application
Name={name}
Exec={p}
Path={p.parent}
Terminal=false
Categories=Utility;
"""
        try:
            target.write_text(content,encoding="utf-8")
            os.chmod(target,0o644)
            self.launcher_log.appendPlainText(f"Created: {target}")
            QMessageBox.information(self,"Launcher created",str(target))
        except Exception as e:QMessageBox.critical(self,"Launcher failed",str(e))

    def make_report(self):
        lines=["JASS APPIMAGE MANAGER REPORT","="*70,
               f"Generated: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
               f"AppImages: {len(self.apps):,}",
               f"Total size: {human(sum(a['size'] for a in self.apps))}","",
               "INVENTORY"]
        for a in sorted(self.apps,key=lambda x:x["app_name"].lower()):
            lines.append(f"{a['app_name']} | {a['version'] or '—'} | {human(a['size'])} | {'X' if a['executable'] else '-'} | {a['path']}")
        self.report.setPlainText("\n".join(lines))

    def report_text(self):
        self.make_report();self.tabs.setCurrentIndex(5)

    def export_json(self):
        if not self.apps:return
        p,_=QFileDialog.getSaveFileName(self,"Export JSON","appimage_inventory.json","JSON (*.json)")
        if not p:return
        Path(p).write_text(json.dumps({"application":APP_NAME,"version":VERSION,
            "generated":datetime.datetime.now().isoformat(),"apps":self.apps},indent=2),encoding="utf-8")
        QMessageBox.information(self,"Exported",p)

    def export_csv(self):
        if not self.apps:return
        p,_=QFileDialog.getSaveFileName(self,"Export CSV","appimage_inventory.csv","CSV (*.csv)")
        if not p:return
        with open(p,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f);w.writerow(["application","filename","version","size","executable","modified","path"])
            for a in self.apps:w.writerow([a["app_name"],a["name"],a["version"],a["size"],a["executable"],fmt_dt(a["modified"]),a["path"]])
        QMessageBox.information(self,"Exported",p)

def main():
    app=QApplication(sys.argv);app.setApplicationName(APP_NAME)
    w=MainWindow();w.show();sys.exit(app.exec())

if __name__=="__main__":main()
