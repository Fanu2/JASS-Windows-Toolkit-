#!/usr/bin/env python3
"""
JASS Healthspan Explorer v1.0
Offline PySide6 explorer for the frozen JASS Healthspan Research 2011-2014 dataset.

Reads the v1.2 CSV/Parquet dataset without modifying it.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QObject, QThread, Signal, Slot
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QSplitter, QStatusBar, QTableView, QTabWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
)

try:
    from PySide6.QtCharts import (
        QChart, QChartView, QLineSeries, QBarSeries, QBarSet,
        QValueAxis, QBarCategoryAxis
    )
    CHARTS_AVAILABLE = True
except Exception:
    CHARTS_AVAILABLE = False


APP_NAME = "JASS Healthspan Explorer"
VERSION = "1.0"
DEFAULT_DATASET = (
    Path.home() / "Projects" / "JASS_Healthspan_Research"
    / "JASS_Healthspan_Research_2011_2014"
    / "processed" / "JASS_Healthspan_Research_2011_2014_v1.2.parquet"
)


def fmt_num(x, digits=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    try:
        return f"{float(x):,.{digits}f}"
    except Exception:
        return str(x)


def fmt_pct(x):
    return "—" if x is None else f"{x:.1f}%"


class DataFrameModel(QAbstractTableModel):
    def __init__(self, df=None, parent=None):
        super().__init__(parent)
        self.df = df if df is not None else pd.DataFrame()

    def set_df(self, df):
        self.beginResetModel()
        self.df = df
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.df)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self.df.iat[index.row(), index.column()]
        if role == Qt.DisplayRole:
            if pd.isna(value):
                return "—"
            if isinstance(value, (float, np.floating)):
                return f"{value:.4g}"
            return str(value)
        if role == Qt.TextAlignmentRole:
            return Qt.AlignLeft | Qt.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self.df.columns[section])
        return str(section + 1)


class LoadWorker(QObject):
    finished = Signal(object, str)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, path):
        super().__init__()
        self.path = Path(path)

    @Slot()
    def run(self):
        try:
            self.progress.emit(f"Loading {self.path.name} …")
            if self.path.suffix.lower() == ".parquet":
                df = pd.read_parquet(self.path)
            else:
                df = pd.read_csv(self.path, low_memory=False)
            self.finished.emit(df, str(self.path))
        except Exception as exc:
            self.error.emit(str(exc))


class ChartDialog(QDialog):
    def __init__(self, title, x_title, y_title, points, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 560)
        layout = QVBoxLayout(self)

        if not CHARTS_AVAILABLE:
            layout.addWidget(QLabel(
                "QtCharts is not available in this PySide6 installation.\n"
                "The numerical analysis remains available."
            ))
            return

        chart = QChart()
        chart.setTitle(title)
        chart.legend().setVisible(False)

        series = QLineSeries()
        for x, y in points:
            series.append(float(x), float(y))
        chart.addSeries(series)

        axis_x = QValueAxis()
        axis_x.setTitleText(x_title)
        axis_y = QValueAxis()
        axis_y.setTitleText(y_title)
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

        view = QChartView(chart)
        view.setRenderHint(view.renderHints())
        layout.addWidget(view)


class Explorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1500, 900)
        self.df = pd.DataFrame()
        self.filtered = pd.DataFrame()
        self.current_path = None
        self.thread = None
        self.worker = None

        self.setStatusBar(QStatusBar())
        self._build_menu()
        self._build_ui()

        if DEFAULT_DATASET.exists():
            self.path_edit.setText(str(DEFAULT_DATASET))
            self.load_dataset(DEFAULT_DATASET)

    def _build_menu(self):
        menu = self.menuBar().addMenu("&File")
        open_action = QAction("&Open Dataset…", self)
        open_action.triggered.connect(self.choose_dataset)
        menu.addAction(open_action)

        reload_action = QAction("&Reload", self)
        reload_action.triggered.connect(self.reload)
        menu.addAction(reload_action)

        menu.addSeparator()
        quit_action = QAction("E&xit", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("&About", self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Frozen JASS Healthspan dataset (.parquet or .csv)")
        browse = QPushButton("Open…")
        browse.clicked.connect(self.choose_dataset)
        load = QPushButton("Load")
        load.clicked.connect(lambda: self.load_dataset(Path(self.path_edit.text().strip())))
        top.addWidget(QLabel("Dataset:"))
        top.addWidget(self.path_edit, 1)
        top.addWidget(browse)
        top.addWidget(load)
        root.addLayout(top)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.dashboard_tab = QWidget()
        self._build_dashboard()
        self.tabs.addTab(self.dashboard_tab, "Dashboard")

        self.analysis_tab = QWidget()
        self._build_analysis()
        self.tabs.addTab(self.analysis_tab, "Analysis")

        self.data_tab = QWidget()
        self._build_data()
        self.tabs.addTab(self.data_tab, "Records")

        self.schema_tab = QWidget()
        self._build_schema()
        self.tabs.addTab(self.schema_tab, "Schema")

        self.quality_tab = QWidget()
        self._build_quality()
        self.tabs.addTab(self.quality_tab, "Quality")

        self.research_tab = QWidget()
        self._build_research()
        self.tabs.addTab(self.research_tab, "Research Notes")

        self.setCentralWidget(central)

    def _card(self, title, value="—"):
        box = QGroupBox(title)
        lay = QVBoxLayout(box)
        lab = QLabel(value)
        lab.setObjectName("metric")
        f = QFont()
        f.setPointSize(18)
        f.setBold(True)
        lab.setFont(f)
        lay.addWidget(lab)
        return box, lab

    def _build_dashboard(self):
        lay = QVBoxLayout(self.dashboard_tab)
        self.metrics = {}
        grid = QHBoxLayout()
        for key, title in [
            ("rows", "Participants"),
            ("columns", "Variables"),
            ("age", "Age range"),
            ("grip", "Grip records"),
            ("bmi", "BMI records"),
            ("activity", "Activity records"),
        ]:
            box, lab = self._card(title)
            self.metrics[key] = lab
            grid.addWidget(box)
        lay.addLayout(grid)

        self.dashboard_text = QTextEdit()
        self.dashboard_text.setReadOnly(True)
        lay.addWidget(self.dashboard_text)

    def _build_analysis(self):
        lay = QVBoxLayout(self.analysis_tab)
        controls = QHBoxLayout()

        self.metric_combo = QComboBox()
        self.metric_combo.addItems([
            "Grip strength",
            "BMI",
            "Physical activity",
            "Blood pressure",
            "Sleep",
            "Metabolic markers",
        ])
        run = QPushButton("Analyze")
        run.clicked.connect(self.run_analysis)
        controls.addWidget(QLabel("Research view:"))
        controls.addWidget(self.metric_combo)
        controls.addWidget(run)
        controls.addStretch()
        lay.addLayout(controls)

        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        lay.addWidget(self.analysis_text)

        self.chart_btn = QPushButton("Show Age Trend Chart")
        self.chart_btn.clicked.connect(self.show_age_chart)
        lay.addWidget(self.chart_btn)

    def _build_data(self):
        lay = QVBoxLayout(self.data_tab)
        controls = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search records…")
        self.search_edit.textChanged.connect(self.filter_records)
        self.age_min = QSpinBox()
        self.age_min.setRange(0, 120)
        self.age_min.setValue(0)
        self.age_max = QSpinBox()
        self.age_max.setRange(0, 120)
        self.age_max.setValue(120)
        apply_btn = QPushButton("Apply filters")
        apply_btn.clicked.connect(self.filter_records)
        controls.addWidget(QLabel("Search:"))
        controls.addWidget(self.search_edit, 1)
        controls.addWidget(QLabel("Age:"))
        controls.addWidget(self.age_min)
        controls.addWidget(QLabel("to"))
        controls.addWidget(self.age_max)
        controls.addWidget(apply_btn)
        lay.addLayout(controls)

        self.data_model = DataFrameModel()
        self.data_table = QTableView()
        self.data_table.setModel(self.data_model)
        self.data_table.setSortingEnabled(True)
        self.data_table.setAlternatingRowColors(True)
        lay.addWidget(self.data_table)

        export = QPushButton("Export Current View CSV…")
        export.clicked.connect(self.export_current)
        lay.addWidget(export)

    def _build_schema(self):
        lay = QVBoxLayout(self.schema_tab)
        self.schema_tree = QTreeWidget()
        self.schema_tree.setHeaderLabels(["Column", "Type", "Non-null", "Missing %"])
        lay.addWidget(self.schema_tree)

    def _build_quality(self):
        lay = QVBoxLayout(self.quality_tab)
        controls = QHBoxLayout()
        refresh = QPushButton("Run Quality Summary")
        refresh.clicked.connect(self.run_quality)
        controls.addWidget(refresh)
        controls.addStretch()
        lay.addLayout(controls)
        self.quality_text = QTextEdit()
        self.quality_text.setReadOnly(True)
        lay.addWidget(self.quality_text)

    def _build_research(self):
        lay = QVBoxLayout(self.research_tab)
        lay.addWidget(QLabel(
            "Local research notes. These notes are kept in memory for this session "
            "and do not modify the source dataset."
        ))
        self.notes = QTextEdit()
        self.notes.setPlaceholderText(
            "Record hypotheses, observations, subgroup definitions, caveats…"
        )
        lay.addWidget(self.notes)
        save = QPushButton("Save Notes as Markdown…")
        save.clicked.connect(self.save_notes)
        lay.addWidget(save)

    def choose_dataset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Healthspan Dataset", str(Path.home()),
            "Dataset (*.parquet *.csv);;All files (*)"
        )
        if path:
            self.path_edit.setText(path)
            self.load_dataset(Path(path))

    def load_dataset(self, path):
        if not path.exists():
            QMessageBox.warning(self, APP_NAME, f"Dataset not found:\n{path}")
            return
        self.current_path = path
        self.thread = QThread()
        self.worker = LoadWorker(path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.statusBar().showMessage)
        self.worker.finished.connect(self.on_loaded)
        self.worker.error.connect(self.on_load_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_load_error(self, message):
        QMessageBox.critical(self, APP_NAME, f"Could not load dataset:\n{message}")
        self.statusBar().showMessage("Load failed")

    def on_loaded(self, df, path):
        self.df = df
        self.filtered = df.copy()
        self.data_model.set_df(self.filtered.head(5000))
        self.populate_schema()
        self.update_dashboard()
        self.run_quality()
        self.run_analysis()
        self.statusBar().showMessage(
            f"Loaded {len(df):,} records × {len(df.columns)} variables from {path}"
        )

    def reload(self):
        if self.current_path:
            self.load_dataset(self.current_path)

    def populate_schema(self):
        self.schema_tree.clear()
        for col in self.df.columns:
            s = self.df[col]
            missing = float(s.isna().mean() * 100)
            item = QTreeWidgetItem([
                str(col), str(s.dtype), f"{s.notna().sum():,}", f"{missing:.1f}%"
            ])
            self.schema_tree.addTopLevelItem(item)

    def update_dashboard(self):
        self.metrics["rows"].setText(f"{len(self.df):,}")
        self.metrics["columns"].setText(str(len(self.df.columns)))

        if "Age_years" in self.df:
            age = pd.to_numeric(self.df["Age_years"], errors="coerce")
            self.metrics["age"].setText(
                f"{fmt_num(age.min(), 0)}–{fmt_num(age.max(), 0)}"
            )
        if "NHANES_Combined_Grip_kg" in self.df:
            self.metrics["grip"].setText(
                f"{self.df['NHANES_Combined_Grip_kg'].notna().sum():,}"
            )
        if "BMI" in self.df:
            self.metrics["bmi"].setText(f"{self.df['BMI'].notna().sum():,}")
        if "Reported_activity_minutes_per_week" in self.df:
            self.metrics["activity"].setText(
                f"{self.df['Reported_activity_minutes_per_week'].notna().sum():,}"
            )

        cycles = ""
        if "Cycle" in self.df:
            cycles = "\n".join(
                f"• {k}: {v:,}" for k, v in self.df["Cycle"].value_counts().items()
            )
        self.dashboard_text.setPlainText(
            f"Frozen research dataset\n\n"
            f"Source: NHANES 2011–2012 + 2013–2014\n"
            f"File: {self.current_path}\n\n"
            f"Cycles:\n{cycles}\n\n"
            f"This application is an offline population-level research explorer. "
            f"It does not diagnose disease or predict an individual's health outcome."
        )

    def filter_records(self):
        if self.df.empty:
            return
        df = self.df
        if "Age_years" in df:
            age = pd.to_numeric(df["Age_years"], errors="coerce")
            df = df[age.between(self.age_min.value(), self.age_max.value(), inclusive="both")]

        q = self.search_edit.text().strip().lower()
        if q:
            mask = pd.Series(False, index=df.index)
            for col in df.columns:
                try:
                    mask |= df[col].astype(str).str.lower().str.contains(q, regex=False, na=False)
                except Exception:
                    pass
            df = df[mask]

        self.filtered = df
        self.data_model.set_df(df.head(5000))
        self.statusBar().showMessage(
            f"Showing {min(len(df), 5000):,} of {len(df):,} matching records"
        )

    def run_analysis(self):
        if self.df.empty:
            return
        choice = self.metric_combo.currentText()
        df = self.df
        lines = [f"{choice}", "=" * len(choice), ""]

        if choice == "Grip strength":
            col = "NHANES_Combined_Grip_kg"
            if col in df:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                lines += [
                    f"Available records: {len(s):,}",
                    f"Mean: {fmt_num(s.mean())} kg",
                    f"Median: {fmt_num(s.median())} kg",
                    f"SD: {fmt_num(s.std())} kg",
                    f"Minimum: {fmt_num(s.min())} kg",
                    f"Maximum: {fmt_num(s.max())} kg",
                ]
                self._age_group_summary(lines, df, col, "Grip strength", "kg")
        elif choice == "BMI":
            col = "BMI"
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            lines += [
                f"Available records: {len(s):,}",
                f"Mean: {fmt_num(s.mean())}",
                f"Median: {fmt_num(s.median())}",
                f"SD: {fmt_num(s.std())}",
                f"Minimum: {fmt_num(s.min())}",
                f"Maximum: {fmt_num(s.max())}",
            ]
            self._age_group_summary(lines, df, col, "BMI", "")
        elif choice == "Physical activity":
            col = "Reported_activity_minutes_per_week"
            if col in df:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                lines += [
                    f"Available records: {len(s):,}",
                    f"Mean reported weekly activity: {fmt_num(s.mean())} min",
                    f"Median: {fmt_num(s.median())} min",
                    f"Maximum: {fmt_num(s.max())} min",
                    f"Extreme-activity flags: "
                    f"{int(df.get('Flag_Activity_extreme', pd.Series(dtype=bool)).fillna(False).sum()):,}",
                ]
                self._age_group_summary(lines, df, col, "Activity", "min/week")
        elif choice == "Blood pressure":
            for col in ["SBP_mean_available", "DBP_mean_available", "Pulse"]:
                if col in df:
                    s = pd.to_numeric(df[col], errors="coerce").dropna()
                    lines.append(
                        f"{col}: n={len(s):,}, mean={fmt_num(s.mean())}, "
                        f"median={fmt_num(s.median())}, range={fmt_num(s.min())}–{fmt_num(s.max())}"
                    )
        elif choice == "Sleep":
            col = "Sleep_hours"
            if col in df:
                s = pd.to_numeric(df[col], errors="coerce")
                normal = s[~s.isin([77, 99])].dropna()
                lines += [
                    f"Available records: {len(normal):,}",
                    f"Mean reported sleep: {fmt_num(normal.mean())} hours",
                    f"Median: {fmt_num(normal.median())} hours",
                    f"Range: {fmt_num(normal.min())}–{fmt_num(normal.max())} hours",
                    f"Special-code flags: {int(df.get('Flag_Sleep_hours_special', pd.Series(dtype=bool)).fillna(False).sum()):,}",
                ]
        elif choice == "Metabolic markers":
            for col in [
                "Total_cholesterol_mg_dL", "HDL_mg_dL",
                "Triglycerides_mg_dL", "HbA1c_percent",
                "Fasting_glucose_mg_dL", "Fasting_insulin_uU_mL"
            ]:
                if col in df:
                    s = pd.to_numeric(df[col], errors="coerce").dropna()
                    lines.append(
                        f"{col}: n={len(s):,}, mean={fmt_num(s.mean())}, "
                        f"median={fmt_num(s.median())}, range={fmt_num(s.min())}–{fmt_num(s.max())}"
                    )

        lines += [
            "",
            "Interpretation note:",
            "These are descriptive population-level summaries of the selected "
            "NHANES sample. They are not individual medical assessments."
        ]
        self.analysis_text.setPlainText("\n".join(lines))

    def _age_group_summary(self, lines, df, col, label, unit):
        if "Age_years" not in df:
            return
        work = df[["Age_years", col]].copy()
        work["Age"] = pd.to_numeric(work["Age_years"], errors="coerce")
        work["Value"] = pd.to_numeric(work[col], errors="coerce")
        work = work.dropna(subset=["Age", "Value"])
        bins = [-1, 17, 29, 39, 49, 59, 69, 79, 120]
        labels = ["0–17", "18–29", "30–39", "40–49", "50–59", "60–69", "70–79", "80+"]
        work["Age group"] = pd.cut(work["Age"], bins=bins, labels=labels)
        lines.append("\nAge-group means:")
        for group, part in work.groupby("Age group", observed=True):
            lines.append(
                f"  {group}: n={len(part):,}, mean={fmt_num(part['Value'].mean())}"
                + (f" {unit}" if unit else "")
            )

    def show_age_chart(self):
        if self.df.empty or not CHARTS_AVAILABLE:
            QMessageBox.information(
                self, APP_NAME,
                "QtCharts is unavailable or the dataset is not loaded."
            )
            return

        choice = self.metric_combo.currentText()
        mapping = {
            "Grip strength": "NHANES_Combined_Grip_kg",
            "BMI": "BMI",
            "Physical activity": "Reported_activity_minutes_per_week",
        }
        col = mapping.get(choice)
        if not col or col not in self.df:
            QMessageBox.information(self, APP_NAME, "No age-trend metric is available for this view.")
            return

        work = self.df[["Age_years", col]].copy()
        work["Age"] = pd.to_numeric(work["Age_years"], errors="coerce")
        work["Value"] = pd.to_numeric(work[col], errors="coerce")
        work = work.dropna()
        work["Age"] = work["Age"].round().astype(int)
        grouped = work.groupby("Age")["Value"].mean()
        points = [(age, value) for age, value in grouped.items()]
        ChartDialog(f"{choice} by Age", "Age (years)", choice, points, self).exec()

    def run_quality(self):
        if self.df.empty:
            self.quality_text.setPlainText("Load the frozen dataset first.")
            return
        lines = ["DATASET QUALITY SUMMARY", "========================", ""]
        lines.append(f"Rows: {len(self.df):,}")
        lines.append(f"Columns: {len(self.df.columns):,}")
        lines.append(f"Duplicate SEQN: {self.df['SEQN'].duplicated().sum() if 'SEQN' in self.df else '—'}")

        for flag in [c for c in self.df.columns if c.startswith("Flag_")]:
            lines.append(f"{flag}: {int(self.df[flag].fillna(False).sum()):,}")

        if "Grip_Official_vs_Derived_Diff_kg" in self.df:
            d = pd.to_numeric(
                self.df["Grip_Official_vs_Derived_Diff_kg"], errors="coerce"
            ).dropna()
            lines += [
                "",
                f"Grip comparison records: {len(d):,}",
                f"Non-zero grip differences: {(d > 0).sum():,}",
                f"Maximum grip difference: {fmt_num(d.max())} kg" if len(d) else "No grip comparisons",
            ]

        lines += [
            "",
            "Missingness highlights:"
        ]
        for col in [
            "Age_years", "BMI", "NHANES_Combined_Grip_kg",
            "Reported_activity_minutes_per_week",
            "Sleep_hours", "SBP_mean_available",
            "Total_cholesterol_mg_dL", "HbA1c_percent",
            "Fasting_glucose_mg_dL"
        ]:
            if col in self.df:
                lines.append(
                    f"  {col}: {self.df[col].isna().mean() * 100:.1f}% missing"
                )

        self.quality_text.setPlainText("\n".join(lines))

    def export_current(self):
        if self.filtered.empty:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Current View", "healthspan_filtered.csv",
            "CSV (*.csv)"
        )
        if path:
            self.filtered.head(5000).to_csv(path, index=False)
            self.statusBar().showMessage(f"Exported {min(len(self.filtered),5000):,} rows")

    def save_notes(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Research Notes", "healthspan_research_notes.md",
            "Markdown (*.md)"
        )
        if path:
            text = "# JASS Healthspan Explorer — Research Notes\n\n" + self.notes.toPlainText()
            Path(path).write_text(text, encoding="utf-8")
            self.statusBar().showMessage(f"Saved notes: {path}")

    def show_about(self):
        QMessageBox.about(
            self, APP_NAME,
            f"<b>{APP_NAME} v{VERSION}</b><br><br>"
            "Offline-first explorer for the frozen JASS Healthspan Research "
            "2011–2014 dataset.<br><br>"
            "Read-only analysis. No cloud, no AI, no modification of the source dataset."
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    w = Explorer()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
