#!/usr/bin/env python3
"""JASS Media Laboratory v1.0 — local-first media inspector."""

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QPixmap, QImageReader, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget
)

APP_NAME = "JASS Media Laboratory"
VERSION = "1.0"

IMAGE_EXTS = {".jpg",".jpeg",".png",".bmp",".gif",".webp",".tif",".tiff",".ico",".svg"}
VIDEO_EXTS = {".mp4",".mkv",".avi",".mov",".webm",".m4v",".mpeg",".mpg",".ts",".mts",".m2ts",".3gp",".flv"}
AUDIO_EXTS = {".mp3",".wav",".flac",".ogg",".oga",".opus",".m4a",".aac",".wma",".aiff",".aif"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

def human_size(n):
    units = ["B","KB","MB","GB","TB"]
    n = float(n)
    for u in units:
        if n < 1024 or u == units[-1]:
            return f"{int(n)} B" if u == "B" else f"{n:.1f} {u}"
        n /= 1024

def fmt_duration(seconds):
    try:
        s = float(seconds)
    except Exception:
        return "-"
    total = int(s)
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def probe_available():
    return shutil.which("ffprobe") is not None

def ffprobe_json(path):
    if not probe_available():
        return None
    try:
        p = subprocess.run(
            ["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(path)],
            capture_output=True, text=True, timeout=30
        )
        return json.loads(p.stdout) if p.returncode == 0 else None
    except Exception:
        return None

def classify(path):
    e = path.suffix.lower()
    if e in IMAGE_EXTS: return "Image"
    if e in VIDEO_EXTS: return "Video"
    if e in AUDIO_EXTS: return "Audio"
    return "Other"

def collect_media(root, recursive=True):
    root = Path(root)
    if root.is_file():
        return [root] if root.suffix.lower() in MEDIA_EXTS else []
    iterator = root.rglob("*") if recursive else root.iterdir()
    return sorted(
        (p for p in iterator if p.is_file() and p.suffix.lower() in MEDIA_EXTS),
        key=lambda p: str(p).lower()
    )

def basic_record(path):
    st = path.stat()
    typ = classify(path)
    r = {
        "name": path.name, "path": str(path.resolve()), "type": typ,
        "extension": path.suffix.lower(), "size_bytes": st.st_size,
        "size": human_size(st.st_size),
        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds"),
        "created": datetime.fromtimestamp(st.st_ctime).isoformat(sep=" ", timespec="seconds"),
        "duration": "-", "width": None, "height": None,
        "video_codec": "-", "audio_codec": "-", "codec": "-",
        "container": "-", "bit_rate": "-", "fps": "-",
        "sample_rate": "-", "channels": "-", "metadata": {}, "error": ""
    }

    if typ == "Image":
        reader = QImageReader(str(path))
        size = reader.size()
        r["width"] = size.width() if size.isValid() else None
        r["height"] = size.height() if size.isValid() else None
        r["container"] = bytes(reader.format()).decode(errors="replace").upper() if reader.format() else path.suffix[1:].upper()

    data = ffprobe_json(path) if typ in ("Audio","Video") else None
    if data:
        fmt = data.get("format", {})
        r["container"] = fmt.get("format_name", "-")
        if fmt.get("duration"): r["duration"] = fmt_duration(fmt["duration"])
        if fmt.get("bit_rate"):
            try: r["bit_rate"] = f"{int(float(fmt['bit_rate']))/1000:.0f} kb/s"
            except Exception: r["bit_rate"] = str(fmt["bit_rate"])
        r["metadata"] = {str(k): str(v) for k,v in (fmt.get("tags") or {}).items()}
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                r["width"], r["height"] = s.get("width"), s.get("height")
                r["video_codec"] = s.get("codec_name","-")
                rate = s.get("r_frame_rate")
                if rate and rate != "0/0":
                    try:
                        a,b = rate.split("/")
                        r["fps"] = f"{float(a)/float(b):.2f}".rstrip("0").rstrip(".")
                    except Exception: r["fps"] = rate
            elif s.get("codec_type") == "audio":
                r["audio_codec"] = s.get("codec_name","-")
                r["codec"] = s.get("codec_name","-")
                if s.get("sample_rate"): r["sample_rate"] = f"{s['sample_rate']} Hz"
                if s.get("channels"): r["channels"] = str(s["channels"])
    elif typ in ("Audio","Video"):
        r["error"] = "ffprobe not installed; install FFmpeg for audio/video metadata."
    return r

class ScanWorker(QThread):
    progress = Signal(int,int,str)
    record = Signal(object)
    done = Signal(int,int)

    def __init__(self, root, recursive):
        super().__init__()
        self.root, self.recursive, self.stop_requested = root, recursive, False

    def stop(self):
        self.stop_requested = True

    def run(self):
        files = collect_media(self.root, self.recursive)
        errors = 0
        for i,p in enumerate(files,1):
            if self.stop_requested: break
            try:
                r = basic_record(p)
                errors += bool(r.get("error"))
            except Exception as e:
                errors += 1
                r = {"name":p.name,"path":str(p),"type":classify(p),"extension":p.suffix.lower(),
                     "size_bytes":0,"size":"-","modified":"-","created":"-","error":str(e)}
            self.record.emit(r)
            self.progress.emit(i,len(files),p.name)
        self.done.emit(len(self.parent().records) if False else min(i if files else 0,len(files)), errors)

class HashWorker(QThread):
    done = Signal(str,str)
    error = Signal(str)
    def __init__(self,path):
        super().__init__(); self.path=path
    def run(self):
        try: self.done.emit(self.path,file_hash(self.path))
        except Exception as e: self.error.emit(str(e))

class MetadataDialog(QDialog):
    def __init__(self,r,parent=None):
        super().__init__(parent)
        self.setWindowTitle("Media Details — " + r.get("name",""))
        self.resize(720,560)
        lay=QVBoxLayout(self)
        table=QTableWidget(0,2)
        table.setHorizontalHeaderLabels(["Property","Value"])
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        dims=f"{r.get('width')} × {r.get('height')}" if r.get("width") and r.get("height") else "-"
        vals=[
            ("Name",r.get("name")),("Path",r.get("path")),("Type",r.get("type")),
            ("Extension",r.get("extension")),("Size",r.get("size")),
            ("Modified",r.get("modified")),("Created",r.get("created")),
            ("Dimensions",dims),("Duration",r.get("duration")),
            ("Container",r.get("container")),("Video codec",r.get("video_codec")),
            ("Audio codec",r.get("audio_codec")),("Bit rate",r.get("bit_rate")),
            ("Frame rate",r.get("fps")),("Sample rate",r.get("sample_rate")),
            ("Channels",r.get("channels")),("SHA-256",r.get("sha256","-"))
        ]
        for k,v in vals:
            row=table.rowCount(); table.insertRow(row)
            table.setItem(row,0,QTableWidgetItem(str(k)))
            table.setItem(row,1,QTableWidgetItem(str(v if v not in (None,"") else "-")))
        lay.addWidget(table)
        if r.get("metadata"):
            lay.addWidget(QLabel("Container metadata"))
            meta=QTextEdit(); meta.setReadOnly(True)
            meta.setPlainText(json.dumps(r["metadata"],indent=2,ensure_ascii=False))
            lay.addWidget(meta)
        b=QPushButton("Close"); b.clicked.connect(self.accept); lay.addWidget(b)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1450,850)
        self.records=[]; self.filtered=[]; self.worker=None; self.hash_worker=None; self.current=None
        self.build_ui()
        self.statusBar().showMessage("Ready — analysis is read-only.")
        self.probe_label.setText(
            "● ffprobe available — rich audio/video metadata enabled"
            if probe_available() else
            "● ffprobe not found — install FFmpeg for rich audio/video metadata"
        )

    def build_ui(self):
        c=QWidget(); root=QVBoxLayout(c); self.setCentralWidget(c)
        top=QHBoxLayout()
        self.path_edit=QLineEdit(); self.path_edit.setPlaceholderText("Choose a media folder or file…")
        b=QPushButton("Browse…"); b.clicked.connect(self.choose_path)
        scan=QPushButton("Scan Media"); scan.clicked.connect(self.start_scan)
        self.stop_btn=QPushButton("Stop"); self.stop_btn.setEnabled(False); self.stop_btn.clicked.connect(self.stop_scan)
        self.recursive=QCheckBox("Recursive"); self.recursive.setChecked(True)
        top.addWidget(QLabel("Source:")); top.addWidget(self.path_edit,1); top.addWidget(b)
        top.addWidget(self.recursive); top.addWidget(scan); top.addWidget(self.stop_btn); root.addLayout(top)

        info=QHBoxLayout(); self.probe_label=QLabel(); self.summary_label=QLabel("No media scanned")
        info.addWidget(self.probe_label); info.addStretch(); info.addWidget(self.summary_label); root.addLayout(info)

        split=QSplitter(Qt.Horizontal); root.addWidget(split,1)
        left=QWidget(); lv=QVBoxLayout(left)
        filters=QGroupBox("Filters"); fg=QGridLayout(filters)
        self.search=QLineEdit(); self.search.setPlaceholderText("Search filename or path…"); self.search.textChanged.connect(self.apply_filter)
        self.type_combo=QComboBox(); self.type_combo.addItems(["All types","Image","Video","Audio"]); self.type_combo.currentTextChanged.connect(self.apply_filter)
        self.sort_combo=QComboBox(); self.sort_combo.addItems(["Name","Size (largest)","Modified (newest)","Type"]); self.sort_combo.currentTextChanged.connect(self.apply_filter)
        fg.addWidget(QLabel("Search"),0,0); fg.addWidget(self.search,0,1)
        fg.addWidget(QLabel("Type"),1,0); fg.addWidget(self.type_combo,1,1)
        fg.addWidget(QLabel("Sort"),2,0); fg.addWidget(self.sort_combo,2,1); lv.addWidget(filters)

        self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(["Name","Type","Size","Dimensions","Duration","Codec","Modified","Path"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setAlternatingRowColors(True)
        for col in range(7): self.table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7,QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.selection_changed); self.table.cellDoubleClicked.connect(lambda *_: self.show_details())
        lv.addWidget(self.table,1)

        actions=QHBoxLayout()
        for text,slot in [("Details",self.show_details),("Open",self.open_selected),("Open Folder",self.open_folder),("SHA-256",self.calculate_hash),("Export Report…",self.export_report)]:
            x=QPushButton(text); x.clicked.connect(slot); actions.addWidget(x)
        actions.insertStretch(5); lv.addLayout(actions); split.addWidget(left)

        right=QWidget(); rv=QVBoxLayout(right)
        box=QGroupBox("Preview"); pv=QVBoxLayout(box)
        self.preview=QLabel("Select an image to preview.\n\nAudio and video are inspected without playback.")
        self.preview.setAlignment(Qt.AlignCenter); self.preview.setWordWrap(True); self.preview.setMinimumSize(360,300)
        pv.addWidget(self.preview,1); rv.addWidget(box,1)
        mb=QGroupBox("Quick Metadata"); mg=QFormLayout(mb); self.quick={}
        for key,label in [("name","Name"),("type","Type"),("size","Size"),("dimensions","Dimensions"),("duration","Duration"),
                          ("codec","Codec"),("container","Container"),("bit_rate","Bit rate"),("fps","Frame rate"),
                          ("sample_rate","Sample rate"),("channels","Channels")]:
            w=QLabel("-"); w.setTextInteractionFlags(Qt.TextSelectableByMouse); self.quick[key]=w; mg.addRow(label+":",w)
        rv.addWidget(mb); split.addWidget(right); split.setSizes([950,450])
        self.progress=QProgressBar(); self.progress.setVisible(False); self.statusBar().addPermanentWidget(self.progress,1)

    def choose_path(self):
        p=QFileDialog.getExistingDirectory(self,"Choose Media Folder")
        if p: self.path_edit.setText(p)

    def start_scan(self):
        p=self.path_edit.text().strip()
        if not p or not Path(p).exists():
            QMessageBox.warning(self,"Invalid source","Choose an existing folder.")
            return
        if self.worker and self.worker.isRunning(): return
        self.records=[]; self.table.setRowCount(0); self.clear_selection()
        self.progress.setVisible(True); self.progress.setValue(0); self.stop_btn.setEnabled(True)
        self.worker=ScanWorker(p,self.recursive.isChecked())
        self.worker.progress.connect(lambda i,total,name: self.scan_progress(i,total,name))
        self.worker.record.connect(lambda r: (self.records.append(r),self.apply_filter()))
        self.worker.done.connect(self.scan_finished); self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning(): self.worker.stop()

    def scan_progress(self,i,total,name):
        self.progress.setMaximum(max(total,1)); self.progress.setValue(i)
        self.statusBar().showMessage(f"Scanning {i}/{total}: {name}")

    def scan_finished(self,count,errors):
        self.progress.setVisible(False); self.stop_btn.setEnabled(False)
        imgs=sum(r.get("type")=="Image" for r in self.records); vids=sum(r.get("type")=="Video" for r in self.records); aud=sum(r.get("type")=="Audio" for r in self.records)
        total=sum(r.get("size_bytes",0) for r in self.records)
        self.summary_label.setText(f"{len(self.records)} files • {imgs} images • {vids} videos • {aud} audio • {human_size(total)}")
        self.statusBar().showMessage(f"Scan complete: {len(self.records)} media files; {errors} warnings.")

    def apply_filter(self):
        q=self.search.text().lower().strip(); typ=self.type_combo.currentText()
        arr=[r for r in self.records if (not q or q in r.get("name","").lower() or q in r.get("path","").lower()) and (typ=="All types" or r.get("type")==typ)]
        s=self.sort_combo.currentText()
        if s=="Size (largest)": arr.sort(key=lambda r:r.get("size_bytes",0),reverse=True)
        elif s=="Modified (newest)": arr.sort(key=lambda r:r.get("modified",""),reverse=True)
        elif s=="Type": arr.sort(key=lambda r:(r.get("type",""),r.get("name","").lower()))
        else: arr.sort(key=lambda r:r.get("name","").lower())
        self.filtered=arr; self.table.setRowCount(len(arr))
        for row,r in enumerate(arr):
            dims=f"{r.get('width')} × {r.get('height')}" if r.get("width") and r.get("height") else "-"
            codec=r.get("video_codec") if r.get("type")=="Video" else r.get("codec","-")
            vals=[r.get("name",""),r.get("type",""),r.get("size","-"),dims,r.get("duration","-"),codec or "-",r.get("modified","-"),r.get("path","")]
            for col,v in enumerate(vals): self.table.setItem(row,col,QTableWidgetItem(str(v)))

    def selection_changed(self):
        row=self.table.currentRow()
        if 0<=row<len(self.filtered):
            self.current=self.filtered[row]; self.update_details(self.current)

    def clear_selection(self):
        self.current=None; self.preview.setPixmap(QPixmap()); self.preview.setText("Select an image to preview.\n\nAudio and video are inspected without playback.")
        for w in self.quick.values(): w.setText("-")

    def update_details(self,r):
        if r.get("type")=="Image":
            pix=QPixmap(r["path"])
            self.preview.setPixmap(pix.scaled(self.preview.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation) if not pix.isNull() else QPixmap())
            if pix.isNull(): self.preview.setText("Image preview unavailable.")
        elif r.get("type")=="Video":
            self.preview.setPixmap(QPixmap()); self.preview.setText("🎬 VIDEO\n\nSelect Open to launch the default media player.")
        else:
            self.preview.setPixmap(QPixmap()); self.preview.setText("🎵 AUDIO\n\nSelect Open to launch the default media player.")
        self.quick["name"].setText(r.get("name","-")); self.quick["type"].setText(r.get("type","-")); self.quick["size"].setText(r.get("size","-"))
        self.quick["dimensions"].setText(f"{r.get('width')} × {r.get('height')}" if r.get("width") and r.get("height") else "-")
        self.quick["duration"].setText(r.get("duration","-"))
        self.quick["codec"].setText(r.get("video_codec") if r.get("type")=="Video" else r.get("codec","-"))
        self.quick["container"].setText(r.get("container","-")); self.quick["bit_rate"].setText(r.get("bit_rate","-"))
        self.quick["fps"].setText(r.get("fps","-")); self.quick["sample_rate"].setText(r.get("sample_rate","-")); self.quick["channels"].setText(r.get("channels","-"))

    def show_details(self):
        if self.current: MetadataDialog(self.current,self).exec()

    def open_selected(self):
        if self.current: QDesktopServices.openUrl(QUrl.fromLocalFile(self.current["path"]))

    def open_folder(self):
        if self.current: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.current["path"]).parent)))

    def calculate_hash(self):
        if not self.current: return
        if self.hash_worker and self.hash_worker.isRunning(): return
        self.statusBar().showMessage("Calculating SHA-256…")
        self.hash_worker=HashWorker(self.current["path"]); self.hash_worker.done.connect(self.hash_done)
        self.hash_worker.error.connect(lambda e:self.statusBar().showMessage("Hash error: "+e)); self.hash_worker.start()

    def hash_done(self,path,digest):
        for r in self.records:
            if r.get("path")==path: r["sha256"]=digest; self.current=r; break
        self.statusBar().showMessage("SHA-256: "+digest); MetadataDialog(self.current,self).exec()

    def export_report(self):
        if not self.records:
            QMessageBox.information(self,"Export","Scan a media folder first."); return
        p,_=QFileDialog.getSaveFileName(self,"Export Media Report","jass_media_report.csv","CSV (*.csv);;JSON (*.json)")
        if not p: return
        try:
            if p.lower().endswith(".json"):
                Path(p).write_text(json.dumps(self.records,ensure_ascii=False,indent=2),encoding="utf-8")
            else:
                keys=["name","path","type","extension","size_bytes","size","modified","created","duration","width","height","video_codec","audio_codec","container","bit_rate","fps","sample_rate","channels","codec","error","sha256"]
                with open(p,"w",newline="",encoding="utf-8-sig") as f:
                    w=csv.DictWriter(f,fieldnames=keys,extrasaction="ignore"); w.writeheader(); w.writerows(self.records)
            self.statusBar().showMessage("Report exported: "+p)
        except Exception as e: QMessageBox.critical(self,"Export failed",str(e))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.current and self.current.get("type")=="Image":
            pix=QPixmap(self.current["path"])
            if not pix.isNull(): self.preview.setPixmap(pix.scaled(self.preview.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))

def main():
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setStyle("Fusion")
    w=MainWindow(); w.show(); sys.exit(app.exec())

if __name__=="__main__": main()
