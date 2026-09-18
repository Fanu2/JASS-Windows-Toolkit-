#!/usr/bin/env python3
"""
JASS Literature Explorer v1.0
A beautiful, local-first PySide6 literature library, reader, search and research workspace.

Dependencies:
    Python 3 + PySide6
Optional:
    PyMuPDF (fitz) for PDF text extraction
    ebooklib + BeautifulSoup4 for broader EPUB support (stdlib EPUB support is included)
"""

import sys, os, re, json, csv, html, zipfile, sqlite3, datetime, subprocess
from pathlib import Path
from collections import Counter

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QTextDocument, QFont, QKeySequence, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QTextEdit,
    QPlainTextEdit, QFileDialog, QMessageBox, QProgressBar, QFrame,
    QSplitter, QTreeWidget, QTreeWidgetItem, QMenu, QDialog, QListWidget,
    QListWidgetItem, QAbstractItemView
)

APP_NAME = "JASS Literature Explorer"
VERSION = "1.0"

TEXT_EXTS = {".txt",".md",".rst",".csv",".tsv",".log"}
BOOK_EXTS = {".txt",".md",".epub",".pdf",".html",".htm"}
SKIP_DIRS = {".git",".venv","venv","env","__pycache__","node_modules",
             ".cache","dist","build",".pytest_cache",".mypy_cache"}

def human(n):
    n = float(n)
    for u in ("B","KB","MB","GB","TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"

def safe_text(path, limit=2000000):
    try:
        data = Path(path).read_bytes()[:limit]
        if b"\x00" in data[:4096]:
            return None
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None

def normalize(s):
    return re.sub(r"\s+", " ", s or "").strip()

def words(text):
    return re.findall(r"\b[\w’'-]+\b", text or "", flags=re.UNICODE)

def extract_epub(path):
    """Lightweight EPUB reader using only Python stdlib."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        container = z.read("META-INF/container.xml").decode("utf-8", "replace")
        m = re.search(r'full-path="([^"]+)"', container)
        if not m:
            raise ValueError("EPUB content.opf could not be located.")
        opf_name = m.group(1)
        opf_dir = Path(opf_name).parent
        opf = z.read(opf_name).decode("utf-8", "replace")
        manifest = {}
        for x in re.finditer(r'<item\b[^>]*id="([^"]+)"[^>]*href="([^"]+)"[^>]*media-type="([^"]+)"', opf):
            manifest[x.group(1)] = (x.group(2), x.group(3))
        spine = []
        for x in re.finditer(r'<itemref\b[^>]*idref="([^"]+)"', opf):
            if x.group(1) in manifest:
                spine.append(manifest[x.group(1)][0])
        metadata = {}
        for tag in ("title","creator","language","publisher","date"):
            m = re.search(rf'<(?:dc:)?{tag}\b[^>]*>(.*?)</(?:dc:)?{tag}>', opf, re.I|re.S)
            if m:
                metadata[tag] = normalize(html.unescape(re.sub("<[^>]+>"," ",m.group(1))))
        chapters=[]
        for href in spine:
            full = str((opf_dir / href).as_posix())
            full = str(Path(full))
            if full not in names:
                full = href
            try:
                raw=z.read(full).decode("utf-8","replace")
                raw=re.sub(r"<script\b.*?</script>"," ",raw,flags=re.I|re.S)
                raw=re.sub(r"<style\b.*?</style>"," ",raw,flags=re.I|re.S)
                txt=html.unescape(re.sub(r"<[^>]+>"," ",raw))
                txt=normalize(txt)
                if txt:
                    chapters.append((Path(href).stem,txt))
            except Exception:
                pass
        return metadata, chapters

def extract_pdf(path):
    try:
        import fitz
        doc=fitz.open(path)
        txt="\n\n".join(page.get_text() for page in doc)
        return txt, len(doc)
    except ImportError:
        return None, 0
    except Exception:
        return None, 0

class LibraryWorker(QThread):
    found = Signal(dict)
    progress = Signal(int, str)
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, root, recursive=True, skip=True):
        super().__init__()
        self.root=Path(root)
        self.recursive=recursive
        self.skip=skip
        self.stop_requested=False

    def stop(self):
        self.stop_requested=True

    def run(self):
        start=datetime.datetime.now()
        count=0; total_bytes=0; errors=0
        try:
            iterator=os.walk(self.root) if self.recursive else [(str(self.root),[],os.listdir(self.root))]
            for base, dirs, files in iterator:
                if self.stop_requested: break
                if self.skip:
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for fn in files:
                    if self.stop_requested: break
                    p=Path(base)/fn
                    if p.suffix.lower() not in BOOK_EXTS: continue
                    try:
                        st=p.stat()
                        r={"name":p.name,"path":str(p),"ext":p.suffix.lower(),
                           "size":st.st_size,"modified":st.st_mtime}
                        self.found.emit(r)
                        count+=1; total_bytes+=st.st_size
                    except Exception:
                        errors+=1
                self.progress.emit(count,str(base))
            self.done.emit({"books":count,"bytes":total_bytes,"errors":errors,
                            "duration":(datetime.datetime.now()-start).total_seconds(),
                            "stopped":self.stop_requested})
        except Exception as e:
            self.failed.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1500,920)
        self.library_root=None
        self.books=[]
        self.filtered=[]
        self.current=None
        self.favorites=set()
        self.recent=[]
        self.notes={}
        self._build()
        self._style()

    def _build(self):
        c=QWidget(); self.setCentralWidget(c)
        main=QVBoxLayout(c); main.setContentsMargins(14,14,14,14); main.setSpacing(10)

        hero=QFrame(); hero.setObjectName("hero")
        hl=QVBoxLayout(hero)
        t=QLabel("📖  JASS Literature Explorer"); t.setObjectName("title")
        s=QLabel("Build a private literature library, explore books locally, search passages, and keep research notes.")
        s.setObjectName("subtitle")
        hl.addWidget(t); hl.addWidget(s)
        controls=QHBoxLayout()
        self.path=QLineEdit(); self.path.setPlaceholderText("Choose your literature folder…")
        b=QPushButton("📂 Library"); b.clicked.connect(self.choose_library)
        scan=QPushButton("🔎 Scan Library"); scan.setObjectName("primary"); scan.clicked.connect(self.scan)
        stop=QPushButton("⏹ Stop"); stop.clicked.connect(self.stop)
        self.rec=QCheckBox("Recursive"); self.rec.setChecked(True)
        self.skip=QCheckBox("Skip technical folders"); self.skip.setChecked(True)
        controls.addWidget(self.path,1); controls.addWidget(b); controls.addWidget(self.rec)
        controls.addWidget(self.skip); controls.addWidget(scan); controls.addWidget(stop)
        hl.addLayout(controls); main.addWidget(hero)

        self.progress=QProgressBar(); self.progress.setTextVisible(True); self.progress.setFormat("Ready")
        main.addWidget(self.progress)

        self.tabs=QTabWidget(); main.addWidget(self.tabs,1)
        self.dashboard(); self.library_tab(); self.reader_tab(); self.search_tab()
        self.notes_tab(); self.collections_tab(); self.metadata_tab(); self.reports_tab()

        st=QLabel("Local-first • Read-only library scanning • Your books stay on your computer")
        st.setObjectName("status"); main.addWidget(st)

    def card(self,title):
        f=QFrame(); f.setObjectName("card"); l=QVBoxLayout(f)
        a=QLabel(title); a.setObjectName("cardTitle")
        v=QLabel("—"); v.setObjectName("cardValue")
        l.addWidget(a); l.addWidget(v); return f,v

    def dashboard(self):
        w=QWidget(); l=QVBoxLayout(w)
        g=QGridLayout(); self.cards={}
        for i,(k,t) in enumerate([("books","Books"),("size","Library Size"),("authors","Authors"),
                                  ("formats","Formats"),("words","Indexed Words"),("favorites","Favorites")]):
            f,v=self.card(t); self.cards[k]=v; g.addWidget(f,i//3,i%3)
        l.addLayout(g)
        self.dash=QTextEdit(); self.dash.setReadOnly(True); l.addWidget(self.dash,1)
        self.tabs.addTab(w,"🏠 Dashboard")

    def library_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        bar=QHBoxLayout()
        self.filter=QLineEdit(); self.filter.setPlaceholderText("Search title, filename, author or path…")
        self.format=QComboBox(); self.format.addItems(["All formats",".epub",".pdf",".txt",".md",".html"])
        self.onlyfav=QCheckBox("★ Favorites")
        self.filter.textChanged.connect(self.refresh_library)
        self.format.currentTextChanged.connect(self.refresh_library)
        self.onlyfav.stateChanged.connect(self.refresh_library)
        bar.addWidget(self.filter,1); bar.addWidget(self.format); bar.addWidget(self.onlyfav)
        l.addLayout(bar)
        self.libtable=QTableWidget(0,6)
        self.libtable.setHorizontalHeaderLabels(["★","Title / File","Format","Size","Modified","Path"])
        self.libtable.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.libtable.horizontalHeader().setSectionResizeMode(5,QHeaderView.Stretch)
        self.libtable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.libtable.doubleClicked.connect(self.open_selected)
        self.libtable.setContextMenuPolicy(Qt.CustomContextMenu)
        self.libtable.customContextMenuRequested.connect(self.library_menu)
        l.addWidget(self.libtable)
        self.tabs.addTab(w,"📚 Library")

    def reader_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        top=QHBoxLayout()
        self.reader_title=QLabel("No book selected"); self.reader_title.setObjectName("section")
        self.fontsize=QSpinBox(); self.fontsize.setRange(8,40); self.fontsize.setValue(15)
        self.fontsize.valueChanged.connect(lambda n:self.reader.setFont(QFont("Serif",n)))
        top.addWidget(self.reader_title,1); top.addWidget(QLabel("Font")); top.addWidget(self.fontsize)
        b=QPushButton("★ Favorite"); b.clicked.connect(self.toggle_current_favorite); top.addWidget(b)
        l.addLayout(top)
        self.reader=QTextEdit(); self.reader.setReadOnly(True); self.reader.setFont(QFont("Serif",15))
        l.addWidget(self.reader,1)
        self.tabs.addTab(w,"📖 Reader")

    def search_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        bar=QHBoxLayout()
        self.q=QLineEdit(); self.q.setPlaceholderText("Search inside indexed books…")
        self.scope=QComboBox(); self.scope.addItems(["All readable books","Current book"])
        b=QPushButton("🔍 Search"); b.clicked.connect(self.search_text)
        bar.addWidget(self.q,1); bar.addWidget(self.scope); bar.addWidget(b); l.addLayout(bar)
        self.results=QTableWidget(0,4)
        self.results.setHorizontalHeaderLabels(["Book","Match","Context","Path"])
        self.results.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)
        self.results.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        self.results.doubleClicked.connect(self.open_search_result)
        l.addWidget(self.results,1)
        self.tabs.addTab(w,"🔎 Full-Text Search")

    def notes_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.note_book=QLabel("Select a book to attach research notes.")
        l.addWidget(self.note_book)
        self.notes=QPlainTextEdit(); self.notes.setPlaceholderText("Write your notes, quotations, themes, observations or research questions…")
        l.addWidget(self.notes,1)
        b=QPushButton("💾 Save Local Note"); b.clicked.connect(self.save_note)
        l.addWidget(b)
        self.tabs.addTab(w,"📝 Research Notes")

    def collections_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.collections=QListWidget()
        for x in ["Romance","Poetry","Classics","Philosophy","History","Punjabi","Shahmukhi","Mizo","Hindi","Research"]:
            self.collections.addItem(x)
        l.addWidget(QLabel("Starter collections (organize your library manually):"))
        l.addWidget(self.collections,1)
        self.tabs.addTab(w,"🗂 Collections")

    def metadata_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.meta=QPlainTextEdit(); self.meta.setReadOnly(True); l.addWidget(self.meta)
        self.tabs.addTab(w,"ℹ️ Book Details")

    def reports_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        row=QHBoxLayout()
        for label,fn in [("💾 JSON",self.export_json),("📄 CSV",self.export_csv),("📑 Report",self.show_report)]:
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
        QLineEdit,QComboBox,QSpinBox,QTextEdit,QPlainTextEdit,QTableWidget,QListWidget{
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

    def choose_library(self):
        p=QFileDialog.getExistingDirectory(self,"Choose Literature Library",str(Path.home()))
        if p:self.path.setText(p)

    def scan(self):
        p=self.path.text().strip()
        if not Path(p).is_dir():
            QMessageBox.warning(self,"Literature Explorer","Choose a valid literature directory."); return
        self.library_root=Path(p); self.books=[]; self.progress.setRange(0,0)
        self.progress.setFormat("Scanning literature…")
        self.worker=LibraryWorker(self.library_root,self.rec.isChecked(),self.skip.isChecked())
        self.worker.found.connect(self.found)
        self.worker.progress.connect(lambda n,x:self.progress.setFormat(f"Found {n:,} books • {x}"))
        self.worker.done.connect(self.done)
        self.worker.failed.connect(lambda e:QMessageBox.critical(self,"Scan failed",e))
        self.worker.start()

    def stop(self):
        if hasattr(self,"worker") and self.worker.isRunning(): self.worker.stop()

    def found(self,r): self.books.append(r)

    def done(self,info):
        self.progress.setRange(0,100); self.progress.setValue(100)
        self.progress.setFormat(f"Library ready • {info['books']:,} books • {human(info['bytes'])}")
        self.refresh_library(); self.refresh_dashboard(); self.build_report()

    def refresh_dashboard(self):
        authors=set(); formats=Counter()
        total_words=0
        for b in self.books:
            formats[b["ext"]]+=1
            stem=Path(b["name"]).stem
            m=re.search(r"\s[-–—]\s(.+)$",stem)
            if m: authors.add(m.group(1))
            if b is self.current: pass
        self.cards["books"].setText(f"{len(self.books):,}")
        self.cards["size"].setText(human(sum(b["size"] for b in self.books)))
        self.cards["authors"].setText(f"{len(authors):,}" if authors else "—")
        self.cards["formats"].setText(str(len(formats)))
        self.cards["words"].setText(f"{total_words:,}")
        self.cards["favorites"].setText(str(len(self.favorites)))
        self.dash.setPlainText(
            f"Library: {self.library_root or '—'}\n\n"
            f"Supported formats: {', '.join(sorted({b['ext'] for b in self.books})) or '—'}\n"
            f"Scan contains {len(self.books):,} recognized literature files.\n\n"
            "TIP\nDouble-click a TXT/MD/HTML/EPUB/PDF item to open it. "
            "PDF reading requires PyMuPDF for text extraction."
        )

    def refresh_library(self):
        q=self.filter.text().lower(); fmt=self.format.currentText()
        rows=[]
        for b in self.books:
            if fmt!="All formats" and b["ext"]!=fmt: continue
            if self.onlyfav.isChecked() and b["path"] not in self.favorites: continue
            if q and q not in (b["name"]+" "+b["path"]).lower(): continue
            rows.append(b)
        rows.sort(key=lambda x:x["name"].lower())
        self.filtered=rows; self.libtable.setRowCount(len(rows))
        for i,b in enumerate(rows):
            vals=["★" if b["path"] in self.favorites else "",Path(b["name"]).stem,b["ext"],human(b["size"]),
                  datetime.datetime.fromtimestamp(b["modified"]).strftime("%Y-%m-%d %H:%M"),b["path"]]
            for j,v in enumerate(vals): self.libtable.setItem(i,j,QTableWidgetItem(v))
        self.refresh_dashboard()

    def selected_book(self):
        row=self.libtable.currentRow()
        if row<0 or row>=len(self.filtered): return None
        return self.filtered[row]

    def open_selected(self):
        b=self.selected_book()
        if b:self.open_book(b)

    def open_book(self,b):
        self.current=b
        p=Path(b["path"]); text=None; details={}
        if b["ext"] in (".txt",".md",".html",".htm"):
            text=safe_text(p)
            if b["ext"] in (".html",".htm") and text:
                text=html.unescape(re.sub("<[^>]+>"," ",text))
        elif b["ext"]==".epub":
            try:
                meta,ch=extract_epub(p)
                text="\n\n".join(t for _,t in ch)
                details={"EPUB metadata":json.dumps(meta,indent=2,ensure_ascii=False),
                         "Chapters":len(ch)}
            except Exception as e:text=f"EPUB error: {e}"
        elif b["ext"]==".pdf":
            text,pages=extract_pdf(p)
            if text is None:
                text="PDF text extraction is unavailable.\nInstall PyMuPDF:\n\npython3 -m pip install PyMuPDF"
            details["PDF pages"]=pages
        if text is None:text="[Unable to read this format as text.]"
        self.reader_title.setText(p.name)
        self.reader.setPlainText(text)
        self.meta.setPlainText(self.make_metadata(b,text,details))
        self.note_book.setText(f"Notes for: {p.name}")
        self.notes.setPlainText(self.notes_map().get(b["path"],""))
        self.tabs.setCurrentIndex(2)
        if b["path"] not in self.recent:self.recent.insert(0,b["path"])

    def make_metadata(self,b,text,details):
        return (
            f"Title: {Path(b['name']).stem}\nFile: {b['name']}\n"
            f"Format: {b['ext']}\nPath: {b['path']}\nSize: {human(b['size'])}\n"
            f"Modified: {datetime.datetime.fromtimestamp(b['modified']):%Y-%m-%d %H:%M:%S}\n"
            f"Characters: {len(text):,}\nWords: {len(words(text)):,}\n"
            f"Paragraphs: {len([x for x in re.split(r'\\n\\s*\\n',text) if x.strip()]):,}\n\n"
            + "\n".join(f"{k}: {v}" for k,v in details.items())
        )

    def toggle_current_favorite(self):
        if not self.current:return
        p=self.current["path"]
        if p in self.favorites:self.favorites.remove(p)
        else:self.favorites.add(p)
        self.refresh_library()

    def notes_map(self): return self.notes.__dict__.get("_jass_notes",self.notes_store)
    @property
    def notes_store(self):
        if not hasattr(self,"_notes"):self._notes={}
        return self._notes

    def save_note(self):
        if not self.current:return
        self.notes_store[self.current["path"]]=self.notes.toPlainText()
        QMessageBox.information(self,"Saved","Research note saved for this session.")

    def search_text(self):
        q=self.q.text().strip()
        self.results.setRowCount(0)
        if not q:return
        candidates=self.books
        if self.scope.currentText()=="Current book" and self.current:candidates=[self.current]
        hits=[]
        for b in candidates:
            p=Path(b["path"])
            if b["ext"]==".epub":
                try:
                    _,chs=extract_epub(p); text="\n\n".join(t for _,t in chs)
                except:text=""
            elif b["ext"]==".pdf": text,_=extract_pdf(p)
            else:text=safe_text(p,3000000)
            if not text:continue
            for m in re.finditer(re.escape(q),text,re.I):
                a=max(0,m.start()-110); z=min(len(text),m.end()+170)
                hits.append((b,m.group(),normalize(text[a:z])))
                if len(hits)>=500:break
            if len(hits)>=500:break
        self.results.setRowCount(len(hits))
        self.search_hits=hits
        for i,(b,match,ctx) in enumerate(hits):
            for j,v in enumerate([b["name"],match,ctx,b["path"]]):
                self.results.setItem(i,j,QTableWidgetItem(v))

    def open_search_result(self,index):
        if not hasattr(self,"search_hits"):return
        b=self.search_hits[index.row()][0]; self.open_book(b)

    def library_menu(self,pos):
        row=self.libtable.rowAt(pos.y())
        if row<0:return
        b=self.filtered[row]; menu=QMenu(self)
        op=menu.addAction("📖 Open")
        fav=menu.addAction("★ Toggle Favorite")
        cp=menu.addAction("📋 Copy Path")
        folder=menu.addAction("📂 Open Folder")
        a=menu.exec(self.libtable.viewport().mapToGlobal(pos))
        if a==op:self.open_book(b)
        elif a==fav:
            self.current=b; self.toggle_current_favorite()
        elif a==cp:QApplication.clipboard().setText(b["path"])
        elif a==folder:subprocess.Popen(["xdg-open",str(Path(b["path"]).parent)])

    def export_json(self):
        if not self.books:return
        p,_=QFileDialog.getSaveFileName(self,"Export Library JSON","literature_library.json","JSON (*.json)")
        if not p:return
        data={"application":APP_NAME,"version":VERSION,"root":str(self.library_root),
              "books":self.books,"favorites":list(self.favorites),"notes":self.notes_store}
        Path(p).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
        QMessageBox.information(self,"Exported",p)

    def export_csv(self):
        if not self.books:return
        p,_=QFileDialog.getSaveFileName(self,"Export Library CSV","literature_library.csv","CSV (*.csv)")
        if not p:return
        with open(p,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f); w.writerow(["name","format","size","modified","path","favorite"])
            for b in self.books:w.writerow([b["name"],b["ext"],b["size"],b["modified"],b["path"],b["path"] in self.favorites])
        QMessageBox.information(self,"Exported",p)

    def build_report(self):
        if not self.books:return
        by=Counter(b["ext"] for b in self.books)
        lines=["JASS LITERATURE EXPLORER REPORT","="*70,
               f"Generated: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
               f"Root: {self.library_root}","",f"Books/files: {len(self.books):,}",
               f"Total size: {human(sum(b['size'] for b in self.books))}","",
               "FORMATS"]
        lines += [f"{k:10} {v:,}" for k,v in by.most_common()]
        lines += ["","LARGEST ITEMS"]
        for b in sorted(self.books,key=lambda x:x["size"],reverse=True)[:20]:
            lines.append(f"{human(b['size']):>12}  {b['name']}  {b['path']}")
        self.report.setPlainText("\n".join(lines))

    def show_report(self):
        self.build_report(); self.tabs.setCurrentIndex(7)

def main():
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME)
    w=MainWindow(); w.show(); sys.exit(app.exec())

if __name__=="__main__":
    main()
