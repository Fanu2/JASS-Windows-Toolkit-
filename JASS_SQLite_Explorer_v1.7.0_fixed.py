#!/usr/bin/env python3
"""JASS SQLite Explorer v1.3 - local-first, read-only SQLite investigation and corpus laboratory."""
import csv, json, os, re, sqlite3, sys, math, unicodedata
from collections import Counter
from datetime import datetime
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QInputDialog, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QStatusBar,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QHeaderView,
    QCheckBox, QProgressBar, QDialogButtonBox, QDoubleSpinBox
)

APP_NAME, VERSION = "JASS SQLite Explorer", "1.7.0"

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



class CorpusWorker(QThread):
    done=Signal(object); error=Signal(str); progress=Signal(int,str)

    def __init__(self,path,table,text_column,sample_size=50000):
        super().__init__()
        self.path=path; self.table=table; self.text_column=text_column
        self.sample_size=max(1000,int(sample_size))

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
            qt=qid(self.table); qc=qid(self.text_column)

            self._phase(4,"Counting corpus rows…")
            total=c.execute(f"SELECT COUNT(*) FROM {qt}").fetchone()[0]

            self._phase(10,"Checking NULL and empty records…")
            nulls=c.execute(f"SELECT COUNT(*) FROM {qt} WHERE {qc} IS NULL").fetchone()[0]
            empty=c.execute(
                f"SELECT COUNT(*) FROM {qt} WHERE {qc} IS NOT NULL AND CAST({qc} AS TEXT)=''"
            ).fetchone()[0]
            if self.isInterruptionRequested(): raise InterruptedError

            self._phase(18,"Calculating exact text-length statistics…")
            length=c.execute(
                f"""SELECT AVG(LENGTH(CAST({qc} AS TEXT))),
                          MIN(LENGTH(CAST({qc} AS TEXT))),
                          MAX(LENGTH(CAST({qc} AS TEXT))),
                          SUM(LENGTH(CAST({qc} AS TEXT)))
                   FROM {qt} WHERE {qc} IS NOT NULL"""
            ).fetchone()
            if self.isInterruptionRequested(): raise InterruptedError

            self._phase(30,f"Building linguistic sample ({self.sample_size:,} rows)…")
            cur=c.execute(
                f"SELECT {qc} FROM {qt} "
                f"WHERE {qc} IS NOT NULL AND CAST({qc} AS TEXT)<>'' "
                f"LIMIT ?",
                (self.sample_size,)
            )

            word_counter=Counter()
            char_counter=Counter()
            length_bins=Counter()
            token_length_bins=Counter()
            freq_buckets=Counter()
            sample_sentence_lengths=[]
            sample_word_lengths=[]
            duplicate_sample_counter=Counter()
            anomaly_chars=Counter()
            script_blocks=Counter()
            sampled=0; word_count=0
            punctuation=digits=whitespace_chars=letters=non_ascii=0

            def clean_token(tok):
                return tok.strip(
                    ".,;:!?\"“”‘’()[]{}<>|/\\\\—–…"
                ).lower()

            def block_for(cp):
                if 0x0000 <= cp <= 0x007F: return "Basic Latin"
                if 0x0080 <= cp <= 0x024F: return "Latin Extended"
                if 0x0300 <= cp <= 0x036F: return "Combining Marks"
                if 0x0900 <= cp <= 0x097F: return "Devanagari"
                if 0x0A00 <= cp <= 0x0A7F: return "Gurmukhi"
                if 0x0590 <= cp <= 0x05FF: return "Hebrew"
                if 0x0600 <= cp <= 0x06FF: return "Arabic"
                if 0x1000 <= cp <= 0x109F: return "Myanmar"
                if 0x0400 <= cp <= 0x04FF: return "Cyrillic"
                if 0x4E00 <= cp <= 0x9FFF: return "CJK"
                if 0x1F300 <= cp <= 0x1FAFF: return "Emoji/Symbols"
                return "Other"

            # Expected for a Latin-script Mizo corpus is configurable only in
            # the report for now; characters outside Basic Latin / Latin
            # Extended / common punctuation/marks are flagged as anomalies.
            for row in cur:
                if self.isInterruptionRequested(): raise InterruptedError
                text=str(row[0]); sampled += 1
                duplicate_sample_counter[text] += 1
                sample_sentence_lengths.append(len(text))

                L=len(text)
                if L<=25: length_bins["0–25"]+=1
                elif L<=50: length_bins["26–50"]+=1
                elif L<=75: length_bins["51–75"]+=1
                elif L<=100: length_bins["76–100"]+=1
                elif L<=150: length_bins["101–150"]+=1
                elif L<=250: length_bins["151–250"]+=1
                else: length_bins["251+"]+=1

                words=re.findall(r"[\w’'-]+", text, flags=re.UNICODE)
                for raw in words:
                    w=clean_token(raw)
                    if not w: continue
                    word_counter[w]+=1
                    wl=len(w)
                    sample_word_lengths.append(wl)
                    token_length_bins[min(wl,20)] += 1
                word_count += len(words)

                for ch in text:
                    char_counter[ch]+=1
                    cp=ord(ch)
                    if ch.isspace(): whitespace_chars+=1
                    if ch.isdigit(): digits+=1
                    if ch.isalpha(): letters+=1
                    if cp>127: non_ascii+=1
                    if unicodedata.category(ch).startswith("P"): punctuation+=1
                    block=block_for(cp)
                    script_blocks[block]+=1
                    # Flag script/block characters outside the expected
                    # Latin-oriented set. This is a detector, not a claim
                    # that such characters are erroneous.
                    if block not in {"Basic Latin","Latin Extended","Combining Marks"}:
                        anomaly_chars[ch]+=1

                if sampled % max(1000,self.sample_size//10)==0:
                    self._phase(
                        30+int(60*sampled/max(1,self.sample_size)),
                        f"Analyzing sample: {sampled:,}/{self.sample_size:,}…"
                    )

            top_chars=char_counter.most_common(100)
            top_words=word_counter.most_common(500)
            unique_sample_words=len(word_counter)
            avg_words=(word_count/sampled) if sampled else 0.0
            lexical_ratio=(unique_sample_words/word_count*100) if word_count else 0.0
            sample_dupe_groups=sum(1 for n in duplicate_sample_counter.values() if n>1)
            sample_dupe_rows=sum(n-1 for n in duplicate_sample_counter.values() if n>1)

            for n in word_counter.values():
                if n==1: freq_buckets["1 (hapax)"]+=1
                elif n<=5: freq_buckets["2–5"]+=1
                elif n<=10: freq_buckets["6–10"]+=1
                elif n<=100: freq_buckets["11–100"]+=1
                else: freq_buckets["101+"]+=1

            sample_sentence_lengths.sort()
            sample_word_lengths.sort()
            median_sentence=(
                sample_sentence_lengths[len(sample_sentence_lengths)//2]
                if sample_sentence_lengths else 0
            )
            median_word=(
                sample_word_lengths[len(sample_word_lengths)//2]
                if sample_word_lengths else 0
            )
            avg_word_length=(
                sum(sample_word_lengths)/len(sample_word_lengths)
                if sample_word_lengths else 0.0
            )

            self._phase(94,"Preparing corpus intelligence report…")
            avg_len,mn_len,mx_len,total_chars=length

            result={
                "path":self.path,"table":self.table,"text_column":self.text_column,
                "total":total,"nulls":nulls,"empty":empty,
                "avg_length":avg_len,"min_length":mn_len,"max_length":mx_len,
                "total_chars":total_chars,
                "sampled":sampled,"sample_words":word_count,
                "unique_sample_words":unique_sample_words,
                "avg_words_per_record":avg_words,
                "sample_lexical_ratio":lexical_ratio,
                "avg_word_length":avg_word_length,
                "median_word_length":median_word,
                "median_sentence_length":median_sentence,
                "whitespace_chars":whitespace_chars,"digits":digits,
                "letters":letters,"non_ascii":non_ascii,"punctuation":punctuation,
                "top_chars":top_chars,"top_words":top_words,
                "freq_buckets":dict(freq_buckets),
                "script_blocks":dict(script_blocks),
                "length_bins":dict(length_bins),
                "token_length_bins":dict(token_length_bins),
                "anomaly_chars":anomaly_chars.most_common(100),
                "sample_duplicate_groups":sample_dupe_groups,
                "sample_duplicate_rows":sample_dupe_rows
            }
            self._phase(100,"Corpus intelligence analysis complete.")
            c.close()
            self.done.emit(result)
        except InterruptedError:
            try: c.close()
            except Exception: pass
            self.error.emit("Corpus analysis cancelled.")
        except Exception as e:
            try: c.close()
            except Exception: pass
            self.error.emit(f"{type(e).__name__}: {e}")


class DuplicateWorker(QThread):
    done=Signal(object); error=Signal(str); progress=Signal(int,str)

    def __init__(self,path,table,text_column):
        super().__init__()
        self.path=path; self.table=table; self.text_column=text_column

    def _progress_handler(self):
        return 1 if self.isInterruptionRequested() else 0

    def run(self):
        c=None
        try:
            c=sqlite3.connect(self.path)
            c.set_progress_handler(self._progress_handler,50000)
            qt=qid(self.table); qc=qid(self.text_column)
            self.progress.emit(3,"Starting exact duplicate analysis…")
            # This is intentionally opt-in. GROUP BY over a multi-million-row
            # text column can be expensive and may require a large temp B-tree.
            sql=f"""
                SELECT
                    COUNT(*) AS duplicate_groups,
                    COALESCE(SUM(cnt-1),0) AS duplicate_rows,
                    COALESCE(MAX(cnt),0) AS largest_group
                FROM (
                    SELECT {qc} AS value, COUNT(*) AS cnt
                    FROM {qt}
                    WHERE {qc} IS NOT NULL AND CAST({qc} AS TEXT)<>''
                    GROUP BY {qc}
                    HAVING COUNT(*) > 1
                )
            """
            self.progress.emit(20,"Scanning for exact duplicate values…")
            r=c.execute(sql).fetchone()
            if self.isInterruptionRequested(): raise InterruptedError
            self.progress.emit(100,"Exact duplicate analysis complete.")
            c.close()
            self.done.emit({
                "duplicate_groups":int(r[0] or 0),
                "duplicate_rows":int(r[1] or 0),
                "largest_group":int(r[2] or 0)
            })
        except InterruptedError:
            try: c.close()
            except Exception: pass
            self.error.emit("Exact duplicate analysis cancelled.")
        except Exception as e:
            try: c.close()
            except Exception: pass
            self.error.emit(f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f"{APP_NAME} v{VERSION}"); self.resize(1550,950)
        self.path=""; self.table_name=""; self.rows=[]; self.cols=[]; self.history=[]; self.schema_data={}; self.load_generation=0
        self.saved_queries=[]; self.load_saved_queries()
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
        a=QAction("Open Investigation",self); a.triggered.connect(lambda: self.tabs.setCurrentWidget(self.investigation_widget)); m.addAction(a)
        a=QAction("Open Corpus Lab",self); a.triggered.connect(lambda: self.tabs.setCurrentWidget(self.corpus_widget)); m.addAction(a)
        m=self.menuBar().addMenu("&Help"); a=QAction("Read-Only Safety",self); a.triggered.connect(self.safety); m.addAction(a)

    def _ui(self):
        root=QVBoxLayout(); top=QHBoxLayout()
        self.db=QLabel("No database open"); self.db.setStyleSheet("font-weight:bold"); top.addWidget(self.db,1); top.addWidget(QLabel("● READ-ONLY"))
        root.addLayout(top)
        sp=QSplitter(Qt.Horizontal); self.tree=QTreeWidget(); self.tree.setHeaderLabels(["Database Objects"]); self.tree.itemClicked.connect(self.clicked); sp.addWidget(self.tree)
        self.tabs=QTabWidget(); sp.addWidget(self.tabs); sp.setSizes([310,1240]); root.addWidget(sp,1)
        self.tabs.addTab(self.dashboard(),"Dashboard"); self.tabs.addTab(self.data(),"Data Browser"); self.tabs.addTab(self.search(),"FTS Search"); self.tabs.addTab(self.stats_view(),"Statistics"); self.tabs.addTab(self.schema(),"Schema"); self.tabs.addTab(self.query(),"SQL Console"); self.tabs.addTab(self.investigation(),"Investigation"); self.tabs.addTab(self.corpus_lab(),"Corpus Lab"); self.tabs.addTab(self.report(),"Reports")
        w=QWidget(); w.setLayout(root); self.setCentralWidget(w); self.setStatusBar(QStatusBar()); self.statusBar().showMessage("Open an SQLite database.")

    def dashboard(self):
        w=QWidget(); l=QVBoxLayout(w); row=QHBoxLayout(); self.stat={}
        for k,t in (("tables","Tables"),("views","Views"),("indexes","Indexes"),("triggers","Triggers"),("rows","Rows"),("fts","FTS")):
            f=QFrame(); fl=QVBoxLayout(f); v=QLabel("—"); v.setFont(QFont("Sans Serif",20,QFont.Bold)); fl.addWidget(v); fl.addWidget(QLabel(t)); row.addWidget(f); self.stat[k]=v
        l.addLayout(row); self.dash=QTextEdit(); self.dash.setReadOnly(True); l.addWidget(self.dash,1); return w

    def data(self):
        self.data_widget=QWidget(); w=self.data_widget; l=QVBoxLayout(w); b=QHBoxLayout()
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
        self.fts_open_source=QPushButton("Open Source Record"); self.fts_open_source.clicked.connect(self.open_fts_source)
        b.addWidget(QLabel("FTS index")); b.addWidget(self.fts_combo); b.addWidget(self.fts_query,1); b.addWidget(QLabel("Limit")); b.addWidget(self.fts_limit); b.addWidget(q); b.addWidget(self.fts_open_source); l.addLayout(b)
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
        self.query_widget=QWidget(); w=self.query_widget; l=QVBoxLayout(w); l.addWidget(QLabel("Read-only: SELECT, WITH, PRAGMA and EXPLAIN."))
        self.sql=QPlainTextEdit("SELECT name,type FROM sqlite_master ORDER BY type,name;"); self.sql.setFont(QFont("Monospace",11)); l.addWidget(self.sql,1)
        qb=QHBoxLayout()
        q=QPushButton("Run Query"); q.clicked.connect(self.run_query); qb.addWidget(q)
        q=QPushButton("Save Query"); q.clicked.connect(self.save_current_query); qb.addWidget(q)
        q=QPushButton("Clear"); q.clicked.connect(lambda: self.sql.clear()); qb.addWidget(q)
        l.addLayout(qb)
        self.qt=QTableWidget(); self.qt.setEditTriggers(QAbstractItemView.NoEditTriggers); self.qt.setAlternatingRowColors(True); l.addWidget(self.qt,1); self.qi=QLabel(); l.addWidget(self.qi)
        return w

    def investigation(self):
        self.investigation_widget=QWidget(); w=self.investigation_widget; l=QVBoxLayout(w)

        top=QHBoxLayout()
        top.addWidget(QLabel("Saved Queries"))
        self.saved_combo=QComboBox(); self.saved_combo.setMinimumWidth(300)
        self.saved_combo.currentIndexChanged.connect(self.load_saved_query)
        top.addWidget(self.saved_combo,1)
        for text,fn in (("Load",self.load_saved_query),("Save Current SQL",self.save_current_query),("Delete",self.delete_saved_query)):
            q=QPushButton(text); q.clicked.connect(fn); top.addWidget(q)
        l.addLayout(top)

        split=QSplitter(Qt.Horizontal)

        left=QWidget(); ll=QVBoxLayout(left)
        ll.addWidget(QLabel("Query History — current session"))
        self.history_table=QTableWidget(); self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Type","Query","Time","Rows / ms"])
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.cellDoubleClicked.connect(self.history_double_click)
        ll.addWidget(self.history_table,1)
        split.addWidget(left)

        right=QWidget(); rl=QVBoxLayout(right)
        rl.addWidget(QLabel("Investigation notes"))
        self.investigation_notes=QTextEdit()
        self.investigation_notes.setReadOnly(True)
        self.investigation_notes.setPlainText(
            "Use this workspace to revisit saved SQL and FTS investigations.\\n\\n"
            "• Double-click a history item to load its SQL into the console.\\n"
            "• Saved queries are stored locally in your user configuration.\\n"
            "• FTS results can be mapped back to their source record.\\n"
            "• The application remains read-only."
        )
        rl.addWidget(self.investigation_notes,1)
        split.addWidget(right)
        split.setSizes([900,500])
        l.addWidget(split,1)
        self.refresh_saved_combo()
        return w

    def corpus_lab(self):
        self.corpus_widget=QWidget(); w=self.corpus_widget; l=QVBoxLayout(w)

        b=QHBoxLayout()
        self.corpus_table=QComboBox(); self.corpus_table.setMinimumWidth(210)
        self.corpus_column=QComboBox(); self.corpus_column.setMinimumWidth(210)
        self.corpus_sample=QSpinBox(); self.corpus_sample.setRange(1000,500000); self.corpus_sample.setValue(50000)
        b.addWidget(QLabel("Table")); b.addWidget(self.corpus_table)
        b.addWidget(QLabel("Text column")); b.addWidget(self.corpus_column)
        b.addWidget(QLabel("Sample")); b.addWidget(self.corpus_sample)

        self.corpus_run=QPushButton("Run Corpus Intelligence"); self.corpus_run.clicked.connect(self.run_corpus_analysis); b.addWidget(self.corpus_run)
        self.corpus_dup=QPushButton("Exact Duplicate Check"); self.corpus_dup.clicked.connect(self.run_duplicate_check); b.addWidget(self.corpus_dup)
        self.corpus_cancel=QPushButton("Cancel"); self.corpus_cancel.setEnabled(False); self.corpus_cancel.clicked.connect(self.cancel_corpus); b.addWidget(self.corpus_cancel)
        l.addLayout(b)

        self.corpus_progress=QLabel("Open a database to begin.")
        self.corpus_bar=QProgressBar(); self.corpus_bar.setRange(0,100)
        pb=QHBoxLayout(); pb.addWidget(self.corpus_progress); pb.addWidget(self.corpus_bar,1); l.addLayout(pb)

        self.corpus_tabs=QTabWidget()

        self.corpus_report=QPlainTextEdit(); self.corpus_report.setReadOnly(True)
        self.corpus_tabs.addTab(self.corpus_report,"Overview")

        vocab=QWidget(); vl=QVBoxLayout(vocab)
        vb=QHBoxLayout()
        self.vocab_filter=QLineEdit(); self.vocab_filter.setPlaceholderText("Filter vocabulary…")
        self.vocab_min=QSpinBox(); self.vocab_min.setRange(1,100000000); self.vocab_min.setValue(1)
        self.vocab_sort=QComboBox(); self.vocab_sort.addItems(["Frequency","Alphabetical"])
        self.vocab_source=QPushButton("Investigate Token"); self.vocab_source.clicked.connect(self.investigate_selected_token)
        self.vocab_export=QPushButton("Export Vocabulary"); self.vocab_export.clicked.connect(self.export_vocabulary)
        vb.addWidget(QLabel("Search")); vb.addWidget(self.vocab_filter,1)
        vb.addWidget(QLabel("Min frequency")); vb.addWidget(self.vocab_min)
        vb.addWidget(QLabel("Sort")); vb.addWidget(self.vocab_sort)
        vb.addWidget(self.vocab_source); vb.addWidget(self.vocab_export)
        vl.addLayout(vb)
        self.corpus_words=QTableWidget(); self.corpus_words.setColumnCount(4)
        self.corpus_words.setHorizontalHeaderLabels(["#","Token","Frequency","% of sample tokens"])
        self.corpus_words.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.corpus_words.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.corpus_words.cellDoubleClicked.connect(lambda r,c: self.find_vocabulary_sources())
        vl.addWidget(self.corpus_words,1)
        self.corpus_tabs.addTab(vocab,"Vocabulary")

        length_tab=QWidget(); ll=QVBoxLayout(length_tab)
        self.length_report=QPlainTextEdit(); self.length_report.setReadOnly(True); ll.addWidget(self.length_report)
        self.length_table=QTableWidget(); self.length_table.setColumnCount(3)
        self.length_table.setHorizontalHeaderLabels(["Sentence length","Sample records","Percentage"])
        self.length_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ll.addWidget(self.length_table,1)
        self.token_length_table=QTableWidget(); self.token_length_table.setColumnCount(3)
        self.token_length_table.setHorizontalHeaderLabels(["Token length","Tokens","Percentage"])
        self.token_length_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ll.addWidget(self.token_length_table,1)
        self.corpus_tabs.addTab(length_tab,"Sentence Length")

        unicode_tab=QWidget(); ul=QVBoxLayout(unicode_tab)
        self.unicode_report=QPlainTextEdit(); self.unicode_report.setReadOnly(True); ul.addWidget(self.unicode_report)
        self.corpus_chars=QTableWidget(); self.corpus_chars.setColumnCount(4)
        self.corpus_chars.setHorizontalHeaderLabels(["#","Character","Unicode","Frequency"])
        self.corpus_chars.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ul.addWidget(self.corpus_chars,1)
        ub=QHBoxLayout()
        self.unicode_investigate=QPushButton("Investigate Selected Character")
        self.unicode_investigate.clicked.connect(self.investigate_selected_character)
        ub.addWidget(self.unicode_investigate); ub.addStretch(1)
        ul.addLayout(ub)
        self.corpus_tabs.addTab(unicode_tab,"Unicode")

        stats_tab=QWidget(); sl=QVBoxLayout(stats_tab)
        self.vocab_stats=QPlainTextEdit(); self.vocab_stats.setReadOnly(True); sl.addWidget(self.vocab_stats)
        self.freq_table=QTableWidget(); self.freq_table.setColumnCount(3)
        self.freq_table.setHorizontalHeaderLabels(["Frequency bucket","Unique tokens","% of vocabulary"])
        self.freq_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        sl.addWidget(self.freq_table,1)
        self.corpus_tabs.addTab(stats_tab,"Vocabulary Stats")

        anomaly_tab=QWidget(); al=QVBoxLayout(anomaly_tab)
        self.anomaly_report=QPlainTextEdit(); self.anomaly_report.setReadOnly(True); al.addWidget(self.anomaly_report)
        self.anomaly_table=QTableWidget(); self.anomaly_table.setColumnCount(4)
        self.anomaly_table.setHorizontalHeaderLabels(["#","Character","Unicode / Name","Frequency"])
        self.anomaly_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        al.addWidget(self.anomaly_table,1)
        self.corpus_tabs.addTab(anomaly_tab,"Anomalies")

        dup_tab=QWidget(); dl=QVBoxLayout(dup_tab)
        self.duplicate_report=QPlainTextEdit(); self.duplicate_report.setReadOnly(True)
        self.duplicate_report.setPlainText(
            "Exact duplicate analysis has not been run.\n\n"
            "Use “Exact Duplicate Check” to perform an exact GROUP BY over the "
            "selected text column. On a multi-million-row corpus this can be "
            "substantially slower than the sample-based analysis."
        )
        dl.addWidget(self.duplicate_report,1)
        self.corpus_tabs.addTab(dup_tab,"Duplicates")

        # Corpus Investigation: move from aggregate statistics to actual
        # source-record inspection without modifying the database.
        inv=QWidget(); il=QVBoxLayout(inv)
        ib=QHBoxLayout()
        self.inv_mode=QComboBox()
        self.inv_mode.addItems([
            "Word / phrase",
            "Unicode character",
            "Longest records",
            "Shortest records",
            "Contains text",
        ])
        self.inv_target=QLineEdit()
        self.inv_target.setPlaceholderText("Enter a word, phrase, or Unicode character…")
        self.inv_limit=QSpinBox(); self.inv_limit.setRange(1,500); self.inv_limit.setValue(50)
        self.inv_run=QPushButton("Investigate"); self.inv_run.clicked.connect(self.run_corpus_investigation)
        self.inv_export=QPushButton("Export Results"); self.inv_export.clicked.connect(self.export_investigation)
        ib.addWidget(QLabel("Mode")); ib.addWidget(self.inv_mode)
        ib.addWidget(QLabel("Target")); ib.addWidget(self.inv_target,1)
        ib.addWidget(QLabel("Limit")); ib.addWidget(self.inv_limit)
        ib.addWidget(self.inv_run); ib.addWidget(self.inv_export)
        il.addLayout(ib)

        self.inv_info=QPlainTextEdit()
        self.inv_info.setReadOnly(True)
        self.inv_info.setMaximumHeight(130)
        self.inv_info.setPlainText(
            "Corpus Investigation moves from statistics to the actual source records "
            "behind a result. It is read-only and bounded.\n\n"
            "Word / phrase and Unicode searches use a portable LIKE search. "
            "Longest / Shortest records inspect the selected text column directly."
        )
        il.addWidget(self.inv_info)

        self.inv_table=QTableWidget()
        self.inv_table.setColumnCount(3)
        self.inv_table.setHorizontalHeaderLabels(["Row ID","Length","Source record"])
        self.inv_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.inv_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.inv_table.setAlternatingRowColors(True)
        self.inv_table.cellDoubleClicked.connect(self.open_investigation_record)
        il.addWidget(self.inv_table,1)
        self.corpus_tabs.addTab(inv,"Investigation")

        # Corpus Quality Investigator: bounded, read-only inspection for
        # suspiciously long, repetitive, web/SEO-like, URL-heavy, or
        # otherwise unusual corpus records.
        qtab=QWidget(); ql=QVBoxLayout(qtab)

        qb=QHBoxLayout()
        self.quality_mode=QComboBox()
        self.quality_mode.addItems([
            "Quality scan — sample",
            "Longest records",
            "Most repetitive records",
            "Web / SEO pattern candidates",
            "URL / email candidates",
            "Very long records",
        ])
        self.quality_sample=QSpinBox(); self.quality_sample.setRange(100,100000); self.quality_sample.setValue(50000)
        self.quality_limit=QSpinBox(); self.quality_limit.setRange(10,500); self.quality_limit.setValue(100)
        self.quality_run=QPushButton("Run Quality Investigation")
        self.quality_run.clicked.connect(self.run_quality_investigation)
        self.quality_export=QPushButton("Export Findings")
        self.quality_export.clicked.connect(self.export_quality_findings)
        qb.addWidget(QLabel("Mode")); qb.addWidget(self.quality_mode)
        qb.addWidget(QLabel("Sample")); qb.addWidget(self.quality_sample)
        qb.addWidget(QLabel("Results")); qb.addWidget(self.quality_limit)
        qb.addWidget(self.quality_run); qb.addWidget(self.quality_export)
        ql.addLayout(qb)

        self.quality_threshold=QDoubleSpinBox()
        self.quality_threshold.setRange(0.0,100.0); self.quality_threshold.setDecimals(1)
        self.quality_threshold.setValue(35.0)
        self.quality_threshold.setSuffix(" minimum score")
        qtrow=QHBoxLayout()
        qtrow.addWidget(QLabel("Flag threshold"))
        qtrow.addWidget(self.quality_threshold)
        qtrow.addWidget(QLabel("Higher score = more unusual"))
        qtrow.addStretch(1)
        ql.addLayout(qtrow)

        self.quality_info=QPlainTextEdit()
        self.quality_info.setReadOnly(True)
        self.quality_info.setMaximumHeight(120)
        self.quality_info.setPlainText(
            "Quality Investigator is diagnostic only. It does not delete, "
            "rewrite, or modify corpus records.\n\n"
            "Scores combine measurable signals such as extreme length, "
            "token repetition, URLs/emails, repeated phrases, web/SEO-like "
            "phrases, digits, punctuation, and script-mix indicators. "
            "A high score means 'review', not 'incorrect'."
        )
        ql.addWidget(self.quality_info)

        self.quality_table=QTableWidget()
        self.quality_table.setColumnCount(8)
        self.quality_table.setHorizontalHeaderLabels([
            "Row ID","Score","Level","Length","Repeat %","URLs","Signals","Preview"
        ])
        self.quality_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.quality_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.quality_table.setAlternatingRowColors(True)
        self.quality_table.cellDoubleClicked.connect(self.open_quality_record)
        ql.addWidget(self.quality_table,1)

        self.corpus_tabs.addTab(qtab,"Quality Investigator")

        l.addWidget(self.corpus_tabs,1)
        return w

    def load_saved_queries(self):
        self.saved_query_path=os.path.expanduser("~/.config/jass_sqlite_explorer_saved_queries.json")
        try:
            with open(self.saved_query_path,encoding="utf-8") as f:
                data=json.load(f)
            self.saved_queries=data if isinstance(data,list) else []
        except Exception:
            self.saved_queries=[]

    def persist_saved_queries(self):
        try:
            os.makedirs(os.path.dirname(self.saved_query_path),exist_ok=True)
            with open(self.saved_query_path,"w",encoding="utf-8") as f:
                json.dump(self.saved_queries,f,ensure_ascii=False,indent=2)
        except Exception as e:
            self.err(f"Could not save query library: {e}")

    def refresh_saved_combo(self):
        if not hasattr(self,"saved_combo"): return
        self.saved_combo.blockSignals(True); self.saved_combo.clear()
        self.saved_combo.addItem("— Select saved query —")
        for q in self.saved_queries:
            self.saved_combo.addItem(q.get("name","Unnamed"))
        self.saved_combo.blockSignals(False)

    def save_current_query(self):
        sql=self.sql.toPlainText().strip()
        if not sql: return QMessageBox.information(self,"Save Query","Enter a SQL query first.")
        name,ok=QInputDialog.getText(self,"Save Query","Name:",QLineEdit.Normal,sql.splitlines()[0][:60])
        if not ok or not name.strip(): return
        self.saved_queries.append({"name":name.strip(),"sql":sql,"saved_at":datetime.now().isoformat(timespec="seconds")})
        self.persist_saved_queries(); self.refresh_saved_combo()
        self.statusBar().showMessage(f"Saved query: {name.strip()}")

    def load_saved_query(self,index=None):
        if index is None:
            index=self.saved_combo.currentIndex()
        if index<=0 or index>len(self.saved_queries): return
        self.sql.setPlainText(self.saved_queries[index-1].get("sql",""))
        self.tabs.setCurrentWidget(self.query_widget)

    def delete_saved_query(self):
        idx=self.saved_combo.currentIndex()
        if idx<=0 or idx>len(self.saved_queries): return
        q=self.saved_queries.pop(idx-1); self.persist_saved_queries(); self.refresh_saved_combo()
        self.statusBar().showMessage(f"Deleted saved query: {q.get('name','')}")

    def history_double_click(self,row,col):
        if row<0 or row>=len(self.history): return
        item=self.history[row]
        if len(item)>=2:
            self.sql.setPlainText(str(item[1]))
            self.tabs.setCurrentWidget(self.query_widget)

    def refresh_history_view(self):
        if not hasattr(self,"history_table"): return
        self.history_table.setRowCount(len(self.history))
        for i,item in enumerate(self.history):
            vals=[item[0] if len(item)>0 else "", item[1] if len(item)>1 else "",
                  item[2] if len(item)>2 else "", item[3] if len(item)>3 else ""]
            for j,v in enumerate(vals): self.history_table.setItem(i,j,QTableWidgetItem(str(v)))
        self.history_table.resizeColumnsToContents()
        if self.history_table.columnWidth(1)>650: self.history_table.setColumnWidth(1,650)

    def populate_corpus_selectors(self):
        if not hasattr(self,"corpus_table"): return
        self.corpus_table.blockSignals(True); self.corpus_table.clear(); self.corpus_column.clear()
        tables=[o for o in self.schema_data.get("objects",[])
                if o["type"]=="table" and not o.get("fts_virtual") and not o.get("fts_shadow")]
        for o in tables: self.corpus_table.addItem(o["name"])
        preferred_names=("sentences","sentence","corpus","documents","document","texts","text","entries","data")
        chosen=-1
        for pref in preferred_names:
            for i in range(self.corpus_table.count()):
                if self.corpus_table.itemText(i).lower()==pref: chosen=i; break
            if chosen>=0: break
        if chosen<0 and tables:
            candidates=[(int(o.get("rows") or 0),i) for i,o in enumerate(tables)]
            chosen=max(candidates)[1] if candidates else 0
        if chosen>=0: self.corpus_table.setCurrentIndex(chosen)
        self.corpus_table.blockSignals(False)
        try: self.corpus_table.currentTextChanged.disconnect(self.corpus_table_changed)
        except Exception: pass
        self.corpus_table.currentTextChanged.connect(self.corpus_table_changed)
        self.corpus_table_changed(self.corpus_table.currentText())

    def corpus_table_changed(self,name):
        if not self.path or not name: return
        try:
            c=sqlite3.connect(self.path)
            cols=c.execute(f"PRAGMA table_info({qid(name)})").fetchall(); c.close()
            self.corpus_column.blockSignals(True); self.corpus_column.clear()
            candidates=[]
            for r in cols:
                typ=(r[2] or "").upper()
                if "CHAR" in typ or "TEXT" in typ or not typ: candidates.append(r[1])
            preferred=("text","sentence","content","body","document","native_word","romanized_word","word")
            ordered=[]
            for pref in preferred:
                ordered.extend([x for x in candidates if x.lower()==pref and x not in ordered])
            ordered.extend([x for x in candidates if x not in ordered])
            for name in ordered: self.corpus_column.addItem(name)
            self.corpus_column.blockSignals(False)
        except Exception:
            pass

    def run_corpus_analysis(self):
        if not self.path: return QMessageBox.warning(self,APP_NAME,"Open a database first.")
        table=self.corpus_table.currentText(); col=self.corpus_column.currentText()
        if not table or not col: return QMessageBox.warning(self,"Corpus Lab","Select a table and text column.")
        self.corpus_run.setEnabled(False); self.corpus_dup.setEnabled(False); self.corpus_cancel.setEnabled(True)
        self.corpus_bar.setValue(0); self.corpus_progress.setText("Starting corpus intelligence…")
        self.cw=CorpusWorker(self.path,table,col,self.corpus_sample.value())
        self.cw.progress.connect(lambda p,t:(self.corpus_bar.setValue(p),self.corpus_progress.setText(t)))
        self.cw.done.connect(self.corpus_done); self.cw.error.connect(self.corpus_error); self.cw.start()

    def run_duplicate_check(self):
        if not self.path: return QMessageBox.warning(self,APP_NAME,"Open a database first.")
        table=self.corpus_table.currentText(); col=self.corpus_column.currentText()
        if not table or not col: return QMessageBox.warning(self,"Duplicates","Select a table and text column.")
        ans=QMessageBox.question(
            self,"Exact Duplicate Check",
            "This performs an exact GROUP BY over the selected text column. "
            "On a 4-million-row corpus it may be slow and use temporary SQLite storage.\n\nContinue?",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No
        )
        if ans!=QMessageBox.Yes: return
        self.corpus_run.setEnabled(False); self.corpus_dup.setEnabled(False); self.corpus_cancel.setEnabled(True)
        self.corpus_bar.setValue(0); self.corpus_progress.setText("Starting exact duplicate analysis…")
        self.dw=DuplicateWorker(self.path,table,col)
        self.dw.progress.connect(lambda p,t:(self.corpus_bar.setValue(p),self.corpus_progress.setText(t)))
        self.dw.done.connect(self.duplicate_done); self.dw.error.connect(self.corpus_error); self.dw.start()
        self.corpus_tabs.setCurrentIndex(5)

    def cancel_corpus(self):
        for worker in (getattr(self,"cw",None),getattr(self,"dw",None)):
            if worker and worker.isRunning(): worker.requestInterruption()
        self.corpus_cancel.setEnabled(False); self.corpus_progress.setText("Cancelling…")

    def corpus_error(self,msg):
        self.corpus_run.setEnabled(True); self.corpus_dup.setEnabled(True); self.corpus_cancel.setEnabled(False)
        self.corpus_progress.setText(msg)
        if "cancelled" not in msg.lower(): QMessageBox.critical(self,"Corpus Analysis",msg)

    def corpus_done(self,d):
        self.corpus_run.setEnabled(True); self.corpus_dup.setEnabled(True); self.corpus_cancel.setEnabled(False)
        self.corpus_bar.setValue(100); self.corpus_progress.setText("Corpus intelligence analysis complete.")
        total=d["total"]; nulls=d["nulls"]; empty=d["empty"]
        null_pct=(nulls/total*100) if total else 0.0
        empty_pct=(empty/total*100) if total else 0.0
        vocab=len(d["top_words"]); anomaly_total=sum(n for _,n in d["anomaly_chars"])

        report=f"""CORPUS INTELLIGENCE REPORT

Database: {d["path"]}
Table: {d["table"]}
Text column: {d["text_column"]}

STRUCTURE
Records:              {total:,}
NULL records:         {nulls:,} ({null_pct:.3f}%)
Empty records:        {empty:,} ({empty_pct:.3f}%)

EXACT TEXT LENGTH
Average characters:   {d["avg_length"]:.2f}
Minimum characters:   {d["min_length"]:,}
Maximum characters:   {d["max_length"]:,}
Total characters:      {d["total_chars"]:,}

LINGUISTIC SAMPLE
Sample records:       {d["sampled"]:,}
Sample tokens:        {d["sample_words"]:,}
Unique sample tokens: {d["unique_sample_words"]:,}
Avg tokens/record:    {d["avg_words_per_record"]:.2f}
Sample lexical ratio: {d["sample_lexical_ratio"]:.2f}%

WORD LENGTH
Average word length:  {d["avg_word_length"]:.2f}
Median word length:   {d["median_word_length"]}
Median sentence chars:{d["median_sentence_length"]}

CHARACTER CLASSES IN SAMPLE
Letters:              {d["letters"]:,}
Whitespace:           {d["whitespace_chars"]:,}
Digits:               {d["digits"]:,}
Punctuation:          {d["punctuation"]:,}
Non-ASCII:            {d["non_ascii"]:,}

VOCABULARY
Unique normalized tokens: {d["unique_sample_words"]:,}
Hapax tokens (freq=1):    {d["freq_buckets"].get("1 (hapax)",0):,}
Tokens with freq 2–5:     {d["freq_buckets"].get("2–5",0):,}
Tokens with freq 6–10:    {d["freq_buckets"].get("6–10",0):,}
Tokens with freq 11–100:  {d["freq_buckets"].get("11–100",0):,}
Tokens with freq 101+:    {d["freq_buckets"].get("101+",0):,}

UNICODE / SCRIPT HINTS
{chr(10).join(f"  {k}: {v:,}" for k,v in sorted(d["script_blocks"].items(), key=lambda x:-x[1]))}

POTENTIAL SCRIPT ANOMALIES
Characters outside Basic Latin / Latin Extended / Combining Marks:
{anomaly_total:,} character occurrences
See the Anomalies tab for the top characters.

SAMPLE DUPLICATE INDICATOR
Duplicate groups:     {d["sample_duplicate_groups"]:,}
Duplicate surplus:    {d["sample_duplicate_rows"]:,}

NOTES
• Records, NULL/empty counts and text-length statistics are exact.
• Vocabulary, word-length, character frequency and anomaly counts use the bounded sample.
• Anomaly detection flags characters for inspection; it does not declare them errors.
• Exact whole-corpus duplicate analysis is available separately.
• Tokenization is diagnostic and not a language-specific gold-standard tokenizer.
"""
        self.corpus_report.setPlainText(report)

        self._corpus_words_data=list(d["top_words"])
        self._corpus_total_words=max(1,d["sample_words"])
        try:
            self.vocab_filter.textChanged.disconnect(self._refresh_vocabulary_table)
        except Exception:
            pass
        try:
            self.vocab_min.valueChanged.disconnect(self._refresh_vocabulary_table)
        except Exception:
            pass
        try:
            self.vocab_sort.currentTextChanged.disconnect(self._refresh_vocabulary_table)
        except Exception:
            pass
        self.vocab_filter.textChanged.connect(self._refresh_vocabulary_table)
        self.vocab_min.valueChanged.connect(self._refresh_vocabulary_table)
        self.vocab_sort.currentTextChanged.connect(self._refresh_vocabulary_table)
        self._refresh_vocabulary_table()

        self.length_report.setPlainText(
            "SENTENCE / TOKEN LENGTH REPORT\n\n"
            f"Sample size: {d['sampled']:,}\n"
            f"Exact corpus average characters: {d['avg_length']:.2f}\n"
            f"Sample median sentence characters: {d['median_sentence_length']}\n"
            f"Average word length: {d['avg_word_length']:.2f}\n"
            f"Median word length: {d['median_word_length']}"
        )
        bins=("0–25","26–50","51–75","76–100","101–150","151–250","251+")
        self.length_table.setRowCount(len(bins))
        for i,k in enumerate(bins):
            n=d["length_bins"].get(k,0)
            self.length_table.setItem(i,0,QTableWidgetItem(k))
            self.length_table.setItem(i,1,QTableWidgetItem(f"{n:,}"))
            self.length_table.setItem(i,2,QTableWidgetItem(f"{n/max(1,d['sampled'])*100:.2f}%"))
        self.length_table.resizeColumnsToContents()

        token_bins=[(str(i),d["token_length_bins"].get(i,0)) for i in range(1,20)]
        token_bins.append(("20+",d["token_length_bins"].get(20,0)))
        self.token_length_table.setRowCount(len(token_bins))
        tok_total=max(1,d["sample_words"])
        for i,(k,n) in enumerate(token_bins):
            self.token_length_table.setItem(i,0,QTableWidgetItem(k))
            self.token_length_table.setItem(i,1,QTableWidgetItem(f"{n:,}"))
            self.token_length_table.setItem(i,2,QTableWidgetItem(f"{n/tok_total*100:.2f}%"))
        self.token_length_table.resizeColumnsToContents()

        self.unicode_report.setPlainText(
            "UNICODE / CHARACTER REPORT\n\n"
            f"Distinct characters observed (top 100 shown): {len(d['top_chars']):,}\n"
            f"Non-ASCII character occurrences: {d['non_ascii']:,}\n\n"
            "Broad code-point ranges observed:\n" +
            (chr(10).join(f"  {k}: {v:,}" for k,v in sorted(d["script_blocks"].items(), key=lambda x:-x[1]))
             or "  None")
        )
        chars=d["top_chars"]; self.corpus_chars.setRowCount(len(chars))
        for i,(ch,n) in enumerate(chars):
            name=unicodedata.name(ch,"UNKNOWN")
            display=f"{ch}" if ch not in ("\n","\r","\t"," ") else repr(ch)
            self.corpus_chars.setItem(i,0,QTableWidgetItem(str(i+1)))
            self.corpus_chars.setItem(i,1,QTableWidgetItem(display))
            self.corpus_chars.setItem(i,2,QTableWidgetItem(f"U+{ord(ch):04X} {name}"))
            self.corpus_chars.setItem(i,3,QTableWidgetItem(f"{n:,}"))
        self.corpus_chars.resizeColumnsToContents()
        if self.corpus_chars.columnWidth(2)>500: self.corpus_chars.setColumnWidth(2,500)

        self.vocab_stats.setPlainText(
            "VOCABULARY STATISTICS\n\n"
            f"Unique normalized tokens: {d['unique_sample_words']:,}\n"
            f"Total tokens: {d['sample_words']:,}\n"
            f"Lexical ratio: {d['sample_lexical_ratio']:.2f}%\n\n"
            "Frequency buckets are based on the bounded sample."
        )
        buckets=["1 (hapax)","2–5","6–10","11–100","101+"]
        self.freq_table.setRowCount(len(buckets))
        vtotal=max(1,d["unique_sample_words"])
        for i,k in enumerate(buckets):
            n=d["freq_buckets"].get(k,0)
            self.freq_table.setItem(i,0,QTableWidgetItem(k))
            self.freq_table.setItem(i,1,QTableWidgetItem(f"{n:,}"))
            self.freq_table.setItem(i,2,QTableWidgetItem(f"{n/vtotal*100:.2f}%"))
        self.freq_table.resizeColumnsToContents()

        self.anomaly_report.setPlainText(
            "UNICODE / SCRIPT ANOMALY DETECTOR\n\n"
            "The detector flags characters whose broad Unicode range is outside "
            "Basic Latin, Latin Extended, and Combining Marks.\n\n"
            "These are candidates for inspection, NOT automatic errors.\n"
            f"Flagged character occurrences in sample: {anomaly_total:,}\n"
            f"Distinct flagged characters shown: {len(d['anomaly_chars']):,}"
        )
        self.anomaly_table.setRowCount(len(d["anomaly_chars"]))
        for i,(ch,n) in enumerate(d["anomaly_chars"]):
            self.anomaly_table.setItem(i,0,QTableWidgetItem(str(i+1)))
            self.anomaly_table.setItem(i,1,QTableWidgetItem(repr(ch) if ch.isspace() else ch))
            self.anomaly_table.setItem(i,2,QTableWidgetItem(f"U+{ord(ch):04X} {unicodedata.name(ch,'UNKNOWN')}"))
            self.anomaly_table.setItem(i,3,QTableWidgetItem(f"{n:,}"))
        self.anomaly_table.resizeColumnsToContents()
        if self.anomaly_table.columnWidth(2)>500: self.anomaly_table.setColumnWidth(2,500)

        self.corpus_tabs.setCurrentIndex(0)

    def _refresh_vocabulary_table(self):
        data=list(getattr(self,"_corpus_words_data",[]))
        filt=getattr(self,"vocab_filter",None)
        minbox=getattr(self,"vocab_min",None)
        sortbox=getattr(self,"vocab_sort",None)
        needle=filt.text().strip().lower() if filt else ""
        minimum=minbox.value() if minbox else 1
        if needle: data=[x for x in data if needle in x[0].lower()]
        data=[x for x in data if x[1]>=minimum]
        if sortbox and sortbox.currentText()=="Alphabetical":
            data.sort(key=lambda x:x[0].casefold())
        else:
            data.sort(key=lambda x:(-x[1],x[0].casefold()))
        self.corpus_words.setRowCount(len(data))
        total_words=max(1,getattr(self,"_corpus_total_words",1))
        for i,(word,n) in enumerate(data):
            self.corpus_words.setItem(i,0,QTableWidgetItem(str(i+1)))
            self.corpus_words.setItem(i,1,QTableWidgetItem(word))
            self.corpus_words.setItem(i,2,QTableWidgetItem(f"{n:,}"))
            self.corpus_words.setItem(i,3,QTableWidgetItem(f"{n/total_words*100:.3f}%"))
        self.corpus_words.resizeColumnsToContents()
        if self.corpus_words.columnWidth(1)>350: self.corpus_words.setColumnWidth(1,350)

    def export_vocabulary(self):
        data=list(getattr(self,"_corpus_words_data",[]))
        if not data: return QMessageBox.information(self,"Vocabulary","Run Corpus Intelligence first.")
        p,_=QFileDialog.getSaveFileName(self,"Export Vocabulary","","CSV files (*.csv)")
        if not p: return
        try:
            with open(p,"w",newline="",encoding="utf-8") as f:
                w=csv.writer(f); w.writerow(["rank","token","frequency","percent_of_sample_tokens"])
                total=max(1,getattr(self,"_corpus_total_words",1))
                for i,(word,n) in enumerate(data,1):
                    w.writerow([i,word,n,f"{n/total*100:.6f}"])
            self.statusBar().showMessage(f"Vocabulary exported: {p}")
        except Exception as e:
            self.err(f"Vocabulary export failed: {e}")


    def load_saved_queries(self):
        self.saved_query_path=os.path.expanduser("~/.config/jass_sqlite_explorer_saved_queries.json")
        try:
            with open(self.saved_query_path,encoding="utf-8") as f:
                data=json.load(f)
            self.saved_queries=data if isinstance(data,list) else []
        except Exception:
            self.saved_queries=[]

    def persist_saved_queries(self):
        try:
            os.makedirs(os.path.dirname(self.saved_query_path),exist_ok=True)
            with open(self.saved_query_path,"w",encoding="utf-8") as f:
                json.dump(self.saved_queries,f,ensure_ascii=False,indent=2)
        except Exception as e:
            self.err(f"Could not save query library: {e}")

    def refresh_saved_combo(self):
        if not hasattr(self,"saved_combo"): return
        self.saved_combo.blockSignals(True); self.saved_combo.clear()
        self.saved_combo.addItem("— Select saved query —")
        for q in self.saved_queries:
            self.saved_combo.addItem(q.get("name","Unnamed"))
        self.saved_combo.blockSignals(False)

    def save_current_query(self):
        sql=self.sql.toPlainText().strip()
        if not sql: return QMessageBox.information(self,"Save Query","Enter a SQL query first.")
        name,ok=QInputDialog.getText(self,"Save Query","Name:",QLineEdit.Normal,sql.splitlines()[0][:60])
        if not ok or not name.strip(): return
        self.saved_queries.append({"name":name.strip(),"sql":sql,"saved_at":datetime.now().isoformat(timespec="seconds")})
        self.persist_saved_queries(); self.refresh_saved_combo()
        self.statusBar().showMessage(f"Saved query: {name.strip()}")

    def load_saved_query(self,index=None):
        if index is None:
            index=self.saved_combo.currentIndex()
        if index<=0 or index>len(self.saved_queries): return
        self.sql.setPlainText(self.saved_queries[index-1].get("sql",""))
        self.tabs.setCurrentWidget(self.query_widget)

    def delete_saved_query(self):
        idx=self.saved_combo.currentIndex()
        if idx<=0 or idx>len(self.saved_queries): return
        q=self.saved_queries.pop(idx-1); self.persist_saved_queries(); self.refresh_saved_combo()
        self.statusBar().showMessage(f"Deleted saved query: {q.get('name','')}")

    def history_double_click(self,row,col):
        if row<0 or row>=len(self.history): return
        item=self.history[row]
        if len(item)>=2:
            self.sql.setPlainText(str(item[1]))
            self.tabs.setCurrentWidget(self.query_widget)

    def refresh_history_view(self):
        if not hasattr(self,"history_table"): return
        self.history_table.setRowCount(len(self.history))
        for i,item in enumerate(self.history):
            typ=item[0] if len(item)>0 else ""
            query=item[1] if len(item)>1 else ""
            meta=item[2] if len(item)>2 else ""
            extra=item[3] if len(item)>3 else ""
            vals=[typ,query,meta,extra]
            for j,v in enumerate(vals):
                self.history_table.setItem(i,j,QTableWidgetItem(str(v)))
        self.history_table.resizeColumnsToContents()
        if self.history_table.columnWidth(1)>650: self.history_table.setColumnWidth(1,650)

    def populate_corpus_selectors(self):
        if not hasattr(self,"corpus_table"): return
        self.corpus_table.blockSignals(True)
        self.corpus_table.clear(); self.corpus_column.clear()
        tables=[o for o in self.schema_data.get("objects",[])
                if o["type"]=="table" and not o.get("fts_virtual") and not o.get("fts_shadow")]
        for o in tables:
            self.corpus_table.addItem(o["name"])
        preferred_names=("sentences","sentence","corpus","documents","document",
                         "texts","text","entries","data")
        chosen=-1
        for pref in preferred_names:
            for i in range(self.corpus_table.count()):
                if self.corpus_table.itemText(i).lower()==pref:
                    chosen=i; break
            if chosen>=0: break
        if chosen<0 and tables:
            candidates=[(int(o.get("rows") or 0),i) for i,o in enumerate(tables)]
            chosen=max(candidates)[1] if candidates else 0
        if chosen>=0: self.corpus_table.setCurrentIndex(chosen)
        self.corpus_table.blockSignals(False)
        try: self.corpus_table.currentTextChanged.disconnect(self.corpus_table_changed)
        except Exception: pass
        self.corpus_table.currentTextChanged.connect(self.corpus_table_changed)
        self.corpus_table_changed(self.corpus_table.currentText())

    def corpus_table_changed(self,name):
        if not self.path or not name: return
        try:
            c=sqlite3.connect(self.path)
            cols=c.execute(f"PRAGMA table_info({qid(name)})").fetchall(); c.close()
            self.corpus_column.blockSignals(True); self.corpus_column.clear()
            candidates=[]
            for r in cols:
                typ=(r[2] or "").upper()
                if "CHAR" in typ or "TEXT" in typ or not typ:
                    candidates.append(r[1])
            preferred=("text","sentence","content","body","document","native_word","romanized_word","word")
            ordered=[]
            for pref in preferred:
                ordered.extend([x for x in candidates if x.lower()==pref and x not in ordered])
            ordered.extend([x for x in candidates if x not in ordered])
            for name in ordered: self.corpus_column.addItem(name)
            self.corpus_column.blockSignals(False)
        except Exception:
            pass

    def run_corpus_analysis(self):
        if not self.path: return QMessageBox.warning(self,APP_NAME,"Open a database first.")
        table=self.corpus_table.currentText(); col=self.corpus_column.currentText()
        if not table or not col: return QMessageBox.warning(self,"Corpus Lab","Select a table and text column.")
        self.corpus_run.setEnabled(False); self.corpus_dup.setEnabled(False); self.corpus_cancel.setEnabled(True)
        self.corpus_bar.setValue(0); self.corpus_progress.setText("Starting corpus intelligence…")
        self.cw=CorpusWorker(self.path,table,col,self.corpus_sample.value())
        self.cw.progress.connect(lambda p,t:(self.corpus_bar.setValue(p),self.corpus_progress.setText(t)))
        self.cw.done.connect(self.corpus_done); self.cw.error.connect(self.corpus_error); self.cw.start()

    def run_duplicate_check(self):
        if not self.path: return QMessageBox.warning(self,APP_NAME,"Open a database first.")
        table=self.corpus_table.currentText(); col=self.corpus_column.currentText()
        if not table or not col: return QMessageBox.warning(self,"Duplicates","Select a table and text column.")
        ans=QMessageBox.question(
            self,"Exact Duplicate Check",
            "This performs an exact GROUP BY over the selected text column. "
            "On a 4-million-row corpus it may be slow and use temporary SQLite storage.\\n\\nContinue?",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No
        )
        if ans!=QMessageBox.Yes: return
        self.corpus_run.setEnabled(False); self.corpus_dup.setEnabled(False); self.corpus_cancel.setEnabled(True)
        self.corpus_bar.setValue(0); self.corpus_progress.setText("Starting exact duplicate analysis…")
        self.dw=DuplicateWorker(self.path,table,col)
        self.dw.progress.connect(lambda p,t:(self.corpus_bar.setValue(p),self.corpus_progress.setText(t)))
        self.dw.done.connect(self.duplicate_done); self.dw.error.connect(self.corpus_error); self.dw.start()
        self.corpus_tabs.setCurrentIndex(4)

    def cancel_corpus(self):
        for worker in (getattr(self,"cw",None),getattr(self,"dw",None)):
            if worker and worker.isRunning():
                worker.requestInterruption()
        self.corpus_cancel.setEnabled(False); self.corpus_progress.setText("Cancelling…")

    def corpus_error(self,msg):
        self.corpus_run.setEnabled(True); self.corpus_dup.setEnabled(True); self.corpus_cancel.setEnabled(False)
        self.corpus_progress.setText(msg)
        if "cancelled" not in msg.lower(): QMessageBox.critical(self,"Corpus Analysis",msg)

    def corpus_done(self,d):
        self.corpus_run.setEnabled(True); self.corpus_dup.setEnabled(True); self.corpus_cancel.setEnabled(False)
        self.corpus_bar.setValue(100); self.corpus_progress.setText("Corpus intelligence analysis complete.")
        total=d["total"]; nulls=d["nulls"]; empty=d["empty"]
        null_pct=(nulls/total*100) if total else 0.0
        empty_pct=(empty/total*100) if total else 0.0

        report=f"""CORPUS INTELLIGENCE REPORT

Database: {d["path"]}
Table: {d["table"]}
Text column: {d["text_column"]}

STRUCTURE
Records:              {total:,}
NULL records:         {nulls:,} ({null_pct:.3f}%)
Empty records:        {empty:,} ({empty_pct:.3f}%)

EXACT TEXT LENGTH
Average characters:   {d["avg_length"]:.2f}
Minimum characters:   {d["min_length"]:,}
Maximum characters:   {d["max_length"]:,}
Total characters:      {d["total_chars"]:,}

LINGUISTIC SAMPLE
Sample records:       {d["sampled"]:,}
Sample tokens:        {d["sample_words"]:,}
Unique sample tokens: {d["unique_sample_words"]:,}
Avg tokens/record:    {d["avg_words_per_record"]:.2f}
Sample lexical ratio: {d["sample_lexical_ratio"]:.2f}%

CHARACTER CLASSES IN SAMPLE
Letters:              {d["letters"]:,}
Whitespace:           {d["whitespace_chars"]:,}
Digits:               {d["digits"]:,}
Punctuation:          {d["punctuation"]:,}
Non-ASCII:            {d["non_ascii"]:,}

UNICODE BLOCK HINTS
{chr(10).join(f"  {k}: {v:,}" for k,v in sorted(d["script_blocks"].items(), key=lambda x:-x[1]))}

SAMPLE DUPLICATE INDICATOR
Duplicate groups:     {d["sample_duplicate_groups"]:,}
Duplicate surplus:    {d["sample_duplicate_rows"]:,}

NOTES
• Records, NULL/empty counts and text-length statistics are exact.
• Vocabulary, character frequency and duplicate indicators use the bounded sample.
• Exact whole-corpus duplicate analysis is available separately.
• Tokenization is diagnostic and not a language-specific gold-standard tokenizer.
"""
        self.corpus_report.setPlainText(report)

        words=d["top_words"]; total_words=max(1,d["sample_words"])
        self.corpus_words.setRowCount(len(words))
        for i,(word,n) in enumerate(words):
            self.corpus_words.setItem(i,0,QTableWidgetItem(str(i+1)))
            self.corpus_words.setItem(i,1,QTableWidgetItem(word))
            self.corpus_words.setItem(i,2,QTableWidgetItem(f"{n:,}"))
            self.corpus_words.setItem(i,3,QTableWidgetItem(f"{n/total_words*100:.3f}%"))
        self.corpus_words.resizeColumnsToContents()
        if self.corpus_words.columnWidth(1)>350: self.corpus_words.setColumnWidth(1,350)

        self.length_report.setPlainText(
            "Sentence-length distribution is calculated from the bounded sample.\\n"
            f"Sample size: {d['sampled']:,}\\n"
            f"Exact corpus average: {d['avg_length']:.2f} characters"
        )
        bins=("0–25","26–50","51–75","76–100","101–150","151–250","251+")
        self.length_table.setRowCount(len(bins))
        for i,k in enumerate(bins):
            n=d["length_bins"].get(k,0)
            self.length_table.setItem(i,0,QTableWidgetItem(k))
            self.length_table.setItem(i,1,QTableWidgetItem(f"{n:,}"))
            self.length_table.setItem(i,2,QTableWidgetItem(f"{n/max(1,d['sampled'])*100:.2f}%"))
        self.length_table.resizeColumnsToContents()

        self.unicode_report.setPlainText(
            "UNICODE / CHARACTER REPORT\\n\\n"
            f"Distinct characters observed in sample: {len(d['top_chars']):,} (top 100 shown)\\n"
            f"Non-ASCII characters: {d['non_ascii']:,}\\n\\n"
            "Broad code-point ranges observed:\\n" +
            (chr(10).join(f"  {k}: {v:,}" for k,v in sorted(d["script_blocks"].items(), key=lambda x:-x[1]))
             or "  None")
        )
        chars=d["top_chars"]; self.corpus_chars.setRowCount(len(chars))
        for i,(ch,n) in enumerate(chars):
            name=unicodedata.name(ch,"UNKNOWN")
            display=f"{ch}" if ch not in ("\n","\r","\t"," ") else repr(ch)
            self.corpus_chars.setItem(i,0,QTableWidgetItem(str(i+1)))
            self.corpus_chars.setItem(i,1,QTableWidgetItem(display))
            self.corpus_chars.setItem(i,2,QTableWidgetItem(f"U+{ord(ch):04X} {name}"))
            self.corpus_chars.setItem(i,3,QTableWidgetItem(f"{n:,}"))
        self.corpus_chars.resizeColumnsToContents()
        if self.corpus_chars.columnWidth(2)>500: self.corpus_chars.setColumnWidth(2,500)

        self.corpus_tabs.setCurrentIndex(0)

    def duplicate_done(self,d):
        self.corpus_run.setEnabled(True); self.corpus_dup.setEnabled(True); self.corpus_cancel.setEnabled(False)
        self.corpus_bar.setValue(100); self.corpus_progress.setText("Exact duplicate analysis complete.")
        total_rows=0
        try:
            c=sqlite3.connect(self.path)
            total_rows=int(c.execute(f"SELECT COUNT(*) FROM {qid(self.corpus_table.currentText())}").fetchone()[0] or 0)
            c.close()
        except Exception:
            pass
        dup_pct=(d["duplicate_rows"]/total_rows*100) if total_rows else 0.0
        self.duplicate_report.setPlainText(f"""EXACT DUPLICATE REPORT

Table: {self.corpus_table.currentText()}
Text column: {self.corpus_column.currentText()}

Duplicate groups:       {d["duplicate_groups"]:,}
Duplicate surplus rows: {d["duplicate_rows"]:,}
Largest duplicate group:{d["largest_group"]:,}
Duplicate surplus %:     {dup_pct:.3f}%


Definition
• Duplicate group = a non-empty text value occurring more than once.
• Duplicate surplus rows = all occurrences beyond the first in each group.
• This is an exact whole-column calculation, not a sample estimate.
""")
        self.corpus_tabs.setCurrentIndex(4)

    def _quality_text_column(self):
        return self.corpus_column.currentText().strip()

    def _quality_patterns(self):
        return [
            ("URL", re.compile(r"https?://|www\.", re.I)),
            ("Email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
            ("SEO phrase", re.compile(
                r"\b(?:from a to z|popular names|middle names|training institute|"
                r"best [a-z ]+|near me|click here|index [a-z])\b", re.I)),
            ("HTML", re.compile(r"<(?:html|body|div|p|a|br|span|script)\b", re.I)),
        ]

    def _quality_metrics(self, text):
        """Return deterministic heuristic signals for one record."""
        if text is None:
            text=""
        text=str(text)
        n=len(text)
        stripped=text.strip()
        if not stripped:
            return dict(score=100.0, level="Highly Suspicious", length=0,
                        repeat=100.0, urls=0, signals=["empty"], preview="")

        tokens=re.findall(r"\b[\w'’-]+\b", stripped, flags=re.UNICODE)
        token_count=len(tokens)
        lower=[t.casefold() for t in tokens if t]
        uniq=len(set(lower))
        repeat_pct=(100.0*(1.0-uniq/token_count)) if token_count else 0.0

        signals=[]
        score=0.0

        if n>=50000:
            score+=35; signals.append("extreme length")
        elif n>=25000:
            score+=28; signals.append("very long")
        elif n>=10000:
            score+=20; signals.append("long")
        elif n>=5000:
            score+=10; signals.append("large")

        if repeat_pct>=85:
            score+=35; signals.append("extreme repetition")
        elif repeat_pct>=70:
            score+=25; signals.append("high repetition")
        elif repeat_pct>=50:
            score+=12; signals.append("repetition")

        urls=len(re.findall(r"https?://|www\.",text,re.I))
        emails=len(re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",text,re.I))
        if urls:
            score+=20; signals.append(f"{urls} URL")
        if emails:
            score+=12; signals.append(f"{emails} email")

        for name,pat in self._quality_patterns():
            if name in ("URL","Email"):
                continue
            m=pat.findall(text)
            if m:
                score+=12 if name=="SEO phrase" else 10
                signals.append(name)

        digits=sum(ch.isdigit() for ch in text)
        letters=sum(ch.isalpha() for ch in text)
        punct=sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
        if n and digits/n>0.25:
            score+=8; signals.append("high digit density")
        if n and punct/n>0.35:
            score+=6; signals.append("high punctuation")
        if letters and sum(1 for ch in text if '\u0900'<=ch<='\u097F')/letters>0.15:
            score+=8; signals.append("Devanagari mix")
        if letters and sum(1 for ch in text if '\u4E00'<=ch<='\u9FFF')/letters>0.05:
            score+=8; signals.append("CJK mix")

        # Repeated adjacent token / phrase signal.
        if token_count>=6:
            adjacent=0
            for a,b in zip(lower,lower[1:]):
                if a==b:
                    adjacent+=1
            if adjacent>=3:
                score+=15; signals.append("adjacent repeats")

        score=min(100.0,score)
        if score>=75:
            level="Highly Suspicious"
        elif score>=55:
            level="Suspicious"
        elif score>=35:
            level="Review"
        else:
            level="Normal"

        preview=re.sub(r"\s+"," ",stripped)
        if len(preview)>240:
            preview=preview[:240]+"…"

        return dict(score=score, level=level, length=n, repeat=repeat_pct,
                    urls=urls, signals=signals, preview=preview)

    def _quality_candidate_rows(self, mode, sample, limit, threshold):
        table=self.corpus_table.currentText()
        col=self._quality_text_column()
        if not table or not col:
            raise ValueError("Select a corpus table and text column first.")

        qt=qid(table); qc=qid(col)
        c=sqlite3.connect(self.path)
        c.row_factory=sqlite3.Row

        if mode in ("Longest records","Very long records"):
            rows=c.execute(
                f"""SELECT rowid AS rid, {qc} AS value
                    FROM {qt} WHERE {qc} IS NOT NULL
                    ORDER BY LENGTH(CAST({qc} AS TEXT)) DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            c.close()
            return rows

        if mode=="Most repetitive records":
            # Candidate generation is intentionally bounded. SQLite does the
            # cheap length ordering; Python calculates token repetition.
            rows=c.execute(
                f"""SELECT rowid AS rid, {qc} AS value
                    FROM {qt} WHERE {qc} IS NOT NULL
                    ORDER BY LENGTH(CAST({qc} AS TEXT)) DESC LIMIT ?""",
                (max(sample,limit*20),)
            ).fetchall()
            c.close()
            scored=[]
            for r in rows:
                m=self._quality_metrics(r["value"])
                scored.append((m["repeat"],r))
            scored.sort(key=lambda x:x[0],reverse=True)
            return [r for _,r in scored[:limit]]

        if mode in ("Web / SEO pattern candidates","URL / email candidates"):
            # Bounded LIKE candidates avoid an expensive full-table regex scan.
            clauses=[]
            params=[]
            if mode=="URL / email candidates":
                clauses=["CAST({c} AS TEXT) LIKE '%http://%'",
                         "CAST({c} AS TEXT) LIKE '%https://%'",
                         "CAST({c} AS TEXT) LIKE '%www.%'",
                         "CAST({c} AS TEXT) LIKE '%@%'"]
            else:
                phrases=[
                    "from a to z","popular names","middle names",
                    "training institute","click here","near me","index "
                ]
                clauses=[f"LOWER(CAST({qc} AS TEXT)) LIKE ?" for _ in phrases]
                params=[f"%{p}%" for p in phrases]
            sql=f"""SELECT rowid AS rid, {qc} AS value FROM {qt}
                    WHERE ({' OR '.join(clauses)})
                    LIMIT ?"""
            params.append(max(sample,limit*20))
            rows=c.execute(sql,tuple(params)).fetchall()
            c.close()
            return rows[:max(sample,limit*20)]

        # Quality scan — random-ish rowid sampling is much cheaper than
        # scanning every one of 4M records. It remains deterministic enough
        # for repeated diagnostics on the same database.
        total=c.execute(f"SELECT COUNT(*) FROM {qt}").fetchone()[0]
        step=max(1,total//max(1,sample))
        sql=f"""SELECT rowid AS rid, {qc} AS value
                FROM {qt}
                WHERE rowid % ? = 0
                LIMIT ?"""
        rows=c.execute(sql,(step,sample)).fetchall()
        c.close()
        return rows

    def run_quality_investigation(self):
        if not self.path:
            return QMessageBox.warning(self,APP_NAME,"Open a database first.")
        mode=self.quality_mode.currentText()
        sample=self.quality_sample.value()
        limit=self.quality_limit.value()
        threshold=self.quality_threshold.value()

        self.quality_run.setEnabled(False)
        QApplication.processEvents()
        try:
            rows=self._quality_candidate_rows(mode,sample,limit,threshold)
            findings=[]
            for r in rows:
                m=self._quality_metrics(r["value"])
                if mode=="Quality scan — sample" and m["score"]<threshold:
                    continue
                if mode=="Very long records" and m["length"]<10000:
                    continue
                if mode=="Web / SEO pattern candidates" and not any(
                    x in m["signals"] for x in ("SEO phrase","HTML")
                ):
                    continue
                if mode=="URL / email candidates" and not any(
                    "URL" in x or "email" in x for x in m["signals"]
                ):
                    continue
                findings.append((int(r["rid"]),m))
            findings.sort(key=lambda x:x[1]["score"],reverse=True)
            findings=findings[:limit]
            self._quality_findings=findings

            self.quality_table.setRowCount(len(findings))
            for i,(rid,m) in enumerate(findings):
                vals=[
                    str(rid),f'{m["score"]:.1f}',m["level"],f'{m["length"]:,}',
                    f'{m["repeat"]:.1f}%',str(m["urls"]),
                    ", ".join(m["signals"]) or "—",m["preview"]
                ]
                for j,v in enumerate(vals):
                    self.quality_table.setItem(i,j,QTableWidgetItem(v))
            self.quality_table.resizeColumnsToContents()
            if self.quality_table.columnWidth(7)>850:
                self.quality_table.setColumnWidth(7,850)

            self.quality_info.setPlainText(
                "CORPUS QUALITY INVESTIGATION\\n\\n"
                f"Table: {self.corpus_table.currentText()}\\n"
                f"Text column: {self._quality_text_column()}\\n"
                f"Mode: {mode}\\n"
                f"Candidate sample: {sample:,}\\n"
                f"Returned findings: {len(findings):,}\\n"
                f"Threshold: {threshold:.1f}\\n\\n"
                "Interpretation: a finding is a review candidate, not proof "
                "that the record is wrong or unwanted. Always inspect the "
                "source record before deciding what to do."
            )
            self.corpus_tabs.setCurrentIndex(
                self.corpus_tabs.indexOf(self.quality_table.parentWidget())
                if self.quality_table.parentWidget() else self.corpus_tabs.count()-1
            )
        except Exception as e:
            self.err(f"Quality investigation failed: {type(e).__name__}: {e}")
        finally:
            self.quality_run.setEnabled(True)

    def open_quality_record(self,row,col):
        if row<0 or row>=self.quality_table.rowCount():
            return
        item=self.quality_table.item(row,0)
        if not item: return
        try: rid=int(item.text())
        except Exception: return
        self.inv_mode.setCurrentText("Contains text")
        self.inv_target.setText("")
        table=self.corpus_table.currentText()
        column=self._quality_text_column()
        try:
            c=sqlite3.connect(self.path)
            r=c.execute(
                f"SELECT rowid, {qid(column)} FROM {qid(table)} WHERE rowid=?",(rid,)
            ).fetchone()
            c.close()
            if not r:
                return
            dlg=QDialog(self); dlg.setWindowTitle(f"Quality Investigation — row {rid}")
            dlg.resize(1000,650)
            dl=QVBoxLayout(dlg)
            m=next((x[1] for x in getattr(self,"_quality_findings",[]) if x[0]==rid),None)
            summary=QLabel(
                f"Row ID: {rid}    Length: {m['length']:,}    "
                f"Score: {m['score']:.1f}    Level: {m['level']}\\n"
                f"Signals: {', '.join(m['signals']) or 'none'}"
                if m else f"Row ID: {rid}"
            )
            dl.addWidget(summary)
            edit=QPlainTextEdit(); edit.setReadOnly(True)
            edit.setPlainText("" if r[1] is None else str(r[1]))
            dl.addWidget(edit,1)
            b=QDialogButtonBox(QDialogButtonBox.Close)
            b.rejected.connect(dlg.reject); b.accepted.connect(dlg.accept)
            dl.addWidget(b)
            dlg.exec()
        except Exception as e:
            self.err(f"Could not open quality record: {type(e).__name__}: {e}")

    def export_quality_findings(self):
        findings=getattr(self,"_quality_findings",[])
        if not findings:
            return QMessageBox.information(self,"Quality Investigator","Run a quality investigation first.")
        p,_=QFileDialog.getSaveFileName(
            self,"Export Quality Findings","","CSV files (*.csv)"
        )
        if not p: return
        try:
            with open(p,"w",newline="",encoding="utf-8") as f:
                w=csv.writer(f)
                w.writerow([
                    "row_id","score","level","length","repeat_percent",
                    "url_count","signals","preview"
                ])
                for rid,m in findings:
                    w.writerow([
                        rid,f'{m["score"]:.1f}',m["level"],m["length"],
                        f'{m["repeat"]:.1f}',m["urls"],
                        "; ".join(m["signals"]),m["preview"]
                    ])
            self.statusBar().showMessage(f"Quality findings exported: {p}")
        except Exception as e:
            self.err(f"Quality export failed: {e}")

    def _corpus_investigation_index(self):
        for i in range(self.corpus_tabs.count()):
            if self.corpus_tabs.tabText(i)=="Investigation":
                return i
        return max(0,self.corpus_tabs.count()-1)

    def investigate_selected_token(self):
        row=self.corpus_words.currentRow()
        if row<0:
            return QMessageBox.information(self,"Vocabulary","Select a token first.")
        item=self.corpus_words.item(row,1)
        if not item or not item.text().strip():
            return
        self.inv_mode.setCurrentText("Word / phrase")
        self.inv_target.setText(item.text().strip())
        self.corpus_tabs.setCurrentIndex(self._corpus_investigation_index())
        self.run_corpus_investigation()

    def investigate_selected_character(self):
        row=self.corpus_chars.currentRow()
        if row<0:
            return QMessageBox.information(self,"Unicode","Select a character first.")
        item=self.corpus_chars.item(row,1)
        if not item:
            return
        ch=item.text()
        if ch.startswith("'") and ch.endswith("'") and len(ch)>=3:
            ch=ch[1:-1]
        self.inv_mode.setCurrentText("Unicode character")
        self.inv_target.setText(ch)
        self.corpus_tabs.setCurrentIndex(self._corpus_investigation_index())
        self.run_corpus_investigation()

    def run_corpus_investigation(self):
        if not self.path:
            return QMessageBox.warning(self,APP_NAME,"Open a database first.")
        table=self.corpus_table.currentText()
        col=self.corpus_column.currentText()
        if not table or not col:
            return QMessageBox.warning(self,"Investigation","Select a table and text column.")

        mode=self.inv_mode.currentText()
        target=self.inv_target.text()
        limit=self.inv_limit.value()

        if mode in ("Word / phrase","Unicode character","Contains text") and not target:
            return QMessageBox.information(self,"Investigation","Enter a target first.")

        try:
            c=sqlite3.connect(self.path)
            c.row_factory=sqlite3.Row
            qt=qid(table); qc=qid(col)

            if mode=="Longest records":
                sql=f"""SELECT rowid AS rid, LENGTH(CAST({qc} AS TEXT)) AS len, {qc} AS value
                        FROM {qt}
                        WHERE {qc} IS NOT NULL
                        ORDER BY LENGTH(CAST({qc} AS TEXT)) DESC
                        LIMIT ?"""
                params=(limit,)
                title="Longest records"
            elif mode=="Shortest records":
                sql=f"""SELECT rowid AS rid, LENGTH(CAST({qc} AS TEXT)) AS len, {qc} AS value
                        FROM {qt}
                        WHERE {qc} IS NOT NULL AND CAST({qc} AS TEXT)<>''
                        ORDER BY LENGTH(CAST({qc} AS TEXT)) ASC
                        LIMIT ?"""
                params=(limit,)
                title="Shortest records"
            else:
                sql=f"""SELECT rowid AS rid, LENGTH(CAST({qc} AS TEXT)) AS len, {qc} AS value
                        FROM {qt}
                        WHERE {qc} IS NOT NULL AND CAST({qc} AS TEXT) LIKE ?
                        LIMIT ?"""
                params=(f"%{target}%",limit)
                title=f"Records containing: {target}"

            rows=c.execute(sql,params).fetchall()
            c.close()

            self._investigation_rows=[
                (int(r["rid"]),int(r["len"] or 0),"" if r["value"] is None else str(r["value"]))
                for r in rows
            ]
            self.inv_table.setRowCount(len(self._investigation_rows))
            for i,(rid,L,value) in enumerate(self._investigation_rows):
                self.inv_table.setItem(i,0,QTableWidgetItem(str(rid)))
                self.inv_table.setItem(i,1,QTableWidgetItem(f"{L:,}"))
                self.inv_table.setItem(i,2,QTableWidgetItem(value))
            self.inv_table.resizeColumnsToContents()
            if self.inv_table.columnWidth(2)>900:
                self.inv_table.setColumnWidth(2,900)

            self.inv_info.setPlainText(
                f"CORPUS INVESTIGATION\\n\\n"
                f"Table: {table}\\n"
                f"Text column: {col}\\n"
                f"Mode: {mode}\\n"
                f"Target: {target or '(not applicable)'}\\n"
                f"Returned records: {len(rows):,}\\n"
                f"Limit: {limit:,}\\n\\n"
                f"{title}\\n\\n"
                "The database was opened read-only. No records were changed."
            )
            self.corpus_tabs.setCurrentIndex(self._corpus_investigation_index())
        except Exception as e:
            self.err(f"Investigation failed: {type(e).__name__}: {e}")

    def open_investigation_record(self,row,col):
        if row<0 or row>=self.inv_table.rowCount() or not self.path:
            return
        rid_item=self.inv_table.item(row,0)
        if not rid_item: return
        try: rid=int(rid_item.text())
        except Exception: return
        table=self.corpus_table.currentText()
        column=self.corpus_column.currentText()
        try:
            c=sqlite3.connect(self.path)
            r=c.execute(
                f"SELECT rowid, {qid(column)} FROM {qid(table)} WHERE rowid=?",(rid,)
            ).fetchone()
            c.close()
            if not r:
                return QMessageBox.information(self,"Investigation",f"Record {rid} could not be opened.")
            self.table_name=table
            self.data_title.setText(table)
            self.page.setValue(1)
            self.where.setText(f"rowid = {rid}")
            self.tabs.setCurrentWidget(self.data_widget)
            self.load_table()
        except Exception as e:
            self.err(f"Could not open source record: {type(e).__name__}: {e}")

    def export_investigation(self):
        rows=getattr(self,"_investigation_rows",[])
        if not rows:
            return QMessageBox.information(self,"Investigation","Run an investigation first.")
        p,_=QFileDialog.getSaveFileName(self,"Export Investigation Results","","CSV files (*.csv)")
        if not p: return
        try:
            with open(p,"w",newline="",encoding="utf-8") as f:
                w=csv.writer(f)
                w.writerow(["row_id","length","source_record"])
                w.writerows(rows)
            self.statusBar().showMessage(f"Investigation exported: {p}")
        except Exception as e:
            self.err(f"Investigation export failed: {e}")

    def find_vocabulary_sources(self):
        row=self.corpus_words.currentRow()
        if row<0:
            return QMessageBox.information(self,"Vocabulary","Select a token first.")
        token_item=self.corpus_words.item(row,1)
        if not token_item: return
        token=token_item.text().strip()
        if not token: return
        table=self.corpus_table.currentText(); col=self.corpus_column.currentText()
        if not self.path or not table or not col: return
        try:
            c=sqlite3.connect(self.path)
            # A token-oriented LIKE search is deliberately bounded. It is
            # portable even when the selected corpus has no FTS index.
            rows=c.execute(
                f"""SELECT rowid, {qid(col)}
                    FROM {qid(table)}
                    WHERE {qid(col)} LIKE ?
                    LIMIT 50""",(f"%{token}%",)
            ).fetchall()
            c.close()
            dlg=QDialog(self); dlg.setWindowTitle(f"Source sentences — {token}"); dlg.resize(900,650)
            dl=QVBoxLayout(dlg)
            dl.addWidget(QLabel(f"Up to 50 matching records for: {token}"))
            t=QTableWidget(); t.setColumnCount(2); t.setHorizontalHeaderLabels(["rowid","Source sentence"]); t.setRowCount(len(rows))
            for i,(rid,textv) in enumerate(rows):
                t.setItem(i,0,QTableWidgetItem(str(rid)))
                t.setItem(i,1,QTableWidgetItem("" if textv is None else str(textv)))
            t.resizeColumnsToContents()
            if t.columnWidth(1)>700: t.setColumnWidth(1,700)
            dl.addWidget(t,1)
            q=QPushButton("Close"); q.clicked.connect(dlg.accept); dl.addWidget(q)
            dlg.exec()
        except Exception as e:
            self.err(f"{type(e).__name__}: {e}")


    def load_saved_queries(self):
        self.saved_query_path=os.path.expanduser("~/.config/jass_sqlite_explorer_saved_queries.json")
        try:
            with open(self.saved_query_path,encoding="utf-8") as f:
                data=json.load(f)
            self.saved_queries=data if isinstance(data,list) else []
        except Exception:
            self.saved_queries=[]

    def persist_saved_queries(self):
        try:
            os.makedirs(os.path.dirname(self.saved_query_path),exist_ok=True)
            with open(self.saved_query_path,"w",encoding="utf-8") as f:
                json.dump(self.saved_queries,f,ensure_ascii=False,indent=2)
        except Exception as e:
            self.err(f"Could not save query library: {e}")

    def refresh_saved_combo(self):
        if not hasattr(self,"saved_combo"): return
        self.saved_combo.blockSignals(True); self.saved_combo.clear()
        self.saved_combo.addItem("— Select saved query —")
        for q in self.saved_queries:
            self.saved_combo.addItem(q.get("name","Unnamed"))
        self.saved_combo.blockSignals(False)

    def save_current_query(self):
        sql=self.sql.toPlainText().strip()
        if not sql: return QMessageBox.information(self,"Save Query","Enter a SQL query first.")
        name,ok=QInputDialog.getText(self,"Save Query","Name:",QLineEdit.Normal,sql.splitlines()[0][:60])
        if not ok or not name.strip(): return
        self.saved_queries.append({"name":name.strip(),"sql":sql,"saved_at":datetime.now().isoformat(timespec="seconds")})
        self.persist_saved_queries(); self.refresh_saved_combo()
        self.statusBar().showMessage(f"Saved query: {name.strip()}")

    def load_saved_query(self,index=None):
        if index is None:
            index=self.saved_combo.currentIndex()
        if index<=0 or index>len(self.saved_queries): return
        self.sql.setPlainText(self.saved_queries[index-1].get("sql",""))
        self.tabs.setCurrentWidget(self.query_widget)

    def delete_saved_query(self):
        idx=self.saved_combo.currentIndex()
        if idx<=0 or idx>len(self.saved_queries): return
        q=self.saved_queries.pop(idx-1); self.persist_saved_queries(); self.refresh_saved_combo()
        self.statusBar().showMessage(f"Deleted saved query: {q.get('name','')}")

    def history_double_click(self,row,col):
        if row<0 or row>=len(self.history): return
        item=self.history[row]
        if len(item)>=2:
            self.sql.setPlainText(str(item[1]))
            self.tabs.setCurrentWidget(self.query_widget)

    def refresh_history_view(self):
        if not hasattr(self,"history_table"): return
        self.history_table.setRowCount(len(self.history))
        for i,item in enumerate(self.history):
            typ=item[0] if len(item)>0 else ""
            query=item[1] if len(item)>1 else ""
            meta=item[2] if len(item)>2 else ""
            extra=item[3] if len(item)>3 else ""
            vals=[typ,query,meta,extra]
            for j,v in enumerate(vals):
                self.history_table.setItem(i,j,QTableWidgetItem(str(v)))
        self.history_table.resizeColumnsToContents()
        if self.history_table.columnWidth(1)>650: self.history_table.setColumnWidth(1,650)

    def populate_corpus_selectors(self):
        if not hasattr(self,"corpus_table"): return
        self.corpus_table.blockSignals(True)
        self.corpus_table.clear(); self.corpus_column.clear()
        tables=[o for o in self.schema_data.get("objects",[])
                if o["type"]=="table" and not o.get("fts_virtual") and not o.get("fts_shadow")]
        for o in tables:
            self.corpus_table.addItem(o["name"])

        # Prefer a likely corpus table over metadata/config tables.
        preferred_names=("sentences","sentence","corpus","documents","document",
                         "texts","text","entries","data")
        chosen=-1
        for pref in preferred_names:
            for i in range(self.corpus_table.count()):
                if self.corpus_table.itemText(i).lower()==pref:
                    chosen=i; break
            if chosen>=0: break

        # Otherwise prefer the largest ordinary table when row counts are
        # available from schema analysis.
        if chosen<0 and tables:
            candidates=[(int(o.get("rows") or 0),i) for i,o in enumerate(tables)]
            chosen=max(candidates)[1] if candidates else 0

        if chosen>=0:
            self.corpus_table.setCurrentIndex(chosen)
        self.corpus_table.blockSignals(False)

        try:
            self.corpus_table.currentTextChanged.disconnect(self.corpus_table_changed)
        except Exception:
            pass
        self.corpus_table.currentTextChanged.connect(self.corpus_table_changed)
        self.corpus_table_changed(self.corpus_table.currentText())

    def corpus_table_changed(self,name):
        if not self.path or not name: return
        try:
            c=sqlite3.connect(self.path)
            cols=c.execute(f"PRAGMA table_info({qid(name)})").fetchall(); c.close()
            self.corpus_column.blockSignals(True); self.corpus_column.clear()
            candidates=[]
            for r in cols:
                typ=(r[2] or "").upper()
                if "CHAR" in typ or "TEXT" in typ or not typ:
                    candidates.append(r[1])
            # Prefer actual text/content columns.
            preferred=("text","sentence","content","body","document","native_word",
                       "romanized_word","word")
            ordered=[]
            for pref in preferred:
                ordered.extend([x for x in candidates if x.lower()==pref and x not in ordered])
            ordered.extend([x for x in candidates if x not in ordered])
            for name in ordered:
                self.corpus_column.addItem(name)
            self.corpus_column.blockSignals(False)
        except Exception:
            pass

    def run_corpus_analysis(self):
        if not self.path: return QMessageBox.warning(self,APP_NAME,"Open a database first.")
        table=self.corpus_table.currentText(); col=self.corpus_column.currentText()
        if not table or not col: return QMessageBox.warning(self,"Corpus Lab","Select a table and text column.")
        self.corpus_run.setEnabled(False); self.corpus_cancel.setEnabled(True); self.corpus_bar.setValue(0)
        self.corpus_progress.setText("Starting corpus analysis…")
        self.cw=CorpusWorker(self.path,table,col,self.corpus_sample.value())
        self.cw.progress.connect(lambda p,t:(self.corpus_bar.setValue(p),self.corpus_progress.setText(t)))
        self.cw.done.connect(self.corpus_done); self.cw.error.connect(self.corpus_error); self.cw.start()

    def cancel_corpus(self):
        if hasattr(self,"cw") and self.cw.isRunning():
            self.cw.requestInterruption()
            self.corpus_progress.setText("Cancelling…")

    def corpus_error(self,msg):
        self.corpus_run.setEnabled(True); self.corpus_cancel.setEnabled(False)
        self.corpus_progress.setText(msg)
        if "cancelled" not in msg.lower(): QMessageBox.critical(self,"Corpus Analysis",msg)

    def corpus_done(self,d):
        self.corpus_run.setEnabled(True); self.corpus_cancel.setEnabled(False); self.corpus_bar.setValue(100)
        self.corpus_progress.setText("Corpus analysis complete.")
        null_pct=(d["nulls"]/d["total"]*100) if d["total"] else 0.0
        empty_pct=(d["empty"]/d["total"]*100) if d["total"] else 0.0
        report=f"""CORPUS QUALITY REPORT

Database: {d["path"]}
Table: {d["table"]}
Text column: {d["text_column"]}

STRUCTURE
Records:              {d["total"]:,}
NULL records:         {d["nulls"]:,} ({null_pct:.3f}%)
Empty records:        {d["empty"]:,} ({empty_pct:.3f}%)

TEXT LENGTH
Average characters:   {d["avg_length"]:.2f}
Minimum characters:   {d["min_length"]:,}
Maximum characters:   {d["max_length"]:,}
Total characters:      {d["total_chars"]:,}

LINGUISTIC SAMPLE
Sample records:       {d["sampled"]:,}
Sample tokens:        {d["sample_words"]:,}
Unique sample tokens: {d["unique_sample_words"]:,}
Avg tokens/record:    {d["avg_words_per_record"]:.2f}
Sample lexical ratio: {d["sample_lexical_ratio"]:.2f}%

CHARACTER CLASSES IN SAMPLE
Whitespace:           {d["whitespace_chars"]:,}
Digits:               {d["digits"]:,}
Punctuation:          {d["punctuation"]:,}

UNICODE BLOCK HINTS
{chr(10).join(f"  {k}: {v:,}" for k,v in d["script_blocks"].items()) or "  No Myanmar-range characters detected in sample."}

NOTES
• Row/NULL/empty/length statistics are exact.
• Token and character frequencies are calculated from the bounded sample.
• Sample analysis is diagnostic, not a linguistic gold-standard tokenizer.
"""
        self.corpus_report.setPlainText(report)

        words=d["top_words"]; self.corpus_words.setRowCount(len(words))
        for i,(word,n) in enumerate(words):
            self.corpus_words.setItem(i,0,QTableWidgetItem(str(i+1)))
            self.corpus_words.setItem(i,1,QTableWidgetItem(word))
            self.corpus_words.setItem(i,2,QTableWidgetItem(f"{n:,}"))
        self.corpus_words.resizeColumnsToContents()

        chars=d["top_chars"]; self.corpus_chars.setRowCount(len(chars))
        for i,(ch,n) in enumerate(chars):
            name=unicodedata.name(ch,"UNKNOWN")
            display=f"{ch}  ({name}, U+{ord(ch):04X})"
            self.corpus_chars.setItem(i,0,QTableWidgetItem(str(i+1)))
            self.corpus_chars.setItem(i,1,QTableWidgetItem(display))
            self.corpus_chars.setItem(i,2,QTableWidgetItem(f"{n:,}"))
        self.corpus_chars.resizeColumnsToContents()

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
        dlg=QFileDialog(self,"Open SQLite Database",start,
                        "SQLite databases (*.db *.sqlite *.sqlite3);;All files (*)")
        dlg.setFileMode(QFileDialog.ExistingFile)
        dlg.setNameFilter("SQLite databases (*.db *.sqlite *.sqlite3);;All files (*)")
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)
        if dlg.exec():
            files=dlg.selectedFiles()
            p=files[0] if files else ""
        else:
            p=""
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
            if header != b"SQLite format 3\x00":
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
        self.make_report()
        self.populate_corpus_selectors()
        self.refresh_history_view()
        self.statusBar().showMessage("Database loaded and analyzed.")

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
        self.history.append(("FTS",query,datetime.now().strftime("%H:%M:%S"),"running")); self.refresh_history_view()

    def fts_done(self,cols,rows,ms):
        self.fill(self.ft,cols,rows); self.fts_info.setText(f"{len(rows):,} results displayed • {ms:.1f} ms • ranked with BM25 when supported.")
        if self.history:
            h=list(self.history[-1]); h[3]=f"{len(rows):,} results • {ms:.1f} ms"; self.history[-1]=tuple(h); self.refresh_history_view()

    def open_fts_source(self):
        row=self.ft.currentRow()
        if row<0: return QMessageBox.information(self,"FTS Source","Select an FTS result first.")
        rid_item=self.ft.item(row,0)
        if not rid_item:
            return QMessageBox.warning(self,"FTS Source","The selected FTS result has no row identifier.")
        try:
            rid=int(rid_item.text())
        except Exception:
            return QMessageBox.warning(self,"FTS Source","Could not read the FTS row identifier.")
        fts=self.fts_combo.currentText()
        sql=next((o.get("sql") for o in self.schema_data.get("objects",[])
                  if o["name"]==fts and o.get("fts_virtual")),None)
        m=re.search(r"content\\s*=\\s*['\"]([^'\"]+)['\"]",sql or "",re.I)
        rm=re.search(r"content_rowid\\s*=\\s*['\"]([^'\"]+)['\"]",sql or "",re.I)
        source=m.group(1) if m else None
        rowid_col=rm.group(1) if rm else "rowid"
        if not source:
            return QMessageBox.information(self,"FTS Source",
                "This FTS index does not expose an external content table in its SQL definition.")
        try:
            c=sqlite3.connect(self.path); c.row_factory=sqlite3.Row
            r=c.execute(f"SELECT * FROM {qid(source)} WHERE {qid(rowid_col)}=?",(rid,)).fetchone()
            c.close()
            if not r:
                return QMessageBox.information(self,"FTS Source",f"No source record found for {source}.{rowid_col}={rid}.")
            self.table_name=source; self.data_title.setText(source); self.page.setValue(1); self.where.setText(f"{qid(rowid_col)} = {rid}")
            self.tabs.setCurrentWidget(self.data_widget); self.load_table()
        except Exception as e:
            self.err(f"{type(e).__name__}: {e}")

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
        self.qw=QueryWorker(self.path,s); self.qw.done.connect(self.query_done); self.qw.error.connect(self.err); self.qw.start()
        self.history.append(("SQL",s,datetime.now().strftime("%H:%M:%S"),"running"))
        self.refresh_history_view()

    def query_done(self,cols,rows,ms):
        self.fill(self.qt,cols,rows); self.qi.setText(f"{len(rows):,} rows displayed (maximum 5,000) • {ms:.1f} ms")
        if self.history:
            h=list(self.history[-1]); h[3]=f"{len(rows):,} rows • {ms:.1f} ms"; self.history[-1]=tuple(h); self.refresh_history_view()

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
