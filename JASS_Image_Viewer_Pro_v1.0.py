#!/usr/bin/env python3
"""JASS Image Viewer Pro v1.0 - lightweight PySide6 image viewer."""
import sys, os, json, shutil, subprocess
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction, QImage, QPixmap, QPainter, QTransform, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QToolButton,
    QFileDialog, QHBoxLayout, QVBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QComboBox, QCheckBox, QSpinBox, QMenu, QDialog, QDialogButtonBox,
    QFormLayout, QMessageBox, QFrame
)

APP_NAME = "JASS Image Viewer Pro"
VERSION = "1.0.0"
SUPPORTED = {".jpg",".jpeg",".png",".bmp",".webp",".gif",".tif",".tiff",".ico"}

def human_size(n):
    v = float(n)
    for u in ("B","KB","MB","GB","TB"):
        if v < 1024 or u == "TB":
            return f"{v:.1f} {u}"
        v /= 1024

class ImageCanvas(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.sc = QGraphicsScene(self)
        self.setScene(self.sc)
        self.item = QGraphicsPixmapItem()
        self.sc.addItem(self.item)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(Qt.black)
        self.setFrameShape(QFrame.NoFrame)

    def set_pixmap(self, pm):
        self.item.setPixmap(pm)
        self.sc.setSceneRect(self.item.boundingRect())
        self.fit_image()

    def fit_image(self):
        if not self.item.pixmap().isNull():
            self.resetTransform()
            self.fitInView(self.item, Qt.KeepAspectRatio)

    def actual_size(self):
        self.resetTransform()

    def zoom(self, factor):
        self.scale(factor, factor)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)

class InfoDialog(QDialog):
    def __init__(self, parent, path):
        super().__init__(parent)
        self.setWindowTitle("Image Information")
        self.resize(560, 330)
        form = QFormLayout(self)
        img = QImage(str(path))
        st = path.stat()
        rows = [
            ("File", path.name),
            ("Folder", str(path.parent)),
            ("Format", path.suffix.upper().lstrip(".")),
            ("Dimensions", f"{img.width()} × {img.height()} px"),
            ("File size", human_size(st.st_size)),
            ("Modified", datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")),
            ("Color depth", f"{img.depth()} bit"),
            ("Alpha channel", "Yes" if img.hasAlphaChannel() else "No"),
        ]
        for k, v in rows:
            lab = QLabel(v)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(QLabel(f"<b>{k}</b>"), lab)
        b = QDialogButtonBox(QDialogButtonBox.Close)
        b.rejected.connect(self.reject)
        form.addRow(b)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1450, 900)
        self.folder = None
        self.files = []
        self.index = -1
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False
        self.favorites = set()
        self.fav_file = Path.home() / ".jass_image_viewer_favorites.json"
        self.load_favorites()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_image)
        self.build_ui()
        self.build_menu()
        self.style_ui()
        self.statusBar().showMessage("Open a folder or image to begin")

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(10,10,10,10)
        main.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel(f"🖼️ <b>{APP_NAME}</b>")
        title.setObjectName("title")
        top.addWidget(title)
        top.addStretch()
        self.folder_btn = QPushButton("📁 Open Folder")
        self.folder_btn.clicked.connect(self.open_folder)
        top.addWidget(self.folder_btn)
        self.open_btn = QPushButton("🖼️ Open Image")
        self.open_btn.clicked.connect(self.open_image)
        top.addWidget(self.open_btn)
        self.favorite_btn = QPushButton("☆ Favorite")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        top.addWidget(self.favorite_btn)
        main.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        main.addWidget(split, 1)

        left = QFrame(); left.setObjectName("panel")
        lv = QVBoxLayout(left)
        self.folder_label = QLabel("No folder selected")
        self.folder_label.setWordWrap(True)
        lv.addWidget(self.folder_label)
        row = QHBoxLayout()
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Name","Name (reverse)","Newest","Oldest","Largest","Smallest"])
        self.sort_combo.currentIndexChanged.connect(self.sort_files)
        row.addWidget(self.sort_combo)
        self.fav_only = QCheckBox("★")
        self.fav_only.setToolTip("Show favorites only")
        self.fav_only.toggled.connect(self.refresh_list)
        row.addWidget(self.fav_only)
        lv.addLayout(row)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.IconMode)
        self.thumbs.setIconSize(QSize(150,105))
        self.thumbs.setGridSize(QSize(180,145))
        self.thumbs.setResizeMode(QListWidget.Adjust)
        self.thumbs.setSpacing(5)
        self.thumbs.currentRowChanged.connect(self.select_row)
        self.thumbs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.thumbs.customContextMenuRequested.connect(self.thumb_menu)
        lv.addWidget(self.thumbs, 1)
        split.addWidget(left)

        center = QFrame()
        cv = QVBoxLayout(center); cv.setContentsMargins(0,0,0,0)
        self.canvas = ImageCanvas()
        cv.addWidget(self.canvas, 1)
        controls = QHBoxLayout()
        for text, tip, slot in [
            ("⟲","Rotate left",lambda:self.rotate(-90)),
            ("⟳","Rotate right",lambda:self.rotate(90)),
            ("↔","Flip horizontal",self.flip_horizontal),
            ("↕","Flip vertical",self.flip_vertical),
            ("−","Zoom out",lambda:self.canvas.zoom(.8)),
            ("1:1","Actual size",self.actual),
            ("Fit","Fit image",self.fit),
            ("＋","Zoom in",lambda:self.canvas.zoom(1.25)),
        ]:
            b = QToolButton(); b.setText(text); b.setToolTip(tip); b.clicked.connect(slot)
            controls.addWidget(b)
        controls.addStretch()
        self.slide_btn = QPushButton("▶ Slideshow")
        self.slide_btn.clicked.connect(self.toggle_slideshow)
        controls.addWidget(self.slide_btn)
        self.interval = QSpinBox()
        self.interval.setRange(1,60); self.interval.setValue(3); self.interval.setSuffix(" s")
        controls.addWidget(self.interval)
        cv.addLayout(controls)
        split.addWidget(center)

        right = QFrame(); right.setObjectName("panel")
        rv = QVBoxLayout(right)
        rv.addWidget(QLabel("<b>IMAGE DETAILS</b>"))
        self.preview = QLabel("No image selected")
        self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumHeight(180)
        rv.addWidget(self.preview)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rv.addWidget(self.info)
        ib = QPushButton("ℹ Full Information")
        ib.clicked.connect(self.show_info); rv.addWidget(ib)
        rv.addStretch()
        split.addWidget(right)
        split.setSizes([330,800,300])

        nav = QHBoxLayout()
        p = QPushButton("◀ Previous"); p.clicked.connect(self.prev_image); nav.addWidget(p)
        n = QPushButton("Next ▶"); n.clicked.connect(self.next_image); nav.addWidget(n)
        nav.addStretch()
        self.counter = QLabel("0 / 0"); nav.addWidget(self.counter)
        main.addLayout(nav)

    def build_menu(self):
        bar = self.menuBar()
        fm = bar.addMenu("&File")
        self.action(fm,"Open Folder",self.open_folder,"Ctrl+O")
        self.action(fm,"Open Image",self.open_image,"Ctrl+Shift+O")
        self.action(fm,"Save As",self.save_as,"Ctrl+S")
        self.action(fm,"Copy Image",self.copy_image,"Ctrl+C")
        fm.addSeparator(); self.action(fm,"Exit",self.close,"Ctrl+Q")
        vm = bar.addMenu("&View")
        self.action(vm,"Fit Image",self.fit,"F")
        self.action(vm,"Actual Size",self.actual,"1")
        self.action(vm,"Zoom In",lambda:self.canvas.zoom(1.25),"+")
        self.action(vm,"Zoom Out",lambda:self.canvas.zoom(.8),"-")
        self.action(vm,"Fullscreen",self.toggle_fullscreen,"F11")
        tm = bar.addMenu("&Tools")
        self.action(tm,"Rotate Left",lambda:self.rotate(-90),"L")
        self.action(tm,"Rotate Right",lambda:self.rotate(90),"R")
        self.action(tm,"Flip Horizontal",self.flip_horizontal)
        self.action(tm,"Flip Vertical",self.flip_vertical)
        self.action(tm,"Image Information",self.show_info,"I")

    def action(self, menu, text, slot, shortcut=None):
        a = QAction(text,self)
        if shortcut: a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot); menu.addAction(a)

    def style_ui(self):
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#20242b;color:#e8ecf1}
        QFrame#panel{background:#282d35;border:1px solid #3b424d;border-radius:10px}
        QLabel#title{font-size:20px;padding:4px}
        QPushButton,QToolButton,QComboBox,QSpinBox{background:#303640;border:1px solid #48515e;border-radius:7px;padding:7px 10px}
        QPushButton:hover,QToolButton:hover{background:#3b4450}
        QListWidget{background:#20242b;border:0;border-radius:8px}
        QListWidget::item{border-radius:7px;padding:4px}
        QListWidget::item:selected{background:#45505e}
        QToolButton{min-width:38px;font-size:16px}
        QStatusBar{background:#181b20}
        QMenu{background:#282d35;border:1px solid #48515e}
        QMenu::item:selected{background:#3b4450}
        """)

    def load_favorites(self):
        try: self.favorites=set(json.loads(self.fav_file.read_text()))
        except Exception: self.favorites=set()

    def save_favorites(self):
        try: self.fav_file.write_text(json.dumps(sorted(self.favorites),indent=2))
        except Exception: pass

    def open_folder(self):
        d=QFileDialog.getExistingDirectory(self,"Choose Image Folder")
        if d:
            self.folder=Path(d); self.folder_label.setText(str(self.folder)); self.load_folder()

    def open_image(self):
        f,_=QFileDialog.getOpenFileName(self,"Open Image",str(self.folder or Path.home()),
            "Images (*.jpg *.jpeg *.png *.bmp *.webp *.gif *.tif *.tiff *.ico)")
        if f:
            self.folder=Path(f).parent; self.folder_label.setText(str(self.folder)); self.load_folder(Path(f))

    def load_folder(self, select=None):
        try:
            self.files=[p for p in self.folder.iterdir()
                        if p.is_file() and p.suffix.lower() in SUPPORTED]
        except OSError: self.files=[]
        self.sort_files()
        if select:
            try:self.index=self.files.index(Path(select))
            except ValueError:self.index=0
        elif self.files:self.index=0
        else:self.index=-1
        self.refresh_list()
        if self.index>=0:self.show_current()

    def sort_files(self):
        if not self.folder:return
        mode=self.sort_combo.currentText()
        if mode=="Name": key=lambda p:p.name.lower(); rev=False
        elif mode=="Name (reverse)": key=lambda p:p.name.lower(); rev=True
        elif mode=="Newest": key=lambda p:p.stat().st_mtime; rev=True
        elif mode=="Oldest": key=lambda p:p.stat().st_mtime; rev=False
        elif mode=="Largest": key=lambda p:p.stat().st_size; rev=True
        else:key=lambda p:p.stat().st_size; rev=False
        try:self.files.sort(key=key,reverse=rev)
        except OSError:pass
        self.refresh_list()

    def refresh_list(self):
        self.thumbs.blockSignals(True); self.thumbs.clear()
        for p in self.files:
            if self.fav_only.isChecked() and str(p) not in self.favorites: continue
            item=QListWidgetItem()
            item.setText(("★ " if str(p) in self.favorites else "")+p.name)
            item.setToolTip(str(p)); item.setData(Qt.UserRole,str(p))
            img=QImage(str(p))
            if not img.isNull():
                item.setIcon(QPixmap.fromImage(img.scaled(150,105,Qt.KeepAspectRatio,Qt.SmoothTransformation)))
            self.thumbs.addItem(item)
        self.thumbs.blockSignals(False)
        self.counter.setText(f"{self.index+1 if self.index>=0 else 0} / {len(self.files)}")

    def select_row(self,row):
        item=self.thumbs.item(row)
        if not item:return
        p=Path(item.data(Qt.UserRole))
        try:self.index=self.files.index(p)
        except ValueError:return
        self.show_current()

    def show_current(self):
        if not 0<=self.index<len(self.files):return
        p=self.files[self.index]; img=QImage(str(p))
        if img.isNull():
            self.statusBar().showMessage(f"Cannot read {p.name}"); return
        self.rotation=0; self.flip_h=False; self.flip_v=False
        self.canvas.set_pixmap(QPixmap.fromImage(img))
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(270,190,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        self.info.setText(f"<b>{p.name}</b><br>{img.width()} × {img.height()} px<br>"
                         f"{human_size(p.stat().st_size)}<br>{img.depth()} bit • "
                         f"{'Alpha' if img.hasAlphaChannel() else 'No alpha'}<br>"
                         f"{p.suffix.upper().lstrip('.')}")
        self.counter.setText(f"{self.index+1} / {len(self.files)}")
        self.favorite_btn.setText("★ Favorite" if str(p) in self.favorites else "☆ Favorite")
        self.statusBar().showMessage(f"{p.name}  •  {img.width()}×{img.height()}  •  {human_size(p.stat().st_size)}")
        for i in range(self.thumbs.count()):
            if Path(self.thumbs.item(i).data(Qt.UserRole))==p:
                self.thumbs.setCurrentRow(i); break

    def prev_image(self):
        if self.files:self.index=(self.index-1)%len(self.files);self.show_current()

    def next_image(self):
        if self.files:self.index=(self.index+1)%len(self.files);self.show_current()

    def fit(self): self.canvas.fit_image()
    def actual(self): self.canvas.actual_size()

    def rotate(self,d):
        if self.files:self.rotation=(self.rotation+d)%360;self.transform_display()

    def flip_horizontal(self):
        self.flip_h=not self.flip_h; self.transform_display()

    def flip_vertical(self):
        self.flip_v=not self.flip_v; self.transform_display()

    def transform_display(self):
        if not 0<=self.index<len(self.files):return
        img=QImage(str(self.files[self.index]))
        t=QTransform(); t.rotate(self.rotation)
        if self.flip_h:t.scale(-1,1)
        if self.flip_v:t.scale(1,-1)
        self.canvas.set_pixmap(QPixmap.fromImage(img.transformed(t,Qt.SmoothTransformation)))

    def toggle_favorite(self):
        if not 0<=self.index<len(self.files):return
        k=str(self.files[self.index])
        if k in self.favorites:self.favorites.remove(k)
        else:self.favorites.add(k)
        self.save_favorites();self.show_current();self.refresh_list()

    def toggle_slideshow(self):
        if self.timer.isActive():
            self.timer.stop();self.slide_btn.setText("▶ Slideshow")
        else:
            self.timer.start(self.interval.value()*1000)
            self.slide_btn.setText("⏸ Stop Slideshow");self.next_image()

    def current_pixmap(self):
        if not 0<=self.index<len(self.files):return QPixmap()
        img=QImage(str(self.files[self.index]))
        t=QTransform();t.rotate(self.rotation)
        if self.flip_h:t.scale(-1,1)
        if self.flip_v:t.scale(1,-1)
        return QPixmap.fromImage(img.transformed(t,Qt.SmoothTransformation))

    def save_as(self):
        if not 0<=self.index<len(self.files):return
        src=self.files[self.index]
        out,_=QFileDialog.getSaveFileName(self,"Save Image As",
            str(src.with_name(src.stem+"_copy"+src.suffix)),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if out and self.current_pixmap().save(out):
            self.statusBar().showMessage(f"Saved: {out}")

    def copy_image(self):
        pm=self.current_pixmap()
        if not pm.isNull():
            QApplication.clipboard().setPixmap(pm)
            self.statusBar().showMessage("Image copied to clipboard")

    def show_info(self):
        if 0<=self.index<len(self.files):InfoDialog(self,self.files[self.index]).exec()

    def thumb_menu(self,pos):
        item=self.thumbs.itemAt(pos)
        if not item:return
        p=Path(item.data(Qt.UserRole));m=QMenu(self)
        m.addAction("Open",lambda:self.open_external(p))
        m.addAction("Open Containing Folder",lambda:self.open_external(p.parent))
        m.addAction("Copy Path",lambda:QApplication.clipboard().setText(str(p)))
        m.addAction("Image Information",lambda:InfoDialog(self,p).exec())
        m.addSeparator();m.addAction("★ Toggle Favorite",lambda:self.toggle_path_favorite(p))
        m.exec(self.thumbs.mapToGlobal(pos))

    def toggle_path_favorite(self,p):
        k=str(p)
        if k in self.favorites:self.favorites.remove(k)
        else:self.favorites.add(k)
        self.save_favorites();self.refresh_list()

    def open_external(self,p):
        try:
            if sys.platform.startswith("linux"):subprocess.Popen(["xdg-open",str(p)])
            elif sys.platform=="win32":os.startfile(str(p))
            elif sys.platform=="darwin":subprocess.Popen(["open",str(p)])
        except Exception as e:QMessageBox.warning(self,"Open failed",str(e))

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def keyPressEvent(self,e):
        if e.key()==Qt.Key_Delete and 0<=self.index<len(self.files):self.delete_current()
        elif e.key()==Qt.Key_Escape and self.isFullScreen():self.showNormal()
        else:super().keyPressEvent(e)

    def delete_current(self):
        p=self.files[self.index]
        if QMessageBox.question(self,"Move to Trash?",f"Move this image to Trash?\\n\\n{p.name}",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:
            trash=Path.home()/".local/share/Trash/files";trash.mkdir(parents=True,exist_ok=True)
            target=trash/p.name
            if target.exists():target=trash/f"{p.stem}_{datetime.now():%Y%m%d%H%M%S}{p.suffix}"
            shutil.move(str(p),str(target))
            self.files.pop(self.index)
            self.index=min(self.index,len(self.files)-1)
            self.refresh_list();self.show_current()
        except Exception as e:QMessageBox.warning(self,"Trash failed",str(e))


if __name__=="__main__":
    app=QApplication(sys.argv)
    app.setApplicationName(APP_NAME);app.setApplicationVersion(VERSION)
    w=MainWindow();w.show();sys.exit(app.exec())
