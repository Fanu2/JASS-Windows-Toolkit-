#!/usr/bin/env python3
"""
JASS Android Transfer Manager v1.0
A beautiful PySide6 GUI for transferring files between Android devices and Linux.

Backend strategy:
- KDE Connect CLI is the preferred backend when available.
- ADB is supported when Android USB debugging is enabled.
- Local filesystem browsing is supported for ADB-connected devices.
- No cloud service is required.

The application never deletes or moves Android files automatically.
"""

import sys, os, re, json, csv, shutil, subprocess, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QTextEdit,
    QPlainTextEdit, QFileDialog, QMessageBox, QProgressBar, QFrame,
    QSplitter, QTreeWidget, QTreeWidgetItem, QMenu, QDialog,
    QAbstractItemView, QGroupBox
)

APP_NAME = "JASS Android Transfer Manager"
VERSION = "1.0"

def human(n):
    n=float(n)
    for u in ("B","KB","MB","GB","TB"):
        if n<1024:return f"{n:.1f} {u}"
        n/=1024
    return f"{n:.1f} PB"

def run_cmd(args, timeout=30):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except Exception as e:return -1,"",str(e)

def command_exists(name): return shutil.which(name) is not None

class DeviceWorker(QThread):
    done=Signal(list)
    error=Signal(str)
    def run(self):
        devices=[]
        if command_exists("kdeconnect-cli"):
            rc,out,err=run_cmd(["kdeconnect-cli","-a"])
            if rc==0:
                for line in out.splitlines():
                    m=re.match(r"-\s+(.+?):\s+([0-9a-fA-F]{8,})(?:\s+\((.*?)\))?$",line.strip())
                    if m:
                        devices.append({"backend":"KDE Connect","name":m.group(1).strip(),
                                        "id":m.group(2),"status":m.group(3) or "reachable"})
        if command_exists("adb"):
            rc,out,err=run_cmd(["adb","devices"])
            if rc==0:
                for line in out.splitlines()[1:]:
                    parts=line.split()
                    if len(parts)>=2 and parts[1]=="device":
                        serial=parts[0]
                        _,name,_=run_cmd(["adb","-s",serial,"shell","getprop","ro.product.model"])
                        devices.append({"backend":"ADB","name":name or serial,"id":serial,"status":"USB / ADB"})
        self.done.emit(devices)

class TransferWorker(QThread):
    progress=Signal(int,str)
    done=Signal(bool,str)
    def __init__(self,backend,device,action,source,target):
        super().__init__();self.backend=backend;self.device=device
        self.action=action;self.source=source;self.target=target
    def run(self):
        try:
            if self.backend=="ADB":
                if self.action=="push":
                    args=["adb","-s",self.device,"push",self.source,self.target]
                else:
                    args=["adb","-s",self.device,"pull",self.source,self.target]
                rc,out,err=run_cmd(args,timeout=3600)
                self.progress.emit(100,out or err)
                self.done.emit(rc==0,out or err)
            elif self.backend=="KDE Connect":
                if self.action=="send":
                    # kdeconnect-cli --share accepts files and folders.
                    args=["kdeconnect-cli","-d",self.device,"--share",self.source]
                    rc,out,err=run_cmd(args,timeout=3600)
                    self.progress.emit(100,out or err)
                    self.done.emit(rc==0,out or err)
                else:
                    self.done.emit(False,"KDE Connect receiving is handled by the Android share/send workflow in v1.0.")
            else:self.done.emit(False,"Unknown transfer backend.")
        except Exception as e:self.done.emit(False,str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1500,930)
        self.devices=[]
        self.current=None
        self.worker=None
        self._build()
        self._style()
        self.refresh_devices()

    def _build(self):
        c=QWidget();self.setCentralWidget(c)
        main=QVBoxLayout(c);main.setContentsMargins(14,14,14,14);main.setSpacing(10)

        hero=QFrame();hero.setObjectName("hero");hl=QVBoxLayout(hero)
        t=QLabel("📱  JASS Android Transfer Manager");t.setObjectName("title")
        s=QLabel("Move files between Android and Linux using KDE Connect or ADB — with a clean, local-first workflow.")
        s.setObjectName("subtitle")
        hl.addWidget(t);hl.addWidget(s)
        row=QHBoxLayout()
        self.device_box=QComboBox();self.device_box.currentIndexChanged.connect(self.device_changed)
        refresh=QPushButton("🔄 Refresh Devices");refresh.clicked.connect(self.refresh_devices)
        self.backend=QComboBox();self.backend.addItems(["Auto","KDE Connect","ADB"])
        row.addWidget(QLabel("Device:"));row.addWidget(self.device_box,1)
        row.addWidget(QLabel("Backend:"));row.addWidget(self.backend);row.addWidget(refresh)
        hl.addLayout(row);main.addWidget(hero)

        self.progress=QProgressBar();self.progress.setTextVisible(True);self.progress.setFormat("Ready")
        main.addWidget(self.progress)

        self.tabs=QTabWidget();main.addWidget(self.tabs,1)
        self.transfer_tab();self.android_browser();self.quick();self.history();self.help_tab()

        st=QLabel("Local network / USB • No cloud storage • No automatic deletion • Transfers occur only when explicitly started")
        st.setObjectName("status");main.addWidget(st)

    def card(self,title):
        f=QFrame();f.setObjectName("card");l=QVBoxLayout(f)
        a=QLabel(title);a.setObjectName("cardTitle");v=QLabel("—");v.setObjectName("cardValue")
        l.addWidget(a);l.addWidget(v);return f,v

    def transfer_tab(self):
        w=QWidget();l=QVBoxLayout(w)
        grid=QGridLayout()
        self.cards={}
        for i,(k,t) in enumerate([("status","Connection"),("backend","Backend"),
                                   ("device","Device"),("queue","Queue")]):
            f,v=self.card(t);self.cards[k]=v;grid.addWidget(f,0,i)
        l.addLayout(grid)

        box=QGroupBox("Linux → Android")
        bl=QVBoxLayout(box)
        r=QHBoxLayout();self.send_path=QLineEdit();self.send_path.setPlaceholderText("File or folder to send to Android…")
        b=QPushButton("📂 Choose");b.clicked.connect(self.choose_send)
        r.addWidget(self.send_path,1);r.addWidget(b);bl.addLayout(r)
        r=QHBoxLayout();self.android_dest=QLineEdit("/sdcard/Download")
        r.addWidget(QLabel("ADB destination:"));r.addWidget(self.android_dest,1)
        send=QPushButton("📤 Send to Android");send.setObjectName("primary");send.clicked.connect(self.send)
        r.addWidget(send);bl.addLayout(r)
        l.addWidget(box)

        box2=QGroupBox("Android → Linux")
        b2=QVBoxLayout(box2)
        r=QHBoxLayout();self.pull_path=QLineEdit();self.pull_path.setPlaceholderText("Android path, e.g. /sdcard/Download/photo.jpg")
        r.addWidget(self.pull_path,1);b2.addLayout(r)
        r=QHBoxLayout();self.local_dest=QLineEdit(str(Path.home()/"Downloads"))
        choose=QPushButton("📂 Destination");choose.clicked.connect(self.choose_dest)
        pull=QPushButton("📥 Receive to Linux");pull.setObjectName("primary");pull.clicked.connect(self.pull)
        r.addWidget(self.local_dest,1);r.addWidget(choose);r.addWidget(pull);b2.addLayout(r)
        l.addWidget(box2)

        note=QLabel("KDE Connect: sending from Linux is supported here. For Android → Linux, use Android's KDE Connect Share/Send action and choose this computer.")
        note.setWordWrap(True);note.setObjectName("hint");l.addWidget(note)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);l.addWidget(self.log,1)
        self.tabs.addTab(w,"📤 Transfer")

    def android_browser(self):
        w=QWidget();l=QVBoxLayout(w)
        top=QHBoxLayout()
        self.remote_path=QLineEdit("/sdcard/Download")
        browse=QPushButton("📂 Browse Android Path");browse.clicked.connect(self.adb_list)
        top.addWidget(QLabel("ADB path:"));top.addWidget(self.remote_path,1);top.addWidget(browse);l.addLayout(top)
        self.remote=QTableWidget(0,4)
        self.remote.setHorizontalHeaderLabels(["Type","Name","Size","Path"])
        self.remote.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.remote.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        self.remote.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.remote.doubleClicked.connect(self.remote_double)
        self.remote.setContextMenuPolicy(Qt.CustomContextMenu);self.remote.customContextMenuRequested.connect(self.remote_menu)
        l.addWidget(self.remote,1)
        l.addWidget(QLabel("ADB browser works when an ADB-connected device is selected. Double-click a directory to enter it."))
        self.tabs.addTab(w,"🗂 Android Browser")

    def quick(self):
        w=QWidget();l=QVBoxLayout(w)
        l.addWidget(QLabel("Quick destinations for common Android folders. Select an item and send a Linux file/folder."))
        self.quicklist=QTableWidget(0,2);self.quicklist.setHorizontalHeaderLabels(["Destination","ADB Path"])
        paths=[("Downloads","/sdcard/Download"),("Pictures","/sdcard/Pictures"),
               ("DCIM Camera","/sdcard/DCIM/Camera"),("Movies","/sdcard/Movies"),
               ("Music","/sdcard/Music"),("Documents","/sdcard/Documents")]
        self.quicklist.setRowCount(len(paths))
        for i,(a,b) in enumerate(paths):
            self.quicklist.setItem(i,0,QTableWidgetItem(a));self.quicklist.setItem(i,1,QTableWidgetItem(b))
        self.quicklist.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addWidget(self.quicklist,1)
        b=QPushButton("Use Selected Destination");b.clicked.connect(self.use_quick);l.addWidget(b)
        self.tabs.addTab(w,"⚡ Quick Destinations")

    def history(self):
        w=QWidget();l=QVBoxLayout(w)
        self.history_table=QTableWidget(0,4);self.history_table.setHorizontalHeaderLabels(["Time","Action","Source","Target"])
        self.history_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        l.addWidget(self.history_table)
        self.tabs.addTab(w,"🕘 Session History")

    def help_tab(self):
        w=QWidget();l=QVBoxLayout(w)
        text=QPlainTextEdit();text.setReadOnly(True)
        text.setPlainText("""JASS ANDROID TRANSFER MANAGER

KDE CONNECT
-----------
Best for wireless everyday transfers.

Linux → Android:
1. Select a paired/reachable KDE Connect device.
2. Choose a Linux file or folder.
3. Click Send to Android.

Android → Linux:
Use KDE Connect on Android, choose Share/Send,
select this computer, then choose the files/folders.

ADB
---
Best for direct USB transfers and Android filesystem browsing.

Requirements:
    sudo apt install adb

On Android:
    Enable Developer Options.
    Enable USB debugging.
    Connect the phone with USB.
    Approve the computer on the phone.

Useful ADB paths:
    /sdcard/Download
    /sdcard/DCIM
    /sdcard/Pictures
    /sdcard/Documents
    /sdcard/Music
    /sdcard/Movies

SECURITY
--------
The application does not automatically delete, move or overwrite
Android files. Transfer operations are explicit.

KDE Connect uses the local network.
ADB uses the USB debugging connection.

The application does not upload your files to a cloud service.
""")
        l.addWidget(text);self.tabs.addTab(w,"ℹ️ Help")

    def _style(self):
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#11151b;color:#e8edf2;font-size:13px}
        #hero{background:#1a2230;border:1px solid #304057;border-radius:16px}
        #title{font-size:28px;font-weight:700;color:#f4f7fa}
        #subtitle{font-size:14px;color:#aeb9c7}
        #primary{background:#2d8cff;color:white;font-weight:700;padding:9px 16px;border-radius:8px}
        QPushButton{background:#202936;border:1px solid #354255;padding:8px 12px;border-radius:7px}
        QPushButton:hover{background:#2b3748}
        QLineEdit,QComboBox,QSpinBox,QTextEdit,QPlainTextEdit,QTableWidget,QTreeWidget{
          background:#0d1117;border:1px solid #303b4b;border-radius:7px}
        QTabWidget::pane{border:1px solid #2c3746;border-radius:8px}
        QTabBar::tab{padding:10px 15px;background:#18202b;border:1px solid #293546}
        QTabBar::tab:selected{background:#263348}
        #card{background:#18202b;border:1px solid #2c3746;border-radius:12px}
        #cardTitle{color:#8f9baa}#cardValue{font-size:21px;font-weight:700}
        #status{color:#7f8b99;padding:4px}#hint{color:#91a1b3;padding:8px}
        QHeaderView::section{background:#202936;padding:7px;border:0}
        QProgressBar{border:1px solid #303b4b;border-radius:7px;text-align:center;height:22px}
        QProgressBar::chunk{background:#2d8cff;border-radius:6px}
        """)

    def refresh_devices(self):
        self.progress.setRange(0,0);self.progress.setFormat("Discovering Android devices…")
        self.dw=DeviceWorker();self.dw.done.connect(self.devices_done);self.dw.start()

    def devices_done(self,devices):
        self.devices=devices;self.device_box.clear()
        for d in devices:self.device_box.addItem(f"{d['name']}  •  {d['backend']}  •  {d['status']}",d)
        self.progress.setRange(0,100);self.progress.setValue(100)
        if devices:self.device_changed(0)
        else:
            self.progress.setFormat("No device detected")
            self.cards["status"].setText("Not connected");self.cards["backend"].setText("—")
            self.cards["device"].setText("—")
            self.log.appendPlainText("No Android device detected. Pair KDE Connect or connect an ADB device.")

    def device_changed(self,index):
        if index<0 or index>=len(self.devices):return
        self.current=self.devices[index]
        self.cards["status"].setText(self.current["status"])
        self.cards["backend"].setText(self.current["backend"])
        self.cards["device"].setText(self.current["name"])
        self.cards["queue"].setText("Ready")

    def choose_send(self):
        p=QFileDialog.getOpenFileName(self,"Choose File",str(Path.home()))[0]
        if p:self.send_path.setText(p)

    def choose_dest(self):
        p=QFileDialog.getExistingDirectory(self,"Choose Linux Destination",str(Path.home()/"Downloads"))
        if p:self.local_dest.setText(p)

    def effective_backend(self):
        if not self.current:return None
        selected=self.backend.currentText()
        if selected=="Auto":return self.current["backend"]
        return selected if selected==self.current["backend"] else None

    def send(self):
        if not self.current:return QMessageBox.warning(self,"No device","Select an Android device first.")
        source=self.send_path.text().strip()
        if not source or not Path(source).exists():return QMessageBox.warning(self,"Source missing","Choose an existing file or folder.")
        backend=self.effective_backend()
        if not backend:return QMessageBox.warning(self,"Backend mismatch","Selected backend is not available for the current device.")
        target=self.android_dest.text().strip()
        action="send" if backend=="KDE Connect" else "push"
        self.start_transfer(backend,self.current["id"],action,source,target)

    def pull(self):
        if not self.current:return QMessageBox.warning(self,"No device","Select an Android device first.")
        backend=self.effective_backend()
        if backend!="ADB":return QMessageBox.information(self,"ADB required","Android → Linux direct path transfer in this release uses ADB.")
        src=self.pull_path.text().strip()
        dst=self.local_dest.text().strip()
        if not src:return QMessageBox.warning(self,"Missing path","Enter an Android path.")
        if not Path(dst).is_dir():return QMessageBox.warning(self,"Destination","Choose an existing Linux destination folder.")
        self.start_transfer("ADB",self.current["id"],"pull",src,dst)

    def start_transfer(self,backend,device,action,source,target):
        self.progress.setRange(0,0);self.progress.setFormat("Transferring…")
        self.cards["queue"].setText("Active")
        self.worker=TransferWorker(backend,device,action,source,target)
        self.worker.progress.connect(lambda n,s:self.log.appendPlainText(s))
        self.worker.done.connect(lambda ok,msg:self.transfer_done(ok,msg,action,source,target))
        self.worker.start()

    def transfer_done(self,ok,msg,action,source,target):
        self.progress.setRange(0,100);self.progress.setValue(100)
        self.progress.setFormat("Transfer complete" if ok else "Transfer failed")
        self.cards["queue"].setText("Ready")
        self.log.appendPlainText(("✓ " if ok else "✗ ")+msg)
        row=self.history_table.rowCount();self.history_table.insertRow(row)
        vals=[datetime.datetime.now().strftime("%H:%M:%S"),action,source,target]
        for j,v in enumerate(vals):self.history_table.setItem(row,j,QTableWidgetItem(str(v)))
        if not ok:QMessageBox.warning(self,"Transfer failed",msg)

    def adb_list(self):
        if not self.current or self.current["backend"]!="ADB":
            QMessageBox.information(self,"ADB browser","Select an ADB-connected device.");return
        path=self.remote_path.text().strip() or "/sdcard"
        rc,out,err=run_cmd(["adb","-s",self.current["id"],"shell","ls","-la",path],timeout=30)
        if rc!=0:return QMessageBox.warning(self,"ADB error",err or out)
        rows=[]
        for line in out.splitlines():
            line=line.strip()
            if not line or line.startswith("total "):continue
            parts=line.split(None,7)
            if len(parts)<7:continue
            name=parts[-1];size=parts[4] if len(parts)>4 else ""
            typ="DIR" if line.startswith("d") else "FILE"
            full=path.rstrip("/")+"/"+name
            rows.append((typ,name,size,full))
        self.remote.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,v in enumerate(r):self.remote.setItem(i,j,QTableWidgetItem(v))

    def remote_double(self,index):
        path=self.remote.item(index.row(),3).text()
        if self.remote.item(index.row(),0).text()=="DIR":
            self.remote_path.setText(path);self.adb_list()

    def remote_menu(self,pos):
        row=self.remote.rowAt(pos.y())
        if row<0:return
        path=self.remote.item(row,3).text()
        menu=QMenu(self);pull=menu.addAction("📥 Receive Selected")
        cp=menu.addAction("📋 Copy Android Path")
        a=menu.exec(self.remote.viewport().mapToGlobal(pos))
        if a==cp:QApplication.clipboard().setText(path)
        elif a==pull:
            self.pull_path.setText(path);self.tabs.setCurrentIndex(0)

    def use_quick(self):
        row=self.quicklist.currentRow()
        if row<0:return
        self.android_dest.setText(self.quicklist.item(row,1).text())
        self.tabs.setCurrentIndex(0)

def main():
    app=QApplication(sys.argv);app.setApplicationName(APP_NAME)
    w=MainWindow();w.show();sys.exit(app.exec())

if __name__=="__main__":main()
