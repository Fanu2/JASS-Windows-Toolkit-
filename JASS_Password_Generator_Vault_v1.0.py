#!/usr/bin/env python3
"""
JASS Password Generator Vault v1.0

Local-first password generator and encrypted credential vault.
Security design:
- Password generation uses Python's cryptographically secure `secrets`.
- Vault encryption uses AES-256-GCM.
- Key derivation uses scrypt with a random salt.
- Vault is stored as a single encrypted JSON container.
- Plaintext passwords are never intentionally written to the vault file.
- No cloud, telemetry, browser integration, or network access.

Requires:
    python3 -m pip install PySide6 cryptography
"""

import base64
import json
import os
import secrets
import string
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QClipboard, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSlider,
    QSpinBox, QSplitter, QStatusBar, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

APP_NAME = "JASS Password Generator Vault"
VERSION = "1.0"
VAULT_VERSION = 1

MAGIC = b"JASS-PGV1"
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32

@dataclass
class Entry:
    id: str
    title: str
    username: str = ""
    password: str = ""
    url: str = ""
    notes: str = ""
    tags: str = ""
    created: str = ""
    modified: str = ""
    favorite: bool = False

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def b64e(data):
    return base64.b64encode(data).decode("ascii")

def b64d(data):
    return base64.b64decode(data.encode("ascii"))

def derive_key(master_password, salt):
    if not master_password:
        raise ValueError("Master password cannot be empty.")
    kdf = Scrypt(salt=salt, length=KEY_LEN, n=2**15, r=8, p=1)
    return kdf.derive(master_password.encode("utf-8"))

def encrypt_vault(master_password, entries):
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(master_password, salt)
    payload = {
        "vault_version": VAULT_VERSION,
        "created": now_iso(),
        "entries": [asdict(e) for e in entries],
    }
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, MAGIC)
    return {
        "format": "JASS-PGV1",
        "kdf": "scrypt",
        "scrypt": {"n": 2**15, "r": 8, "p": 1},
        "cipher": "AES-256-GCM",
        "salt": b64e(salt),
        "nonce": b64e(nonce),
        "ciphertext": b64e(ciphertext),
    }

def decrypt_vault(master_password, container):
    if container.get("format") != "JASS-PGV1":
        raise ValueError("Unsupported or invalid JASS vault format.")
    salt = b64d(container["salt"])
    nonce = b64d(container["nonce"])
    ciphertext = b64d(container["ciphertext"])
    key = derive_key(master_password, salt)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, MAGIC)
    payload = json.loads(plaintext.decode("utf-8"))
    entries = []
    for raw in payload.get("entries", []):
        entries.append(Entry(
            id=str(raw.get("id", secrets.token_hex(12))),
            title=str(raw.get("title", "")),
            username=str(raw.get("username", "")),
            password=str(raw.get("password", "")),
            url=str(raw.get("url", "")),
            notes=str(raw.get("notes", "")),
            tags=str(raw.get("tags", "")),
            created=str(raw.get("created", now_iso())),
            modified=str(raw.get("modified", now_iso())),
            favorite=bool(raw.get("favorite", False)),
        ))
    return entries

def generate_password(length, lower, upper, digits, symbols, exclude_ambiguous, custom_symbols):
    pools = []
    if lower:
        pools.append(string.ascii_lowercase)
    if upper:
        pools.append(string.ascii_uppercase)
    if digits:
        pools.append(string.digits)
    if symbols:
        pools.append(custom_symbols or "!@#$%^&*()-_=+[]{}:,.?")

    if not pools:
        raise ValueError("Select at least one character set.")

    ambiguous = set("O0oIl1|`'\"")
    cleaned = []
    for pool in pools:
        pool2 = "".join(c for c in pool if not (exclude_ambiguous and c in ambiguous))
        if pool2:
            cleaned.append(pool2)
    pools = cleaned
    if not pools:
        raise ValueError("Character rules leave no usable characters.")

    if length < len(pools):
        raise ValueError(f"Length must be at least {len(pools)} for the selected rules.")

    chars = [secrets.choice(pool) for pool in pools]
    combined = "".join(pools)
    chars += [secrets.choice(combined) for _ in range(length - len(chars))]

    # Fisher-Yates using secrets for unbiased final ordering.
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)

def generate_passphrase(words, separator, capitalize, add_number, add_symbol):
    # Small built-in word list keeps generation completely offline and dependency-free.
    words_pool = """
apple river mountain forest candle window garden silver morning thunder
planet meadow coffee summer winter autumn spring ocean valley sunrise
violet orange maple cedar willow amber crystal breeze shadow lantern
journey harmony freedom wisdom quiet bright gentle honest curious
falcon tiger rabbit eagle dolphin panda comet galaxy island castle
book music poetry camera village bridge garden keyboard notebook archive
""".split()
    chosen = [secrets.choice(words_pool) for _ in range(words)]
    if capitalize:
        chosen = [w.capitalize() for w in chosen]
    result = separator.join(chosen)
    if add_number:
        result += str(secrets.randbelow(10000)).zfill(2)
    if add_symbol:
        result += secrets.choice("!@#$%^&*+-=?")
    return result

def strength_info(password):
    n = len(password)
    pools = 0
    if any(c.islower() for c in password): pools += 26
    if any(c.isupper() for c in password): pools += 26
    if any(c.isdigit() for c in password): pools += 10
    if any(c in string.punctuation for c in password): pools += 32
    entropy = n * (pools.bit_length() if pools else 0)
    if n >= 20 and pools >= 80:
        label = "Very strong"
    elif n >= 14 and pools >= 60:
        label = "Strong"
    elif n >= 10 and pools >= 40:
        label = "Moderate"
    else:
        label = "Weak"
    return label, entropy

class PasswordDialog(QDialog):
    def __init__(self, parent=None, entry=None):
        super().__init__(parent)
        self.setWindowTitle("Vault Entry")
        self.resize(700, 600)
        self.entry = entry
        lay = QVBoxLayout(self)

        form = QFormLayout()
        self.title = QLineEdit(entry.title if entry else "")
        self.username = QLineEdit(entry.username if entry else "")
        self.password = QLineEdit(entry.password if entry else "")
        self.password.setEchoMode(QLineEdit.Password)
        self.url = QLineEdit(entry.url if entry else "")
        self.tags = QLineEdit(entry.tags if entry else "")
        self.notes = QPlainTextEdit(entry.notes if entry else "")
        form.addRow("Title:", self.title)
        form.addRow("Username:", self.username)

        pwrow = QHBoxLayout()
        pwrow.addWidget(self.password, 1)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(lambda checked: self.password.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password))
        pwrow.addWidget(show)
        gen = QPushButton("Generate")
        gen.clicked.connect(self.make_password)
        pwrow.addWidget(gen)
        form.addRow("Password:", pwrow)

        form.addRow("URL:", self.url)
        form.addRow("Tags:", self.tags)
        form.addRow("Notes:", self.notes)
        lay.addLayout(form)

        self.strength = QLabel("")
        lay.addWidget(self.strength)
        self.password.textChanged.connect(self.update_strength)
        self.update_strength(self.password.text())

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def make_password(self):
        try:
            self.password.setText(generate_password(24, True, True, True, True, True, ""))
        except Exception as e:
            QMessageBox.warning(self, "Generator", str(e))

    def update_strength(self, text):
        label, entropy = strength_info(text)
        self.strength.setText(f"Strength: {label}  •  Approx. character-pool entropy: {entropy} bits")

    def validate(self):
        if not self.title.text().strip():
            QMessageBox.warning(self, "Vault Entry", "Title is required.")
            return
        self.accept()

    def get_values(self):
        return {
            "title": self.title.text().strip(),
            "username": self.username.text(),
            "password": self.password.text(),
            "url": self.url.text().strip(),
            "tags": self.tags.text().strip(),
            "notes": self.notes.toPlainText(),
        }

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1450, 900)
        self.entries = []
        self.vault_path = None
        self.dirty = False
        self.master_password = None
        self.build_ui()
        self.apply_style()
        self.update_all()

    def build_ui(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 10)

        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        subtitle = QLabel("Cryptographically secure generation • AES-256-GCM encrypted vault • Offline-first")
        subtitle.setObjectName("Subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        bar = QHBoxLayout()
        self.vault_label = QLabel("No vault open")
        self.vault_label.setObjectName("VaultStatus")
        newb = QPushButton("New Vault")
        newb.clicked.connect(self.new_vault)
        openb = QPushButton("Open Vault")
        openb.clicked.connect(self.open_vault)
        saveb = QPushButton("Save Vault")
        saveb.clicked.connect(self.save_vault)
        saveb.setObjectName("Primary")
        closeb = QPushButton("Close Vault")
        closeb.clicked.connect(self.close_vault)
        bar.addWidget(self.vault_label, 1)
        bar.addWidget(newb); bar.addWidget(openb); bar.addWidget(saveb); bar.addWidget(closeb)
        outer.addLayout(bar)

        self.tabs = QTabWidget()
        self.generator = self.make_generator()
        self.vault = self.make_vault()
        self.dashboard = self.make_dashboard()
        self.security = self.make_security()
        self.tabs.addTab(self.generator, "Password Generator")
        self.tabs.addTab(self.vault, "Vault")
        self.tabs.addTab(self.dashboard, "Dashboard")
        self.tabs.addTab(self.security, "Security")
        outer.addWidget(self.tabs, 1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.make_menu()

    def make_menu(self):
        m = self.menuBar().addMenu("Vault")
        for text, fn in [
            ("New Vault", self.new_vault), ("Open Vault…", self.open_vault),
            ("Save Vault", self.save_vault), ("Close Vault", self.close_vault),
        ]:
            a = QAction(text, self); a.triggered.connect(fn); m.addAction(a)
        m.addSeparator()
        a = QAction("Quit", self); a.triggered.connect(self.close); m.addAction(a)

    def make_generator(self):
        w = QWidget(); lay = QVBoxLayout(w)
        split = QSplitter(Qt.Horizontal)

        left = QWidget(); gl = QVBoxLayout(left)
        box = QGroupBox("Random Password")
        g = QGridLayout(box)
        g.addWidget(QLabel("Length:"), 0, 0)
        self.pw_len = QSpinBox(); self.pw_len.setRange(4, 256); self.pw_len.setValue(24)
        g.addWidget(self.pw_len, 0, 1)
        self.lower = QCheckBox("Lowercase"); self.lower.setChecked(True)
        self.upper = QCheckBox("Uppercase"); self.upper.setChecked(True)
        self.digits = QCheckBox("Digits"); self.digits.setChecked(True)
        self.symbols = QCheckBox("Symbols"); self.symbols.setChecked(True)
        self.ambiguous = QCheckBox("Exclude ambiguous characters"); self.ambiguous.setChecked(True)
        for r, cb in enumerate([self.lower, self.upper, self.digits, self.symbols], 1):
            g.addWidget(cb, r, 0, 1, 2)
        g.addWidget(self.ambiguous, 5, 0, 1, 2)
        g.addWidget(QLabel("Custom symbols:"), 6, 0)
        self.custom_symbols = QLineEdit("!@#$%^&*()-_=+[]{}:,.?")
        g.addWidget(self.custom_symbols, 6, 1)
        gen = QPushButton("Generate Secure Password")
        gen.setObjectName("Primary")
        gen.clicked.connect(self.generate)
        g.addWidget(gen, 7, 0, 1, 2)
        gl.addWidget(box)

        box2 = QGroupBox("Passphrase")
        p = QGridLayout(box2)
        p.addWidget(QLabel("Words:"), 0, 0)
        self.words = QSpinBox(); self.words.setRange(3, 12); self.words.setValue(5)
        p.addWidget(self.words, 0, 1)
        p.addWidget(QLabel("Separator:"), 1, 0)
        self.separator = QLineEdit("-"); p.addWidget(self.separator, 1, 1)
        self.capitalize = QCheckBox("Capitalize words"); self.capitalize.setChecked(True)
        self.add_number = QCheckBox("Add number"); self.add_number.setChecked(True)
        self.add_symbol = QCheckBox("Add symbol"); self.add_symbol.setChecked(True)
        p.addWidget(self.capitalize, 2, 0, 1, 2)
        p.addWidget(self.add_number, 3, 0, 1, 2)
        p.addWidget(self.add_symbol, 4, 0, 1, 2)
        b = QPushButton("Generate Passphrase"); b.clicked.connect(self.generate_phrase)
        p.addWidget(b, 5, 0, 1, 2)
        gl.addWidget(box2)
        gl.addStretch()

        right = QWidget(); rl = QVBoxLayout(right)
        out = QGroupBox("Generated Secret")
        ol = QVBoxLayout(out)
        self.generated = QLineEdit()
        self.generated.setReadOnly(True)
        self.generated.setFont(QFont("Monospace", 16))
        ol.addWidget(self.generated)
        self.gen_strength = QLabel("Generate a password.")
        ol.addWidget(self.gen_strength)
        row = QHBoxLayout()
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: self.copy_secret(self.generated.text()))
        use = QPushButton("Create Vault Entry")
        use.clicked.connect(self.create_from_generated)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.generated.clear)
        row.addWidget(copy); row.addWidget(use); row.addWidget(clear)
        ol.addLayout(row)
        rl.addWidget(out)

        tips = QGroupBox("Generator Notes")
        tl = QVBoxLayout(tips)
        t = QLabel(
            "Generation uses Python's `secrets` module, intended for cryptographic "
            "randomness. Each selected character class contributes at least one character."
        )
        t.setWordWrap(True); tl.addWidget(t)
        rl.addWidget(tips)
        rl.addStretch()

        split.addWidget(left); split.addWidget(right)
        split.setSizes([600, 700])
        lay.addWidget(split)
        return w

    def make_vault(self):
        w = QWidget(); lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.vault_search = QLineEdit()
        self.vault_search.setPlaceholderText("Search title, username, URL, tags, notes…")
        self.vault_search.textChanged.connect(self.filter_vault)
        self.tag_filter = QLineEdit()
        self.tag_filter.setPlaceholderText("Tag filter")
        self.tag_filter.textChanged.connect(self.filter_vault)
        top.addWidget(self.vault_search, 1); top.addWidget(self.tag_filter)
        lay.addLayout(top)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["★", "Title", "Username", "URL", "Tags", "Modified", "ID"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self.edit_entry)
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        for text, fn in [
            ("＋ Add Entry", self.add_entry),
            ("Edit", self.edit_entry),
            ("★ Favorite", self.toggle_favorite),
            ("Copy Password", self.copy_entry_password),
            ("Copy Username", self.copy_entry_username),
            ("Delete", self.delete_entry),
        ]:
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch(); lay.addLayout(row)
        return w

    def make_dashboard(self):
        w = QWidget(); lay = QVBoxLayout(w)
        grid = QGridLayout()
        self.cards = {}
        for i, (key, label) in enumerate([
            ("entries", "Vault Entries"), ("favorites", "Favorites"),
            ("passwords", "Passwords Stored"), ("tags", "Tagged Entries"),
            ("with_url", "Entries With URL"), ("vault", "Vault State")
        ]):
            f = QFrame(); f.setObjectName("Card")
            l = QVBoxLayout(f); a = QLabel(label); a.setObjectName("CardLabel")
            b = QLabel("0"); b.setObjectName("CardValue")
            l.addWidget(a); l.addWidget(b); self.cards[key] = b
            grid.addWidget(f, i // 3, i % 3)
        lay.addLayout(grid)
        self.dashboard_info = QPlainTextEdit(); self.dashboard_info.setReadOnly(True)
        lay.addWidget(self.dashboard_info, 1)
        return w

    def make_security(self):
        w = QWidget(); lay = QVBoxLayout(w)
        t = QPlainTextEdit(); t.setReadOnly(True)
        t.setPlainText("""JASS Password Generator Vault — Security Model

PASSWORD GENERATION
-------------------
Passwords use Python's `secrets` module rather than a general-purpose PRNG.
Selected character classes are represented and the final character order is
shuffled using secrets.randbelow().

VAULT ENCRYPTION
----------------
Vault contents are encrypted using AES-256-GCM.

The master password is converted into a 256-bit encryption key using scrypt
with a random 128-bit salt.

Each vault save creates a fresh random salt and nonce.

FILE FORMAT
-----------
The vault is a JSON container containing:
• format/version information
• KDF parameters
• random salt
• random nonce
• AES-GCM ciphertext

The actual entries exist inside the ciphertext.

MASTER PASSWORD
---------------
The master password is not stored in the vault.

If you forget the master password, the vault cannot be recovered by JASS.

MEMORY
------
The application needs plaintext passwords in memory while the vault is open.
Python does not provide reliable guaranteed memory wiping for ordinary strings,
so this program does not claim to provide secure-memory erasure.

CLIPBOARD
---------
Copying a password places it in the desktop clipboard. The clipboard is outside
the application's control. Avoid copying secrets on shared/untrusted desktops.

THREAT MODEL
------------
This tool is intended for local personal use against ordinary file disclosure.
It is not a hardened password manager designed for hostile processes with
administrator/root access, memory inspection, keyloggers, compromised desktops,
or malware.

BACKUPS
-------
An encrypted vault file can be backed up. Protect backup copies because they
are encrypted but still security-sensitive.

RECOMMENDED PRACTICES
---------------------
• Use a strong, unique master password.
• Keep the vault file on a protected filesystem.
• Lock your desktop when away.
• Keep secure backups.
• Do not reuse generated passwords across services.
• Do not put the master password in the vault itself.
""")
        lay.addWidget(t, 1)
        return w

    def generate(self):
        try:
            pw = generate_password(
                self.pw_len.value(), self.lower.isChecked(), self.upper.isChecked(),
                self.digits.isChecked(), self.symbols.isChecked(),
                self.ambiguous.isChecked(), self.custom_symbols.text()
            )
            self.generated.setText(pw)
            self.update_generated_strength()
        except Exception as e:
            QMessageBox.warning(self, "Generator", str(e))

    def generate_phrase(self):
        try:
            p = generate_passphrase(
                self.words.value(), self.separator.text(), self.capitalize.isChecked(),
                self.add_number.isChecked(), self.add_symbol.isChecked()
            )
            self.generated.setText(p)
            self.update_generated_strength()
        except Exception as e:
            QMessageBox.warning(self, "Passphrase", str(e))

    def update_generated_strength(self):
        label, entropy = strength_info(self.generated.text())
        self.gen_strength.setText(f"Strength: {label}  •  Approx. entropy indicator: {entropy} bits")

    def copy_secret(self, text):
        if not text: return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Secret copied to clipboard.")
        QTimer.singleShot(30000, lambda: self.clear_clipboard_if_matches(text))

    def clear_clipboard_if_matches(self, text):
        cb = QApplication.clipboard()
        if cb.text() == text:
            cb.clear()

    def create_from_generated(self):
        if not self.generated.text():
            self.generate()
        if not self.generated.text():
            return
        e = Entry(secrets.token_hex(12), "New Account", password=self.generated.text(),
                  created=now_iso(), modified=now_iso())
        dlg = PasswordDialog(self, e)
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.get_values()
            for k, v in vals.items(): setattr(e, k, v)
            self.entries.append(e); self.dirty = True
            self.update_all()
            self.tabs.setCurrentWidget(self.vault)

    def add_entry(self):
        e = Entry(secrets.token_hex(12), "", created=now_iso(), modified=now_iso())
        dlg = PasswordDialog(self, e)
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.get_values()
            for k, v in vals.items(): setattr(e, k, v)
            self.entries.append(e); self.dirty = True
            self.update_all()

    def selected_entry(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        # Table is rebuilt in source order, so map visible row through hidden state.
        visible = [e for e in self.entries if self.entry_visible(e)]
        return visible[row] if 0 <= row < len(visible) else None

    def entry_visible(self, e):
        needle = self.vault_search.text().lower().strip()
        tag = self.tag_filter.text().lower().strip()
        hay = " ".join([e.title, e.username, e.url, e.tags, e.notes]).lower()
        return (not needle or needle in hay) and (not tag or tag in e.tags.lower())

    def filter_vault(self):
        for r in range(self.table.rowCount()):
            # Table has one row per entry in source order.
            e = self.entries[r] if r < len(self.entries) else None
            self.table.setRowHidden(r, not (e and self.entry_visible(e)))

    def rebuild_table(self):
        self.table.setRowCount(0)
        for e in self.entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            vals = ["★" if e.favorite else "", e.title, e.username, e.url, e.tags, e.modified, e.id[:8]]
            for c, v in enumerate(vals):
                self.table.setItem(row, c, QTableWidgetItem(str(v)))
        self.filter_vault()

    def edit_entry(self):
        e = self.selected_entry()
        if not e:
            QMessageBox.information(self, APP_NAME, "Select a vault entry first.")
            return
        dlg = PasswordDialog(self, e)
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.get_values()
            for k, v in vals.items(): setattr(e, k, v)
            e.modified = now_iso()
            self.dirty = True
            self.update_all()

    def toggle_favorite(self):
        e = self.selected_entry()
        if not e: return
        e.favorite = not e.favorite
        e.modified = now_iso()
        self.dirty = True
        self.update_all()

    def copy_entry_password(self):
        e = self.selected_entry()
        if e: self.copy_secret(e.password)

    def copy_entry_username(self):
        e = self.selected_entry()
        if e: self.copy_secret(e.username)

    def delete_entry(self):
        e = self.selected_entry()
        if not e: return
        ans = QMessageBox.question(
            self, "Delete Entry", f"Delete '{e.title}' from the open vault?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            self.entries.remove(e)
            self.dirty = True
            self.update_all()

    def new_vault(self):
        if self.dirty and not self.confirm_discard():
            return
        p, _ = QFileDialog.getSaveFileName(self, "Create Vault", "JASS_Vault.jassvault",
                                            "JASS Vault (*.jassvault)")
        if not p: return
        pw = self.ask_master("Create Master Password", "Enter a strong master password:")
        if pw is None: return
        confirm = self.ask_master("Confirm Master Password", "Re-enter the master password:")
        if confirm != pw:
            QMessageBox.warning(self, APP_NAME, "Master passwords do not match.")
            return
        if len(pw) < 12:
            ans = QMessageBox.question(
                self, APP_NAME,
                "The master password is shorter than 12 characters. Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if ans != QMessageBox.Yes: return
        self.entries = []
        self.master_password = pw
        self.vault_path = Path(p)
        self.dirty = True
        self.save_vault()
        self.update_all()

    def open_vault(self):
        if self.dirty and not self.confirm_discard():
            return
        p, _ = QFileDialog.getOpenFileName(self, "Open Vault", "", "JASS Vault (*.jassvault);;JSON (*.json)")
        if not p: return
        pw = self.ask_master("Unlock Vault", "Enter master password:")
        if pw is None: return
        try:
            container = json.loads(Path(p).read_text(encoding="utf-8"))
            self.entries = decrypt_vault(pw, container)
            self.master_password = pw
            self.vault_path = Path(p)
            self.dirty = False
            self.update_all()
            self.statusBar().showMessage("Vault unlocked.")
        except Exception:
            QMessageBox.critical(self, APP_NAME,
                                 "Could not unlock the vault. Check the file and master password.")

    def save_vault(self):
        if self.vault_path is None or self.master_password is None:
            QMessageBox.information(self, APP_NAME, "Create or open a vault first.")
            return
        try:
            container = encrypt_vault(self.master_password, self.entries)
            tmp = self.vault_path.with_suffix(self.vault_path.suffix + ".tmp")
            tmp.write_text(json.dumps(container, indent=2), encoding="utf-8")
            os.replace(tmp, self.vault_path)
            self.dirty = False
            self.update_all()
            self.statusBar().showMessage(f"Vault saved: {self.vault_path}")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not save vault:\n{e}")

    def close_vault(self):
        if self.dirty and not self.confirm_discard():
            return
        self.entries = []
        self.master_password = None
        self.vault_path = None
        self.dirty = False
        self.update_all()
        self.statusBar().showMessage("Vault closed.")

    def ask_master(self, title, prompt):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(520, 180)
        lay = QVBoxLayout(dlg)
        lab = QLabel(prompt); lab.setWordWrap(True); lay.addWidget(lab)
        edit = QLineEdit(); edit.setEchoMode(QLineEdit.Password); lay.addWidget(edit)
        show = QCheckBox("Show password")
        show.toggled.connect(lambda x: edit.setEchoMode(QLineEdit.Normal if x else QLineEdit.Password))
        lay.addWidget(show)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() == QDialog.Accepted:
            return edit.text()
        return None

    def confirm_discard(self):
        ans = QMessageBox.question(
            self, APP_NAME,
            "The open vault has unsaved changes. Discard them?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        return ans == QMessageBox.Yes

    def update_all(self):
        self.rebuild_table()
        n = len(self.entries)
        self.cards["entries"].setText(str(n))
        self.cards["favorites"].setText(str(sum(e.favorite for e in self.entries)))
        self.cards["passwords"].setText(str(sum(bool(e.password) for e in self.entries)))
        self.cards["tags"].setText(str(sum(bool(e.tags) for e in self.entries)))
        self.cards["with_url"].setText(str(sum(bool(e.url) for e in self.entries)))
        self.cards["vault"].setText("Unsaved" if self.dirty else ("Open" if self.vault_path else "Closed"))
        self.vault_label.setText(
            f"🔓 {self.vault_path}" if self.vault_path else "🔒 No vault open"
        )
        self.dashboard_info.setPlainText(
            f"Vault: {self.vault_path or 'None'}\n"
            f"Entries: {n}\n"
            f"Favorites: {sum(e.favorite for e in self.entries)}\n"
            f"Unsaved changes: {'Yes' if self.dirty else 'No'}\n\n"
            "The vault is encrypted when saved. While open, decrypted entry data is present in application memory."
        )

    def closeEvent(self, event):
        if self.dirty and not self.confirm_discard():
            event.ignore()
            return
        self.entries = []
        self.master_password = None
        event.accept()

    def apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { font-size: 13px; }
            #Title { font-size: 28px; font-weight: 700; padding: 2px 0; }
            #Subtitle { color: #5b7187; font-size: 14px; padding-bottom: 6px; }
            #VaultStatus { font-weight: 700; padding: 6px; }
            QGroupBox { font-weight: 700; border: 1px solid #cbd3dc; border-radius: 8px; margin-top: 8px; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QFrame#Card { border: 1px solid #d3dae2; border-radius: 10px; background: #f8fafc; min-height: 80px; }
            #CardLabel { color: #5f6f7f; font-weight: 600; }
            #CardValue { font-size: 24px; font-weight: 700; }
            QPushButton { padding: 7px 13px; border: 1px solid #b9c2cc; border-radius: 6px; }
            QPushButton:hover { background: #eef3f7; }
            QPushButton#Primary { font-weight: 700; padding: 8px 16px; }
            QLineEdit, QComboBox, QSpinBox { padding: 6px; }
            QTableWidget { gridline-color: #d8dee5; }
            QHeaderView::section { padding: 7px; font-weight: 700; }
            QTabBar::tab { padding: 8px 15px; }
        """)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w = MainWindow()
    w.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
