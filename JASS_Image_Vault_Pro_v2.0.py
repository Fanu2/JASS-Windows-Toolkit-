"""
JASS Image Vault Pro
AES-256-GCM image encryption/decryption utility.

Based on the supplied Tkinter Image Encryption Decryption application.
The original used a random floating-point division key and JPEG output;
this version replaces that with authenticated AES-GCM encryption of the
original image bytes, preserving lossless recovery.
"""

import os
import sys
import json
import base64
import hashlib
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QImageReader, QAction, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QLineEdit, QCheckBox,
    QFrame, QScrollArea, QSplitter, QStatusBar, QProgressBar, QGroupBox,
    QFormLayout, QComboBox, QSpinBox
)

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
except ImportError:
    AESGCM = None
    Scrypt = None


APP_NAME = "JASS Image Vault Pro"
VERSION = "2.0"
MAGIC = b"JASSIMG2"
SALT_SIZE = 16
NONCE_SIZE = 12
KEY_SIZE = 32
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def human_size(n):
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:,.1f} {unit}"
        value /= 1024


def derive_key(password, salt):
    kdf = Scrypt(
        salt=salt,
        length=KEY_SIZE,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    return kdf.derive(password.encode("utf-8"))


class CryptoWorker(QThread):
    finished = Signal(bool, str)
    progress = Signal(int)
    status = Signal(str)

    def __init__(self, mode, source, destination, password):
        super().__init__()
        self.mode = mode
        self.source = source
        self.destination = destination
        self.password = password

    def run(self):
        try:
            if AESGCM is None:
                raise RuntimeError(
                    "The 'cryptography' package is required.\n"
                    "Install it with: python3 -m pip install cryptography"
                )

            self.progress.emit(5)
            self.status.emit("Reading image data…")

            if self.mode == "encrypt":
                raw = Path(self.source).read_bytes()
                if not raw:
                    raise ValueError("The selected file is empty.")

                self.progress.emit(20)
                salt = os.urandom(SALT_SIZE)
                nonce = os.urandom(NONCE_SIZE)

                self.status.emit("Deriving encryption key…")
                key = derive_key(self.password, salt)

                self.progress.emit(55)
                self.status.emit("Encrypting with AES-256-GCM…")

                aad = MAGIC + b"|AES256-GCM"
                encrypted = AESGCM(key).encrypt(nonce, raw, aad)

                header = {
                    "version": 2,
                    "algorithm": "AES-256-GCM",
                    "kdf": "scrypt",
                    "scrypt": {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P},
                    "original_name": Path(self.source).name,
                    "original_suffix": Path(self.source).suffix.lower(),
                    "original_size": len(raw),
                    "salt": base64.b64encode(salt).decode("ascii"),
                    "nonce": base64.b64encode(nonce).decode("ascii"),
                }
                header_bytes = json.dumps(
                    header, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")

                output = (
                    MAGIC
                    + len(header_bytes).to_bytes(4, "big")
                    + header_bytes
                    + encrypted
                )

                self.progress.emit(85)
                Path(self.destination).write_bytes(output)
                self.progress.emit(100)
                self.finished.emit(
                    True,
                    f"Encrypted successfully.\n\n"
                    f"Original: {human_size(len(raw))}\n"
                    f"Vault: {human_size(len(output))}\n"
                    f"Saved to: {self.destination}",
                )

            else:
                vault = Path(self.source).read_bytes()
                if len(vault) < len(MAGIC) + 4 or not vault.startswith(MAGIC):
                    raise ValueError("This is not a valid JASS Image Vault file.")

                self.progress.emit(20)
                header_len_start = len(MAGIC)
                header_len = int.from_bytes(
                    vault[header_len_start:header_len_start + 4], "big"
                )
                header_start = header_len_start + 4
                header_end = header_start + header_len

                if header_end > len(vault):
                    raise ValueError("The vault header is damaged or incomplete.")

                header = json.loads(vault[header_start:header_end].decode("utf-8"))
                salt = base64.b64decode(header["salt"])
                nonce = base64.b64decode(header["nonce"])
                encrypted = vault[header_end:]

                self.status.emit("Deriving decryption key…")
                key = derive_key(self.password, salt)

                self.progress.emit(60)
                self.status.emit("Authenticating and decrypting…")

                aad = MAGIC + b"|AES256-GCM"
                raw = AESGCM(key).decrypt(nonce, encrypted, aad)

                self.progress.emit(90)
                Path(self.destination).write_bytes(raw)
                self.progress.emit(100)

                self.finished.emit(
                    True,
                    f"Decrypted successfully.\n\n"
                    f"Recovered: {human_size(len(raw))}\n"
                    f"Saved to: {self.destination}",
                )

        except Exception as exc:
            self.finished.emit(False, str(exc))


class ImageCanvas(QLabel):
    def __init__(self, placeholder):
        super().__init__()
        self.placeholder = placeholder
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 280)
        self.setText(placeholder)
        self.setObjectName("imageCanvas")
        self._pixmap = None
        self.zoom = 1.0

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.zoom = 1.0
        self.refresh()

    def clear_image(self):
        self._pixmap = None
        self.setPixmap(QPixmap())
        self.setText(self.placeholder)

    def set_zoom(self, value):
        self.zoom = max(0.1, min(5.0, value))
        self.refresh()

    def refresh(self):
        if self._pixmap is None or self._pixmap.isNull():
            self.setText(self.placeholder)
            return

        available = self.size()
        scaled = self._pixmap.scaled(
            int(available.width() * self.zoom),
            int(available.height() * self.zoom),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.source_path = ""
        self.original_pixmap = None
        self.worker = None
        self.current_mode = None

        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1380, 850)
        self.setMinimumSize(1050, 700)

        self.build_ui()
        self.apply_style()
        self.update_controls()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel(
            "Private image protection with password-based AES-256-GCM encryption"
        )
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.mode_badge = QLabel("READY")
        self.mode_badge.setObjectName("badge")
        header.addWidget(self.mode_badge)
        root.addLayout(header)

        # File controls
        file_panel = QFrame()
        file_panel.setObjectName("panel")
        grid = QGridLayout(file_panel)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setSpacing(9)

        grid.addWidget(QLabel("Source"), 0, 0)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText(
            "Choose an image to encrypt, or a .jassvault file to decrypt…"
        )
        self.source_edit.textChanged.connect(self.on_source_changed)
        grid.addWidget(self.source_edit, 0, 1, 1, 4)

        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_source)
        grid.addWidget(browse, 0, 5)

        grid.addWidget(QLabel("Password"), 1, 0)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Enter encryption password")
        self.password_edit.textChanged.connect(self.update_password_strength)
        grid.addWidget(self.password_edit, 1, 1, 1, 3)

        self.show_password = QCheckBox("Show")
        self.show_password.toggled.connect(self.toggle_password)
        grid.addWidget(self.show_password, 1, 4)

        self.strength_label = QLabel("Password strength: —")
        self.strength_label.setObjectName("muted")
        grid.addWidget(self.strength_label, 1, 5)

        grid.addWidget(QLabel("Operation"), 2, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Encrypt image", "Decrypt vault"])
        self.mode_combo.currentIndexChanged.connect(self.mode_changed)
        grid.addWidget(self.mode_combo, 2, 1)

        self.remember_output = QCheckBox("Suggest output filename")
        self.remember_output.setChecked(True)
        grid.addWidget(self.remember_output, 2, 2, 1, 2)

        self.action_button = QPushButton("🔐  Encrypt Image")
        self.action_button.setObjectName("primary")
        self.action_button.clicked.connect(self.start_operation)
        grid.addWidget(self.action_button, 2, 4, 1, 2)

        root.addWidget(file_panel)

        # Preview area
        splitter = QSplitter(Qt.Horizontal)

        original_panel = QFrame()
        original_panel.setObjectName("panel")
        op = QVBoxLayout(original_panel)
        op.setContentsMargins(12, 12, 12, 12)
        op.addWidget(self.make_panel_title("Original / Source Preview"))
        self.original_view = ImageCanvas("No image selected")
        op.addWidget(self.original_view, 1)

        self.original_info = QLabel("No image loaded")
        self.original_info.setObjectName("muted")
        op.addWidget(self.original_info)

        zoom_row = QHBoxLayout()
        zoom_out = QPushButton("−")
        zoom_out.clicked.connect(lambda: self.change_zoom(self.original_view, -0.1))
        zoom_in = QPushButton("+")
        zoom_in.clicked.connect(lambda: self.change_zoom(self.original_view, 0.1))
        fit = QPushButton("Fit")
        fit.clicked.connect(lambda: self.original_view.set_zoom(1.0))
        zoom_row.addWidget(zoom_out)
        zoom_row.addWidget(fit)
        zoom_row.addWidget(zoom_in)
        zoom_row.addStretch()
        op.addLayout(zoom_row)

        result_panel = QFrame()
        result_panel.setObjectName("panel")
        rp = QVBoxLayout(result_panel)
        rp.setContentsMargins(12, 12, 12, 12)
        rp.addWidget(self.make_panel_title("Result Preview"))
        self.result_view = ImageCanvas("Encrypted/decrypted result appears here")
        rp.addWidget(self.result_view, 1)
        self.result_info = QLabel("No result")
        self.result_info.setObjectName("muted")
        rp.addWidget(self.result_info)

        splitter.addWidget(original_panel)
        splitter.addWidget(result_panel)
        splitter.setSizes([1, 1])
        root.addWidget(splitter, 1)

        # Security/info panel
        bottom = QHBoxLayout()

        security = QGroupBox("Security")
        sf = QFormLayout(security)
        sf.addRow("Cipher:", QLabel("AES-256-GCM"))
        sf.addRow("Key derivation:", QLabel("scrypt"))
        sf.addRow("Authentication:", QLabel("Built-in GCM tag"))
        bottom.addWidget(security)

        info = QGroupBox("Workflow")
        inf = QFormLayout(info)
        inf.addRow("Encrypt:", QLabel("Image → .jassvault"))
        inf.addRow("Decrypt:", QLabel(".jassvault → original bytes"))
        inf.addRow("Data handling:", QLabel("Local only"))
        bottom.addWidget(info)

        bottom.addStretch()
        root.addLayout(bottom)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        root.addWidget(self.progress)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    def make_panel_title(self, text):
        label = QLabel(text)
        label.setObjectName("panelTitle")
        return label

    def apply_style(self):
        self.setStyleSheet("""
        QWidget {
            font-family: "Noto Sans", "Segoe UI", sans-serif;
            font-size: 13px;
        }
        QMainWindow, QWidget {
            background: #f4f6fa;
            color: #1f2937;
        }
        QLabel#title {
            font-size: 28px;
            font-weight: 750;
            color: #111827;
        }
        QLabel#subtitle, QLabel#muted {
            color: #667085;
        }
        QLabel#badge {
            background: #e9eefc;
            color: #4053b5;
            border-radius: 16px;
            padding: 8px 16px;
            font-weight: 700;
        }
        QFrame#panel {
            background: #ffffff;
            border: 1px solid #dfe4ec;
            border-radius: 12px;
        }
        QLabel#panelTitle {
            font-size: 15px;
            font-weight: 700;
            color: #273142;
            padding-bottom: 5px;
        }
        QLabel#imageCanvas {
            background: #f7f8fb;
            border: 1px dashed #cbd3df;
            border-radius: 9px;
            color: #8a94a6;
            font-size: 14px;
        }
        QLineEdit, QComboBox, QSpinBox {
            background: white;
            border: 1px solid #cbd3df;
            border-radius: 7px;
            padding: 8px 10px;
            min-height: 18px;
        }
        QLineEdit:focus, QComboBox:focus {
            border: 1px solid #6478e5;
        }
        QPushButton {
            background: #ffffff;
            border: 1px solid #cbd3df;
            border-radius: 7px;
            padding: 8px 14px;
            min-height: 18px;
        }
        QPushButton:hover {
            background: #eef2ff;
        }
        QPushButton#primary {
            background: #4f63d8;
            color: white;
            border: none;
            font-weight: 700;
        }
        QPushButton#primary:hover {
            background: #4053c5;
        }
        QGroupBox {
            background: white;
            border: 1px solid #dfe4ec;
            border-radius: 9px;
            margin-top: 10px;
            padding: 10px;
            min-width: 280px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 5px;
            font-weight: 700;
        }
        QProgressBar {
            border: none;
            background: #e5e9f0;
            border-radius: 5px;
            height: 8px;
        }
        QProgressBar::chunk {
            background: #6378e6;
            border-radius: 5px;
        }
        QStatusBar {
            background: #eef1f6;
            color: #667085;
        }
        """)

    def choose_source(self):
        if self.mode_combo.currentIndex() == 0:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Choose Image",
                "",
                "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All Files (*)",
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Choose JASS Vault",
                "",
                "JASS Vault (*.jassvault);;All Files (*)",
            )

        if path:
            self.source_edit.setText(path)

    def on_source_changed(self, path):
        if path and os.path.isfile(path) and self.mode_combo.currentIndex() == 0:
            self.load_preview(path)
        elif self.mode_combo.currentIndex() == 1:
            self.original_view.clear_image()
            self.original_info.setText("Encrypted vault selected")

    def load_preview(self, path):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self.original_view.clear_image()
            self.original_info.setText("Unable to preview this image.")
            return

        self.original_pixmap = QPixmap.fromImage(image)
        self.original_view.set_pixmap(self.original_pixmap)

        size = os.path.getsize(path)
        self.original_info.setText(
            f"{Path(path).name}  •  {image.width()} × {image.height()} px  •  "
            f"{human_size(size)}"
        )

    def mode_changed(self):
        decrypt = self.mode_combo.currentIndex() == 1
        self.current_mode = "decrypt" if decrypt else "encrypt"
        self.action_button.setText(
            "🔓  Decrypt Vault" if decrypt else "🔐  Encrypt Image"
        )
        self.mode_badge.setText("DECRYPT" if decrypt else "ENCRYPT")
        self.source_edit.clear()
        self.original_view.clear_image()
        self.result_view.clear_image()
        self.original_info.setText("No image loaded")
        self.result_info.setText("No result")
        self.update_controls()

    def update_controls(self):
        pass

    def toggle_password(self, checked):
        self.password_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        )

    def update_password_strength(self, password):
        if not password:
            self.strength_label.setText("Password strength: —")
            return

        score = 0
        if len(password) >= 8:
            score += 1
        if len(password) >= 12:
            score += 1
        if any(c.islower() for c in password) and any(c.isupper() for c in password):
            score += 1
        if any(c.isdigit() for c in password):
            score += 1
        if any(not c.isalnum() for c in password):
            score += 1

        labels = ["Very weak", "Weak", "Fair", "Good", "Strong", "Strong"]
        self.strength_label.setText(f"Password strength: {labels[score]}")

    def change_zoom(self, view, delta):
        view.set_zoom(view.zoom + delta)

    def start_operation(self):
        if self.worker and self.worker.isRunning():
            return

        source = self.source_edit.text().strip()
        password = self.password_edit.text()

        if not source or not os.path.isfile(source):
            QMessageBox.warning(self, "Source required", "Please choose a valid source file.")
            return

        if not password:
            QMessageBox.warning(self, "Password required", "Enter a password first.")
            return

        if len(password) < 8:
            answer = QMessageBox.question(
                self,
                "Weak password",
                "This password is shorter than 8 characters.\n"
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        encrypting = self.mode_combo.currentIndex() == 0

        if encrypting:
            suffix = Path(source).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
                QMessageBox.warning(
                    self, "Unsupported image",
                    "Choose a common image file such as PNG, JPG, BMP or WEBP."
                )
                return

            suggested = str(Path(source).with_suffix(".jassvault"))
            destination, _ = QFileDialog.getSaveFileName(
                self, "Save Encrypted Vault", suggested,
                "JASS Vault (*.jassvault)"
            )
        else:
            suggested_name = Path(source).stem
            try:
                with open(source, "rb") as f:
                    data = f.read()
                if data.startswith(MAGIC):
                    hlen = int.from_bytes(data[len(MAGIC):len(MAGIC)+4], "big")
                    hstart = len(MAGIC) + 4
                    header = json.loads(data[hstart:hstart+hlen].decode("utf-8"))
                    suggested_name = header.get("original_name", suggested_name)
            except Exception:
                pass

            destination, _ = QFileDialog.getSaveFileName(
                self, "Save Decrypted Image", suggested_name,
                "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*)"
            )

        if not destination:
            return

        self.progress.setValue(0)
        self.progress.show()
        self.action_button.setEnabled(False)
        self.mode_badge.setText("WORKING…")

        self.worker = CryptoWorker(
            "encrypt" if encrypting else "decrypt",
            source,
            destination,
            password,
        )
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.finished.connect(self.operation_finished)
        self.worker.start()

    def operation_finished(self, success, message):
        self.progress.hide()
        self.action_button.setEnabled(True)
        self.mode_badge.setText(
            "ENCRYPT" if self.mode_combo.currentIndex() == 0 else "DECRYPT"
        )

        if success:
            self.statusBar().showMessage("Operation completed")
            self.result_info.setText(message.replace("\n", "  •  "))

            # Display decrypted result; encrypted vault itself cannot be previewed.
            if self.mode_combo.currentIndex() == 1:
                destination = self.last_destination_from_message(message)
                if destination and os.path.isfile(destination):
                    self.load_result_preview(destination)
            else:
                self.result_view.setText(
                    "Encrypted vault created\n\n"
                    "The encrypted file is intentionally not previewable."
                )
                self.result_view.setStyleSheet(
                    "background:#f7f8fb;border:1px dashed #cbd3df;"
                    "border-radius:9px;color:#687386;font-size:14px;"
                )

            QMessageBox.information(self, "Success", message)
        else:
            self.statusBar().showMessage("Operation failed")
            QMessageBox.critical(
                self,
                "Encryption / Decryption failed",
                message + "\n\n"
                "For decryption, a wrong password or modified/corrupt vault "
                "will produce an authentication failure."
            )

        self.worker = None

    @staticmethod
    def last_destination_from_message(message):
        marker = "Saved to: "
        if marker in message:
            return message.split(marker, 1)[1].strip()
        return None

    def load_result_preview(self, path):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            self.result_view.clear_image()
            self.result_info.setText("Decryption succeeded, but the image could not be previewed.")
            return

        pixmap = QPixmap.fromImage(image)
        self.result_view.set_pixmap(pixmap)
        self.result_info.setText(
            f"{Path(path).name}  •  {image.width()} × {image.height()} px  •  "
            f"{human_size(os.path.getsize(path))}"
        )

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(1000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")

    if AESGCM is None:
        QMessageBox.critical(
            None,
            "Missing dependency",
            "JASS Image Vault Pro requires the 'cryptography' package.\n\n"
            "Install it with:\n"
            "python3 -m pip install cryptography"
        )
        return

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
