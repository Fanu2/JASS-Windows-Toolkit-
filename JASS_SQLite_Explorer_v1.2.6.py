#!/usr/bin/env python3
"""JASS SQLite Explorer v1.1 - local-first, read-only SQLite laboratory."""
import csv, json, os, re, sqlite3, sys
from datetime import datetime
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QInputDialog, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QStatusBar,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QHeaderView,
    QCheckBox, QProgressBar
)

APP_NAME, VERSION = "JASS SQLite Explorer", "1.2.6"

def qid(s):
    return '"' + str(s).replace('"', '""') + '"'

def hsize(n):
    x=float(n or 0)
    for u in ("B","KB","MB","GB","TB"):
        if x < 1024 or u=="TB":
            return f"{x:.1f} {u}" if u!="B" else f"{int(x):,} B"
        x /= 1024

FTS_SHADOW_SUFFIXES = (
    "_config", "_data", "_docsize", "_idx",
    "_content", "_segments", "_segdir", "_stat"
)

def is_fts_virtual_sql(sql):
    return "VIRTUAL TABLE" in (sql or "").upper() and "USING FTS" in (sql or "").upper()


def readonly_sql(sql):
    s=sql.strip().lower()
    if not s or not s.startswith(("select","with","pragma","explain")):
        return False
    blocked=("insert ","update ","delete ","drop ","alter ","create ","replace ",
             "vacuum","attach ","detach ","reindex ","begin","commit","rollback",
             "end ")
    return not any(x in s for x in blocked)

class SchemaWorker(QThread):
    done=Signal(object); error=Signal(str)
    def __init__(self,path): super().__init__(); self.path=path
    def run(self):
        try:
            c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row
            objs=c.execute("""SELECT type,name,sql FROM sqlite_master
                              WHERE name NOT LIKE 'sqlite_%'
                              ORDER BY type,name""").fetchall()
            out=[]
            for o in objs:
                d=dict(o)
                d["count"]=None
                d["fts_shadow"]=False
                d["fts_virtual"]=(d["type"]=="table" and is_fts_virtual_sql(d["sql"]))
                out.append(d)

            # Only classify a table as an FTS shadow table when it belongs to
            # an actually detected FTS virtual table. This avoids hiding normal
            # user tables that happen to end in "_data", "_idx", etc.
            fts_names=[d["name"] for d in out if d.get("fts_virtual")]
            for d in out:
                if d["type"]=="table" and not d["fts_virtual"]:
                    d["fts_shadow"]=any(
                        d["name"] == base + suffix
                        for base in fts_names
                        for suffix in FTS_SHADOW_SUFFIXES
                    )

            for d in out:
                if d["type"]=="table" and not d["fts_virtual"] and not d["fts_shadow"]:
                    try:
                        d["count"]=c.execute(f"SELECT COUNT(*) FROM {qid(d['name'])}").fetchone()[0]
                    except Exception:
                        pass

            fks={}
            for o in out:
                if o["type"]=="table":
                    try:
                        fks[o["name"]]=[dict(x) for x in c.execute(f"PRAGMA foreign_key_list({qid(o['name'])})").fetchall()]
                    except Exception: fks[o["name"]]=[]
            fts=[]
            for o in out:
                if o["type"]=="table" and o.get("fts_virtual"):
                    fts.append(o["name"])
            info={}
            for pragma in ("page_size","page_count","freelist_count","journal_mode","encoding"):
                try: info[pragma]=c.execute(f"PRAGMA {pragma}").fetchone()[0]
                except Exception: info[pragma]=None
            try: info["integrity"]=c.execute("PRAGMA integrity_check").fetchone()[0]
            except Exception as e: info["integrity"]=f"ERROR: {e}"
            try: info["foreign_key_check"]=len(c.execute("PRAGMA foreign_key_check").fetchall())
            except Exception: info["foreign_key_check"]=None
            c.close(); self.done.emit({"objects":out,"fks":fks,"fts":fts,"info":info})
        except Exception as e: self.error.emit(f"{type(e).__name__}: {e}")

class TableWorker(QThread):
    done=Signal(object,object,object); error=Signal(str)
    def __init__(self,path,table,page,size,where):
        super().__init__(); self.path=path; self.table=table; self.page=page; self.size=size; self.where=where.strip()
    def run(self):
        try:
            c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row
            w=(" WHERE "+self.where) if self.where else ""
            total=c.execute(f"SELECT COUNT(*) FROM {qid(self.table)}{w}").fetchone()[0]
            cur=c.execute(f"SELECT * FROM {qid(self.table)}{w} LIMIT ? OFFSET ?",(self.size,self.page*self.size))
            rows=cur.fetchall(); cols=[x[0] for x in cur.description]
            c.close(); self.done.emit(cols,[dict(r) for r in rows],total)
        except Exception as e: self.error.emit(f"{type(e).__name__}: {e}")

class QueryWorker(QThread):
    done=Signal(object,object,float); error=Signal(str)
    def __init__(self,path,sql): super().__init__(); self.path=path; self.sql=sql
    def run(self):
        try:
            t=datetime.now(); c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row
            cur=c.execute(self.sql); cols=[x[0] for x in cur.description] if cur.description else []
            rows=cur.fetchmany(5000) if cols else []
            ms=(datetime.now()-t).total_seconds()*1000; c.close()
            self.done.emit(cols,[dict(r) for r in rows],ms)
        except Exception as e: self.error.emit(f"{type(e).__name__}: {e}")

class FTSWorker(QThread):
    done=Signal(object,object,float); error=Signal(str)
    def __init__(self,path,fts,query,limit):
        super().__init__(); self.path=path; self.fts=fts; self.query=query; self.limit=limit
    def run(self):
        try:
            t=datetime.now(); c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row
            # FTS5 MATCH plus bm25; rowid is preserved for external-content FTS tables.
            sql=f"""SELECT rowid AS _rowid_, *, bm25({qid(self.fts)}) AS _rank_
                    FROM {qid(self.fts)}
                    WHERE {qid(self.fts)} MATCH ?
                    ORDER BY _rank_ LIMIT ?"""
            rows=c.execute(sql,(self.query,self.limit)).fetchall()
            cols=[d[0] for d in c.execute(
                f"SELECT rowid AS _rowid_, * FROM {qid(self.fts)} LIMIT 0"
            ).description] + ["_rank_"]
            ms=(datetime.now()-t).total_seconds()*1000; c.close()
            self.done.emit(cols,[dict(r) for r in rows],ms)
        except Exception as e: self.error.emit(f"{type(e).__name__}: {e}")

class StatsWorker(QThread):
    done=Signal(object); error=Signal(str); progress=Signal(int,str)

    LARGE_ROWS = 1_000_000

    def __init__(self,path,table,deep=False):
        super().__init__(); self.path=path; self.table=table; self.deep=deep

    def _progress_handler(self):
        return 1 if self.isInterruptionRequested() else 0

    def _phase(self,pct,text):
        self.progress.emit(pct,text)

    def run(self):
        c=None
        try:
            c=sqlite3.connect(self.path)
            c.row_factory=sqlite3.Row
            c.set_progress_handler(self._progress_handler,50000)
            qt=qid(self.table)

            self._phase(3,"Reading table definition…")
            cols=[dict(r) for r in c.execute(f"PRAGMA table_info({qt})").fetchall()]

            self._phase(8,"Counting rows…")
            total=c.execute(f"SELECT COUNT(*) FROM {qt}").fetchone()[0]
            large=(total >= self.LARGE_ROWS) and not self.deep

            if large:
                # Safe/fast mode for multi-million-row tables. Avoid several
                # full-table DISTINCT/GROUP BY operations that can take minutes
                # on USB/HDD storage. Basic NULL/length statistics are exact.
                self._phase(15,"Large table detected — using fast exact statistics…")

            out=[]; ncols=max(1,len(cols))
            for i,col in enumerate(cols):
                n=col["name"]; qi=qid(n)
                base=15+int(i*75/ncols)

                self._phase(base,f"Analyzing {n} — NULL values…")
                nulls=c.execute(f"SELECT COUNT(*) FROM {qt} WHERE {qi} IS NULL").fetchone()[0]
                if self.isInterruptionRequested(): raise InterruptedError

                avglen=maxlen=None
                try:
                    self._phase(min(95,base+12),f"Analyzing {n} — value lengths…")
                    avglen,maxlen=c.execute(
                        f"SELECT AVG(LENGTH(CAST({qi} AS TEXT))),MAX(LENGTH(CAST({qi} AS TEXT))) FROM {qt}"
                    ).fetchone()
                except Exception:
                    pass

                distinct=None
                if not large:
                    self._phase(min(97,base+25),f"Analyzing {n} — distinct values…")
                    distinct=c.execute(f"SELECT COUNT(DISTINCT {qi}) FROM {qt}").fetchone()[0]
                    if self.isInterruptionRequested(): raise InterruptedError

                out.append({
                    "column":n,"type":col["type"],"pk":col["pk"],"notnull":col["notnull"],
                    "nulls":nulls,"distinct":distinct,
                    "avg_length":avglen,"max_length":maxlen,
                    "large_table_deferred":large
                })

            self._phase(100,"Statistics complete.")
            c.close()
            self.done.emit({
                "path":self.path,"table":self.table,"rows":total,
                "columns":out,"large_table":large,"deep":self.deep
            })
        except InterruptedError:
            try: c.close()
            except Exception: pass
            self.error.emit("Statistics cancelled.")
        except Exception as e:
            try: c.close()
            except Exception: pass
            self.error.emit(f"{type(e).__name__}: {e}")


class ColumnProfileWorker(QThread):
    done=Signal(object); error=Signal(str); progress=Signal(int,str)

    LARGE_ROWS=1_000_000

    def __init__(self,path,table,column,top_n=25,deep=False):
        super().__init__(); self.path=path; self.table=table; self.column=column
        self.top_n=top_n; self.deep=deep

    def _progress_handler(self):
        return 1 if self.isInterruptionRequested() else 0

    def _phase(self,pct,text):
        self.progress.emit(pct,text)

    def run(self):
        c=None
        try:
            c=sqlite3.connect(self.path)
            c.set_progress_handler(self._progress_handler,50000)
            qi,qt=qid(self.column),qid(self.table)

            self._phase(5,"Counting rows…")
            total=c.execute(f"SELECT COUNT(*) FROM {qt}").fetchone()[0]
            large=(total>=self.LARGE_ROWS) and not self.deep

            self._phase(15,"Counting NULL values…")
            nulls=c.execute(f"SELECT COUNT(*) FROM {qt} WHERE {qi} IS NULL").fetchone()[0]
            if self.isInterruptionRequested(): raise InterruptedError

            self._phase(25,"Counting empty values…")
            empty=c.execute(
                f"SELECT COUNT(*) FROM {qt} WHERE {qi} IS NOT NULL AND CAST({qi} AS TEXT) = ''"
            ).fetchone()[0]
            if self.isInterruptionRequested(): raise InterruptedError

            nonnull=total-nulls
            distinct=None
            duplicates=None
            freq_rows=[]

            if large:
                self._phase(40,"Large table — skipping expensive DISTINCT/GROUP BY in fast mode…")
            else:
                self._phase(40,"Counting distinct values…")
                distinct=c.execute(f"SELECT COUNT(DISTINCT {qi}) FROM {qt}").fetchone()[0]
                if self.isInterruptionRequested(): raise InterruptedError

                self._phase(58,"Calculating top-value frequencies…")
                freq_rows=c.execute(
                    f"""SELECT {qi} AS value, COUNT(*) AS occurrences
                        FROM {qt}
                        WHERE {qi} IS NOT NULL
                        GROUP BY {qi}
                        ORDER BY occurrences DESC, CAST({qi} AS TEXT)
                        LIMIT ?""",(self.top_n,)
                ).fetchall()
                if self.isInterruptionRequested(): raise InterruptedError
                duplicates=max(0,nonnull-distinct)

            self._phase(78,"Calculating numeric summary…")
            numeric=None
            try:
                numeric=c.execute(
                    f"""SELECT MIN({qi}), MAX({qi}), AVG({qi})
                        FROM {qt}
                        WHERE {qi} IS NOT NULL
                          AND typeof({qi}) IN ('integer','real')"""
                ).fetchone()
            except Exception:
                pass

            self._phase(88,"Calculating value-length summary…")
            length_stats=None
            try:
                length_stats=c.execute(
                    f"""SELECT AVG(LENGTH(CAST({qi} AS TEXT))),
                              MIN(LENGTH(CAST({qi} AS TEXT))),
                              MAX(LENGTH(CAST({qi} AS TEXT)))
                       FROM {qt}
                       WHERE {qi} IS NOT NULL"""
                ).fetchone()
            except Exception:
                pass

            self._phase(100,"Column profile complete.")
            c.close()
            self.done.emit({
                "path":self.path,"table":self.table,"column":self.column,
                "total":total,"nulls":nulls,"empty":empty,
                "distinct":distinct,"duplicates":duplicates,"nonnull":nonnull,
                "frequencies":[{"value":r[0],"occurrences":r[1]} for r in freq_rows],
                "numeric":numeric,"length":length_stats,
                "large_table":large,"deep":self.deep
            })
        except InterruptedError:
            try: c.close()
            except Exception: pass
            self.error.emit("Column profiling cancelled.")
        except Exception as e:
            try: c.close()
            except Exception: pass
            self.error.emit(f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f"{APP_NAME} v{VERSION}"); self.resize(1550,950)
        self.path=""; self.table_name=""; self.rows=[]; self.cols=[]; self.history=[]; self.schema_data={}; self.load_generation=0
        self._ui(); self._menu()

    def _menu(self):
        m=self.menuBar().addMenu("&File")
        a=QAction("&Open Database…",self); a.setShortcut("Ctrl+O"); a.triggered.connect(self.open_db); m.addAction(a)
        a=QAction("Open Database by &Path…",self); a.setShortcut("Ctrl+Shift+O"); a.triggered.connect(self.open_db_by_path); m.addAction(a)
        m.addSeparator()
        a=QAction("&Refresh",self); a.setShortcut("F5"); a.triggered.connect(self.refresh); m.addAction(a)
        a=QAction("&Close",self); a.triggered.connect(self.close_db); m.addAction(a)
        m.addSeparator(); a=QAction("E&xit",self); a.triggered.connect(self.close); m.addAction(a)
        m=self.menuBar().addMenu("&Tools")
        a=QAction("Database Information",self); a.triggered.connect(self.info); m.addAction(a)
        a=QAction("Run Integrity Check",self); a.triggered.connect(self.health); m.addAction(a)
        m=self.menuBar().addMenu("&Help"); a=QAction("Read-Only Safety",self); a.triggered.connect(self.safety); m.addAction(a)

    def _ui(self):
        root=QVBoxLayout(); top=QHBoxLayout()
        self.db=QLabel("No database open"); self.db.setStyleSheet("font-weight:bold"); top.addWidget(self.db,1); top.addWidget(QLabel("● READ-ONLY"))
        root.addLayout(top)
        sp=QSplitter(Qt.Horizontal); self.tree=QTreeWidget(); self.tree.setHeaderLabels(["Database Objects"]); self.tree.itemClicked.connect(self.clicked); sp.addWidget(self.tree)
        self.tabs=QTabWidget(); sp.addWidget(self.tabs); sp.setSizes([310,1240]); root.addWidget(sp,1)
        self.tabs.addTab(self.dashboard(),"Dashboard"); self.tabs.addTab(self.data(),"Data Browser"); self.tabs.addTab(self.search(),"FTS Search"); self.tabs.addTab(self.stats_view(),"Statistics"); self.tabs.addTab(self.schema(),"Schema"); self.tabs.addTab(self.query(),"SQL Console"); self.tabs.addTab(self.report(),"Reports")
        w=QWidget(); w.setLayout(root); self.setCentralWidget(w); self.setStatusBar(QStatusBar()); self.statusBar().showMessage("Open an SQLite database.")

    def dashboard(self):
        w=QWidget(); l=QVBoxLayout(w); row=QHBoxLayout(); self.stat={}
        for k,t in (("tables","Tables"),("views","Views"),("indexes","Indexes"),("triggers","Triggers"),("rows","Rows"),("fts","FTS")):
            f=QFrame(); fl=QVBoxLayout(f); v=QLabel("—"); v.setFont(QFont("Sans Serif",20,QFont.Bold)); fl.addWidget(v); fl.addWidget(QLabel(t)); row.addWidget(f); self.stat[k]=v
        l.addLayout(row); self.dash=QTextEdit(); self.dash.setReadOnly(True); l.addWidget(self.dash,1); return w

    def data(self):
        w=QWidget(); l=QVBoxLayout(w); b=QHBoxLayout()
        self.data_title=QLabel("No table selected"); self.where=QLineEdit(); self.where.setPlaceholderText("Optional WHERE expression, e.g. age > 30")
        self.page=QSpinBox(); self.page.setRange(1,1000000); self.page.setValue(1); self.ps=QComboBox(); self.ps.addItems(["100","250","500","1000","5000"]); self.ps.setCurrentText("500")
        for x in (QLabel("Table:"),self.data_title,self.where,QLabel("Page"),self.page,QLabel("Rows"),self.ps): b.addWidget(x)
        for text,fn in (("◀",self.prev),("▶",self.next),("Load",self.load_table)):
            q=QPushButton(text); q.clicked.connect(fn); b.addWidget(q)
        l.addLayout(b); self.dt=QTableWidget(); self.dt.setEditTriggers(QAbstractItemView.NoEditTriggers); self.dt.setSelectionBehavior(QAbstractItemView.SelectRows); self.dt.setAlternatingRowColors(True); l.addWidget(self.dt,1); self.di=QLabel("Read-only"); l.addWidget(self.di); return w

    def search(self):
        w=QWidget(); l=QVBoxLayout(w); b=QHBoxLayout()
        self.fts_combo=QComboBox(); self.fts_combo.setMinimumWidth(250); self.fts_query=QLineEdit(); self.fts_query.setPlaceholderText("FTS5 query, e.g. hmangaihna or \"hmangaihna\"")
        self.fts_limit=QSpinBox(); self.fts_limit.setRange(1,5000); self.fts_limit.setValue(100)
        q=QPushButton("Search"); q.clicked.connect(self.run_fts)
        b.addWidget(QLabel("FTS index")); b.addWidget(self.fts_combo); b.addWidget(self.fts_query,1); b.addWidget(QLabel("Limit")); b.addWidget(self.fts_limit); b.addWidget(q); l.addLayout(b)
        self.fts_info=QLabel("No FTS table detected."); l.addWidget(self.fts_info)
        self.ft=QTableWidget(); self.ft.setEditTriggers(QAbstractItemView.NoEditTriggers); self.ft.setAlternatingRowColors(True); l.addWidget(self.ft,1); return w

    def stats_view(self):
        w=QWidget(); l=QVBoxLayout(w)
        b=QHBoxLayout()
        self.stats_table=QLabel("No table selected")
        b.addWidget(self.stats_table,1)
        q=QPushButton("Analyze Current Table"); q.clicked.connect(self.analyze); b.addWidget(q)
        self.profile_btn=QPushButton("Profile Selected Column"); self.profile_btn.clicked.connect(self.profile_selected_column); b.addWidget(self.profile_btn)
        self.deep_stats=QCheckBox("Deep exact analysis")
        self.deep_stats.setToolTip("For tables with 1M+ rows, enable this to run exact DISTINCT/frequency operations. It may be slow on USB/HDD storage.")
        b.addWidget(self.deep_stats)
        self.stats_cancel=QPushButton("Cancel"); self.stats_cancel.clicked.connect(self.cancel_analysis); self.stats_cancel.setEnabled(False); b.addWidget(self.stats_cancel)
        l.addLayout(b)
        pb=QHBoxLayout()
        self.stats_progress=QLabel("Ready")
        self.stats_bar=QProgressBar(); self.stats_bar.setRange(0,100); self.stats_bar.setValue(0)
        pb.addWidget(self.stats_progress); pb.addWidget(self.stats_bar,1)
        l.addLayout(pb)

        split=QSplitter(Qt.Horizontal)

        left=QWidget(); ll=QVBoxLayout(left)
        ll.addWidget(QLabel("Column overview — double-click or select a row and profile it"))
        self.stt=QTableWidget()
        self.stt.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stt.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stt.setAlternatingRowColors(True)
        self.stt.cellDoubleClicked.connect(lambda r,c: self.profile_column_row(r))
        ll.addWidget(self.stt,1)
        split.addWidget(left)

        right=QWidget(); rl=QVBoxLayout(right)
        self.column_profile_title=QLabel("Column Profile")
        self.column_profile_title.setStyleSheet("font-weight:bold; font-size:16px;")
        rl.addWidget(self.column_profile_title)
        self.column_profile=QTextEdit()
        self.column_profile.setReadOnly(True)
        rl.addWidget(self.column_profile,1)
        rl.addWidget(QLabel("Top values / frequencies"))
        self.freq_table=QTableWidget()
        self.freq_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.freq_table.setAlternatingRowColors(True)
        rl.addWidget(self.freq_table,1)
        split.addWidget(right)
        split.setSizes([800,600])
        l.addWidget(split,1)
        return w

    def schema(self):
        w=QWidget(); l=QVBoxLayout(w); self.st=QTextEdit(); self.st.setReadOnly(True); self.st.setFont(QFont("Monospace",10)); l.addWidget(self.st); return w

    def query(self):
        w=QWidget(); l=QVBoxLayout(w); l.addWidget(QLabel("Read-only: SELECT, WITH, PRAGMA and EXPLAIN."))
        self.sql=QPlainTextEdit("SELECT name,type FROM sqlite_master ORDER BY type,name;"); self.sql.setFont(QFont("Monospace",11)); l.addWidget(self.sql,1)
        q=QPushButton("Run Query"); q.clicked.connect(self.run_query); l.addWidget(q)
        self.qt=QTableWidget(); self.qt.setEditTriggers(QAbstractItemView.NoEditTriggers); self.qt.setAlternatingRowColors(True); l.addWidget(self.qt,1); self.qi=QLabel(); l.addWidget(self.qi)
        return w

    def report(self):
        w=QWidget(); l=QVBoxLayout(w); self.rp=QPlainTextEdit(); self.rp.setReadOnly(True); l.addWidget(self.rp,1)
        row=QHBoxLayout()
        for t,fn in (("Current CSV",self.csv),("Current JSON",self.json_export),("Report TXT",self.txt),("Report JSON",self.report_json)):
            q=QPushButton(t); q.clicked.connect(fn); row.addWidget(q)
        l.addLayout(row); return w

    def open_db(self):
        # Native Linux file choosers do not always accept an absolute path typed
        # into the File name field. Start in the current database directory when
        # possible, and provide "Open Database by Path…" as a reliable fallback.
        start=os.path.dirname(self.path) if self.path and os.path.isdir(os.path.dirname(self.path)) else os.path.expanduser("~")
        p,_=QFileDialog.getOpenFileName(
            self,"Open SQLite Database",start,
            "SQLite databases (*.db *.sqlite *.sqlite3);;All files (*)"
        )
        if p:
            self.load(p)

    def open_db_by_path(self):
        default=self.path if self.path else os.path.expanduser("~")
        p,ok=QInputDialog.getText(
            self,"Open SQLite Database by Path",
            "Enter the full path to the SQLite database:",
            QLineEdit.Normal,default
        )
        if not ok:
            return
        p=os.path.abspath(os.path.expanduser(os.path.expandvars(p.strip())))
        if not p:
            return
        if not os.path.isfile(p):
            QMessageBox.warning(self,"Database Not Found",f"File does not exist:\n\n{p}")
            return
        self.load(p)

    def load(self,p):
        p=os.path.abspath(os.path.expanduser(os.path.expandvars(str(p).strip())))
        if not os.path.isfile(p):
            QMessageBox.warning(self,"Database Not Found",f"File does not exist:\n\n{p}")
            return

        # SQLite databases have a standard header. Validate it before starting
        # background schema analysis, while keeping the existing DB intact if
        # the new selection is invalid.
        try:
            with open(p,"rb") as fh:
                header=fh.read(16)
            if header != b"SQLite format 3\\x00":
                # Some SQLite-compatible files may still be readable, so perform
                # a lightweight SQLite open as a second validation.
                test=sqlite3.connect(f"file:{p}?mode=ro",uri=True)
                test.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
                test.close()
        except Exception as e:
            QMessageBox.critical(self,"Cannot Open SQLite Database",
                                 f"The selected file could not be opened as a readable SQLite database.\\n\\n{p}\\n\\n{type(e).__name__}: {e}")
            return

        self.load_generation += 1
        self.close_db(False)
        self.path=p
        self.db.setText(self.path)
        self.profile_table_name=""
        self.statusBar().showMessage("Analyzing database…")
        self.sw=SchemaWorker(self.path); self.sw.done.connect(self.schema_loaded); self.sw.error.connect(self.err); self.sw.start()

    def schema_loaded(self,d):
        self.schema_data=d; objs=d["objects"]; self.tree.clear(); groups={}
        for o in objs: groups.setdefault(o["type"],[]).append(o)
        # Keep SQLite FTS implementation/shadow tables out of the normal table count.
        user_tables=[o for o in groups.get("table",[]) if not o.get("fts_shadow") and not o.get("fts_virtual")]
        fts_virtuals=[o for o in groups.get("table",[]) if o.get("fts_virtual")]
        fts_shadows=[o for o in groups.get("table",[]) if o.get("fts_shadow")]
        display_groups=dict(groups)
        display_groups["table"]=user_tables
        for typ in ("table","view","index","trigger"):
            items=display_groups.get(typ,[])
            if not items: continue
            par=QTreeWidgetItem([f"{typ.title()}s ({len(items)})"]); self.tree.addTopLevelItem(par); par.setExpanded(True)
            for o in items:
                s=o["name"]+(f"  [{o['count']:,}]" if o["count"] is not None else "")
                it=QTreeWidgetItem([s]); it.setData(0,Qt.UserRole,(typ,o["name"],o["sql"])); par.addChild(it)
        if fts_virtuals:
            par=QTreeWidgetItem([f"FTS Virtual Tables ({len(fts_virtuals)})"])
            self.tree.addTopLevelItem(par); par.setExpanded(True)
            for o in fts_virtuals:
                it=QTreeWidgetItem([o["name"]])
                it.setData(0,Qt.UserRole,("fts_virtual",o["name"],o["sql"]))
                par.addChild(it)
        if fts_shadows:
            par=QTreeWidgetItem([f"FTS Internal Tables ({len(fts_shadows)})"])
            self.tree.addTopLevelItem(par); par.setExpanded(False)
            for o in fts_shadows:
                it=QTreeWidgetItem([o["name"]]); it.setData(0,Qt.UserRole,("fts_shadow",o["name"],o["sql"])); par.addChild(it)
        rows=sum((o["count"] or 0) for o in user_tables); fts=len(d["fts"])
        for k,v in (("tables",len(user_tables)),("views",len(groups.get("view",[]))),("indexes",len(groups.get("index",[]))),("triggers",len(groups.get("trigger",[]))),("rows",rows),("fts",fts)): self.stat[k].setText(f"{v:,}")
        self.fts_combo.clear(); self.fts_combo.addItems(d["fts"]); self.fts_info.setText(f"{fts} FTS virtual table(s) detected.")
        size=os.path.getsize(self.path); mt=datetime.fromtimestamp(os.path.getmtime(self.path)); inf=d["info"]
        fts_text="\\n".join("  • "+x for x in d["fts"]) or "  • None detected"
        fk_count=sum(len(x) for x in d["fks"].values())
        self.dash.setPlainText(f"""{APP_NAME} v{VERSION}

Database: {self.path}
Size: {hsize(size)}
Modified: {mt:%Y-%m-%d %H:%M:%S}

Objects
Tables: {len(groups.get('table',[]))}
Views: {len(groups.get('view',[]))}
Indexes: {len(groups.get('index',[]))}
Triggers: {len(groups.get('trigger',[]))}
Estimated table rows: {rows:,}

Full-Text Search
{fts_text}

Relationships
Foreign-key definitions: {fk_count}

Database Health
Integrity check: {inf.get('integrity')}
Foreign-key violations: {inf.get('foreign_key_check')}
Journal mode: {inf.get('journal_mode')}
Encoding: {inf.get('encoding')}
Page size: {inf.get('page_size')}
Page count: {inf.get('page_count')}

READ-ONLY MODE""")
        self.make_report(); self.statusBar().showMessage("Database loaded and analyzed.")

    def clicked(self,it,_):
        d=it.data(0,Qt.UserRole)
        if not d: return
        typ,name,sql=d
        if typ=="table":
            self.table_name=name; self.data_title.setText(name); self.stats_table.setText(f"Table: {name}"); self.page.setValue(1); self.where.clear(); self.tabs.setCurrentIndex(1); self.load_table()
            self.analyze()
            self.st.setPlainText(self.table_schema(name))
        elif typ=="fts_virtual":
            self.st.setPlainText(f"FTS virtual table: {name}\\n\\nThis is a full-text search index. Use the FTS Search tab for searching.\\n\\nSQL:\\n{sql or '(none)'}")
            self.tabs.setCurrentIndex(4)
        elif typ=="fts_shadow":
            self.st.setPlainText(f"FTS internal/shadow table: {name}\\n\\nThis is an SQLite FTS implementation table and is excluded from ordinary user-table statistics.")
            self.tabs.setCurrentIndex(4)
        else:
            self.st.setPlainText(f"Object: {name}\\nType: {typ}\\n\\nSQL:\\n{sql or '(none)'}"); self.tabs.setCurrentIndex(4)

    def table_schema(self,name):
        c=sqlite3.connect(self.path); info=c.execute(f"PRAGMA table_info({qid(name)})").fetchall(); idx=c.execute(f"PRAGMA index_list({qid(name)})").fetchall(); fk=c.execute(f"PRAGMA foreign_key_list({qid(name)})").fetchall(); c.close()
        lines=[f"TABLE: {name}","="*72,"","COLUMNS"]
        for r in info: lines.append(f"{r[1]} | type={r[2]} | notnull={r[3]} | default={r[4]} | pk={r[5]}")
        lines += ["","INDEXES"]+[str(tuple(r)) for r in idx]
        lines += ["","FOREIGN KEYS"]+[str(tuple(r)) for r in fk]
        return "\\n".join(lines)

    def load_table(self):
        if not self.path or not self.table_name: return
        self.tw_generation=self.load_generation; self.tw=TableWorker(self.path,self.table_name,self.page.value()-1,int(self.ps.currentText()),self.where.text()); self.tw.done.connect(self.table_loaded); self.tw.error.connect(self.err); self.tw.start()

    def table_loaded(self,cols,rows,total):
        if getattr(self, "tw_generation", self.load_generation) != self.load_generation:
            return
        self.cols,self.rows=cols,rows
        self.fill(self.dt,cols,rows)
        size=int(self.ps.currentText()); pages=max(1,(total+size-1)//size)
        self.di.setText(f"{total:,} matching rows • page {self.page.value():,} of {pages:,} • showing {len(rows):,}")

    def fill(self,w,cols,rows):
        w.clear(); w.setColumnCount(len(cols)); w.setHorizontalHeaderLabels(cols); w.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,col in enumerate(cols):
                v=row.get(col); w.setItem(r,c,QTableWidgetItem("NULL" if v is None else str(v)))
        w.resizeColumnsToContents()
        for i in range(w.columnCount()):
            if w.columnWidth(i)>350: w.setColumnWidth(i,350)

    def prev(self):
        if self.page.value()>1: self.page.setValue(self.page.value()-1); self.load_table()
    def next(self): self.page.setValue(self.page.value()+1); self.load_table()

    def run_fts(self):
        if not self.path or not self.fts_combo.currentText(): return
        query=self.fts_query.text().strip()
        if not query: return QMessageBox.warning(self,"FTS Search","Enter a search query.")
        fts=self.fts_combo.currentText(); self.fts_info.setText(f"Searching {fts}…")
        self.fw=FTSWorker(self.path,fts,query,self.fts_limit.value()); self.fw.done.connect(self.fts_done); self.fw.error.connect(self.err); self.fw.start()
        self.history.append(("FTS",query))

    def fts_done(self,cols,rows,ms):
        self.fill(self.ft,cols,rows); self.fts_info.setText(f"{len(rows):,} results displayed • {ms:.1f} ms • ranked with BM25 when supported.")

    def analyze(self):
        if not self.path or not self.table_name: return
        self.stats_table.setText(f"Analyzing: {self.table_name}…")
        self.xw_generation=self.load_generation
        self.xw=StatsWorker(self.path,self.table_name,self.deep_stats.isChecked())
        self.xw.done.connect(self.stats_done); self.xw.error.connect(self.err); self.xw.progress.connect(self.stats_progress_update)
        self.stats_cancel.setEnabled(True); self.stats_progress.setText("Starting…"); self.stats_bar.setValue(0)
        self.xw.start()

    def stats_progress_update(self,pct,text):
        self.stats_bar.setValue(max(0,min(100,int(pct))))
        self.stats_progress.setText(text)

    def cancel_analysis(self):
        for worker in (getattr(self,"xw",None),getattr(self,"cpw",None)):
            if worker and worker.isRunning():
                worker.requestInterruption()
        self.stats_cancel.setEnabled(False)
        self.stats_progress.setText("Cancelling…")

    def stats_done(self,d):
        if d.get("path") != self.path or getattr(self, "xw_generation", self.load_generation) != self.load_generation:
            return
        if d.get("table") != self.table_name:
            return
        self.stats_table.setText(f"Table: {d['table']} • {d['rows']:,} rows")
        self.stats_cancel.setEnabled(False); self.stats_progress.setText("Statistics complete"); self.stats_bar.setValue(100)
        self.profile_table_name = d["table"]
        cols=["column","type","pk","notnull","nulls","distinct","avg_length","max_length"]
        display_columns=[]
        for row in d["columns"]:
            r=dict(row)
            if r.get("distinct") is None:
                r["distinct"]="deferred"
            display_columns.append(r)
        self.fill(self.stt,cols,display_columns)
        if d.get("large_table") and not d.get("deep"):
            self.stt.setToolTip(
                "Large-table Fast Mode: DISTINCT counts are intentionally deferred. "
                "Enable 'Deep exact analysis' for exact DISTINCT/frequency calculations."
            )
        self.column_profile_title.setText("Column Profile — select a column")
        self.column_profile.clear()
        self.freq_table.clear()
        self.tabs.setCurrentIndex(3)

    def profile_selected_column(self):
        row = self.stt.currentRow()
        if row < 0:
            return QMessageBox.information(self, "Column Profile", "Select a column first.")
        self.profile_column_row(row)

    def profile_column_row(self, row):
        if not getattr(self, "profile_table_name", ""):
            return
        item = self.stt.item(row, 0)
        if not item:
            return
        column = item.text()
        self.column_profile_title.setText(f"Column Profile — {column}")
        self.column_profile.setPlainText("Analyzing column…")
        self.freq_table.clear()
        self.cpw_generation=self.load_generation
        self.cpw = ColumnProfileWorker(self.path, self.profile_table_name, column, 25, self.deep_stats.isChecked())
        self.cpw.done.connect(self.column_profile_done)
        self.cpw.error.connect(self.err); self.cpw.progress.connect(self.stats_progress_update)
        self.stats_cancel.setEnabled(True); self.stats_progress.setText("Starting column profile…"); self.stats_bar.setValue(0)
        self.cpw.start()

    def column_profile_done(self, d):
        if d.get("path") != self.path or getattr(self, "cpw_generation", self.load_generation) != self.load_generation:
            return
        if d.get("table") != self.table_name:
            return
        current_row=self.stt.currentRow()
        current_col=self.stt.item(current_row,0).text() if current_row >= 0 and self.stt.item(current_row,0) else None
        if current_col != d.get("column"):
            return
        self.stats_cancel.setEnabled(False); self.stats_progress.setText("Column profile complete"); self.stats_bar.setValue(100)
        total=d["total"]; nulls=d["nulls"]; empty=d["empty"]
        distinct=d["distinct"]; dup=d["duplicates"]; nonnull=d["nonnull"]
        unique_pct=(distinct/nonnull*100) if (nonnull and distinct is not None) else None
        null_pct=(nulls/total*100) if total else 0.0
        lines=[
            f"Table: {d['table']}",
            f"Column: {d['column']}",
            ("Mode: FAST LARGE-DATABASE PROFILE — exact DISTINCT/frequency analysis deferred"
             if d.get("large_table") and not d.get("deep") else "Mode: EXACT PROFILE"),
            "",
            f"Total rows:       {total:,}",
            f"Non-NULL values:  {nonnull:,}",
            f"NULL values:      {nulls:,} ({null_pct:.2f}%)",
            f"Empty strings:    {empty:,}",
            f"Distinct values:  {distinct:,}" if distinct is not None else "Distinct values:  deferred",
            f"Duplicate surplus:{dup:,}" if dup is not None else "Duplicate surplus: deferred",
            f"Distinct %:       {unique_pct:.2f}%" if distinct is not None else "Distinct %:       deferred",
        ]
        if d.get("numeric") and any(x is not None for x in d["numeric"]):
            mn,mx,av=d["numeric"]
            lines += ["","Numeric summary:",f"Minimum: {mn}",f"Maximum: {mx}",f"Average: {av}"]
        if d.get("length") and any(x is not None for x in d["length"]):
            av,mn,mx=d["length"]
            lines += ["","Text/value length:",f"Average: {av:.2f}" if av is not None else "Average: —",
                      f"Minimum: {mn}" if mn is not None else "Minimum: —",
                      f"Maximum: {mx}" if mx is not None else "Maximum: —"]
        self.column_profile.setPlainText("\n".join(lines))

        freq=d["frequencies"]
        self.freq_table.clear()
        if d.get("large_table") and not d.get("deep"):
            self.freq_table.setColumnCount(1)
            self.freq_table.setHorizontalHeaderLabels(["Frequency analysis deferred"])
            self.freq_table.setRowCount(2)
            self.freq_table.setItem(0,0,QTableWidgetItem(
                "Fast Mode skipped DISTINCT/GROUP BY frequency analysis for this large table."
            ))
            self.freq_table.setItem(1,0,QTableWidgetItem(
                "Enable “Deep exact analysis” and profile again to calculate exact top frequencies."
            ))
            self.freq_table.resizeColumnsToContents()
            return
        self.freq_table.setColumnCount(3)
        self.freq_table.setHorizontalHeaderLabels(["#", "Value", "Occurrences"])
        self.freq_table.setRowCount(len(freq))
        for i,r in enumerate(freq):
            self.freq_table.setItem(i,0,QTableWidgetItem(str(i+1)))
            self.freq_table.setItem(i,1,QTableWidgetItem("NULL" if r["value"] is None else str(r["value"])))
            self.freq_table.setItem(i,2,QTableWidgetItem(f"{r['occurrences']:,}"))
        self.freq_table.resizeColumnsToContents()
        if self.freq_table.columnWidth(1)>450:
            self.freq_table.setColumnWidth(1,450)

    def run_query(self):
        if not self.path: return QMessageBox.warning(self,APP_NAME,"Open a database first.")
        s=self.sql.toPlainText().strip()
        if not readonly_sql(s): return QMessageBox.warning(self,"Read-only SQL","Only SELECT, WITH, PRAGMA and EXPLAIN queries are allowed.")
        self.qw=QueryWorker(self.path,s); self.qw.done.connect(self.query_done); self.qw.error.connect(self.err); self.qw.start(); self.history.append(("SQL",s))

    def query_done(self,cols,rows,ms):
        self.fill(self.qt,cols,rows); self.qi.setText(f"{len(rows):,} rows displayed (maximum 5,000) • {ms:.1f} ms")

    def make_report(self):
        if not self.path: return
        d=self.schema_data; objs=d.get("objects",[]); lines=[f"{APP_NAME} v{VERSION}","="*72,f"Database: {self.path}",f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",""]
        for typ in ("table","view","index","trigger"):
            ss=[o for o in objs if o["type"]==typ]
            if ss:
                lines += [f"{typ.upper()}S ({len(ss)})","-"*72]
                for o in ss:
                    lines += [o["name"],"  "+(o["sql"] or "(none)").replace("\\n","\\n  "),""] 
        lines += ["FULL-TEXT TABLES"]+["  "+x for x in d.get("fts",[])]
        lines += ["","FOREIGN-KEY DEFINITIONS"]
        for t,fks in d.get("fks",{}).items():
            for fk in fks: lines.append(f"  {t} -> {fk.get('table')} ({fk.get('from')} -> {fk.get('to')})")
        self.rp.setPlainText("\\n".join(lines))

    def csv(self):
        if not self.cols: return
        p,_=QFileDialog.getSaveFileName(self,"Export CSV","","CSV (*.csv)")
        if p:
            with open(p,"w",newline="",encoding="utf-8-sig") as f: csv.writer(f).writerows([self.cols]+[[r.get(c) for c in self.cols] for r in self.rows])

    def json_export(self):
        if not self.rows: return
        p,_=QFileDialog.getSaveFileName(self,"Export JSON","","JSON (*.json)")
        if p: open(p,"w",encoding="utf-8").write(json.dumps(self.rows,ensure_ascii=False,indent=2,default=str))

    def txt(self):
        p,_=QFileDialog.getSaveFileName(self,"Export Report","","Text (*.txt)")
        if p: open(p,"w",encoding="utf-8").write(self.rp.toPlainText())

    def report_json(self):
        p,_=QFileDialog.getSaveFileName(self,"Export Report JSON","","JSON (*.json)")
        if not p: return
        d=self.schema_data
        data={"application":APP_NAME,"version":VERSION,"database":self.path,"generated":datetime.now().isoformat(timespec="seconds"),"objects":d.get("objects",[]),"fts_tables":d.get("fts",[]),"foreign_keys":d.get("fks",{}),"health":d.get("info",{})}
        open(p,"w",encoding="utf-8").write(json.dumps(data,ensure_ascii=False,indent=2,default=str))

    def health(self):
        if not self.path: return
        try:
            c=sqlite3.connect(self.path); integrity=c.execute("PRAGMA integrity_check").fetchone()[0]; fk=c.execute("PRAGMA foreign_key_check").fetchall(); quick=c.execute("PRAGMA quick_check").fetchone()[0]; c.close()
            QMessageBox.information(self,"Database Health",f"Integrity check:\\n{integrity}\\n\\nQuick check:\\n{quick}\\n\\nForeign-key violations: {len(fk)}")
        except Exception as e: self.err(str(e))

    def info(self):
        if not self.path: return QMessageBox.information(self,APP_NAME,"No database is open.")
        d=self.schema_data.get("info",{}); QMessageBox.information(self,"Database Information",f"SQLite: {sqlite3.sqlite_version}\\nEncoding: {d.get('encoding')}\\nPage size: {d.get('page_size')}\\nPages: {d.get('page_count')}\\nFreelist: {d.get('freelist_count')}\\nJournal: {d.get('journal_mode')}")

    def safety(self): QMessageBox.information(self,"Read-Only Safety","JASS SQLite Explorer has no record/schema editing controls. SQL is restricted to read-oriented statements. Keep backups of important databases.")
    def refresh(self):
        if self.path: self.load(self.path)
    def close_db(self,reset=True):
        self.path=""; self.table_name=""
        if reset: self.tree.clear(); self.db.setText("No database open"); self.statusBar().showMessage("Database closed.")
    def err(self,msg):
        self.stats_cancel.setEnabled(False)
        self.stats_progress.setText(msg)
        self.statusBar().showMessage("Operation failed.")
        if "cancelled" not in str(msg).lower():
            QMessageBox.critical(self,"Operation Error",msg)

def main():
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); w=MainWindow(); w.show(); return app.exec()
if __name__=="__main__": raise SystemExit(main())
