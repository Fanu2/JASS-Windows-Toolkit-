#!/usr/bin/env python3
"""
JASS Dataset Explorer v1.1
Read-only local dataset inspection and profiling tool.

Supported:
- CSV / TSV
- JSON / JSONL / NDJSON
- Parquet (optional: pyarrow)

Design:
- local-first
- read-only
- bounded sampling for large files
- background workers for expensive operations
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import statistics
import sys
import traceback
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QStatusBar, QTabWidget,
    QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout, QWidget,
    QHeaderView, QAbstractItemView, QMenu, QTextEdit
)

APP_NAME = "JASS Dataset Explorer"
VERSION = "1.2.0"
MAX_PREVIEW_CELL = 4000
DEFAULT_SAMPLE = 5000
MAX_MEMORY_SAMPLE = 100000
SENSITIVE_NAME_RE = re.compile(r"(?:password|passwd|pwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key|credential|auth|authorization|cookie|session[_-]?id)", re.I)


def human_size(n: int | float) -> str:
    try:
        n = float(n)
    except Exception:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while abs(n) >= 1024 and i < len(units) - 1:
        n /= 1024.0
        i += 1
    return f"{n:,.1f} {units[i]}"


def fmt_num(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:,.4g}"
    try:
        return f"{int(x):,}"
    except Exception:
        return str(x)


def safe_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)
    return str(v)


def detect_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in (".tsv",):
        return "tsv"
    if ext in (".csv",):
        return "csv"
    if ext in (".jsonl", ".ndjson"):
        return "jsonl"
    if ext == ".json":
        return "json"
    if ext == ".parquet":
        return "parquet"
    return "unknown"


def infer_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int) and not isinstance(v, bool):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, (list, tuple)):
        return "array"
    if isinstance(v, dict):
        return "object"
    s = str(v).strip()
    if not s:
        return "empty"
    if re.fullmatch(r"[+-]?\d+", s):
        return "integer"
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", s):
        return "number"
    if re.fullmatch(r"(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}", s):
        return "date-like"
    if re.fullmatch(r"https?://\S+", s, re.I):
        return "url-like"
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s):
        return "email-like"
    return "text"


def merge_types(types: Iterable[str]) -> str:
    vals = {x for x in types if x not in ("null", "empty")}
    if not vals:
        return "empty/null"
    if vals <= {"integer"}:
        return "integer"
    if vals <= {"integer", "number"}:
        return "number"
    if len(vals) == 1:
        return next(iter(vals))
    return "mixed"


class DatasetReader:
    """Streaming/bounded reader abstraction. Never writes to source."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.kind = detect_kind(self.path)
        if self.kind == "unknown":
            raise ValueError("Unsupported dataset format.")
        self.size = os.path.getsize(self.path)

    def metadata(self) -> dict[str, Any]:
        st = os.stat(self.path)
        return {
            "path": self.path,
            "filename": os.path.basename(self.path),
            "format": self.kind.upper(),
            "size": self.size,
            "modified": __import__("datetime").datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds"),
        }

    def _csv_reader(self):
        delimiter = "\t" if self.kind == "tsv" else ","
        f = open(self.path, "r", encoding="utf-8-sig", errors="replace", newline="")
        return f, csv.DictReader(f, delimiter=delimiter)

    def _json_records(self, limit: int | None = None):
        with open(self.path, "r", encoding="utf-8-sig", errors="replace") as f:
            if self.kind == "jsonl":
                count = 0
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        yield obj
                    else:
                        yield {"value": obj}
                    count += 1
                    if limit is not None and count >= limit:
                        break
            else:
                data = json.load(f)
                if isinstance(data, list):
                    for i, obj in enumerate(data):
                        yield obj if isinstance(obj, dict) else {"value": obj}
                        if limit is not None and i + 1 >= limit:
                            break
                elif isinstance(data, dict):
                    # Common dataset shapes: {"data":[...]} / {"records":[...]}
                    seq = None
                    for key in ("data", "records", "rows", "items"):
                        if isinstance(data.get(key), list):
                            seq = data[key]
                            break
                    if seq is not None:
                        for i, obj in enumerate(seq):
                            yield obj if isinstance(obj, dict) else {"value": obj}
                            if limit is not None and i + 1 >= limit:
                                break
                    else:
                        yield data

    def _parquet_available(self):
        try:
            import pyarrow.parquet as pq
            return pq
        except Exception:
            return None

    def sample_and_count(self, limit: int, progress_cb=None):
        """Read line-oriented datasets once: collect a bounded sample and exact row count.

        This avoids the old two-pass behavior where large CSV/JSONL files were sampled
        and then scanned from the beginning again just to count rows.
        """
        if self.kind in ("csv", "tsv"):
            f, rdr = self._csv_reader()
            try:
                fields = rdr.fieldnames or []
                sample = []
                type_evidence = {x: [] for x in fields}
                total = 0
                file_size = max(1, os.path.getsize(self.path))
                for row in rdr:
                    total += 1
                    item = dict(row)
                    if len(sample) < limit:
                        sample.append(item)
                        for k in fields:
                            type_evidence[k].append(infer_scalar(item.get(k)))
                    if progress_cb and total % 5000 == 0:
                        try:
                            pos = f.tell()
                            progress_cb(min(99, int(15 + 60 * pos / file_size)),
                                        f"Reading rows: {total:,}")
                        except Exception:
                            pass
                types = {k: merge_types(v) for k, v in type_evidence.items()}
                return fields, types, sample, total
            finally:
                f.close()

        if self.kind == "jsonl":
            fields = []
            seen = set()
            sample = []
            type_evidence = {}
            total = 0
            file_size = max(1, os.path.getsize(self.path))
            with open(self.path, "r", encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    row = obj if isinstance(obj, dict) else {"value": obj}
                    total += 1
                    for k in row:
                        if k not in seen:
                            seen.add(k)
                            fields.append(k)
                            type_evidence[k] = []
                    if len(sample) < limit:
                        sample.append(row)
                        for k in fields:
                            type_evidence[k].append(infer_scalar(row.get(k)))
                    if progress_cb and total % 5000 == 0:
                        try:
                            pos = f.tell()
                            progress_cb(min(99, int(15 + 60 * pos / file_size)),
                                        f"Reading rows: {total:,}")
                        except Exception:
                            pass
            types = {k: merge_types(v) for k, v in type_evidence.items()}
            return fields, types, sample, total

        return None

    def schema(self) -> tuple[list[str], dict[str, str], int | None]:
        if self.kind in ("csv", "tsv"):
            f, rdr = self._csv_reader()
            try:
                fields = rdr.fieldnames or []
                sample_types = {x: [] for x in fields}
                n = 0
                for row in rdr:
                    n += 1
                    for k in fields:
                        sample_types[k].append(infer_scalar(row.get(k)))
                    if n >= min(DEFAULT_SAMPLE, 5000):
                        break
                return fields, {k: merge_types(v) for k, v in sample_types.items()}, None
            finally:
                f.close()
        if self.kind in ("json", "jsonl"):
            rows = list(self.iter_rows(DEFAULT_SAMPLE))
            fields = []
            seen = set()
            for row in rows:
                for k in row:
                    if k not in seen:
                        seen.add(k)
                        fields.append(k)
            types = {}
            for k in fields:
                types[k] = merge_types(infer_scalar(row.get(k)) for row in rows)
            return fields, types, None
        pq = self._parquet_available()
        if pq is None:
            raise RuntimeError("Parquet support requires pyarrow. Install with: python3 -m pip install pyarrow")
        pf = pq.ParquetFile(self.path)
        schema = pf.schema_arrow
        return list(schema.names), {n: str(schema.field(n).type) for n in schema.names}, pf.metadata.num_rows

    def iter_rows(self, limit: int | None = None):
        if self.kind in ("csv", "tsv"):
            f, rdr = self._csv_reader()
            try:
                for i, row in enumerate(rdr):
                    yield dict(row)
                    if limit is not None and i + 1 >= limit:
                        break
            finally:
                f.close()
            return
        if self.kind in ("json", "jsonl"):
            yield from self._json_records(limit)
            return
        pq = self._parquet_available()
        if pq is None:
            raise RuntimeError("Parquet support requires pyarrow. Install with: python3 -m pip install pyarrow")
        pf = pq.ParquetFile(self.path)
        count = 0
        for batch in pf.iter_batches(batch_size=4096):
            for row in batch.to_pylist():
                yield row
                count += 1
                if limit is not None and count >= limit:
                    return

    def total_rows(self) -> int | None:
        if self.kind in ("csv", "tsv"):
            n = 0
            with open(self.path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
                for _ in f:
                    n += 1
            return max(0, n - 1)
        if self.kind == "jsonl":
            n = 0
            with open(self.path, "r", encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    if line.strip():
                        n += 1
            return n
        if self.kind == "json":
            try:
                data = json.load(open(self.path, "r", encoding="utf-8-sig", errors="replace"))
                if isinstance(data, list):
                    return len(data)
                if isinstance(data, dict):
                    for k in ("data", "records", "rows", "items"):
                        if isinstance(data.get(k), list):
                            return len(data[k])
                    return 1
            except Exception:
                return None
        pq = self._parquet_available()
        if pq:
            return pq.ParquetFile(self.path).metadata.num_rows
        return None


class ScanWorker(QThread):
    progress = Signal(int, str)
    done = Signal(object)
    error = Signal(str)

    def __init__(self, path: str, sample_size: int):
        super().__init__()
        self.path = path
        self.sample_size = sample_size

    def run(self):
        try:
            reader = DatasetReader(self.path)
            self.progress.emit(5, "Reading dataset metadata...")

            # CSV/TSV/JSONL used to be scanned twice: once for the sample and
            # again at 90% to count every row. For large datasets that made the
            # GUI appear frozen. Read these line-oriented formats once instead.
            one_pass = reader.sample_and_count(
                self.sample_size,
                lambda pct, msg: self.progress.emit(pct, msg)
            )
            if one_pass is not None:
                fields, types, sample, total = one_pass
            else:
                fields, types, exact_rows = reader.schema()
                self.progress.emit(15, "Sampling rows...")
                sample = []
                for i, row in enumerate(reader.iter_rows(self.sample_size)):
                    sample.append(row)
                    if i % 250 == 0:
                        self.progress.emit(15 + int(55 * (i + 1) / max(1, self.sample_size)),
                                           f"Sampling {i+1:,} rows...")
                total = exact_rows if exact_rows is not None else reader.total_rows()

            self.progress.emit(75, "Profiling columns...")
            profiles = profile_rows(sample, fields)
            duplicate_stats = duplicate_row_stats(sample, fields)
            self.progress.emit(96, f"Finalizing analysis: {total:,} rows")
            self.progress.emit(100, "Complete")
            self.done.emit({
                "metadata": reader.metadata(),
                "fields": fields,
                "types": types,
                "sample": sample,
                "profiles": profiles,
                "duplicate_stats": duplicate_stats,
                "rows": total,
                "sample_rows": len(sample),
            })
        except Exception:
            self.error.emit(traceback.format_exc())


def is_sensitive_column(name: str) -> bool:
    return bool(SENSITIVE_NAME_RE.search(str(name)))


def mask_value(value: Any, column: str, limit: int = 400) -> str:
    text = safe_text(value)
    if is_sensitive_column(column) and text:
        if len(text) <= 4:
            return "••••"
        return "••••" + text[-2:]
    return text[:limit]


def profile_rows(rows: list[dict], fields: list[str]) -> dict[str, dict]:
    out = {}
    sample_n = max(1, len(rows))
    for col in fields:
        vals = [r.get(col) for r in rows]
        nonnull = [v for v in vals if v is not None]
        texts = [safe_text(v) for v in nonnull]
        numeric = []
        types = []
        for v in nonnull:
            types.append(infer_scalar(v))
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                numeric.append(float(v))
            else:
                sv = safe_text(v).strip()
                try:
                    if sv and re.fullmatch(r"[+-]?(?:\d+\.\d*|\d+|\.\d+)(?:[eE][+-]?\d+)?", sv):
                        numeric.append(float(sv))
                except Exception:
                    pass
        counter = Counter(texts)
        lengths = [len(x) for x in texts]
        distinct = len(counter)
        repeated_surplus = len(texts) - distinct
        nonempty = sum(1 for x in texts if x.strip())
        unique_ratio = distinct / max(1, nonempty) * 100
        missing_ratio = (len(vals) - len(nonnull) + sum(1 for x in texts if not x.strip())) / sample_n * 100
        repeat_ratio = repeated_surplus / max(1, len(texts)) * 100
        type_counts = Counter(types)
        type_evidence = ", ".join(f"{k}={v}" for k, v in type_counts.most_common())
        quality = 100.0
        quality -= min(40.0, missing_ratio * 0.7)
        quality -= min(30.0, repeat_ratio * 0.3)
        if merge_types(types) == "mixed":
            quality -= 15.0
        quality = max(0.0, round(quality, 1))
        out[col] = {
            "nulls": len(vals) - len(nonnull),
            "empty": sum(1 for x in texts if not x.strip()),
            "distinct": distinct,
            "duplicate_rows": repeated_surplus,
            "unique_ratio": unique_ratio,
            "missing_ratio": missing_ratio,
            "repeat_ratio": repeat_ratio,
            "avg_length": statistics.mean(lengths) if lengths else 0,
            "min_length": min(lengths) if lengths else 0,
            "max_length": max(lengths) if lengths else 0,
            "numeric_min": min(numeric) if numeric else None,
            "numeric_max": max(numeric) if numeric else None,
            "numeric_avg": statistics.mean(numeric) if numeric else None,
            "top": counter.most_common(10),
            "type": merge_types(types),
            "type_evidence": type_evidence,
            "quality": quality,
            "sensitive": is_sensitive_column(col),
        }
    return out


def duplicate_row_stats(rows: list[dict], fields: list[str]) -> dict[str, Any]:
    counts = Counter()
    for row in rows:
        key = tuple(safe_text(row.get(f)) for f in fields)
        counts[key] += 1
    groups = sum(1 for n in counts.values() if n > 1)
    repeated = sum(n - 1 for n in counts.values() if n > 1)
    return {
        "unique_rows": len(counts),
        "duplicate_groups": groups,
        "duplicate_surplus": repeated,
        "duplicate_pct": repeated / max(1, len(rows)) * 100,
    }



class CopyableTableWidget(QTableWidget):
    """QTableWidget with spreadsheet-like Ctrl+C and context-menu copying."""
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_selection(self):
        ranges = self.selectedRanges()
        if not ranges:
            item = self.currentItem()
            if not item:
                return
            QApplication.clipboard().setText(item.text())
            return

        chunks = []
        for rg in ranges:
            for r in range(rg.topRow(), rg.bottomRow() + 1):
                cells = []
                for c in range(rg.leftColumn(), rg.rightColumn() + 1):
                    item = self.item(r, c)
                    cells.append(item.text() if item else "")
                chunks.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(chunks))

    def copy_all(self):
        rows = []
        for r in range(self.rowCount()):
            if self.isRowHidden(r):
                continue
            rows.append("\t".join(
                self.item(r, c).text() if self.item(r, c) else ""
                for c in range(self.columnCount())
            ))
        QApplication.clipboard().setText("\n".join(rows))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1500, 900)
        self.reader = None
        self.result = None
        self.worker = None
        self.rows = []
        self.fields = []
        self._build()

    def _build(self):
        self.setStatusBar(QStatusBar())
        bar = QToolBar("Main")
        bar.setMovable(False)
        self.addToolBar(bar)

        act_open = QAction("Open Dataset", self)
        act_open.triggered.connect(self.open_dataset)
        bar.addAction(act_open)

        act_reload = QAction("Reload", self)
        act_reload.triggered.connect(self.reload_dataset)
        bar.addAction(act_reload)

        act_export = QAction("Export Report", self)
        act_export.triggered.connect(self.export_report)
        bar.addAction(act_export)

        bar.addSeparator()
        bar.addWidget(QLabel(" Sample: "))
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(100, MAX_MEMORY_SAMPLE)
        self.sample_spin.setSingleStep(1000)
        self.sample_spin.setValue(DEFAULT_SAMPLE)
        bar.addWidget(self.sample_spin)

        self.tabs = QTabWidget()
        self.dashboard_tab = QWidget()
        self.preview_tab = QWidget()
        self.schema_tab = QWidget()
        self.profile_tab = QWidget()
        self.search_tab = QWidget()
        self.quality_tab = QWidget()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.preview_tab, "Data Preview")
        self.tabs.addTab(self.schema_tab, "Schema & Types")
        self.tabs.addTab(self.profile_tab, "Column Profiles")
        self.tabs.addTab(self.search_tab, "Search")
        self.tabs.addTab(self.quality_tab, "Quality")
        self.setCentralWidget(self.tabs)

        self._dashboard_ui()
        self._preview_ui()
        self._schema_ui()
        self._profile_ui()
        self._search_ui()
        self._quality_ui()

        self.statusBar().showMessage("Open a CSV, TSV, JSON, JSONL or Parquet dataset.")

    def _dashboard_ui(self):
        lay = QVBoxLayout(self.dashboard_tab)
        title = QLabel("JASS Dataset Explorer")
        title.setFont(QFont("Sans", 20, QFont.Weight.Bold))
        lay.addWidget(title)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        lay.addWidget(self.summary)
        hint = QLabel("Read-only • local-first • bounded analysis • large-dataset aware")
        lay.addWidget(hint)

    def _preview_ui(self):
        lay = QVBoxLayout(self.preview_tab)

        top = QHBoxLayout()
        top.addWidget(QLabel("Rows"))
        self.preview_rows = QSpinBox()
        self.preview_rows.setRange(10, 5000)
        self.preview_rows.setValue(100)
        self.preview_rows.valueChanged.connect(self.refresh_preview_limit)
        top.addWidget(self.preview_rows)

        self.preview_column_filter = QComboBox()
        self.preview_column_filter.addItem("(all columns)")
        self.preview_column_filter.currentIndexChanged.connect(self.filter_preview)
        top.addWidget(self.preview_column_filter)

        self.preview_filter = QLineEdit()
        self.preview_filter.setPlaceholderText("Filter displayed rows...")
        self.preview_filter.textChanged.connect(self.filter_preview)
        top.addWidget(self.preview_filter, 1)
        lay.addLayout(top)

        tools = QHBoxLayout()
        for label, slot in [
            ("Auto-fit Columns", self.preview_autofit),
            ("Show All Columns", self.preview_show_all_columns),
            ("Copy Cell", self.copy_selected_cell),
            ("Copy Row", self.copy_selected_row),
            ("Row Details", self.show_selected_row_details),
            ("Unicode Info", self.show_selected_unicode_info),
            ("Export Displayed Rows", self.export_displayed_rows),
        ]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            tools.addWidget(b)
        tools.addStretch()
        lay.addLayout(tools)

        self.preview = QTableWidget()
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.preview.setAlternatingRowColors(True)
        self.preview.setSortingEnabled(True)
        self.preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.preview.customContextMenuRequested.connect(self.preview_context_menu)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.preview.verticalHeader().setDefaultSectionSize(26)
        self.preview.itemDoubleClicked.connect(self.show_selected_row_details)
        lay.addWidget(self.preview)

        self.preview_info = QLabel("Preview is bounded to the current analysis sample.")
        lay.addWidget(self.preview_info)

    def _schema_ui(self):
        lay = QVBoxLayout(self.schema_tab)
        self.schema = QTableWidget(0, 4)
        self.schema.setHorizontalHeaderLabels(["Column", "Detected Type", "Nulls in Sample", "Notes"])
        self.schema.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.schema.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.schema)

    def _profile_ui(self):
        lay = QVBoxLayout(self.profile_tab)
        self.profile_table = QTableWidget(0, 13)
        self.profile_table.setHorizontalHeaderLabels([
            "Column", "Type", "Nulls", "Empty", "Distinct", "Unique %",
            "Repeated %", "Quality", "Avg Len", "Min Len", "Max Len", "Numeric Range", "Sensitive"
        ])
        self.profile_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.profile_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.profile_table.cellDoubleClicked.connect(self.show_column_profile)
        lay.addWidget(self.profile_table)

    def _search_ui(self):
        lay = QVBoxLayout(self.search_tab)
        top = QHBoxLayout()
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText("Search text across sampled rows...")
        top.addWidget(self.search_text, 1)
        self.search_column = QComboBox()
        top.addWidget(self.search_column)
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.run_search)
        top.addWidget(self.search_btn)
        lay.addLayout(top)
        self.search_info = QLabel("Search operates on the bounded sample shown by the current analysis.")
        lay.addWidget(self.search_info)

        search_tools = QHBoxLayout()
        self.copy_search_selection_btn = QPushButton("Copy Selected")
        self.copy_search_selection_btn.clicked.connect(self.copy_search_selection)
        search_tools.addWidget(self.copy_search_selection_btn)

        self.copy_search_all_btn = QPushButton("Copy All Results")
        self.copy_search_all_btn.clicked.connect(self.copy_search_all)
        search_tools.addWidget(self.copy_search_all_btn)

        search_tools.addWidget(QLabel("Tip: select cells/rows and press Ctrl+C"))
        search_tools.addStretch()
        lay.addLayout(search_tools)

        self.search_results = CopyableTableWidget()
        self.search_results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.search_results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.search_results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.search_results.setAlternatingRowColors(True)
        self.search_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search_results.customContextMenuRequested.connect(self.search_context_menu)
        self.search_results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        lay.addWidget(self.search_results)

    def _quality_ui(self):
        lay = QVBoxLayout(self.quality_tab)
        controls = QHBoxLayout()
        self.quality_mode = QComboBox()
        self.quality_mode.addItems([
            "Quality overview",
            "Highly duplicated values",
            "Very long values",
            "URL / email candidates",
            "Empty / missing values",
            "Mixed-type columns",
            "Sensitive-column candidates",
            "Duplicate rows"
        ])
        controls.addWidget(self.quality_mode)
        self.quality_limit = QSpinBox()
        self.quality_limit.setRange(10, 500)
        self.quality_limit.setValue(50)
        controls.addWidget(self.quality_limit)
        b = QPushButton("Run Quality Check")
        b.clicked.connect(self.run_quality)
        controls.addWidget(b)
        controls.addStretch()
        lay.addLayout(controls)
        self.quality_text = QPlainTextEdit()
        self.quality_text.setReadOnly(True)
        lay.addWidget(self.quality_text)

    def open_dataset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Dataset", str(Path.home()),
            "Datasets (*.csv *.tsv *.json *.jsonl *.ndjson *.parquet);;All Files (*)"
        )
        if path:
            self.load_dataset(path)

    def reload_dataset(self):
        if self.reader:
            self.load_dataset(self.reader.path)

    def load_dataset(self, path: str):
        try:
            kind = detect_kind(path)
            if kind == "unknown":
                raise ValueError("Unsupported format.")
            self.reader = DatasetReader(path)
        except Exception as e:
            QMessageBox.critical(self, "Open Dataset", str(e))
            return

        self.summary.setPlainText("Analyzing dataset...")
        self.worker = ScanWorker(path, self.sample_spin.value())
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_done)
        self.worker.error.connect(self.on_error)
        self.statusBar().showMessage("Analyzing...")
        self.worker.start()

    def on_progress(self, pct, msg):
        self.statusBar().showMessage(f"{msg}  ({pct}%)")

    def on_done(self, result):
        self.result = result
        self.rows = result["sample"]
        self.fields = result["fields"]
        self.populate_all()
        self.statusBar().showMessage("Dataset loaded and analyzed.")

    def on_error(self, msg):
        self.statusBar().showMessage("Analysis failed.")
        QMessageBox.critical(self, "Dataset Analysis Error", msg)

    def populate_all(self):
        r = self.result
        md = r["metadata"]
        lines = [
            f"Dataset: {md['filename']}",
            f"Path: {md['path']}",
            f"Format: {md['format']}",
            f"Size: {human_size(md['size'])}",
            f"Modified: {md['modified']}",
            "",
            f"Rows: {fmt_num(r['rows']) if r['rows'] is not None else 'unknown'}",
            f"Sample rows: {fmt_num(r['sample_rows'])}",
            f"Columns: {len(r['fields'])}",
            f"Unique sampled rows: {fmt_num(r['duplicate_stats']['unique_rows'])}",
            f"Duplicate row groups in sample: {fmt_num(r['duplicate_stats']['duplicate_groups'])}",
            f"Duplicate-row surplus: {fmt_num(r['duplicate_stats']['duplicate_surplus'])} ({r['duplicate_stats']['duplicate_pct']:.2f}%)",
            f"Sensitive-column candidates: {sum(1 for f in r['fields'] if r['profiles'][f]['sensitive'])}",
            "",
            "Detected columns:",
        ]
        for f in r["fields"]:
            lines.append(f"  • {f} — {r['types'].get(f, 'unknown')}")
        lines += [
            "",
            "READ-ONLY MODE",
            "The source dataset is not modified by this application.",
        ]
        self.summary.setPlainText("\n".join(lines))

        self.populate_preview(self.rows[:self.preview_rows.value()])
        self.populate_schema()
        self.populate_profiles()
        self.search_column.clear()
        self.search_column.addItem("(all columns)")
        self.search_column.addItems(self.fields)
        self.search_results.clear()
        self.search_results.setRowCount(0)
        self.search_results.setColumnCount(0)
        self.quality_text.setPlainText("Choose a quality check and click Run Quality Check.")

    def populate_preview(self, rows):
        self.preview_rows_data = list(rows)
        self.preview.setSortingEnabled(False)
        self.preview.setRowCount(0)
        self.preview.setColumnCount(len(self.fields))
        self.preview.setHorizontalHeaderLabels(self.fields)
        self.preview_column_filter.blockSignals(True)
        self.preview_column_filter.clear()
        self.preview_column_filter.addItem("(all columns)")
        self.preview_column_filter.addItems(self.fields)
        self.preview_column_filter.blockSignals(False)

        for idx, row in enumerate(self.preview_rows_data, 1):
            rr = self.preview.rowCount()
            self.preview.insertRow(rr)
            vh = QTableWidgetItem(str(idx))
            vh.setData(Qt.ItemDataRole.UserRole, idx - 1)
            self.preview.setVerticalHeaderItem(rr, vh)
            for c, f in enumerate(self.fields):
                item = QTableWidgetItem(mask_value(row.get(f), f, MAX_PREVIEW_CELL))
                self.preview.setItem(rr, c, item)

        self.preview.setSortingEnabled(True)
        self.preview_info.setText(
            f"Showing {len(self.preview_rows_data):,} sampled rows • "
            f"double-click a row for full details • right-click for actions."
        )
        self.filter_preview()

    def refresh_preview_limit(self, value):
        if not hasattr(self, "preview_rows_data"):
            return
        self.populate_preview(self.rows[:value])

    def filter_preview(self, *_):
        q = self.preview_filter.text().casefold().strip()
        col = self.preview_column_filter.currentText() if hasattr(self, "preview_column_filter") else "(all columns)"
        for r in range(self.preview.rowCount()):
            columns = range(self.preview.columnCount()) if col == "(all columns)" else [self.fields.index(col)]
            show = True
            if q:
                show = any(
                    q in (self.preview.item(r, c).text().casefold() if self.preview.item(r, c) else "")
                    for c in columns
                )
            self.preview.setRowHidden(r, not show)

    def _selected_preview_cell(self):
        item = self.preview.currentItem()
        if not item:
            return None, None, None
        row = item.row()
        col = item.column()
        if row < 0 or row >= self.preview.rowCount():
            return None, None, None
        header = self.preview.verticalHeaderItem(row)
        source_row = header.data(Qt.ItemDataRole.UserRole) if header else row
        if source_row is None or source_row < 0 or source_row >= len(self.preview_rows_data):
            return None, None, None
        field = self.fields[col]
        return source_row, field, self.preview_rows_data[source_row].get(field)

    def copy_selected_cell(self):
        row, field, value = self._selected_preview_cell()
        if field is None:
            return
        QApplication.clipboard().setText(safe_text(value))
        self.statusBar().showMessage(f"Copied cell: {field}")

    def copy_selected_row(self):
        row = self.preview.currentRow()
        if row < 0 or row >= self.preview.rowCount():
            return
        header = self.preview.verticalHeaderItem(row)
        source_row = header.data(Qt.ItemDataRole.UserRole) if header else row
        if source_row is None or source_row < 0 or source_row >= len(self.preview_rows_data):
            return
        data = [safe_text(self.preview_rows_data[source_row].get(f)) for f in self.fields]
        QApplication.clipboard().setText("\t".join(data))
        self.statusBar().showMessage("Copied selected row as tab-separated text.")

    def show_selected_row_details(self, *_args):
        row = self.preview.currentRow()
        if row < 0 or row >= self.preview.rowCount():
            return
        header = self.preview.verticalHeaderItem(row)
        source_row = header.data(Qt.ItemDataRole.UserRole) if header else row
        if source_row is None or source_row < 0 or source_row >= len(self.preview_rows_data):
            return
        record = self.preview_rows_data[source_row]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Row Details — sample row {source_row + 1}")
        dlg.resize(950, 650)
        lay = QVBoxLayout(dlg)

        table = QTableWidget(len(self.fields), 2)
        table.setHorizontalHeaderLabels(["Column", "Value"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        for r, f in enumerate(self.fields):
            table.setItem(r, 0, QTableWidgetItem(f))
            table.setItem(r, 1, QTableWidgetItem(mask_value(record.get(f), f, 0)))
        lay.addWidget(table)

        note = QLabel(
            "Sensitive-looking columns remain masked. Long text is shown in full here."
        )
        lay.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.exec()

    def show_selected_unicode_info(self):
        row, field, value = self._selected_preview_cell()
        if field is None:
            return
        s = safe_text(value)
        if not s:
            QMessageBox.information(self, "Unicode Information", "The selected value is empty.")
            return

        categories = Counter(unicodedata.category(ch) for ch in s)
        scripts_hint = Counter()
        for ch in s:
            name = unicodedata.name(ch, "")
            if "LATIN" in name:
                scripts_hint["Latin"] += 1
            elif "CYRILLIC" in name:
                scripts_hint["Cyrillic"] += 1
            elif "GREEK" in name:
                scripts_hint["Greek"] += 1
            elif "BENGALI" in name:
                scripts_hint["Bengali"] += 1
            elif "GURMUKHI" in name:
                scripts_hint["Gurmukhi"] += 1
            elif "DEVANAGARI" in name:
                scripts_hint["Devanagari"] += 1
            elif "ARABIC" in name:
                scripts_hint["Arabic"] += 1
            else:
                scripts_hint["Other"] += 1

        sample = s[:120].replace("\n", " ↵ ").replace("\t", " → ")
        lines = [
            "UNICODE INFORMATION",
            "",
            f"Column: {field}",
            f"Characters: {len(s):,}",
            f"Unicode code points: {len(s):,}",
            f"UTF-8 bytes: {len(s.encode('utf-8', errors='replace')):,}",
            f"Unique characters: {len(set(s)):,}",
            f"Whitespace characters: {sum(ch.isspace() for ch in s):,}",
            "",
            "Script/name hints:",
        ]
        lines += [f"  {k}: {v:,}" for k, v in scripts_hint.most_common()]
        lines += ["", "Unicode categories:"]
        lines += [f"  {k}: {v:,}" for k, v in categories.most_common()]
        lines += ["", "Sample:", sample]

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Unicode Information — {field}")
        dlg.resize(700, 600)
        lay = QVBoxLayout(dlg)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText("\n".join(lines))
        lay.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.exec()

    def preview_autofit(self):
        self.preview.resizeColumnsToContents()
        self.preview.resizeRowsToContents()
        self.statusBar().showMessage("Preview columns auto-fitted.")

    def preview_show_all_columns(self):
        for c in range(self.preview.columnCount()):
            self.preview.showColumn(c)
        self.statusBar().showMessage("All preview columns are visible.")

    def preview_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Copy Cell", self.copy_selected_cell)
        menu.addAction("Copy Row", self.copy_selected_row)
        menu.addAction("Row Details", self.show_selected_row_details)
        menu.addAction("Unicode Info", self.show_selected_unicode_info)
        menu.addSeparator()

        hide = menu.addMenu("Hide Column")
        for c, f in enumerate(self.fields):
            act = hide.addAction(f)
            act.triggered.connect(lambda checked=False, col=c: self.preview.hideColumn(col))

        menu.addSeparator()
        menu.addAction("Show All Columns", self.preview_show_all_columns)
        menu.addAction("Auto-fit Columns", self.preview_autofit)
        menu.exec(self.preview.viewport().mapToGlobal(pos))

    def export_displayed_rows(self):
        if not hasattr(self, "preview_rows_data") or not self.preview_rows_data:
            return
        visible_rows = []
        for r in range(self.preview.rowCount()):
            if not self.preview.isRowHidden(r):
                header = self.preview.verticalHeaderItem(r)
                source_row = header.data(Qt.ItemDataRole.UserRole) if header else r
                if source_row is not None and 0 <= source_row < len(self.preview_rows_data):
                    visible_rows.append(self.preview_rows_data[source_row])

        if not visible_rows:
            QMessageBox.information(self, "Export", "There are no visible rows to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Displayed Rows", str(Path.home() / "dataset_preview.csv"),
            "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.fields, extrasaction="ignore")
                writer.writeheader()
                for row in visible_rows:
                    safe_row = {
                        field: ("[MASKED]" if self.result["profiles"][field]["sensitive"] else safe_text(row.get(field)))
                        for field in self.fields
                    }
                    writer.writerow(safe_row)
            self.statusBar().showMessage(
                f"Exported {len(visible_rows):,} displayed rows to {Path(path).name}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def populate_schema(self):
        self.schema.setRowCount(0)
        for f in self.fields:
            rr = self.schema.rowCount()
            self.schema.insertRow(rr)
            p = self.result["profiles"][f]
            vals = [f, self.result["types"].get(f, ""), str(p["nulls"]), ("Sensitive-name candidate; values masked" if p["sensitive"] else "Sample-based type inference") ]
            for c, v in enumerate(vals):
                self.schema.setItem(rr, c, QTableWidgetItem(v))

    def populate_profiles(self):
        self.profile_table.setRowCount(0)
        for f in self.fields:
            p = self.result["profiles"][f]
            rr = self.profile_table.rowCount()
            self.profile_table.insertRow(rr)
            rng = "—"
            if p["numeric_min"] is not None:
                rng = f"{fmt_num(p['numeric_min'])} … {fmt_num(p['numeric_max'])}"
            vals = [
                f, p["type"], fmt_num(p["nulls"]), fmt_num(p["empty"]),
                fmt_num(p["distinct"]), f"{p['unique_ratio']:.1f}%",
                f"{p['repeat_ratio']:.1f}%", f"{p['quality']:.1f}",
                fmt_num(p["avg_length"]), fmt_num(p["min_length"]),
                fmt_num(p["max_length"]), rng, "YES" if p["sensitive"] else ""
            ]
            for c, v in enumerate(vals):
                self.profile_table.setItem(rr, c, QTableWidgetItem(str(v)))

    def show_column_profile(self, row, _col):
        if not self.result or row < 0 or row >= self.profile_table.rowCount():
            return
        item = self.profile_table.item(row, 0)
        if not item:
            return
        f = item.text()
        p = self.result["profiles"].get(f)
        if not p:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Column Profile — {f}")
        dlg.resize(800, 600)
        lay = QVBoxLayout(dlg)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        lines = [
            f"COLUMN PROFILE",
            "",
            f"Column: {f}",
            f"Detected type: {p['type']}",
            f"Sample rows: {self.result['sample_rows']:,}",
            f"NULL values: {p['nulls']:,}",
            f"Empty values: {p['empty']:,}",
            f"Distinct sampled values: {p['distinct']:,}",
            f"Repeated-value surplus: {p['duplicate_rows']:,}",
            f"Unique-value ratio: {p['unique_ratio']:.2f}%",
            f"Repeated-value ratio: {p['repeat_ratio']:.2f}%",
            f"Quality score: {p['quality']:.1f}/100",
            f"Type evidence: {p['type_evidence'] or "none"}",
            f"Sensitive-column candidate: {"YES — values masked in previews" if p['sensitive'] else "No"}",
            f"Average text length: {p['avg_length']:.2f}",
            f"Minimum text length: {p['min_length']:,}",
            f"Maximum text length: {p['max_length']:,}",
        ]
        if p["numeric_min"] is not None:
            lines += [
                "",
                f"Numeric minimum: {p['numeric_min']}",
                f"Numeric maximum: {p['numeric_max']}",
                f"Numeric average: {p['numeric_avg']}",
            ]
        lines += ["", "TOP VALUES"]
        for value, count in p["top"]:
            preview = value.replace("\n", " ")[:250]
            lines.append(f"{count:,} × {preview}")
        text.setPlainText("\n".join(lines))
        lay.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec()

    def copy_search_selection(self):
        self.search_results.copy_selection()
        self.statusBar().showMessage("Copied selected search-result cells.")

    def copy_search_all(self):
        self.search_results.copy_all()
        self.statusBar().showMessage("Copied all visible search results.")

    def search_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Copy Selected", self.copy_search_selection)
        menu.addAction("Copy All Results", self.copy_search_all)
        menu.exec(self.search_results.viewport().mapToGlobal(pos))

    def run_search(self):
        q = self.search_text.text().casefold().strip()
        if not q:
            self.search_results.setRowCount(0)
            return
        col = self.search_column.currentText()
        matches = []
        for row in self.rows:
            vals = self.fields if col == "(all columns)" else [col]
            if any(q in safe_text(row.get(f)).casefold() for f in vals):
                matches.append(row)
                if len(matches) >= 500:
                    break
        self.search_results.setColumnCount(len(self.fields))
        self.search_results.setHorizontalHeaderLabels(self.fields)
        self.search_results.setRowCount(0)
        for source_index, row in enumerate(matches, 1):
            rr = self.search_results.rowCount()
            self.search_results.insertRow(rr)
            self.search_results.setVerticalHeaderItem(rr, QTableWidgetItem(str(source_index)))
            for c, f in enumerate(self.fields):
                self.search_results.setItem(
                    rr, c,
                    QTableWidgetItem(mask_value(row.get(f), f, MAX_PREVIEW_CELL))
                )
        self.search_results.resizeRowsToContents()
        self.search_info.setText(
            f"{len(matches):,} matches in current sample (maximum displayed: 500). "
            "Select text/cells and press Ctrl+C to copy."
        )

    def run_quality(self):
        if not self.result:
            return
        mode = self.quality_mode.currentText()
        limit = self.quality_limit.value()
        p = self.result["profiles"]
        lines = [f"QUALITY CHECK: {mode}", "", f"Dataset: {self.result['metadata']['filename']}", f"Sample: {self.result['sample_rows']:,}", ""]
        if mode == "Quality overview":
            for f in self.fields:
                x = p[f]
                missing_pct = (x["nulls"] + x["empty"]) / max(1, self.result["sample_rows"]) * 100
                dup_pct = x["duplicate_rows"] / max(1, self.result["sample_rows"]) * 100
                lines.append(f"{f}: type={x['type']}; missing={missing_pct:.2f}%; repeated-value surplus={dup_pct:.2f}%; unique={x['unique_ratio']:.2f}%; quality={x['quality']:.1f}; max_len={x['max_length']:,}")
        elif mode == "Highly duplicated values":
            for f in self.fields:
                top = [(v, n) for v, n in p[f]["top"] if n > 1]
                if top:
                    lines.append(f"[{f}]")
                    for v, n in top[:limit]:
                        lines.append(f"  {n:,} × {v[:300]}")
        elif mode == "Very long values":
            vals = []
            for row in self.rows:
                for f in self.fields:
                    s = safe_text(row.get(f))
                    if len(s) >= 1000:
                        vals.append((len(s), f, s))
            vals.sort(reverse=True)
            for n, f, s in vals[:limit]:
                lines.append(f"{n:,} chars | {f} | {s[:500].replace(chr(10),' ')}")
        elif mode == "URL / email candidates":
            url_re = re.compile(r"https?://\S+", re.I)
            email_re = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")
            count = 0
            for i, row in enumerate(self.rows, 1):
                for f in self.fields:
                    s = safe_text(row.get(f))
                    if url_re.search(s) or email_re.search(s):
                        lines.append(f"sample row {i} | {f} | {s[:500]}")
                        count += 1
                        if count >= limit:
                            break
                if count >= limit:
                    break
            lines.insert(4, f"Candidates shown: {count}")
        elif mode == "Empty / missing values":
            for f in self.fields:
                x = p[f]
                if x["nulls"] or x["empty"]:
                    pct = (x["nulls"] + x["empty"]) / max(1, self.result["sample_rows"]) * 100
                    lines.append(f"{f}: {x['nulls']:,} NULL + {x['empty']:,} empty ({pct:.2f}%)")
        elif mode == "Mixed-type columns":
            for f in self.fields:
                if p[f]["type"] == "mixed":
                    lines.append(f"{f}: MIXED — {p[f]['type_evidence'] or 'no type evidence'}")
        elif mode == "Sensitive-column candidates":
            candidates = [f for f in self.fields if p[f]["sensitive"]]
            lines.append(f"Candidates: {len(candidates)}")
            for f in candidates:
                lines.append(f"{f}: values are masked in the UI/report")
        elif mode == "Duplicate rows":
            d = self.result["duplicate_stats"]
            lines += [
                f"Unique sampled rows: {d['unique_rows']:,}",
                f"Duplicate row groups: {d['duplicate_groups']:,}",
                f"Repeated duplicate-row surplus: {d['duplicate_surplus']:,}",
                f"Duplicate-row surplus percentage: {d['duplicate_pct']:.2f}%",
                "Note: this is calculated only within the bounded sample."
            ]
        self.quality_text.setPlainText("\n".join(lines))

    def export_report(self):
        if not self.result:
            QMessageBox.information(self, "Export", "Open and analyze a dataset first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Dataset Report", "dataset_report.txt", "Text (*.txt)")
        if not path:
            return
        r = self.result
        md = r["metadata"]
        lines = [
            f"{APP_NAME} v{VERSION}",
            "=" * 72,
            "",
            f"Dataset: {md['path']}",
            f"Format: {md['format']}",
            f"Size: {human_size(md['size'])}",
            f"Modified: {md['modified']}",
            f"Rows: {r['rows'] if r['rows'] is not None else 'unknown'}",
            f"Sample rows: {r['sample_rows']}",
            f"Columns: {len(r['fields'])}",
            f"Unique sampled rows: {fmt_num(r['duplicate_stats']['unique_rows'])}",
            f"Duplicate row groups in sample: {fmt_num(r['duplicate_stats']['duplicate_groups'])}",
            f"Duplicate-row surplus: {fmt_num(r['duplicate_stats']['duplicate_surplus'])} ({r['duplicate_stats']['duplicate_pct']:.2f}%)",
            f"Sensitive-column candidates: {sum(1 for f in r['fields'] if r['profiles'][f]['sensitive'])}",
            "",
            "COLUMN PROFILES",
            "-" * 72,
        ]
        for f in self.fields:
            p = r["profiles"][f]
            lines += [
                f"{f}",
                f"  Type: {p['type']}",
                f"  Nulls: {p['nulls']}",
                f"  Empty: {p['empty']}",
                f"  Distinct in sample: {p['distinct']}",
                f"  Repeated-value surplus: {p['duplicate_rows']}",
                f"  Unique-value ratio: {p['unique_ratio']:.2f}%",
                f"  Repeated-value ratio: {p['repeat_ratio']:.2f}%",
                f"  Quality score: {p['quality']:.1f}/100",
                f"  Type evidence: {p['type_evidence']}",
                f"  Sensitive candidate: {p['sensitive']}",
                f"  Avg length: {p['avg_length']:.2f}",
                f"  Min length: {p['min_length']}",
                f"  Max length: {p['max_length']}",
                "",
            ]
        lines += [
            "READ-ONLY",
            "The source dataset was not modified.",
        ]
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self.statusBar().showMessage(f"Report saved: {path}")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(1000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
