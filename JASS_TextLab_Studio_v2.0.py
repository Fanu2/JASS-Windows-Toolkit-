#!/usr/bin/env python3
"""
JASS TextLab Studio
A configurable multilingual text-generation and testing workbench.

Designed for:
- placeholder/test text generation
- Unicode and multilingual UI testing
- Latin, Gurmukhi, Shahmukhi/RTL, Mizo and custom corpora
- deterministic seeded generation
- paragraph/word/character controls
- punctuation and formatting stress tests
- JSON/CSV/TXT/Markdown/HTML export
- reusable presets
- no network required
"""

import sys
import re
import json
import csv
import random
import html
import zipfile
import xml.etree.ElementTree as ET
import unicodedata
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QObject, Signal, QThread, QSettings
from PySide6.QtGui import QAction, QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QLineEdit, QTextEdit, QPlainTextEdit, QFileDialog, QMessageBox,
    QSplitter, QGroupBox, QTabWidget, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QStatusBar, QToolBar, QFrame
)

APP_NAME = "JASS TextLab Studio"
APP_VERSION = "1.0.0"


def extract_epub(path):
    """Extract readable XHTML/HTML text and basic metadata from an EPUB."""
    ns = {
        "container": "urn:oasis:names:tc:opendocument:xmlns:container",
        "opf": "http://www.idpf.org/2007/opf",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    with zipfile.ZipFile(path, "r") as z:
        try:
            container_xml = z.read("META-INF/container.xml")
            container_root = ET.fromstring(container_xml)
            rootfile = container_root.find(".//container:rootfile", ns)
            if rootfile is None:
                raise ValueError("EPUB does not contain a valid OPF package file.")
            opf_path = rootfile.attrib.get("full-path")
            if not opf_path:
                raise ValueError("EPUB package path could not be determined.")
        except KeyError:
            raise ValueError("Invalid EPUB: META-INF/container.xml is missing.")

        opf_dir = str(Path(opf_path).parent).replace("\\", "/")
        if opf_dir == ".":
            opf_dir = ""

        opf_root = ET.fromstring(z.read(opf_path))

        metadata = {}
        for child in opf_root.find("opf:metadata", ns) or []:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag in ("title", "creator", "language", "identifier", "date"):
                value = (child.text or "").strip()
                if value and tag not in metadata:
                    metadata[tag] = value

        manifest = {}
        manifest_el = opf_root.find("opf:manifest", ns)
        if manifest_el is not None:
            for item in manifest_el.findall("opf:item", ns):
                manifest[item.attrib.get("id", "")] = item.attrib.get("href", "")

        ordered = []
        spine = opf_root.find("opf:spine", ns)
        if spine is not None:
            for itemref in spine.findall("opf:itemref", ns):
                item_id = itemref.attrib.get("idref")
                href = manifest.get(item_id, "")
                if href:
                    ordered.append(href)

        # Fallback: use all HTML/XHTML manifest items if spine is unavailable.
        if not ordered:
            for item in manifest_el.findall("opf:item", ns) if manifest_el is not None else []:
                media = item.attrib.get("media-type", "")
                href = item.attrib.get("href", "")
                if "html" in media or href.lower().endswith((".html", ".xhtml", ".htm")):
                    ordered.append(href)

        chunks = []
        chapter_count = 0

        for href in ordered:
            # EPUB hrefs may contain URL fragments.
            href = href.split("#", 1)[0]
            if not href:
                continue
            full = f"{opf_dir}/{href}" if opf_dir else href
            full = str(Path(full)).replace("\\", "/")
            try:
                raw = z.read(full).decode("utf-8", errors="replace")
            except KeyError:
                # A few EPUBs use URL quoting or unusual path forms.
                continue

            root = ET.fromstring(raw)
            parts = []
            for element in root.iter():
                tag = element.tag.rsplit("}", 1)[-1].lower() if isinstance(element.tag, str) else ""
                if tag in ("script", "style", "svg", "nav"):
                    continue
                if element.text and element.text.strip():
                    parts.append(element.text.strip())
                if tag in ("p", "div", "section", "article", "h1", "h2", "h3",
                           "h4", "h5", "h6", "li", "blockquote", "br"):
                    parts.append("\n")

            text = " ".join(parts)
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n[ \t]+", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()

            if text:
                chapter_count += 1
                chunks.append(text)

        text = "\n\n".join(chunks)
        text = unicodedata.normalize("NFC", text)

        metadata["chapters"] = chapter_count
        metadata["words"] = len(words_only(text))
        metadata["characters"] = len(text)
        return text, metadata

BUILTIN_CORPORA = {
    "English": """
Knowledge grows when information is organized, connected, searched, tested, and reused.
A useful workspace should remain readable while handling short notes, long documents,
structured records, quotations, identifiers, punctuation, numbers, and repeated content.
Good software should make experimentation easy and results reproducible.
""",
    "Punjabi — Gurmukhi": """
ਪੰਜਾਬੀ ਇੱਕ ਸੁੰਦਰ ਅਤੇ ਸਮਰੱਥ ਭਾਸ਼ਾ ਹੈ। ਇਹ ਪਾਠ ਟੈਸਟਿੰਗ, ਲੇਆਉਟ, ਖੋਜ ਅਤੇ ਯੂਨੀਕੋਡ
ਰੈਂਡਰਿੰਗ ਦੀ ਜਾਂਚ ਲਈ ਵਰਤਿਆ ਜਾ ਸਕਦਾ ਹੈ। ਗਿਆਨ ਨੂੰ ਸੰਭਾਲਣਾ, ਖੋਜਣਾ ਅਤੇ ਸਾਂਝਾ ਕਰਨਾ
ਇੱਕ ਚੰਗੇ ਡਿਜ਼ਿਟਲ ਵਰਕਸਪੇਸ ਦਾ ਮਹੱਤਵਪੂਰਨ ਹਿੱਸਾ ਹੈ।
""",
    "Punjabi — Shahmukhi": """
پنجابی اک خوبصورت تے وسعت والی زبان اے۔ ایہہ متن ٹیسٹنگ، لے آؤٹ، تلاش تے
یونیکوڈ رینڈرنگ دی جانچ لئی ورتیا جا سکدا اے۔ علم نوں سنبھالنا، لبھنا تے
سانجھا کرنا اک چنگے ڈیجیٹل ورک سپیس دا اہم حصہ اے۔
""",
    "Mizo": """
Mizo hi ṭawng mawi tak a ni. Hriatna hi buatsaih, vawn, zawng leh hman
thiam a ngai. He thu hi Unicode, font, line wrapping leh application
layout te test nan hman theih a ni. Digital workspace tha chuan thu te
a vawn tha a, a zawng theih bawk.
""",
    "Hindi — देवनागरी": """
यह बहुभाषी परीक्षण पाठ यूनिकोड, फ़ॉन्ट, पंक्ति-विन्यास, खोज और पाठ संपादन की
जाँच के लिए उपयोगी है। एक अच्छा डिजिटल कार्यक्षेत्र जानकारी को सुरक्षित रखता है,
उसे आसानी से खोजने देता है और अलग-अलग भाषाओं में सही रूप से प्रदर्शित करता है।
""",
    "Bengali — বাংলা": """
বাংলা একটি সমৃদ্ধ ভাষা। এই পরীক্ষামূলক লেখা ইউনিকোড, ফন্ট, লাইন র‍্যাপিং,
অনুসন্ধান এবং বিভিন্ন ধরনের টেক্সট ইন্টারফেস পরীক্ষা করতে ব্যবহার করা যেতে পারে।
ডিজিটাল কর্মক্ষেত্রে তথ্য সংরক্ষণ ও সহজে খুঁজে পাওয়া গুরুত্বপূর্ণ।
""",
    "Assamese — অসমীয়া": """
অসমীয়া এখন সমৃদ্ধ ভাষা। এই পৰীক্ষামূলক পাঠ ইউনিকোড, ফণ্ট, লাইন ৰেপিং,
অনুসন্ধান আৰু বিভিন্ন টেক্সট ইণ্টাৰফেচ পৰীক্ষা কৰিবলৈ ব্যৱহাৰ কৰিব পাৰি।
ডিজিটেল কৰ্মক্ষেত্ৰত তথ্য সুৰক্ষিতভাৱে সংৰক্ষণ আৰু সহজে বিচাৰি পোৱাটো গুৰুত্বপূৰ্ণ।
""",
    "Tamil — தமிழ்": """
தமிழ் ஒரு செழுமையான மொழியாகும். இந்த சோதனை உரை யூனிகோடு, எழுத்துரு,
வரி அமைப்பு, தேடல் மற்றும் உரை இடைமுகங்களைச் சோதிக்க பயன்படுகிறது.
ஒரு நல்ல டிஜிட்டல் பணியிடம் தகவலை எளிதாக சேமித்து தேட உதவுகிறது.
""",
    "Telugu — తెలుగు": """
తెలుగు ఒక సమృద్ధమైన భాష. ఈ పరీక్షా పాఠాన్ని యూనికోడ్, ఫాంట్, లైన్ ర్యాపింగ్,
శోధన మరియు టెక్స్ట్ ఇంటర్‌ఫేస్‌లను పరీక్షించడానికి ఉపయోగించవచ్చు.
డిజిటల్ వర్క్‌స్పేస్‌లో సమాచారాన్ని సులభంగా భద్రపరచడం మరియు వెతకడం అవసరం.
""",
    "Mixed Multilingual": """
English text — ਪੰਜਾਬੀ ਗੁਰਮੁਖੀ — پنجابی شاہ مکھی — Mizo ṭawng — हिन्दी भाषा —
বাংলা লেখা — অসমীয়া — தமிழ் உரை — తెలుగు పాఠ్యం — العربية نص — 日本語テキスト.
Unicode testing should include punctuation, numbers 1234567890, symbols © ™ ₹ € £,
and combining characters such as café, naïve, résumé.
""",
    "Programming / Technical": """
class TextRecord:
    def __init__(self, identifier, language, content):
        self.identifier = identifier
        self.language = language
        self.content = content

def validate_record(record):
    return bool(record.identifier and record.content)

JSON: {"name": "Athena", "version": "1.0", "enabled": true}
SQL: SELECT id, title FROM documents WHERE language = 'Mizo';
Path: /home/user/projects/athena/data/sample.txt
URL-like text: https://example.test/search?q=unicode
""",
    "Avengers — Original Theme": """
The heroes assemble when a difficult problem needs a clear plan. Ironman studies
the system, Captain America organizes the work, Thor brings energy, Black Widow
checks the details, Hulk stress-tests the interface, and Doctor Strange explores
unexpected paths. A good team turns complex work into manageable steps.
"""
}

# Additional names are deliberately data, not hard-coded generation logic.
CHARACTER_THEMES = {
    "Avengers": ["Nick", "Ironman", "Captain America", "Thor", "Black Widow",
                 "Spider Man", "Captain Marvel", "Rocket", "War Machine", "Hulk",
                 "Vision", "Ant Man", "Wasp", "Black Panther", "Winter Soldier",
                 "Doctor Strange", "Star Lord", "Groot", "Gamora", "Loki", "Clint Barton"],
    "Space / Sci-Fi": ["Explorer", "Pilot", "Navigator", "Engineer", "Scientist",
                       "Commander", "Android", "Ranger", "Archivist", "Colonist"],
    "Fantasy": ["Wizard", "Ranger", "Knight", "Healer", "Alchemist", "Bard",
                "Guardian", "Scholar", "Dragon Rider", "Seer"],
    "Developer": ["Parser", "Compiler", "Debugger", "Tester", "Builder",
                  "Indexer", "Crawler", "Worker", "Service", "Controller"]
}


def tokenize(text):
    # Keeps punctuation as separate tokens while retaining Unicode words.
    return re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)


def words_only(text):
    return re.findall(r"\w+", text, flags=re.UNICODE)


def normalize_extension(path):
    return Path(path).suffix.lower()


class GeneratorWorker(QObject):
    finished = Signal(str)
    progress = Signal(int)
    error = Signal(str)

    def __init__(self, source, paragraphs, words_per_paragraph, mode,
                 preserve_punctuation, theme, seed, add_numbers, stress):
        super().__init__()
        self.source = source
        self.paragraphs = paragraphs
        self.words_per_paragraph = words_per_paragraph
        self.mode = mode
        self.preserve_punctuation = preserve_punctuation
        self.theme = theme
        self.seed = seed
        self.add_numbers = add_numbers
        self.stress = stress

    def run(self):
        try:
            rng = random.Random(self.seed)
            if self.mode == "theme":
                vocabulary = CHARACTER_THEMES.get(self.theme, [])
                if not vocabulary:
                    raise ValueError("The selected theme has no vocabulary.")
                base = vocabulary
            else:
                base = words_only(self.source)
                if not base:
                    raise ValueError("The source corpus contains no usable words.")

            tokens = tokenize(self.source)
            result_paragraphs = []

            for p in range(self.paragraphs):
                generated = []
                if self.mode == "theme":
                    for i in range(self.words_per_paragraph):
                        generated.append(rng.choice(base))
                else:
                    for i in range(self.words_per_paragraph):
                        generated.append(rng.choice(base))

                if self.preserve_punctuation and tokens:
                    punctuation = [t for t in tokens if not t.isalnum() and not t.isspace()]
                    if punctuation:
                        for i in range(0, len(generated), max(1, len(generated)//8)):
                            generated[i] += rng.choice(punctuation)

                if self.add_numbers:
                    generated.extend([
                        f"ID-{rng.randint(1000,9999)}",
                        str(rng.randint(1, 999999)),
                        f"{rng.random():.6f}"
                    ])

                if self.stress:
                    generated.extend([
                        "©", "™", "₹", "€", "£", "±", "→",
                        "café", "naïve", "résumé", "Unicode_Δ", "مرحبا"
                    ])

                result_paragraphs.append(" ".join(generated))
                self.progress.emit(int((p + 1) * 100 / self.paragraphs))

            self.finished.emit("\n\n".join(result_paragraphs))
        except Exception as e:
            self.error.emit(str(e))


class TextLab(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("JASS", "TextLabStudio")
        self.thread = None
        self.worker = None
        self.generated = ""
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1450, 900)
        self.build_ui()
        self.restore_settings()

    def build_ui(self):
        self.setStyleSheet("""
        QMainWindow, QWidget { background: #111827; color: #e5e7eb; }
        QGroupBox {
            border: 1px solid #374151; border-radius: 10px;
            margin-top: 12px; padding: 12px; font-weight: 600;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        QPushButton {
            background: #2563eb; border: none; border-radius: 7px;
            padding: 8px 14px; font-weight: 600;
        }
        QPushButton:hover { background: #3b82f6; }
        QPushButton:disabled { background: #374151; color: #9ca3af; }
        QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
            background: #1f2937; border: 1px solid #4b5563;
            border-radius: 6px; padding: 7px;
        }
        QTextEdit, QPlainTextEdit {
            background: #0b1220; border: 1px solid #374151;
            border-radius: 8px; padding: 8px;
            selection-background-color: #2563eb;
        }
        QTabWidget::pane { border: 1px solid #374151; border-radius: 8px; }
        QTabBar::tab { padding: 9px 16px; }
        QTabBar::tab:selected { background: #1f2937; border-radius: 6px; }
        QProgressBar { border: 1px solid #374151; border-radius: 6px; text-align: center; }
        QProgressBar::chunk { background: #2563eb; border-radius: 5px; }
        QTableWidget { background: #0b1220; gridline-color: #374151; }
        QHeaderView::section { background: #1f2937; padding: 7px; border: none; }
        """)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 10)

        header = QHBoxLayout()
        title = QLabel("JASS TextLab Studio")
        title.setStyleSheet("font-size: 26px; font-weight: 800;")
        subtitle = QLabel("Multilingual text-generation • Unicode testing • reproducible test data")
        subtitle.setStyleSheet("color:#9ca3af; font-size:13px;")
        header.addWidget(title)
        header.addSpacing(15)
        header.addWidget(subtitle)
        header.addStretch()
        version = QLabel(APP_VERSION)
        version.setStyleSheet("color:#60a5fa; font-weight:700;")
        header.addWidget(version)
        root.addLayout(header)

        tabs = QTabWidget()
        tabs.addTab(self.generator_tab(), "✦ Generator")
        tabs.addTab(self.corpus_tab(), "📚 Corpus")
        tabs.addTab(self.testing_tab(), "🧪 Text Tests")
        tabs.addTab(self.stats_tab(), "📊 Statistics")
        root.addWidget(tabs, 1)

        self.setCentralWidget(central)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready — local/offline workspace")

        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        for text, slot in [
            ("Generate", self.generate),
            ("Copy", self.copy_text),
            ("Clear", self.clear_output),
            ("Save", self.save_output),
        ]:
            action = QAction(text, self)
            action.triggered.connect(slot)
            toolbar.addAction(action)

    def generator_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        controls = QGroupBox("Generation Controls")
        grid = QGridLayout(controls)

        self.source_combo = QComboBox()
        self.source_combo.addItems(BUILTIN_CORPORA.keys())
        self.source_combo.currentTextChanged.connect(self.load_corpus)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Corpus words", "corpus")
        self.mode_combo.addItem("Theme vocabulary", "theme")
        self.mode_combo.currentIndexChanged.connect(self.update_mode)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(CHARACTER_THEMES.keys())
        self.theme_combo.setEnabled(False)

        self.paragraphs = QSpinBox()
        self.paragraphs.setRange(1, 10000)
        self.paragraphs.setValue(3)

        self.words = QSpinBox()
        self.words.setRange(1, 100000)
        self.words.setValue(80)

        self.seed = QLineEdit()
        self.seed.setPlaceholderText("Blank = random; enter a number for reproducible output")

        self.punctuation = QCheckBox("Preserve punctuation patterns")
        self.numbers = QCheckBox("Inject numbers / IDs")
        self.stress = QCheckBox("Unicode stress characters")

        grid.addWidget(QLabel("Corpus / preset"), 0, 0)
        grid.addWidget(self.source_combo, 0, 1)
        grid.addWidget(QLabel("Generation mode"), 0, 2)
        grid.addWidget(self.mode_combo, 0, 3)
        grid.addWidget(QLabel("Theme"), 0, 4)
        grid.addWidget(self.theme_combo, 0, 5)

        grid.addWidget(QLabel("Paragraphs"), 1, 0)
        grid.addWidget(self.paragraphs, 1, 1)
        grid.addWidget(QLabel("Words / paragraph"), 1, 2)
        grid.addWidget(self.words, 1, 3)
        grid.addWidget(QLabel("Seed"), 1, 4)
        grid.addWidget(self.seed, 1, 5)

        grid.addWidget(self.punctuation, 2, 0, 1, 2)
        grid.addWidget(self.numbers, 2, 2, 1, 2)
        grid.addWidget(self.stress, 2, 4, 1, 2)
        layout.addWidget(controls)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Source corpus"))
        self.source_edit = QPlainTextEdit()
        ll.addWidget(self.source_edit)
        load = QPushButton("Load external corpus…")
        load.clicked.connect(self.load_external_corpus)
        ll.addWidget(load)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Generated text"))
        self.output = QPlainTextEdit()
        self.output.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        rl.addWidget(self.output, 1)

        buttons = QHBoxLayout()
        self.generate_btn = QPushButton("✦ Generate")
        self.generate_btn.clicked.connect(self.generate)
        copy = QPushButton("Copy")
        copy.clicked.connect(self.copy_text)
        save = QPushButton("Save…")
        save.clicked.connect(self.save_output)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_output)
        buttons.addWidget(self.generate_btn)
        buttons.addWidget(copy)
        buttons.addWidget(save)
        buttons.addWidget(clear)
        buttons.addStretch()
        rl.addLayout(buttons)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        rl.addWidget(self.progress)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([480, 900])
        layout.addWidget(splitter, 1)
        return w

    def corpus_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        info = QLabel(
            "Build your own multilingual corpus. Paste text or load TXT/MD/CSV files. "
            "The corpus stays local and can be reused by the Generator."
        )
        info.setWordWrap(True)
        l.addWidget(info)
        self.corpus_editor = QPlainTextEdit()
        self.corpus_editor.setPlainText(BUILTIN_CORPORA["English"])
        l.addWidget(self.corpus_editor, 1)

        row = QHBoxLayout()
        load = QPushButton("Load TXT / Markdown")
        load.clicked.connect(self.load_corpus_file)
        epub = QPushButton("Import EPUB Book")
        epub.clicked.connect(self.load_external_corpus)
        use = QPushButton("Use as Generator Source")
        use.clicked.connect(lambda: self.source_edit.setPlainText(self.corpus_editor.toPlainText()))
        save = QPushButton("Save Corpus")
        save.clicked.connect(self.save_corpus)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.corpus_editor.clear)
        row.addWidget(load); row.addWidget(epub); row.addWidget(use); row.addWidget(save); row.addWidget(clear); row.addStretch()
        l.addLayout(row)
        return w

    def testing_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        top = QHBoxLayout()
        self.test_text = QPlainTextEdit()
        self.test_text.setPlaceholderText("Paste generated or real application text here…")
        l.addWidget(self.test_text, 1)

        actions = QHBoxLayout()
        analyze = QPushButton("Run Text Diagnostics")
        analyze.clicked.connect(self.run_diagnostics)
        unicode_btn = QPushButton("Unicode Inventory")
        unicode_btn.clicked.connect(self.unicode_inventory)
        normalize = QPushButton("Normalize NFC")
        normalize.clicked.connect(self.normalize_text)
        sample = QPushButton("Load Generated Text")
        sample.clicked.connect(lambda: self.test_text.setPlainText(self.output.toPlainText()))
        actions.addWidget(analyze); actions.addWidget(unicode_btn); actions.addWidget(normalize); actions.addWidget(sample)
        actions.addStretch()
        l.addLayout(actions)

        self.diagnostic = QPlainTextEdit()
        self.diagnostic.setReadOnly(True)
        l.addWidget(self.diagnostic, 1)
        return w

    def stats_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.stats = QTableWidget(0, 2)
        self.stats.setHorizontalHeaderLabels(["Metric", "Value"])
        self.stats.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stats.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        l.addWidget(self.stats)
        refresh = QPushButton("Refresh Statistics")
        refresh.clicked.connect(self.update_stats)
        l.addWidget(refresh)
        return w

    def load_corpus(self, name):
        self.source_edit.setPlainText(BUILTIN_CORPORA.get(name, ""))

    def update_mode(self):
        is_theme = self.mode_combo.currentData() == "theme"
        self.theme_combo.setEnabled(is_theme)

    def load_external_corpus(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Corpus / Book", "",
            "EPUB books (*.epub);;Text files (*.txt *.md *.csv);;All files (*)"
        )
        if not path:
            return
        try:
            if Path(path).suffix.lower() == ".epub":
                text, metadata = extract_epub(path)
                if not text.strip():
                    raise ValueError("No readable text was found in this EPUB.")
                self.source_edit.setPlainText(text)
                title = metadata.get("title", Path(path).stem)
                author = metadata.get("creator", "Unknown author")
                self.corpus_editor.setPlainText(text)
                self.source_combo.setCurrentIndex(0)
                self.status.showMessage(
                    f"Imported EPUB: {title} — {author} | "
                    f"{metadata['chapters']} sections | {metadata['words']:,} words"
                )
            else:
                text = Path(path).read_text(encoding="utf-8")
                self.source_edit.setPlainText(text)
                self.status.showMessage(f"Loaded corpus: {Path(path).name}")
        except zipfile.BadZipFile:
            QMessageBox.critical(self, "Invalid EPUB", "The selected file is not a valid EPUB/ZIP container.")
        except ET.ParseError:
            QMessageBox.critical(self, "EPUB parsing error", "The EPUB contains malformed XML/XHTML that could not be parsed.")
        except Exception as e:
            QMessageBox.critical(self, "Import error", str(e))

    def load_corpus_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Corpus", "", "Text files (*.txt *.md *.csv);;All files (*)")
        if path:
            try:
                self.corpus_editor.setPlainText(Path(path).read_text(encoding="utf-8"))
            except Exception as e:
                QMessageBox.critical(self, "Load error", str(e))

    def save_corpus(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Corpus", "corpus.txt", "Text (*.txt);;Markdown (*.md)")
        if path:
            try:
                Path(path).write_text(self.corpus_editor.toPlainText(), encoding="utf-8")
                self.status.showMessage(f"Corpus saved: {Path(path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Save error", str(e))

    def generate(self):
        if self.thread is not None:
            return
        seed_text = self.seed.text().strip()
        try:
            seed = int(seed_text) if seed_text else None
        except ValueError:
            QMessageBox.warning(self, "Invalid seed", "Seed must be an integer or blank.")
            return

        self.generate_btn.setEnabled(False)
        self.progress.setValue(0)
        self.thread = QThread()
        self.worker = GeneratorWorker(
            self.source_edit.toPlainText(),
            self.paragraphs.value(),
            self.words.value(),
            self.mode_combo.currentData(),
            self.punctuation.isChecked(),
            self.theme_combo.currentText(),
            seed,
            self.numbers.isChecked(),
            self.stress.isChecked()
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self.generation_finished)
        self.worker.error.connect(self.generation_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.generation_thread_done)
        self.thread.start()

    def generation_finished(self, text):
        self.generated = text
        self.output.setPlainText(text)
        self.update_stats()
        self.status.showMessage("Generation completed")

    def generation_error(self, msg):
        QMessageBox.critical(self, "Generation error", msg)
        self.status.showMessage("Generation failed")

    def generation_thread_done(self):
        if self.thread:
            self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self.generate_btn.setEnabled(True)
        self.progress.setValue(100)

    def copy_text(self):
        text = self.output.toPlainText()
        QApplication.clipboard().setText(text)
        self.status.showMessage(f"Copied {len(text):,} characters")

    def clear_output(self):
        self.output.clear()
        self.generated = ""
        self.update_stats()

    def save_output(self):
        text = self.output.toPlainText()
        if not text:
            QMessageBox.information(self, "Nothing to save", "Generate some text first.")
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "Save Generated Text", "generated_text.txt",
            "Text (*.txt);;Markdown (*.md);;HTML (*.html);;JSON (*.json);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            suffix = Path(path).suffix.lower()
            if suffix == ".html":
                body = html.escape(text).replace("\n", "<br>\n")
                content = f"<!doctype html><html><meta charset='utf-8'><body><pre>{body}</pre></body></html>"
                Path(path).write_text(content, encoding="utf-8")
            elif suffix == ".json":
                payload = {
                    "application": APP_NAME, "version": APP_VERSION,
                    "created": datetime.now().isoformat(timespec="seconds"),
                    "language_preset": self.source_combo.currentText(),
                    "paragraphs": self.paragraphs.value(),
                    "words_per_paragraph": self.words.value(),
                    "seed": self.seed.text().strip() or None,
                    "text": text
                }
                Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            elif suffix == ".csv":
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(["paragraph", "text"])
                    for i, para in enumerate(text.split("\n\n"), 1):
                        writer.writerow([i, para])
            else:
                Path(path).write_text(text, encoding="utf-8")
            self.status.showMessage(f"Saved: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def run_diagnostics(self):
        text = self.test_text.toPlainText()
        if not text:
            self.diagnostic.setPlainText("No text supplied.")
            return
        lines = text.splitlines()
        words = words_only(text)
        chars = len(text)
        unique = len(set(words))
        whitespace = sum(c.isspace() for c in text)
        controls = [f"U+{ord(c):04X}" for c in text if ord(c) < 32 and c not in "\n\t\r"]
        rtl = sum(1 for c in text if "\u0590" <= c <= "\u08ff")
        combining = sum(1 for c in text if 0x300 <= ord(c) <= 0x36f)
        report = [
            "TEXT DIAGNOSTICS",
            "================",
            f"Characters: {chars:,}",
            f"Words: {len(words):,}",
            f"Unique words: {unique:,}",
            f"Lines: {len(lines):,}",
            f"Paragraphs: {len([p for p in text.split('\\n\\n') if p.strip()]):,}",
            f"Whitespace characters: {whitespace:,}",
            f"Approx. vocabulary ratio: {(unique/len(words)):.3f}" if words else "Approx. vocabulary ratio: 0",
            f"RTL-range characters: {rtl:,}",
            f"Combining marks: {combining:,}",
            f"Control characters: {len(controls):,}",
            "",
            "Useful checks:",
            "• Test search with mixed case and Unicode.",
            "• Test copy/paste and line wrapping.",
            "• Test RTL text in right-aligned widgets.",
            "• Test long identifiers and very long paragraphs.",
            "• Test export/import using UTF-8."
        ]
        self.diagnostic.setPlainText("\n".join(report))

    def unicode_inventory(self):
        text = self.test_text.toPlainText()
        if not text:
            return
        counts = {}
        for c in text:
            key = f"U+{ord(c):04X}"
            counts[key] = counts.get(key, 0) + 1
        rows = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        self.diagnostic.setPlainText(
            "UNICODE INVENTORY\n=================\n" +
            "\n".join(f"{code}: {count}" for code, count in rows[:500])
        )

    def normalize_text(self):
        import unicodedata
        before = self.test_text.toPlainText()
        after = unicodedata.normalize("NFC", before)
        self.test_text.setPlainText(after)
        self.status.showMessage("Text normalized to Unicode NFC")

    def update_stats(self):
        text = self.output.toPlainText()
        rows = [
            ("Characters", f"{len(text):,}"),
            ("Words", f"{len(words_only(text)):,}"),
            ("Lines", f"{len(text.splitlines()):,}"),
            ("Paragraphs", f"{len([p for p in text.split('\\n\\n') if p.strip()]):,}"),
            ("Unique words", f"{len(set(words_only(text))):,}"),
            ("UTF-8 bytes", f"{len(text.encode('utf-8')):,}"),
            ("Language preset", self.source_combo.currentText()),
            ("Mode", self.mode_combo.currentText()),
            ("Seed", self.seed.text().strip() or "random"),
        ]
        self.stats.setRowCount(len(rows))
        for r, (a, b) in enumerate(rows):
            self.stats.setItem(r, 0, QTableWidgetItem(a))
            self.stats.setItem(r, 1, QTableWidgetItem(b))

    def restore_settings(self):
        self.paragraphs.setValue(int(self.settings.value("paragraphs", 3)))
        self.words.setValue(int(self.settings.value("words", 80)))
        self.source_combo.setCurrentText(self.settings.value("corpus", "English"))
        self.seed.setText(self.settings.value("seed", ""))

    def closeEvent(self, event):
        self.settings.setValue("paragraphs", self.paragraphs.value())
        self.settings.setValue("words", self.words.value())
        self.settings.setValue("corpus", self.source_combo.currentText())
        self.settings.setValue("seed", self.seed.text())
        if self.thread:
            QMessageBox.warning(self, "Generation in progress", "Please wait for the current generation to finish.")
            event.ignore()
            return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("JASS")
    app.setFont(QFont("DejaVu Sans", 10))
    window = TextLab()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
