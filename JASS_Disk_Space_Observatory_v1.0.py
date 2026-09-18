
#!/usr/bin/env python3
"""
JASS Disk Space Observatory v1.0
A local-first, read-only disk usage analyzer for Linux.

Requires: Python 3.10+, PySide6
No files are deleted, moved, renamed or modified.
"""

import csv, json, os, shutil, subprocess, sys, time
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget, QSpinBox, QTreeWidget, QTreeWidgetItem, QMenu
)

APP = "JASS Disk Space Observatory"
VERSION = "1.0"

def human(n):
    n=float(n); units=["B","KB","MB","GB","TB","PB"]
    for u in units:
        if n < 1024 or u == units[-1]:
            return f"{int(n)} B" if u=="B" else f"{n:.1f} {u}"
        n/=1024

def pct(a,b):
    return 0 if not b else a*100/b

def fmt_time(ts):
    try: return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception: return "-"

def mount_info():
    rows=[]
    try:
        p=subprocess.run(["df","-P","-T"],capture_output=True,text=True,timeout=10)
        for line in p.stdout.splitlines()[1:]:
            parts=line.split()
            if len(parts)>=7:
                fs,typ,size,used,avail,use,mnt=parts[:7]
                rows.append((fs,typ,int(size)*1024,int(used)*1024,int(avail)*1024,use,mnt))
    except Exception: pass
    return rows

class ScanWorker(QThread):
    item=Signal(object)
    progress=Signal(str,int)
    finished=Signal(object)

    def __init__(self, root, max_depth=0, include_hidden=True):
        super().__init__(); self.root=Path(root); self.max_depth=max_depth; self.include_hidden=include_hidden; self.stop_requested=False
    def stop(self): self.stop_requested=True
    def run(self):
        started=time.time(); count=0; errors=0; total=0
        try:
            st=self.root.stat()
            total=st.st_size if self.root.is_file() else 0
        except Exception: pass
        # Emit the root itself first.
        if self.root.is_dir():
            self._scan_dir(self.root,0)
        elif self.root.is_file():
            self.item.emit({"path":str(self.root),"name":self.root.name,"type":"file","size":self.root.stat().st_size,
                            "mtime":self.root.stat().st_mtime,"depth":0})
            count=1
        self.finished.emit({"count":count,"errors":errors,"seconds":time.time()-started})
    def _scan_dir(self, path, depth):
        if self.stop_requested: return
        try:
            entries = list(os.scandir(path))
        except Exception:
            self.item.emit({"path":str(path),"name":path.name or str(path),"type":"error","size":0,"mtime":0,"depth":depth})
            return 0
        size=0; files=0; dirs=0
        for e in entries:
            if self.stop_requested: break
            if not self.include_hidden and e.name.startswith("."): continue
            try:
                if e.is_symlink(): continue
                if e.is_dir(follow_symlinks=False):
                    dirs += 1
                    if self.max_depth and depth >= self.max_depth:
                        try:
                            child = 0
                            # At the depth limit, don't descend further.
                        except Exception:
                            child = 0
                    else:
                        child = self._scan_dir(Path(e.path), depth+1)
                    size += child
                elif e.is_file(follow_symlinks=False):
                    s=e.stat().st_size; size+=s; files+=1
                    self.item.emit({"path":e.path,"name":e.name,"type":"file","size":s,"mtime":e.stat().st_mtime,"depth":depth+1})
            except (OSError,PermissionError): pass
        try: mt=path.stat().st_mtime
        except Exception: mt=0
        self.item.emit({"path":str(path),"name":path.name or str(path),"type":"dir","size":size,"mtime":mt,
                        "depth":depth,"files":files,"dirs":dirs})
        return size

class TreemapWidget(QWidget):
    selected=Signal(str)
    def __init__(self):
        super().__init__(); self.setMinimumHeight(300); self.nodes=[]; self.hover=None
    def set_nodes(self,nodes):
        self.nodes=sorted(nodes,key=lambda x:x.get("size",0),reverse=True); self.update()
    def mousePressEvent(self,e):
        if e.button()==Qt.LeftButton and self.nodes:
            w=max(self.width(),1); total=sum(max(n["size"],1) for n in self.nodes)
            x=0
            for n in self.nodes[:30]:
                ww=max(4,int(w*n["size"]/total))
                if x <= e.position().x() < x+ww:
                    self.selected.emit(n["path"]); return
                x+=ww
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),self.palette().base())
        if not self.nodes:
            p.drawText(self.rect(),Qt.AlignCenter,"Scan a folder to build the treemap"); return
        total=sum(max(n["size"],1) for n in self.nodes[:30]); x=0; w=max(self.width(),1); h=self.height()
        colors=[QColor("#4f8cff"),QColor("#6fcf97"),QColor("#f2c94c"),QColor("#bb86fc"),QColor("#56ccf2"),QColor("#f2994a"),QColor("#eb5757")]
        for i,n in enumerate(self.nodes[:30]):
            ww=max(5,int(w*n["size"]/total))
            r=self.rect().adjusted(x+2,2,x+ww-2,-2)
            p.fillRect(r,colors[i%len(colors)])
            p.setPen(Qt.white)
            label=n["name"]+"\n"+human(n["size"])
            p.drawText(r.adjusted(6,6,-6,-6),Qt.AlignLeft|Qt.AlignTop,label)
            x+=ww
            if x>=w: break

class Main(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f"{APP} v{VERSION}"); self.resize(1500,900)
        self.records=[]; self.worker=None; self.current_root=""; self.build()
        self.statusBar().showMessage("Ready — read-only analysis.")
    def build(self):
        central=QWidget(); root=QVBoxLayout(central); self.setCentralWidget(central)
        top=QHBoxLayout()
        self.path=QLineEdit(); self.path.setPlaceholderText("Folder to analyze, e.g. /home/jasvir")
        b=QPushButton("Browse…"); b.clicked.connect(self.browse)
        scan=QPushButton("Analyze Disk"); scan.clicked.connect(self.start)
        self.stop=QPushButton("Stop"); self.stop.setEnabled(False); self.stop.clicked.connect(self.stop_scan)
        self.hidden=QCheckBox("Include hidden"); self.hidden.setChecked(True)
        self.depth=QSpinBox(); self.depth.setRange(0,99); self.depth.setValue(0); self.depth.setToolTip("0 = unlimited")
        top.addWidget(QLabel("Source:")); top.addWidget(self.path,1); top.addWidget(b); top.addWidget(QLabel("Depth:")); top.addWidget(self.depth)
        top.addWidget(self.hidden); top.addWidget(scan); top.addWidget(self.stop); root.addLayout(top)

        self.tabs=QTabWidget(); root.addWidget(self.tabs,1)
        self.dashboard=QWidget(); dv=QVBoxLayout(self.dashboard)
        cards=QGridLayout()
        self.card_total=self.card("Files","0"); self.card_dirs=self.card("Folders","0"); self.card_size=self.card("Analyzed size","0"); self.card_errors=self.card("Warnings","0")
        for i,w in enumerate([self.card_total,self.card_dirs,self.card_size,self.card_errors]): cards.addWidget(w,0,i)
        dv.addLayout(cards)
        self.disk_table=QTableWidget(0,6); self.disk_table.setHorizontalHeaderLabels(["Filesystem","Type","Size","Used","Free","Mount"])
        self.disk_table.horizontalHeader().setSectionResizeMode(5,QHeaderView.Stretch); self.disk_table.setAlternatingRowColors(True)
        dv.addWidget(QLabel("Mounted filesystems")); dv.addWidget(self.disk_table,1)
        self.tabs.addTab(self.dashboard,"Dashboard")

        self.explorer=QWidget(); ev=QVBoxLayout(self.explorer)
        ef=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText("Filter files/folders…"); self.search.textChanged.connect(self.refresh)
        self.kind=QComboBox(); self.kind.addItems(["All","Files","Folders"]); self.kind.currentTextChanged.connect(self.refresh)
        self.sort=QComboBox(); self.sort.addItems(["Largest first","Name","Newest"]); self.sort.currentTextChanged.connect(self.refresh)
        ef.addWidget(self.search,1); ef.addWidget(self.kind); ef.addWidget(self.sort); ev.addLayout(ef)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(["Name","Type","Size","% of scan","Modified","Path"])
        for c in range(5): self.table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.Stretch); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu); self.table.customContextMenuRequested.connect(self.context)
        self.table.itemSelectionChanged.connect(self.select_row); ev.addWidget(self.table,1)
        self.tabs.addTab(self.explorer,"Explorer")

        self.tree_tab=QWidget(); tv=QVBoxLayout(self.tree_tab)
        self.tree=QTreeWidget(); self.tree.setHeaderLabels(["Folder / File","Size","Files","Folders"]); self.tree.header().setSectionResizeMode(0,QHeaderView.Stretch)
        tv.addWidget(self.tree); self.tabs.addTab(self.tree_tab,"Hierarchy")

        self.tm_tab=QWidget(); tm=QVBoxLayout(self.tm_tab)
        self.treemap=TreemapWidget(); self.treemap.selected.connect(self.reveal_path); tm.addWidget(self.treemap,1)
        tm.addWidget(QLabel("Treemap: each rectangle represents a top-level item in the selected scan directory. Click a block to select it in Explorer."))
        self.tabs.addTab(self.tm_tab,"Treemap")

        self.types_tab=QWidget(); ty=QVBoxLayout(self.types_tab)
        self.type_table=QTableWidget(0,4); self.type_table.setHorizontalHeaderLabels(["Extension","Files","Total size","% of analyzed"])
        self.type_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents); self.type_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents); self.type_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents); self.type_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        ty.addWidget(self.type_table); self.tabs.addTab(self.types_tab,"File Types")

        self.largest_tab=QWidget(); lv=QVBoxLayout(self.largest_tab)
        bar=QHBoxLayout(); bar.addWidget(QLabel("Show largest")); self.topn=QComboBox(); self.topn.addItems(["25","50","100","250","500"]); self.topn.currentTextChanged.connect(self.refresh_largest); bar.addWidget(self.topn); bar.addStretch(); lv.addLayout(bar)
        self.largest=QTableWidget(0,4); self.largest.setHorizontalHeaderLabels(["File","Size","Modified","Path"]); self.largest.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch); lv.addWidget(self.largest); self.tabs.addTab(self.largest_tab,"Largest Files")

        self.report_tab=QWidget(); rv=QVBoxLayout(self.report_tab); self.report=QTextEdit(); self.report.setReadOnly(True); rv.addWidget(self.report)
        rb=QHBoxLayout(); ec=QPushButton("Export CSV…"); ec.clicked.connect(self.export_csv); ej=QPushButton("Export JSON…"); ej.clicked.connect(self.export_json)
        rb.addWidget(ec); rb.addWidget(ej); rb.addStretch(); rv.addLayout(rb); self.tabs.addTab(self.report_tab,"Report")

        self.progress=QProgressBar(); self.progress.setVisible(False); self.statusBar().addPermanentWidget(self.progress,1)
        self.populate_mounts()

    def card(self,title,value):
        box=QGroupBox(title); l=QVBoxLayout(box); x=QLabel(value); x.setObjectName("cardValue"); f=QFont(); f.setPointSize(20); f.setBold(True); x.setFont(f); l.addWidget(x); box._value=x; return box

    def setcard(self,box,text): box._value.setText(text)
    def populate_mounts(self):
        rows=mount_info(); self.disk_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for c,v in enumerate([r[0],r[1],human(r[2]),human(r[3]),human(r[4]),r[6]]): self.disk_table.setItem(i,c,QTableWidgetItem(str(v)))

    def browse(self):
        p=QFileDialog.getExistingDirectory(self,"Choose Folder")
        if p: self.path.setText(p)
    def start(self):
        p=self.path.text().strip()
        if not p or not Path(p).is_dir(): QMessageBox.warning(self,"Invalid folder","Choose an existing directory."); return
        if self.worker and self.worker.isRunning(): return
        self.records=[]; self.current_root=p; self.table.setRowCount(0); self.tree.clear(); self.report.clear()
        self.progress.setVisible(True); self.progress.setRange(0,0); self.stop.setEnabled(True)
        self.statusBar().showMessage("Analyzing…")
        self.worker=ScanWorker(p,self.depth.value(),self.hidden.isChecked())
        self.worker.item.connect(self.receive); self.worker.finished.connect(self.done); self.worker.start()
    def stop_scan(self):
        if self.worker: self.worker.stop(); self.statusBar().showMessage("Stopping…")
    def receive(self,r):
        if r.get("type") in ("file","dir"): self.records.append(r)
    def done(self,info):
        self.progress.setVisible(False); self.stop.setEnabled(False); self.refresh(); self.refresh_largest()
        files=[r for r in self.records if r["type"]=="file"]; dirs=[r for r in self.records if r["type"]=="dir"]
        total=sum(r["size"] for r in files); self.setcard(self.card_total,str(len(files))); self.setcard(self.card_dirs,str(len(dirs))); self.setcard(self.card_size,human(total))
        self.setcard(self.card_errors,str(info.get("errors",0))); self.build_hierarchy(); self.build_types(); self.build_treemap(); self.build_report()
        self.statusBar().showMessage(f"Analysis complete: {len(files)} files, {len(dirs)} folders, {human(total)}.")
    def refresh(self):
        q=self.search.text().lower().strip(); kind=self.kind.currentText()
        arr=[]
        for r in self.records:
            if q and q not in r["name"].lower() and q not in r["path"].lower(): continue
            if kind=="Files" and r["type"]!="file": continue
            if kind=="Folders" and r["type"]!="dir": continue
            arr.append(r)
        s=self.sort.currentText()
        if s=="Largest first": arr.sort(key=lambda x:x["size"],reverse=True)
        elif s=="Newest": arr.sort(key=lambda x:x["mtime"],reverse=True)
        else: arr.sort(key=lambda x:x["path"].lower())
        total=sum(r["size"] for r in self.records if r["type"]=="file") or 1
        self.table.setRowCount(len(arr))
        for i,r in enumerate(arr):
            vals=[r["name"],"Folder" if r["type"]=="dir" else "File",human(r["size"]),f"{pct(r['size'],total):.2f}%",fmt_time(r["mtime"]),r["path"]]
            for c,v in enumerate(vals): self.table.setItem(i,c,QTableWidgetItem(str(v)))
    def refresh_largest(self):
        files=sorted([r for r in self.records if r["type"]=="file"],key=lambda x:x["size"],reverse=True)[:int(self.topn.currentText())]
        self.largest.setRowCount(len(files))
        for i,r in enumerate(files):
            for c,v in enumerate([r["name"],human(r["size"]),fmt_time(r["mtime"]),r["path"]]): self.largest.setItem(i,c,QTableWidgetItem(str(v)))
    def build_hierarchy(self):
        self.tree.clear()
        root=QTreeWidgetItem([self.current_root,"","",""]); self.tree.addTopLevelItem(root)
        dirs=sorted([r for r in self.records if r["type"]=="dir"],key=lambda x:x["path"].count(os.sep))
        nodes={self.current_root:root}
        for r in dirs:
            parent=str(Path(r["path"]).parent); par=nodes.get(parent,root)
            n=QTreeWidgetItem([r["name"],human(r["size"]),str(r.get("files",0)),str(r.get("dirs",0))]); par.addChild(n); nodes[r["path"]]=n
        root.setExpanded(True)
    def build_types(self):
        d={}
        for r in self.records:
            if r["type"]!="file": continue
            e=Path(r["name"]).suffix.lower() or "[no extension]"
            x=d.setdefault(e,[0,0]); x[0]+=1; x[1]+=r["size"]
        total=sum(v[1] for v in d.values()) or 1
        arr=sorted(d.items(),key=lambda x:x[1][1],reverse=True); self.type_table.setRowCount(len(arr))
        for i,(e,(n,s)) in enumerate(arr):
            for c,v in enumerate([e,n,human(s),f"{pct(s,total):.2f}%"]): self.type_table.setItem(i,c,QTableWidgetItem(str(v)))
    def build_treemap(self):
        root=Path(self.current_root); nodes=[]
        for p in root.iterdir():
            if not self.hidden.isChecked() and p.name.startswith("."): continue
            matches=[r for r in self.records if r["path"]==str(p)]
            if matches: nodes.append(matches[0])
        self.treemap.set_nodes(nodes)
    def build_report(self):
        files=[r for r in self.records if r["type"]=="file"]; dirs=[r for r in self.records if r["type"]=="dir"]; total=sum(r["size"] for r in files)
        lines=[f"{APP} v{VERSION}", "="*60, f"Scan root: {self.current_root}",f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}","",f"Files: {len(files):,}",f"Folders: {len(dirs):,}",f"Analyzed size: {human(total)}","", "Largest files:"]
        for r in sorted(files,key=lambda x:x["size"],reverse=True)[:20]: lines.append(f"  {human(r['size']):>12}  {r['path']}")
        self.report.setPlainText("\n".join(lines))
    def select_row(self):
        row=self.table.currentRow()
        if row>=0: self.statusBar().showMessage(self.table.item(row,5).text())
    def context(self,pos):
        row=self.table.rowAt(pos.y())
        if row<0:return
        path=self.table.item(row,5).text(); m=QMenu(self); copy=m.addAction("Copy path"); opena=m.addAction("Open in File Manager"); a=m.exec(self.table.viewport().mapToGlobal(pos))
        if a==copy: QApplication.clipboard().setText(path)
        elif a==opena: subprocess.Popen(["xdg-open",str(Path(path).parent if Path(path).is_file() else Path(path))])
    def reveal_path(self,path):
        self.search.setText(Path(path).name); self.tabs.setCurrentWidget(self.explorer)
        for i in range(self.table.rowCount()):
            if self.table.item(i,5).text()==path: self.table.selectRow(i); self.table.scrollToItem(self.table.item(i,0)); break
    def export_csv(self):
        p,_=QFileDialog.getSaveFileName(self,"Export CSV","jass_disk_report.csv","CSV (*.csv)")
        if p:
            with open(p,"w",newline="",encoding="utf-8-sig") as f:
                w=csv.DictWriter(f,fieldnames=["name","path","type","size","modified","depth"],extrasaction="ignore"); w.writeheader(); w.writerows(self.records)
    def export_json(self):
        p,_=QFileDialog.getSaveFileName(self,"Export JSON","jass_disk_report.json","JSON (*.json)")
        if p: Path(p).write_text(json.dumps(self.records,indent=2,ensure_ascii=False),encoding="utf-8")

def main():
    app=QApplication(sys.argv); app.setStyle("Fusion")
    w=Main(); w.show(); sys.exit(app.exec())
if __name__=="__main__": main()
