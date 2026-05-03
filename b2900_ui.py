"""
SMU Waveform UI
===============
Standalone PyQt5 app — no B2900 hardware required.

Features
--------
- Start / Stop button to run a simulated waveform loop
- Waveform selector (Ramp, Constant, Sine) with dynamic parameter panels
- Live pyqtgraph plot of voltage vs. time
- CSV export with a custom filename

Install dependencies
--------------------
    pip install PyQt5 pyqtgraph numpy
"""

import sys
import csv
import time
import numpy as np

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QGroupBox, QStackedWidget, QSizePolicy,
    QMessageBox, QFrame,
)
import pyqtgraph as pg


# ── Colour palette ─────────────────────────────────────────────────────────────

DARK_BG      = "#0d1117"
PANEL_BG     = "#161b22"
BORDER       = "#30363d"
ACCENT       = "#58a6ff"
ACCENT_HOT   = "#f78166"
TEXT_PRI     = "#e6edf3"
TEXT_SEC     = "#8b949e"
SUCCESS      = "#3fb950"
WARNING      = "#d29922"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {DARK_BG};
    color: {TEXT_PRI};
    font-family: "Consolas", "Courier New", monospace;
    font-size: 13px;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
    background-color: {PANEL_BG};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    color: {ACCENT};
    font-size: 11px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QLabel {{
    color: {TEXT_PRI};
}}
QLabel#secondary {{
    color: {TEXT_SEC};
    font-size: 11px;
}}
QLineEdit {{
    background-color: {DARK_BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    color: {TEXT_PRI};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox {{
    background-color: {DARK_BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    color: {TEXT_PRI};
    min-width: 140px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    color: {TEXT_PRI};
}}
QPushButton {{
    border-radius: 5px;
    padding: 7px 18px;
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 0.5px;
}}
QPushButton#start {{
    background-color: {SUCCESS};
    color: #0d1117;
    border: none;
}}
QPushButton#start:hover {{
    background-color: #56d364;
}}
QPushButton#stop {{
    background-color: {ACCENT_HOT};
    color: #0d1117;
    border: none;
}}
QPushButton#stop:hover {{
    background-color: #ff9580;
}}
QPushButton#save {{
    background-color: {ACCENT};
    color: #0d1117;
    border: none;
}}
QPushButton#save:hover {{
    background-color: #79c0ff;
}}
QFrame#separator {{
    background-color: {BORDER};
}}
"""


# ── Waveform generators ────────────────────────────────────────────────────────

def make_ramp(v_start, v_mid, v_end, num_points):
    half = max(num_points // 2, 1)
    s1 = np.linspace(v_start, v_mid, half, endpoint=False)
    s2 = np.linspace(v_mid, v_end, half)
    return np.concatenate((s1, s2))


def make_constant(voltage, num_points):
    return np.full(int(num_points), voltage)


def make_sine(amplitude, offset, num_points):
    t = np.linspace(0, 2 * np.pi, int(num_points), endpoint=False)
    return offset + amplitude * np.sin(t)

# def make_sqv(v_base, v_step, sq_amplitude, freq, sample_rate):
#     samples_per_half = max(1, int(sample_rate / (2 * freq)))
#     profile = []
#     step = v_base
#     while abs(step - v_base) <= abs(v_step) * 200:   # max 200 steps
#         profile.extend([step + sq_amplitude]  * samples_per_half)
#         profile.extend([step - sq_amplitude]  * samples_per_half)
#         step += v_step
#         if len(profile) > 10_000:   # safety cap
#             break
#     return np.array(profile)

def make_sqv(v_base, v_step, sq_amplitude, freq, sample_rate, direction="forward"):
    samples_per_half = max(1, int(sample_rate / (2 * freq)))
    
    def _sweep(step_sign):
        profile = []
        step = v_base
        for _ in range(200):                        # max 200 steps
            profile.extend([step + sq_amplitude] * samples_per_half)
            profile.extend([step - sq_amplitude] * samples_per_half)
            step += v_step * step_sign
            if len(profile) > 10_000:
                break
        return np.array(profile)

    if direction == "forward":
        return _sweep(+1)
    elif direction == "reverse":
        return _sweep(-1) + sq_amplitude * freq/2
    else:                                           # dual
        fwd = _sweep(+1)
        rev = _sweep(-1) + sq_amplitude * freq/2
        return np.concatenate([fwd, rev])

# ── Worker thread ──────────────────────────────────────────────────────────────

class WaveformWorker(QThread):
    """Emits one voltage sample at a time so the GUI can update live."""
    new_sample   = pyqtSignal(float, float)   # (time_s, voltage)
    finished_run = pyqtSignal()

    def __init__(self, profile: np.ndarray, sample_rate: float = 10.0):
        super().__init__()
        self._profile     = profile
        self._dt          = 1.0 / sample_rate
        self._running     = True

    def stop(self):
        self._running = False

    def run(self):
        t0 = time.perf_counter()
        for idx, v in enumerate(self._profile):
            if not self._running:
                break
            t = idx * self._dt
            self.new_sample.emit(t, float(v))
            # Sleep remaining time to maintain sample rate
            elapsed = time.perf_counter() - t0 - t
            sleep_s = self._dt - elapsed
            if sleep_s > 0:
                time.sleep(sleep_s)
        self.finished_run.emit()


# ── Parameter panels ───────────────────────────────────────────────────────────

def _make_field(label_text, default, tooltip=""):
    lbl = QLabel(label_text)
    lbl.setObjectName("secondary")
    edit = QLineEdit(str(default))
    if tooltip:
        edit.setToolTip(tooltip)
    return lbl, edit


class RampParamPanel(QWidget):
    def __init__(self):
        super().__init__()
        grid = QGridLayout(self)
        grid.setSpacing(8)

        l0, self.v_start  = _make_field("V start (V)",    5.0)
        l1, self.v_mid    = _make_field("V mid (V)",      2.0)
        l2, self.v_end    = _make_field("V end (V)",      1.0)
        l3, self.n_points = _make_field("Num points",     20)
        l4, self.rate     = _make_field("Sample rate (Hz)", 10.0)
        l5, self.cycles   = _make_field("Cycles", 1)


        for row, (lbl, edit) in enumerate(
            [(l0, self.v_start), (l1, self.v_mid),
             (l2, self.v_end),   (l3, self.n_points), (l4, self.rate), (l5, self.cycles)]
        ):
            grid.addWidget(lbl,  row, 0)
            grid.addWidget(edit, row, 1)

    # def build_profile(self):
    #     return make_ramp(
    #         float(self.v_start.text()),
    #         float(self.v_mid.text()),
    #         float(self.v_end.text()),
    #         int(self.n_points.text()),
    #     ), float(self.rate.text())
    
    def build_profile(self):
        profile = make_ramp(
            float(self.v_start.text()),
            float(self.v_mid.text()),
            float(self.v_end.text()),
            int(self.n_points.text()),
        )
        profile = np.tile(profile, max(int(self.cycles.text()), 1))
        return profile, float(self.rate.text())


class ConstantParamPanel(QWidget):
    def __init__(self):
        super().__init__()
        grid = QGridLayout(self)
        grid.setSpacing(8)

        l0, self.voltage  = _make_field("Voltage (V)",      3.3)
        l1, self.n_points = _make_field("Num points",       30)
        l2, self.rate     = _make_field("Sample rate (Hz)", 10.0)
        l3, self.cycles   = _make_field("Cycles", 1)

        for row, (lbl, edit) in enumerate(
            [(l0, self.voltage), (l1, self.n_points), (l2, self.rate), (l3, self.cycles)]
        ):
            grid.addWidget(lbl,  row, 0)
            grid.addWidget(edit, row, 1)

    def build_profile(self):
        profile = make_constant(float(self.voltage.text()), int(self.n_points.text()))
        profile = np.tile(profile, max(int(self.cycles.text()), 1))
        return profile, float(self.rate.text())


class SineParamPanel(QWidget):
    def __init__(self):
        super().__init__()
        grid = QGridLayout(self)
        grid.setSpacing(8)

        l0, self.amplitude = _make_field("Amplitude (V)",    2.0)
        l1, self.offset    = _make_field("Offset (V)",       0.0)
        l2, self.n_points  = _make_field("Num points",       50)
        l3, self.rate      = _make_field("Sample rate (Hz)", 20.0)
        l4, self.cycles    = _make_field("Cycles", 1)


        for row, (lbl, edit) in enumerate(
            [(l0, self.amplitude), (l1, self.offset),
             (l2, self.n_points),  (l3, self.rate), (l4, self.cycles)]
        ):
            grid.addWidget(lbl,  row, 0)
            grid.addWidget(edit, row, 1)

    # def build_profile(self):
    #     return make_sine(
    #         float(self.amplitude.text()),
    #         float(self.offset.text()),
    #         int(self.n_points.text()),
    #     ), float(self.rate.text())
    
    def build_profile(self):
        profile = make_sine(
            float(self.amplitude.text()),
            float(self.offset.text()),
            int(self.n_points.text()),
        )
        profile = np.tile(profile, max(int(self.cycles.text()), 1))
        return profile, float(self.rate.text())

class SqvParamPanel(QWidget):
    def __init__(self):
        super().__init__()
        grid = QGridLayout(self)
        grid.setSpacing(8)

        l0, self.v_base     = _make_field("Base potential (V)",   0.0)
        l1, self.v_step     = _make_field("Step potential (V)",   0.01)
        l2, self.sq_amp     = _make_field("SW amplitude (V)",     0.05)
        l3, self.freq       = _make_field("SW frequency (Hz)",    25.0)
        l4, self.rate       = _make_field("Sample rate (Hz)",     1000.0)
        l5, self.cycles     = _make_field("Cycles",               1)

        for row, (lbl, edit) in enumerate(
            [(l0, self.v_base), (l1, self.v_step), (l2, self.sq_amp),
             (l3, self.freq),   (l4, self.rate),   (l5, self.cycles)]
        ):
            grid.addWidget(lbl,  row, 0)
            grid.addWidget(edit, row, 1)
            
        lbl_dir = QLabel("Direction")
        lbl_dir.setObjectName("secondary")
        self.cmb_direction = QComboBox()
        self.cmb_direction.addItems(["Forward", "Reverse", "Dual"])
        grid.addWidget(lbl_dir,          6, 0)
        grid.addWidget(self.cmb_direction, 6, 1)

    def build_profile(self):
        direction = self.cmb_direction.currentText().lower()
        profile = make_sqv(
            float(self.v_base.text()),
            float(self.v_step.text()),
            float(self.sq_amp.text()),
            float(self.freq.text()),
            float(self.rate.text()),
            direction=direction,
        )
        profile = np.tile(profile, max(int(self.cycles.text()), 1))
        return profile, float(self.rate.text())

# ── Main window ────────────────────────────────────────────────────────────────

class SMUApp(QMainWindow):

    WAVEFORMS = ["Ramp", "Constant", "Sine", "SWV"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMU Waveform Controller")
        self.setMinimumSize(960, 600)

        self._worker: WaveformWorker | None = None
        self._time_data: list[float] = []
        self._volt_data: list[float] = []

        self._build_ui()
        self.setStyleSheet(STYLESHEET)
        self._update_run_buttons(running=False)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(12)
        root.setContentsMargins(14, 14, 14, 14)

        root.addWidget(self._build_left_panel(), stretch=0)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        root.addWidget(sep)

        root.addWidget(self._build_right_panel(), stretch=1)

    # ── Left panel ─────────────────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(280)
        vbox = QVBoxLayout(panel)
        vbox.setSpacing(12)
        vbox.setContentsMargins(0, 0, 0, 0)

        vbox.addWidget(self._build_control_group())
        vbox.addWidget(self._build_waveform_group())
        vbox.addWidget(self._build_export_group())
        vbox.addStretch()
        return panel

    def _build_control_group(self) -> QGroupBox:
        grp = QGroupBox("Control")
        hbox = QHBoxLayout(grp)
        hbox.setSpacing(8)

        self.btn_start = QPushButton("▶  Start")
        self.btn_start.setObjectName("start")
        self.btn_stop  = QPushButton("■  Stop")
        self.btn_stop.setObjectName("stop")

        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)

        hbox.addWidget(self.btn_start)
        hbox.addWidget(self.btn_stop)
        return grp

    def _build_waveform_group(self) -> QGroupBox:
        grp = QGroupBox("Waveform")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(8)

        # Selector
        row = QHBoxLayout()
        row.addWidget(QLabel("Type"))
        self.cmb_waveform = QComboBox()
        self.cmb_waveform.addItems(self.WAVEFORMS)
        self.cmb_waveform.currentIndexChanged.connect(self._on_waveform_changed)
        row.addWidget(self.cmb_waveform)
        vbox.addLayout(row)

        # Stacked parameter panels
        self.param_stack = QStackedWidget()
        self._panel_ramp     = RampParamPanel()
        self._panel_constant = ConstantParamPanel()
        self._panel_sine     = SineParamPanel()
        self._panel_sqv      = SqvParamPanel()
        self.param_stack.addWidget(self._panel_ramp)      # index 0
        self.param_stack.addWidget(self._panel_constant)  # index 1
        self.param_stack.addWidget(self._panel_sine)      # index 2
        self.param_stack.addWidget(self._panel_sqv)      # index 3
        vbox.addWidget(self.param_stack)

        return grp

    def _build_export_group(self) -> QGroupBox:
        grp = QGroupBox("Export CSV")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(8)

        lbl = QLabel("Filename")
        lbl.setObjectName("secondary")
        self.edit_filename = QLineEdit("waveform_data")
        self.edit_filename.setPlaceholderText("e.g. measurement_01")

        self.btn_save = QPushButton("💾  Save CSV")
        self.btn_save.setObjectName("save")
        self.btn_save.clicked.connect(self._on_save_csv)

        vbox.addWidget(lbl)
        vbox.addWidget(self.edit_filename)
        vbox.addWidget(self.btn_save)
        return grp

    # ── Right panel (plot) ─────────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setSpacing(6)
        vbox.setContentsMargins(0, 0, 0, 0)

        # Status bar
        self.lbl_status = QLabel("Idle")
        self.lbl_status.setObjectName("secondary")
        self.lbl_status.setAlignment(Qt.AlignRight)
        vbox.addWidget(self.lbl_status)

        # pyqtgraph plot
        pg.setConfigOptions(antialias=True, background=DARK_BG, foreground=TEXT_PRI)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left",   "Voltage", units="V",  color=TEXT_SEC)
        self.plot_widget.setLabel("bottom", "Time",    units="s",  color=TEXT_SEC)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.getAxis("left").setPen(pg.mkPen(BORDER))
        self.plot_widget.getAxis("bottom").setPen(pg.mkPen(BORDER))

        # Two curves: static preview + live trace
        self.curve_preview = self.plot_widget.plot(
            pen=pg.mkPen(color=BORDER, width=1, style=Qt.DashLine),
            name="Preview",
        )
        self.curve_live = self.plot_widget.plot(
            pen=pg.mkPen(color=ACCENT, width=2),
            name="Live",
        )

        vbox.addWidget(self.plot_widget, stretch=1)

        # Draw initial preview
        self._refresh_preview()
        return panel

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_waveform_changed(self, index: int):
        self.param_stack.setCurrentIndex(index)
        self._refresh_preview()

    def _refresh_preview(self):
        """Show the waveform shape as a dashed grey preview line."""
        try:
            profile, rate = self._current_panel().build_profile()
            t = np.arange(len(profile)) / rate
            self.curve_preview.setData(t, profile)
        except Exception:
            pass

    def _current_panel(self):
        return self.param_stack.currentWidget()

    def _on_start(self):
        if self._worker and self._worker.isRunning():
            return

        try:
            profile, rate = self._current_panel().build_profile()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return

        # Reset live data
        self._time_data.clear()
        self._volt_data.clear()
        self.curve_live.setData([], [])

        # Update preview with fresh params
        t_prev = np.arange(len(profile)) / rate
        self.curve_preview.setData(t_prev, profile)

        self._worker = WaveformWorker(profile, sample_rate=rate)
        self._worker.new_sample.connect(self._on_new_sample)
        self._worker.finished_run.connect(self._on_run_finished)
        self._worker.start()

        self._update_run_buttons(running=True)
        self._set_status("Running…", ACCENT)

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
            self._worker.wait()
        self._on_run_finished()

    def _on_new_sample(self, t: float, v: float):
        self._time_data.append(t)
        self._volt_data.append(v)
        self.curve_live.setData(self._time_data, self._volt_data)

    def _on_run_finished(self):
        self._update_run_buttons(running=False)
        self._set_status(f"Done — {len(self._time_data)} samples", SUCCESS)

    def _on_save_csv(self):
        if not self._time_data:
            QMessageBox.information(self, "No data", "Run the waveform first.")
            return

        raw_name = self.edit_filename.text().strip() or "waveform_data"
        filename = raw_name if raw_name.endswith(".csv") else raw_name + ".csv"

        try:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["time_s", "voltage_V"])
                writer.writerows(zip(self._time_data, self._volt_data))
            self._set_status(f"Saved → {filename}", WARNING)
            QMessageBox.information(self, "Saved", f"Data written to:\n{filename}")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    # ── Helpers ────────────────────────────────────────────────────────────

    def _update_run_buttons(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.cmb_waveform.setEnabled(not running)

    def _set_status(self, text: str, color: str = TEXT_SEC):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color};")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait()
        super().closeEvent(event)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette baseline (stylesheet overrides most things)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(DARK_BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT_PRI))
    app.setPalette(palette)

    win = SMUApp()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()