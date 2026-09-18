#!/usr/bin/env python3
import sys, json, random
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient, QFontMetrics
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
 QFormLayout,QLabel,QPushButton,QPlainTextEdit,QLineEdit,QComboBox,QSpinBox,QCheckBox,
 QColorDialog,QFileDialog,QMessageBox,QSlider,QTabWidget,QScrollArea)

class PosterCanvas(QWidget):
    def __init__(self):
        super().__init__(); self.setMinimumSize(500,600)
        self.quote="Your quote goes here."; self.author=""; self.subtitle=""
        self.bg1=QColor("#172033"); self.bg2=QColor("#384c72")
        self.text_color=QColor("#ffffff"); self.accent=QColor("#f4c95d")
        self.border_color=QColor("#ffffff"); self.font_family="DejaVu Sans"
        self.font_size=42; self.author_size=20; self.align=Qt.AlignCenter
        self.bold=False; self.italic=False; self.bg_style="Gradient"
        self.pattern=False; self.padding=70; self.border=True; self.border_width=3
        self.overlay=0.0; self.offset_y=0.0; self.setMouseTracking(True); self.drag=False

    def _background(self,p,r):
        if self.bg_style=="Solid": p.fillRect(r,self.bg1)
        elif self.bg_style=="Radial":
            g=QRadialGradient(r.center(),max(r.width(),r.height())*.65); g.setColorAt(0,self.bg1); g.setColorAt(1,self.bg2); p.fillRect(r,QBrush(g))
        elif self.bg_style=="Warm":
            g=QLinearGradient(r.topLeft(),r.bottomRight()); g.setColorAt(0,self.bg1); g.setColorAt(.55,self.accent.darker(125)); g.setColorAt(1,self.bg2); p.fillRect(r,QBrush(g))
        else:
            g=QLinearGradient(r.topLeft(),r.bottomRight()); g.setColorAt(0,self.bg1); g.setColorAt(1,self.bg2); p.fillRect(r,QBrush(g))
        if self.pattern:
            pen=QPen(QColor(self.text_color.red(),self.text_color.green(),self.text_color.blue(),25),1); p.setPen(pen)
            for x in range(-r.height(),int(r.width()),42): p.drawLine(x,r.top(),x+r.height(),r.bottom())
        if self.overlay: p.fillRect(r,QColor(0,0,0,int(255*self.overlay)))

    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r=QRectF(0,0,self.width(),self.height()); self._background(p,r)
        p.setPen(Qt.NoPen); p.setBrush(self.accent); p.drawRoundedRect(QRectF(40,40,90,7),3,3)
        content=r.adjusted(self.padding,self.padding,-self.padding,-self.padding)
        font=QFont(self.font_family,self.font_size); font.setBold(self.bold); font.setItalic(self.italic)
        fm=QFontMetrics(font); words=self.quote.split(); lines=[]; line=""
        for word in words:
            trial=word if not line else line+" "+word
            if fm.horizontalAdvance(trial)<=content.width(): line=trial
            else:
                if line: lines.append(line)
                line=word
        if line or not lines: lines.append(line)
        lh=fm.lineSpacing(); block=len(lines)*lh
        ah=QFontMetrics(QFont(self.font_family,self.author_size)).height()+25 if self.author.strip() else 0
        sh=QFontMetrics(QFont(self.font_family,max(12,self.author_size-2))).height()+15 if self.subtitle.strip() else 0
        y=content.top()+(content.height()-(block+ah+sh))/2+lh+self.offset_y
        p.setPen(self.text_color); p.setFont(font)
        for s in lines:
            p.drawText(QRectF(content.left(),y-lh,content.width(),lh),self.align|Qt.TextSingleLine,s); y+=lh
        if self.author.strip():
            y+=12; af=QFont(self.font_family,self.author_size); af.setBold(True); p.setFont(af); p.setPen(self.accent)
            p.drawText(QRectF(content.left(),y,content.width(),ah),self.align|Qt.TextSingleLine,"— "+self.author.strip()); y+=ah
        if self.subtitle.strip():
            sf=QFont(self.font_family,max(12,self.author_size-2)); p.setFont(sf); p.setPen(QColor(self.text_color.red(),self.text_color.green(),self.text_color.blue(),190))
            p.drawText(QRectF(content.left(),y,content.width(),sh),self.align|Qt.TextSingleLine,self.subtitle.strip())
        if self.border:
            p.setPen(QPen(self.border_color,self.border_width)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(r.adjusted(18,18,-18,-18),14,14)
        p.end()

    def mousePressEvent(self,e):
        if e.button()==Qt.LeftButton: self.drag=True; self.last=e.position()
    def mouseMoveEvent(self,e):
        if self.drag:
            self.offset_y=max(-self.height()*.25,min(self.height()*.25,self.offset_y+(e.position()-self.last).y())); self.last=e.position(); self.update()
    def mouseReleaseEvent(self,e): self.drag=False

    def render_image(self,w,h):
        img=QImage(w,h,QImage.Format_ARGB32); img.fill(Qt.transparent)
        old=self.size(); old_min=self.minimumSize(); self.setMinimumSize(1,1); self.resize(w,h)
        # QWidget.render() in PySide6 requires a target offset argument when
        # rendering into a QPainter.  Passing only the painter can also leave
        # the QPaintDevice active and cause a crash on exit.
        p=QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        try:
            self.render(p, QPointF(0, 0).toPoint())
        finally:
            p.end()
            self.resize(old)
            self.setMinimumSize(old_min)
        return img

class ColorButton(QPushButton):
    def __init__(self,color,callback):
        super().__init__(); self.color=QColor(color); self.callback=callback; self.clicked.connect(self.pick); self.refresh()
    def pick(self):
        c=QColorDialog.getColor(self.color,self,"Choose Color")
        if c.isValid(): self.color=c; self.refresh(); self.callback(c)
    def refresh(self):
        fg="#000000" if self.color.lightness()>150 else "#ffffff"
        self.setText(self.color.name().upper()); self.setStyleSheet(f"QPushButton{{background:{self.color.name()};color:{fg};font-weight:700;padding:7px;border-radius:6px;}}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("JASS Quote & Poster Studio v1.0"); self.resize(1250,850)
        self.build(); self.sync()

    def build(self):
        root=QWidget(); self.setCentralWidget(root); main=QHBoxLayout(root)
        left=QWidget(); left.setMaximumWidth(430); lv=QVBoxLayout(left)
        t=QLabel("JASS Quote & Poster Studio"); t.setObjectName("Title"); lv.addWidget(t)
        s=QLabel("Create • Design • Export • Share"); s.setObjectName("SubTitle"); lv.addWidget(s)
        # Create the canvas before building the control tabs because the
        # controls use the canvas defaults when they are initialized.
        self.canvas=PosterCanvas()
        tabs=QTabWidget(); tabs.addTab(self.content_tab(),"✍ Content"); tabs.addTab(self.design_tab(),"🎨 Design"); tabs.addTab(self.type_tab(),"🔤 Typography"); tabs.addTab(self.export_tab(),"📤 Export"); lv.addWidget(tabs,1)
        row=QHBoxLayout()
        for name,fn in [("New",self.new),("Random",self.random),("Save Project",self.save),("Load",self.load)]:
            b=QPushButton(name); b.clicked.connect(fn); row.addWidget(b)
        lv.addLayout(row); main.addWidget(left)
        preview=QWidget(); pv=QVBoxLayout(preview); h=QHBoxLayout(); h.addWidget(QLabel("LIVE PREVIEW")); h.addStretch(); self.info=QLabel(); h.addWidget(self.info); pv.addLayout(h)
        sc=QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(self.canvas); pv.addWidget(sc,1); main.addWidget(preview,1)

    def content_tab(self):
        w=QWidget(); f=QFormLayout(w)
        self.quote=QPlainTextEdit(); self.quote.setPlainText(self.canvas.quote); self.quote.textChanged.connect(self.sync)
        self.author=QLineEdit(); self.author.textChanged.connect(self.sync)
        self.subtitle=QLineEdit(); self.subtitle.textChanged.connect(self.sync)
        f.addRow("Quote",self.quote); f.addRow("Author",self.author); f.addRow("Subtitle",self.subtitle)
        self.template=QComboBox(); self.template.addItems(["Original Quote","Motivational","Romantic","Wisdom","Poetry","Minimal"]); self.template.currentTextChanged.connect(self.preset); f.addRow("Template",self.template)
        b=QPushButton("Clear Text"); b.clicked.connect(lambda:(self.quote.clear(),self.author.clear(),self.subtitle.clear())); f.addRow("",b); return w

    def design_tab(self):
        w=QWidget(); f=QFormLayout(w)
        self.bgstyle=QComboBox(); self.bgstyle.addItems(["Gradient","Solid","Radial","Warm"]); self.bgstyle.currentTextChanged.connect(self.sync)
        self.bg1=ColorButton("#172033",lambda c:self.setc("bg1",c)); self.bg2=ColorButton("#384c72",lambda c:self.setc("bg2",c))
        self.accent=ColorButton("#f4c95d",lambda c:self.setc("accent",c)); self.textcol=ColorButton("#ffffff",lambda c:self.setc("text_color",c)); self.bordercol=ColorButton("#ffffff",lambda c:self.setc("border_color",c))
        self.pattern=QCheckBox("Subtle diagonal pattern"); self.pattern.stateChanged.connect(self.sync)
        self.border=QCheckBox("Show border"); self.border.setChecked(True); self.border.stateChanged.connect(self.sync)
        self.overlay=QSlider(Qt.Horizontal); self.overlay.setRange(0,70); self.overlay.valueChanged.connect(self.sync)
        for a,b in [("Background",self.bgstyle),("Color 1",self.bg1),("Color 2",self.bg2),("Accent",self.accent),("Text",self.textcol),("Border",self.bordercol),("Effects",self.pattern),("",self.border),("Dark overlay",self.overlay)]: f.addRow(a,b)
        return w

    def type_tab(self):
        w=QWidget(); f=QFormLayout(w)
        self.font=QComboBox(); self.font.addItems(["DejaVu Sans","DejaVu Serif","Liberation Sans","Liberation Serif","Monospace","Sans Serif","Serif"]); self.font.currentTextChanged.connect(self.sync)
        self.fontsize=QSpinBox(); self.fontsize.setRange(14,100); self.fontsize.setValue(42); self.fontsize.valueChanged.connect(self.sync)
        self.authsize=QSpinBox(); self.authsize.setRange(10,48); self.authsize.setValue(20); self.authsize.valueChanged.connect(self.sync)
        self.align=QComboBox(); self.align.addItems(["Center","Left","Right"]); self.align.currentTextChanged.connect(self.sync)
        self.bold=QCheckBox("Bold"); self.bold.stateChanged.connect(self.sync); self.italic=QCheckBox("Italic"); self.italic.stateChanged.connect(self.sync)
        self.padding=QSpinBox(); self.padding.setRange(25,180); self.padding.setValue(70); self.padding.valueChanged.connect(self.sync)
        for a,b in [("Font",self.font),("Quote size",self.fontsize),("Author size",self.authsize),("Alignment",self.align),("",self.bold),("",self.italic),("Padding",self.padding)]: f.addRow(a,b)
        return w

    def export_tab(self):
        w=QWidget(); v=QVBoxLayout(w); v.addWidget(QLabel("High-resolution export for social media, messaging, archiving or printing."))
        self.size=QComboBox(); self.size.addItems(["1200 × 1600 — Portrait","1080 × 1350 — Instagram Portrait","1080 × 1080 — Square","1600 × 900 — Landscape","2048 × 2048 — Large Square","Custom"]); v.addWidget(self.size)
        r=QHBoxLayout(); self.cw=QSpinBox(); self.cw.setRange(200,6000); self.cw.setValue(1200); self.ch=QSpinBox(); self.ch.setRange(200,6000); self.ch.setValue(1600); r.addWidget(self.cw); r.addWidget(QLabel("×")); r.addWidget(self.ch); v.addLayout(r)
        for text,fn in [("Export PNG",self.export_png),("Export JPEG",self.export_jpg)]:
            b=QPushButton(text); b.clicked.connect(fn); v.addWidget(b)
        v.addStretch(); return w

    def setc(self,n,c): setattr(self.canvas,n,c); self.sync()
    def sync(self):
        if not hasattr(self,"canvas") or not hasattr(self,"quote"): return
        self.canvas.quote=self.quote.toPlainText(); self.canvas.author=self.author.text(); self.canvas.subtitle=self.subtitle.text()
        self.canvas.bg_style=self.bgstyle.currentText(); self.canvas.pattern=self.pattern.isChecked(); self.canvas.border=self.border.isChecked(); self.canvas.overlay=self.overlay.value()/100
        self.canvas.font_family=self.font.currentText(); self.canvas.font_size=self.fontsize.value(); self.canvas.author_size=self.authsize.value(); self.canvas.padding=self.padding.value(); self.canvas.bold=self.bold.isChecked(); self.canvas.italic=self.italic.isChecked()
        self.canvas.align={"Center":Qt.AlignCenter,"Left":Qt.AlignLeft,"Right":Qt.AlignRight}[self.align.currentText()]; self.canvas.update(); self.info.setText(f"{self.canvas.width()} × {self.canvas.height()} px")

    def preset(self,n):
        d={"Motivational":("Keep moving forward. Small steps become great journeys.","JASS",""),"Romantic":("Some moments are remembered because they were felt.","","A little love, a little light"),"Wisdom":("The quietest lessons often stay with us the longest.","",""),"Poetry":("Let the heart speak softly; the world is listening.","",""),"Minimal":("Breathe. Begin. Become.","",""),"Original Quote":("Your quote goes here.","","")}
        q,a,s=d.get(n,d["Original Quote"]); self.quote.setPlainText(q); self.author.setText(a); self.subtitle.setText(s)

    def new(self):
        self.preset("Original Quote"); self.bgstyle.setCurrentText("Gradient"); self.canvas.offset_y=0
    def random(self):
        q,a=random.choice([("Dreams need direction, not permission.","JASS"),("Create something today that tomorrow can remember.","JASS"),("Love is often found in ordinary moments.",""),("A quiet mind can hear what noise cannot.",""),("Begin where you are. Build from there.","")]); self.quote.setPlainText(q); self.author.setText(a)
        vals=random.choice([("#111827","#4B5563","#FBBF24"),("#1E293B","#0F766E","#FDE68A"),("#312E81","#7C3AED","#F5D0FE"),("#3F1D2E","#7F1D1D","#FBCFE8")])
        for obj,val in zip([self.bg1,self.bg2,self.accent],vals): obj.color=QColor(val); obj.refresh()
        for n,val in zip(["bg1","bg2","accent"],vals): self.setc(n,QColor(val))

    def dims(self):
        d={"1200 × 1600 — Portrait":(1200,1600),"1080 × 1350 — Instagram Portrait":(1080,1350),"1080 × 1080 — Square":(1080,1080),"1600 × 900 — Landscape":(1600,900),"2048 × 2048 — Large Square":(2048,2048)}
        return d.get(self.size.currentText(),(self.cw.value(),self.ch.value()))

    def export_png(self):
        p,_=QFileDialog.getSaveFileName(self,"Export PNG",f"jass_quote_{datetime.now():%Y%m%d_%H%M%S}.png","PNG Images (*.png)")
        if p and not self.canvas.render_image(*self.dims()).save(p,"PNG"): QMessageBox.critical(self,"Export Failed","Could not save the PNG.")
        elif p: QMessageBox.information(self,"Export Complete",f"Saved:\n{p}")
    def export_jpg(self):
        p,_=QFileDialog.getSaveFileName(self,"Export JPEG",f"jass_quote_{datetime.now():%Y%m%d_%H%M%S}.jpg","JPEG Images (*.jpg *.jpeg)")
        if p:
            img=self.canvas.render_image(*self.dims()).convertToFormat(QImage.Format_RGB32)
            if img.save(p,"JPEG",95): QMessageBox.information(self,"Export Complete",f"Saved:\n{p}")
            else: QMessageBox.critical(self,"Export Failed","Could not save the JPEG.")

    def data(self):
        return {"version":"1.0","quote":self.quote.toPlainText(),"author":self.author.text(),"subtitle":self.subtitle.text(),"bg_style":self.canvas.bg_style,"bg1":self.canvas.bg1.name(),"bg2":self.canvas.bg2.name(),"text_color":self.canvas.text_color.name(),"accent":self.canvas.accent.name(),"border_color":self.canvas.border_color.name(),"pattern":self.canvas.pattern,"border":self.canvas.border,"overlay":self.canvas.overlay,"font_family":self.canvas.font_family,"font_size":self.canvas.font_size,"author_size":self.canvas.author_size,"padding":self.canvas.padding,"bold":self.canvas.bold,"italic":self.canvas.italic,"alignment":self.align.currentText()}
    def save(self):
        p,_=QFileDialog.getSaveFileName(self,"Save Poster Project","jass_poster_project.json","JASS Poster Project (*.json)")
        if p: Path(p).write_text(json.dumps(self.data(),indent=2),encoding="utf-8")
    def load(self):
        p,_=QFileDialog.getOpenFileName(self,"Load Poster Project","","JASS Poster Project (*.json)")
        if not p:return
        try:
            d=json.loads(Path(p).read_text(encoding="utf-8")); self.quote.setPlainText(d.get("quote","")); self.author.setText(d.get("author","")); self.subtitle.setText(d.get("subtitle",""))
            self.bgstyle.setCurrentText(d.get("bg_style","Gradient"))
            for obj,key in [(self.bg1,"bg1"),(self.bg2,"bg2"),(self.accent,"accent")]: obj.color=QColor(d.get(key,obj.color.name())); obj.refresh()
            for key in ["bg1","bg2","accent","text_color","border_color"]: setattr(self.canvas,key,QColor(d.get(key,getattr(self.canvas,key)).name() if isinstance(getattr(self.canvas,key),QColor) else d.get(key)))
            self.pattern.setChecked(d.get("pattern",False)); self.border.setChecked(d.get("border",True)); self.overlay.setValue(int(d.get("overlay",0)*100))
            self.font.setCurrentText(d.get("font_family","DejaVu Sans")); self.fontsize.setValue(int(d.get("font_size",42))); self.authsize.setValue(int(d.get("author_size",20))); self.padding.setValue(int(d.get("padding",70)))
            self.bold.setChecked(d.get("bold",False)); self.italic.setChecked(d.get("italic",False)); self.align.setCurrentText(d.get("alignment","Center")); self.sync()
        except Exception as e: QMessageBox.critical(self,"Load Failed",str(e))

app=QApplication(sys.argv); app.setApplicationName("JASS Quote & Poster Studio")
app.setStyleSheet("""QWidget{font-size:13px} QLineEdit,QPlainTextEdit,QComboBox,QSpinBox{padding:7px} QPushButton{padding:8px 12px} #Title{font-size:23px;font-weight:800} #SubTitle{color:#64748b;margin-bottom:6px}""")
w=MainWindow(); w.show(); sys.exit(app.exec())
