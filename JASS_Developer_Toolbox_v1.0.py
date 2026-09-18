#!/usr/bin/env python3
"""
JASS Developer Toolbox v1.0

A local-first PySide6 developer workbench combining practical inspection,
conversion, hashing, JSON formatting, regex testing, command execution,
environment diagnostics, and project utilities.

Safety:
- No network access is performed by the application.
- File operations are explicit and mostly read-only.
- Command Runner executes only commands entered by the user.
"""

import sys, os, re, json, csv, hashlib, subprocess, datetime, shutil, platform, socket, textwrap
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QTextEdit,
    QPlainTextEdit, QFileDialog, QMessageBox, QProgressBar, QFrame,
    QSplitter, QGroupBox, QFormLayout, QDialog, QMenu, QAbstractItemView
)

APP_NAME = "JASS Developer Toolbox"
VERSION = "1.0"

def human(n):
    n=float(n)
    for u in ("B","KB","MB","GB","TB"):
        if n < 1024: return f"{n:.1f} {u}"
        n/=1024
    return f"{n:.1f} PB"

def run_command(command, timeout=60):
    try:
        p=subprocess.run(command, shell=True, capture_output=True, text=True,
                         timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out."
    except Exception as e:
        return -1, "", str(e)

def safe_read(path, limit=5000000):
    try:
        data=Path(path).read_bytes()[:limit]
        return data.decode("utf-8", errors="replace")
    except Exception as e:
        return f"[Unable to read file: {e}]"

class CommandWorker(QThread):
    output=Signal(int,str,str)
    def __init__(self,command):
        super().__init__(); self.command=command
    def run(self):
        rc,out,err=run_command(self.command,300)
        self.output.emit(rc,out,err)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1550,950)
        self.command_worker=None
        self._build()
        self._style()
        self.refresh_system()

    def _build(self):
        c=QWidget(); self.setCentralWidget(c)
        main=QVBoxLayout(c); main.setContentsMargins(14,14,14,14); main.setSpacing(10)

        hero=QFrame(); hero.setObjectName("hero")
        hl=QVBoxLayout(hero)
        title=QLabel("🧰  JASS Developer Toolbox"); title.setObjectName("title")
        sub=QLabel("A practical local workbench for developers: inspect, format, hash, test, convert and diagnose.")
        sub.setObjectName("subtitle")
        hl.addWidget(title); hl.addWidget(sub)
        main.addWidget(hero)

        self.tabs=QTabWidget(); main.addWidget(self.tabs,1)
        self.dashboard_tab()
        self.file_tab()
        self.text_tab()
        self.json_tab()
        self.regex_tab()
        self.hash_tab()
        self.command_tab()
        self.project_tab()
        self.system_tab()
        self.conversion_tab()

        st=QLabel("Local-first • No cloud APIs • Utilities are explicit • Command Runner executes exactly what you enter")
        st.setObjectName("status"); main.addWidget(st)

    def _card(self,title):
        f=QFrame(); f.setObjectName("card"); l=QVBoxLayout(f)
        a=QLabel(title); a.setObjectName("cardTitle")
        v=QLabel("—"); v.setObjectName("cardValue")
        l.addWidget(a); l.addWidget(v)
        return f,v

    def dashboard_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        g=QGridLayout(); self.cards={}
        for i,(k,t) in enumerate([
            ("os","Operating System"),("python","Python"),("qt","PySide6"),
            ("cpu","CPU"),("ram","RAM"),("shell","Shell")
        ]):
            f,v=self._card(t); self.cards[k]=v; g.addWidget(f,i//3,i%3)
        l.addLayout(g)
        self.dashboard=QTextEdit(); self.dashboard.setReadOnly(True); l.addWidget(self.dashboard,1)
        self.tabs.addTab(w,"🏠 Dashboard")

    def file_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        top=QHBoxLayout()
        self.file_path=QLineEdit(); self.file_path.setPlaceholderText("Choose a file…")
        b=QPushButton("📂 Browse"); b.clicked.connect(self.choose_file)
        load=QPushButton("Open"); load.clicked.connect(self.load_file)
        top.addWidget(self.file_path,1); top.addWidget(b); top.addWidget(load); l.addLayout(top)
        split=QSplitter(Qt.Horizontal)
        self.file_info=QPlainTextEdit(); self.file_info.setReadOnly(True)
        self.file_preview=QPlainTextEdit(); self.file_preview.setReadOnly(True)
        split.addWidget(self.file_info); split.addWidget(self.file_preview)
        l.addWidget(split,1)
        row=QHBoxLayout()
        for label,fn in [("📋 Copy Path",self.copy_file_path),("📂 Open Folder",self.open_file_folder)]:
            b=QPushButton(label); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row)
        self.tabs.addTab(w,"📄 File Inspector")

    def text_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        split=QSplitter(Qt.Horizontal)
        left=QWidget(); ll=QVBoxLayout(left)
        self.text_input=QPlainTextEdit(); self.text_input.setPlaceholderText("Paste text here…")
        ll.addWidget(self.text_input,1)
        right=QWidget(); rl=QVBoxLayout(right)
        self.text_stats=QPlainTextEdit(); self.text_stats.setReadOnly(True); rl.addWidget(self.text_stats)
        b=QPushButton("📊 Analyze Text"); b.clicked.connect(self.analyze_text); rl.addWidget(b)
        split.addWidget(left); split.addWidget(right); split.setSizes([800,500])
        l.addWidget(split,1)
        row=QHBoxLayout()
        for label,fn in [("Uppercase",lambda:self.transform_text(str.upper)),
                         ("Lowercase",lambda:self.transform_text(str.lower)),
                         ("Trim Lines",self.trim_lines),
                         ("Sort Lines",self.sort_lines),
                         ("Unique Lines",self.unique_lines)]:
            b=QPushButton(label); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row)
        self.tabs.addTab(w,"🔤 Text Lab")

    def json_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        split=QSplitter(Qt.Horizontal)
        self.json_in=QPlainTextEdit(); self.json_in.setPlaceholderText("Paste JSON here…")
        self.json_out=QPlainTextEdit(); self.json_out.setReadOnly(False)
        split.addWidget(self.json_in); split.addWidget(self.json_out); split.setSizes([750,750])
        l.addWidget(split,1)
        row=QHBoxLayout()
        for label,fn in [("✨ Format",self.format_json),("🗜 Minify",self.minify_json),
                         ("🔍 Validate",self.validate_json),("📋 Copy Result",self.copy_json)]:
            b=QPushButton(label); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row)
        self.tabs.addTab(w,"{} JSON Lab")

    def regex_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        form=QFormLayout()
        self.regex_pattern=QLineEdit(); self.regex_pattern.setPlaceholderText(r"e.g. \b[A-Z]\w+")
        self.regex_flags=QLineEdit(); self.regex_flags.setPlaceholderText("Flags: i m s")
        form.addRow("Pattern:",self.regex_pattern); form.addRow("Flags:",self.regex_flags)
        l.addLayout(form)
        split=QSplitter(Qt.Vertical)
        self.regex_text=QPlainTextEdit(); self.regex_text.setPlaceholderText("Test text…")
        self.regex_result=QPlainTextEdit(); self.regex_result.setReadOnly(True)
        split.addWidget(self.regex_text); split.addWidget(self.regex_result)
        l.addWidget(split,1)
        b=QPushButton("🔎 Test Regex"); b.setObjectName("primary"); b.clicked.connect(self.test_regex)
        l.addWidget(b); self.tabs.addTab(w,"🔎 Regex Lab")

    def hash_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        row=QHBoxLayout()
        self.hash_path=QLineEdit(); self.hash_path.setPlaceholderText("Choose a file…")
        b=QPushButton("📂 Browse"); b.clicked.connect(self.choose_hash)
        go=QPushButton("🔐 Calculate Hashes"); go.setObjectName("primary"); go.clicked.connect(self.calculate_hashes)
        row.addWidget(self.hash_path,1); row.addWidget(b); row.addWidget(go); l.addLayout(row)
        self.hash_output=QPlainTextEdit(); self.hash_output.setReadOnly(True); l.addWidget(self.hash_output,1)
        self.tabs.addTab(w,"🔐 Hash Lab")

    def command_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.command=QLineEdit(); self.command.setPlaceholderText("Enter a shell command…")
        row=QHBoxLayout(); row.addWidget(self.command,1)
        b=QPushButton("▶ Run"); b.setObjectName("primary"); b.clicked.connect(self.run_command)
        clear=QPushButton("Clear"); clear.clicked.connect(lambda:self.command_output.clear())
        row.addWidget(b);row.addWidget(clear);l.addLayout(row)
        self.command_output=QPlainTextEdit();self.command_output.setReadOnly(True);l.addWidget(self.command_output,1)
        self.tabs.addTab(w,"⌨ Command Runner")

    def project_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        row=QHBoxLayout()
        self.project_path=QLineEdit();self.project_path.setPlaceholderText("Choose project directory…")
        b=QPushButton("📂 Browse");b.clicked.connect(self.choose_project)
        scan=QPushButton("🔎 Inspect Project");scan.setObjectName("primary");scan.clicked.connect(self.inspect_project)
        row.addWidget(self.project_path,1);row.addWidget(b);row.addWidget(scan);l.addLayout(row)
        self.project_output=QPlainTextEdit();self.project_output.setReadOnly(True);l.addWidget(self.project_output,1)
        self.tabs.addTab(w,"🗂 Project Inspector")

    def system_tab(self):
        w=QWidget();l=QVBoxLayout(w)
        b=QPushButton("🔄 Refresh Diagnostics");b.clicked.connect(self.refresh_system);l.addWidget(b)
        self.system_output=QPlainTextEdit();self.system_output.setReadOnly(True);l.addWidget(self.system_output,1)
        self.tabs.addTab(w,"🖥 System Diagnostics")

    def conversion_tab(self):
        w=QWidget();l=QVBoxLayout(w)
        box=QGroupBox("CSV → JSON")
        f=QFormLayout(box)
        self.csv_path=QLineEdit();bc=QPushButton("Browse");bc.clicked.connect(self.choose_csv)
        r=QHBoxLayout();r.addWidget(self.csv_path,1);r.addWidget(bc);f.addRow("CSV:",r)
        self.json_save=QLineEdit();bj=QPushButton("Save As");bj.clicked.connect(self.choose_json_save)
        r=QHBoxLayout();r.addWidget(self.json_save,1);r.addWidget(bj);f.addRow("JSON:",r)
        go=QPushButton("Convert CSV → JSON");go.clicked.connect(self.csv_to_json);f.addRow(go)
        l.addWidget(box)
        box2=QGroupBox("JSON → CSV")
        f2=QFormLayout(box2)
        self.json_path=QLineEdit();b2=QPushButton("Browse");b2.clicked.connect(self.choose_json)
        r=QHBoxLayout();r.addWidget(self.json_path,1);r.addWidget(b2);f2.addRow("JSON:",r)
        self.csv_save=QLineEdit();b3=QPushButton("Save As");b3.clicked.connect(self.choose_csv_save)
        r=QHBoxLayout();r.addWidget(self.csv_save,1);r.addWidget(b3);f2.addRow("CSV:",r)
        go2=QPushButton("Convert JSON → CSV");go2.clicked.connect(self.json_to_csv);f2.addRow(go2)
        l.addWidget(box2);l.addStretch()
        self.tabs.addTab(w,"🔄 Converters")

    def _style(self):
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#11151b;color:#e8edf2;font-size:13px}
        #hero{background:#1a2230;border:1px solid #304057;border-radius:16px}
        #title{font-size:29px;font-weight:700;color:#f4f7fa}
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
        #cardTitle{color:#8f9baa}#cardValue{font-size:20px;font-weight:700}
        #status{color:#7f8b99;padding:4px}
        QHeaderView::section{background:#202936;padding:7px;border:0}
        """)

    def choose_file(self):
        p=QFileDialog.getOpenFileName(self,"Choose File",str(Path.home()))[0]
        if p:self.file_path.setText(p)

    def load_file(self):
        p=Path(self.file_path.text().strip())
        if not p.is_file():return QMessageBox.warning(self,"File Inspector","Choose an existing file.")
        try:
            st=p.stat()
            self.file_info.setPlainText(
                f"Name: {p.name}\nPath: {p}\nSuffix: {p.suffix or '—'}\n"
                f"Size: {human(st.st_size)} ({st.st_size:,} bytes)\n"
                f"Modified: {datetime.datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}\n"
                f"Permissions: {oct(st.st_mode & 0o777)}\n"
                f"Readable: {os.access(p,os.R_OK)}\nWritable: {os.access(p,os.W_OK)}\nExecutable: {os.access(p,os.X_OK)}"
            )
            if st.st_size <= 5_000_000:self.file_preview.setPlainText(safe_read(p))
            else:self.file_preview.setPlainText("[Preview suppressed for files larger than 5 MB.]")
        except Exception as e:QMessageBox.critical(self,"Error",str(e))

    def copy_file_path(self):
        QApplication.clipboard().setText(self.file_path.text());self.statusBar().showMessage("Path copied",2000)

    def open_file_folder(self):
        p=Path(self.file_path.text())
        if p.exists():subprocess.Popen(["xdg-open",str(p.parent)])

    def analyze_text(self):
        t=self.text_input.toPlainText()
        lines=t.splitlines(); ws=words=re.findall(r"\b[\w’'-]+\b",t,re.UNICODE)
        chars=len(t); nonspace=len(re.sub(r"\s","",t))
        self.text_stats.setPlainText(
            f"Characters: {chars:,}\nNon-whitespace: {nonspace:,}\n"
            f"Words: {len(ws):,}\nLines: {len(lines):,}\n"
            f"Paragraphs: {len([x for x in re.split(r'\\n\\s*\\n',t) if x.strip()]):,}\n"
            f"Unique words: {len(set(x.lower() for x in ws)):,}\n"
            f"Average word length: {(sum(map(len,ws))/len(ws)) if ws else 0:.2f}"
        )

    def transform_text(self,fn):self.text_input.setPlainText(fn(self.text_input.toPlainText()))
    def trim_lines(self):self.text_input.setPlainText("\n".join(x.strip() for x in self.text_input.toPlainText().splitlines()))
    def sort_lines(self):self.text_input.setPlainText("\n".join(sorted(self.text_input.toPlainText().splitlines(),key=str.casefold)))
    def unique_lines(self):
        seen=set();out=[]
        for x in self.text_input.toPlainText().splitlines():
            if x not in seen:seen.add(x);out.append(x)
        self.text_input.setPlainText("\n".join(out))

    def format_json(self):
        try:self.json_out.setPlainText(json.dumps(json.loads(self.json_in.toPlainText()),indent=2,ensure_ascii=False))
        except Exception as e:self.json_out.setPlainText(f"INVALID JSON\n\n{e}")

    def minify_json(self):
        try:self.json_out.setPlainText(json.dumps(json.loads(self.json_in.toPlainText()),ensure_ascii=False,separators=(",",":")))
        except Exception as e:self.json_out.setPlainText(f"INVALID JSON\n\n{e}")

    def validate_json(self):
        try:json.loads(self.json_in.toPlainText());self.json_out.setPlainText("✓ Valid JSON")
        except Exception as e:self.json_out.setPlainText(f"✗ Invalid JSON\n\n{e}")

    def copy_json(self):QApplication.clipboard().setText(self.json_out.toPlainText())

    def test_regex(self):
        flags=0
        for x in self.regex_flags.text().lower().split():
            flags|={"i":re.I,"m":re.M,"s":re.S}.get(x,0)
        try:
            pat=re.compile(self.regex_pattern.text(),flags);t=self.regex_text.toPlainText()
            ms=list(pat.finditer(t))
            lines=[f"Matches: {len(ms)}"]
            for i,m in enumerate(ms[:500],1):lines.append(f"{i}. {m.group()!r}  span={m.span()}")
            self.regex_result.setPlainText("\n".join(lines))
        except Exception as e:self.regex_result.setPlainText(f"Regex error:\n{e}")

    def choose_hash(self):
        p=QFileDialog.getOpenFileName(self,"Choose File",str(Path.home()))[0]
        if p:self.hash_path.setText(p)

    def calculate_hashes(self):
        p=Path(self.hash_path.text().strip())
        if not p.is_file():return QMessageBox.warning(self,"Hash Lab","Choose an existing file.")
        try:
            md5=hashlib.md5();sha1=hashlib.sha1();sha256=hashlib.sha256()
            with open(p,"rb") as f:
                while b:=f.read(1024*1024):
                    md5.update(b);sha1.update(b);sha256.update(b)
            self.hash_output.setPlainText(
                f"File: {p}\nSize: {human(p.stat().st_size)}\n\n"
                f"MD5:\n{md5.hexdigest()}\n\nSHA-1:\n{sha1.hexdigest()}\n\n"
                f"SHA-256:\n{sha256.hexdigest()}"
            )
        except Exception as e:QMessageBox.critical(self,"Hash error",str(e))

    def run_command(self):
        cmd=self.command.text().strip()
        if not cmd:return
        self.command_output.appendPlainText(f"$ {cmd}\n")
        self.command_worker=CommandWorker(cmd);self.command_worker.output.connect(self.command_done)
        self.command_worker.start()

    def command_done(self,rc,out,err):
        self.command_output.appendPlainText(out or "")
        if err:self.command_output.appendPlainText(f"[stderr]\n{err}")
        self.command_output.appendPlainText(f"\n[exit code: {rc}]\n")

    def choose_project(self):
        p=QFileDialog.getExistingDirectory(self,"Choose Project",str(Path.home()))
        if p:self.project_path.setText(p)

    def inspect_project(self):
        root=Path(self.project_path.text().strip())
        if not root.is_dir():return QMessageBox.warning(self,"Project Inspector","Choose a valid directory.")
        counts={};total=0;size=0;largest=[];special=[]
        for base,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in {".git","node_modules",".venv","venv","__pycache__","build","dist"}]
            for fn in files:
                p=Path(base)/fn
                try:
                    st=p.stat();ext=p.suffix.lower() or "[none]"
                    counts[ext]=counts.get(ext,0)+1;total+=1;size+=st.st_size
                    largest.append((st.st_size,str(p)))
                except:pass
        largest=sorted(largest,reverse=True)[:20]
        git=(root/".git").is_dir()
        report=[f"PROJECT: {root}","",f"Files: {total:,}",f"Size: {human(size)}",
                f"Git repository: {'Yes' if git else 'No'}","",
                "FILE TYPES"]
        report += [f"{k:15} {v:,}" for k,v in sorted(counts.items(),key=lambda x:x[1],reverse=True)]
        report += ["","LARGEST FILES"]
        report += [f"{human(s):>12}  {p}" for s,p in largest]
        self.project_output.setPlainText("\n".join(report))

    def refresh_system(self):
        if not hasattr(self,"system_output"):return
        py=sys.version.split()[0]
        qt=QApplication.instance().property("qt_version") or "PySide6"
        cpu=platform.processor() or platform.machine()
        shell=os.environ.get("SHELL","—")
        ram="—"
        try:
            if Path("/proc/meminfo").exists():
                m=re.search(r"MemTotal:\s+(\d+)",Path("/proc/meminfo").read_text())
                if m:ram=human(int(m.group(1))*1024)
        except:pass
        self.cards["os"].setText(f"{platform.system()} {platform.release()}")
        self.cards["python"].setText(py);self.cards["qt"].setText(str(qt))
        self.cards["cpu"].setText(cpu[:28]);self.cards["ram"].setText(ram);self.cards["shell"].setText(Path(shell).name if shell!="—" else "—")
        lines=[
            f"Platform: {platform.platform()}",
            f"Machine: {platform.machine()}",
            f"Processor: {platform.processor() or '—'}",
            f"Python: {sys.version}",
            f"Executable: {sys.executable}",
            f"Working directory: {os.getcwd()}",
            f"Hostname: {socket.gethostname()}",
            f"User: {os.environ.get('USER',os.environ.get('USERNAME','—'))}",
            f"Shell: {shell}",
            f"PySide6: {qt}",
            "",
            "TOOLS",
            f"git: {shutil.which('git') or 'not found'}",
            f"python3: {shutil.which('python3') or 'not found'}",
            f"pip3: {shutil.which('pip3') or 'not found'}",
            f"ffmpeg: {shutil.which('ffmpeg') or 'not found'}",
            f"adb: {shutil.which('adb') or 'not found'}",
            f"docker: {shutil.which('docker') or 'not found'}",
            f"ollama: {shutil.which('ollama') or 'not found'}",
        ]
        self.system_output.setPlainText("\n".join(lines))
        self.dashboard.setPlainText("\n".join(lines))

    def choose_csv(self):
        p=QFileDialog.getOpenFileName(self,"Choose CSV",str(Path.home()),"CSV (*.csv)")[0]
        if p:self.csv_path.setText(p)
    def choose_json_save(self):
        p=QFileDialog.getSaveFileName(self,"Save JSON",str(Path.home()/"output.json"),"JSON (*.json)")[0]
        if p:self.json_save.setText(p)
    def choose_json(self):
        p=QFileDialog.getOpenFileName(self,"Choose JSON",str(Path.home()),"JSON (*.json)")[0]
        if p:self.json_path.setText(p)
    def choose_csv_save(self):
        p=QFileDialog.getSaveFileName(self,"Save CSV",str(Path.home()/"output.csv"),"CSV (*.csv)")[0]
        if p:self.csv_save.setText(p)

    def csv_to_json(self):
        try:
            with open(self.csv_path.text(),newline="",encoding="utf-8-sig") as f:data=list(csv.DictReader(f))
            Path(self.json_save.text()).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
            QMessageBox.information(self,"Converted","CSV → JSON complete.")
        except Exception as e:QMessageBox.critical(self,"Conversion failed",str(e))

    def json_to_csv(self):
        try:
            data=json.loads(Path(self.json_path.text()).read_text(encoding="utf-8"))
            if isinstance(data,dict):data=[data]
            if not data:raise ValueError("JSON contains no records.")
            keys=[];[keys.append(k) for row in data if isinstance(row,dict) for k in row if k not in keys]
            with open(self.csv_save.text(),"w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
                for row in data:w.writerow(row)
            QMessageBox.information(self,"Converted","JSON → CSV complete.")
        except Exception as e:QMessageBox.critical(self,"Conversion failed",str(e))

def main():
    app=QApplication(sys.argv);app.setApplicationName(APP_NAME)
    w=MainWindow();w.show();sys.exit(app.exec())

if __name__=="__main__":main()
