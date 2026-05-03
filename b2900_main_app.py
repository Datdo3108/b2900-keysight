"""
SMU Combined App
================
Imports `b2900_controller` and `smu_app` and wires them together.

- All UI widgets come from smu_app.SMUApp (unchanged).
- A new "Instrument" panel lets the user enter a VISA resource string
  and connect / disconnect the B2900.
- When connected, Start fires the real hardware via B2900Controller;
  when disconnected it falls back to the simulation worker from smu_app.
- Measured voltage *and* current are both plotted (current on a second
  Y-axis) and saved to CSV.

Place this file in the same directory as b2900_controller.py and smu_app.py.

    python smu_combined.py
"""

import sys
import os
import csv
import time
import numpy as np

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
    QGroupBox, QFrame, QMessageBox,
)
import pyqtgraph as pg

# ── Import our two modules ─────────────────────────────────────────────────────
from b2900_controller import B2900Controller          # hardware layer
from b2900_ui import (                                  # UI building blocks
    DARK_BG, PANEL_BG, BORDER, ACCENT, ACCENT_HOT,
    TEXT_PRI, TEXT_SEC, SUCCESS, WARNING, STYLESHEET,
    WaveformWorker,                                    # simulation fallback
    RampParamPanel, ConstantParamPanel, SineParamPanel, SqvParamPanel, 
)
from PyQt5.QtWidgets import QComboBox, QStackedWidget, QSizePolicy


# ── Hardware worker ────────────────────────────────────────────────────────────

class B2900HardwareWorker(QThread):
    """
    Runs the full B2900 sequence in a background thread and streams
    (time_s, voltage_V, current_A) tuples back to the GUI.
    """
    new_sample   = pyqtSignal(float, float, float)   # t, V, I
    finished_run = pyqtSignal()
    error        = pyqtSignal(str)

    def __init__(
        self,
        controller: B2900Controller,
        profile: np.ndarray,
        sample_rate: float,
        voltage_range: float = 20.0,
        current_nplc: float  = 0.1,
        meas_count: int      = 101,
        meas_timer_ms: float = 1.0,
        trigger_timer_ms: float = 5.0,
    ):
        super().__init__()
        self._smu              = controller
        self._profile          = profile
        self._dt               = 1.0 / sample_rate
        self._voltage_range    = voltage_range
        self._current_nplc     = current_nplc
        self._meas_count       = meas_count
        self._meas_timer_ms    = meas_timer_ms
        self._trigger_timer_ms = trigger_timer_ms

    def run(self):
        try:
            for ch in self._smu.channels:
                ch.configure_voltage_output(
                    voltage_range=self._voltage_range,
                    current_nplc=self._current_nplc,
                )
                ch.configure_voltage_list(
                    self._profile,
                    trigger_timer_ms=self._trigger_timer_ms,
                )
                ch.configure_measurement_trigger(
                    count=self._meas_count,
                    timer_ms=self._meas_timer_ms,
                )
                ch.enable()
                ch.initiate()

                voltage_data = ch.fetch_voltage()
                current_data = ch.fetch_current()

                # Pad shorter array so zip doesn't drop points
                n = max(len(voltage_data), len(current_data))
                voltage_data = np.resize(voltage_data, n)
                current_data = np.resize(current_data, n)

                t0 = time.perf_counter()
                for idx in range(n):
                    t = idx * self._dt
                    # honour timing even though data is already fetched
                    elapsed = time.perf_counter() - t0 - t
                    if self._dt - elapsed > 0:
                        time.sleep(self._dt - elapsed)
                    self.new_sample.emit(t, float(voltage_data[idx]), float(current_data[idx]))

        except Exception as exc:
            self.error.emit(f"{exc.__class__.__name__}: {exc}")

        self.finished_run.emit()


# ── Simulation worker adapter ──────────────────────────────────────────────────

class SimWorkerAdapter(QThread):
    """
    Wraps smu_app.WaveformWorker and re-emits its signal as
    (t, voltage, 0.0) so both hardware and sim paths share one handler.
    """
    new_sample   = pyqtSignal(float, float, float)
    finished_run = pyqtSignal()

    def __init__(self, profile: np.ndarray, sample_rate: float):
        super().__init__()
        self._inner = WaveformWorker(profile, sample_rate)
        self._inner.new_sample.connect(self._relay)
        self._inner.finished_run.connect(self.finished_run)

    def _relay(self, t: float, v: float):
        self.new_sample.emit(t, v, 0.0)

    def stop(self):
        self._inner.stop()

    def run(self):
        self._inner.run()

    def wait(self, *args):
        return self._inner.wait(*args)

    def isRunning(self):
        return self._inner.isRunning()

    def start(self):
        self._inner.start()


# ── Combined main window ───────────────────────────────────────────────────────

class SMUCombinedApp(QMainWindow):

    WAVEFORMS = ["Ramp", "Constant", "Sine", "SWV"]

    DEFAULT_RESOURCE = "USB0::0x0957::0xD018::MY51142876::0::INSTR"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMU Controller — B2900 + UI")
        self.setMinimumSize(1100, 640)

        self._smu: B2900Controller | None = None
        self._worker = None

        self._time_data: list[float] = []
        self._volt_data: list[float] = []
        self._curr_data: list[float] = []

        self._build_ui()
        self.setStyleSheet(STYLESHEET)
        self._update_run_buttons(running=False)
        self._update_connect_buttons(connected=False)

    # ── UI ─────────────────────────────────────────────────────────────────

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
        panel.setFixedWidth(300)
        vbox = QVBoxLayout(panel)
        vbox.setSpacing(12)
        vbox.setContentsMargins(0, 0, 0, 0)

        vbox.addWidget(self._build_instrument_group())
        vbox.addWidget(self._build_control_group())
        vbox.addWidget(self._build_waveform_group())
        vbox.addWidget(self._build_export_group())
        vbox.addStretch()
        return panel

    def _build_instrument_group(self) -> QGroupBox:
        grp = QGroupBox("Instrument")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(8)

        lbl = QLabel("VISA resource")
        lbl.setObjectName("secondary")
        self.edit_resource = QLineEdit(self.DEFAULT_RESOURCE)

        btn_row = QHBoxLayout()
        self.btn_connect    = QPushButton("Connect")
        self.btn_connect.setObjectName("save")          # reuse blue style
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setObjectName("stop")
        self.btn_connect.clicked.connect(self._on_connect)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_disconnect)

        self.lbl_hw_status = QLabel("● Disconnected")
        self.lbl_hw_status.setObjectName("secondary")

        vbox.addWidget(lbl)
        vbox.addWidget(self.edit_resource)
        vbox.addLayout(btn_row)
        vbox.addWidget(self.lbl_hw_status)
        return grp

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

        row = QHBoxLayout()
        row.addWidget(QLabel("Type"))
        self.cmb_waveform = QComboBox()
        self.cmb_waveform.addItems(self.WAVEFORMS)
        self.cmb_waveform.currentIndexChanged.connect(self._on_waveform_changed)
        row.addWidget(self.cmb_waveform)
        vbox.addLayout(row)

        self.param_stack = QStackedWidget()
        self._panel_ramp     = RampParamPanel()
        self._panel_constant = ConstantParamPanel()
        self._panel_sine     = SineParamPanel()
        self._panel_sqv      = SqvParamPanel()
        self.param_stack.addWidget(self._panel_ramp)
        self.param_stack.addWidget(self._panel_constant)
        self.param_stack.addWidget(self._panel_sine)
        self.param_stack.addWidget(self._panel_sqv)
        vbox.addWidget(self.param_stack)

        return grp

    def _build_export_group(self) -> QGroupBox:
        grp = QGroupBox("Export CSV")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(8)

        lbl = QLabel("Filename")
        lbl.setObjectName("secondary")
        self.edit_filename = QLineEdit("measurement")
        self.edit_filename.setPlaceholderText("e.g. run_01")

        self.btn_save = QPushButton("💾  Save CSV")
        self.btn_save.setObjectName("save")
        self.btn_save.clicked.connect(self._on_save_csv)

        vbox.addWidget(lbl)
        vbox.addWidget(self.edit_filename)
        vbox.addWidget(self.btn_save)
        return grp

    # ── Right panel ─────────────────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setSpacing(6)
        vbox.setContentsMargins(0, 0, 0, 0)

        self.lbl_status = QLabel("Idle")
        self.lbl_status.setObjectName("secondary")
        self.lbl_status.setAlignment(Qt.AlignRight)
        vbox.addWidget(self.lbl_status)

        pg.setConfigOptions(antialias=True, background=DARK_BG, foreground=TEXT_PRI)

        # Voltage plot
        self.plot_v = pg.PlotWidget(title="Voltage")
        self.plot_v.setLabel("left",   "Voltage", units="V", color=TEXT_SEC)
        self.plot_v.setLabel("bottom", "Time",    units="s", color=TEXT_SEC)
        self.plot_v.showGrid(x=True, y=True, alpha=0.15)
        self.curve_v_preview = self.plot_v.plot(
            pen=pg.mkPen(color=BORDER, width=1, style=Qt.DashLine), name="Preview"
        )
        self.curve_v_live = self.plot_v.plot(
            pen=pg.mkPen(color=ACCENT, width=2), name="Voltage"
        )

        # Current plot
        self.plot_i = pg.PlotWidget(title="Current")
        self.plot_i.setLabel("left",   "Current", units="A", color=TEXT_SEC)
        self.plot_i.setLabel("bottom", "Time",    units="s", color=TEXT_SEC)
        self.plot_i.showGrid(x=True, y=True, alpha=0.15)
        self.curve_i_live = self.plot_i.plot(
            pen=pg.mkPen(color=ACCENT_HOT, width=2), name="Current"
        )

        # Link X axes so they scroll together
        self.plot_i.setXLink(self.plot_v)

        vbox.addWidget(self.plot_v, stretch=1)
        vbox.addWidget(self.plot_i, stretch=1)

        self._refresh_preview()
        return panel

    # ── Instrument slots ───────────────────────────────────────────────────

    def _on_connect(self):
        resource = self.edit_resource.text().strip()
        if not resource:
            QMessageBox.warning(self, "Missing resource", "Enter a VISA resource string.")
            return
        try:
            self._smu = B2900Controller(resource)
            self._smu.open()
            self._update_connect_buttons(connected=True)
            model = self._smu.model
            ch_n  = self._smu.num_channels
            self.lbl_hw_status.setText(f"● {model}  ({ch_n} ch)")
            self.lbl_hw_status.setStyleSheet(f"color: {SUCCESS};")
            self._set_status(f"Connected — {model}", SUCCESS)
        except Exception as exc:
            self._smu = None
            QMessageBox.critical(self, "Connection failed", str(exc))
            self._set_status("Connection failed", ACCENT_HOT)

    def _on_disconnect(self):
        if self._smu:
            try:
                self._smu.disable_all()
                self._smu.drain_error_queue()
            except Exception:
                pass
            self._smu.close()
            self._smu = None
        self._update_connect_buttons(connected=False)
        self.lbl_hw_status.setText("● Disconnected")
        self.lbl_hw_status.setStyleSheet(f"color: {TEXT_SEC};")
        self._set_status("Disconnected", TEXT_SEC)

    # ── Run slots ──────────────────────────────────────────────────────────

    def _on_start(self):
        if self._worker and self._worker.isRunning():
            return

        try:
            profile, rate = self._current_panel().build_profile()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return

        self._time_data.clear()
        self._volt_data.clear()
        self._curr_data.clear()
        self.curve_v_live.setData([], [])
        self.curve_i_live.setData([], [])

        t_prev = np.arange(len(profile)) / rate
        self.curve_v_preview.setData(t_prev, profile)

        if self._smu is not None:
            # ── Real hardware path ──────────────────────────────────────
            self._worker = B2900HardwareWorker(
                self._smu, profile, rate
            )
            self._worker.error.connect(self._on_worker_error)
            self._set_status("Running on hardware…", ACCENT)
        else:
            # ── Simulation fallback ─────────────────────────────────────
            self._worker = SimWorkerAdapter(profile, rate)
            self._set_status("Simulating (no hardware)…", WARNING)

        self._worker.new_sample.connect(self._on_new_sample)
        self._worker.finished_run.connect(self._on_run_finished)
        self._worker.start()
        self._update_run_buttons(running=True)

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
            self._worker.wait()
        self._on_run_finished()

    def _on_new_sample(self, t: float, v: float, i: float):
        self._time_data.append(t)
        self._volt_data.append(v)
        self._curr_data.append(i)
        self.curve_v_live.setData(self._time_data, self._volt_data)
        self.curve_i_live.setData(self._time_data, self._curr_data)

    def _on_run_finished(self):
        self._update_run_buttons(running=False)
        n = len(self._time_data)
        src = "hardware" if self._smu else "simulation"
        self._set_status(f"Done — {n} samples ({src})", SUCCESS)

    def _on_worker_error(self, msg: str):
        QMessageBox.critical(self, "Hardware error", msg)
        self._on_run_finished()

    # ── Waveform slots ─────────────────────────────────────────────────────

    def _on_waveform_changed(self, index: int):
        self.param_stack.setCurrentIndex(index)
        self._refresh_preview()

    def _refresh_preview(self):
        try:
            profile, rate = self._current_panel().build_profile()
            t = np.arange(len(profile)) / rate
            self.curve_v_preview.setData(t, profile)
        except Exception:
            pass

    def _current_panel(self):
        return self.param_stack.currentWidget()

    # ── CSV export ─────────────────────────────────────────────────────────
    
    def get_unique_filename(self, base_name):
        filename = f"{base_name}.csv"
        counter = 1

        while os.path.exists(filename):
            filename = f"{base_name}_{counter}.csv"
            counter += 1

        return filename

    def _on_save_csv(self):
        if not self._time_data:
            QMessageBox.information(self, "No data", "Run the waveform first.")
            return

        raw  = self.edit_filename.text().strip() or "measurement"
        base_name = raw if raw.endswith(".csv") else raw + ".csv"
        
        name = self.get_unique_filename(base_name)

        try:
            with open(name, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Time (s)", "Voltage (V)", "Current (A)"])
                writer.writerows(zip(self._time_data, self._volt_data, self._curr_data))
            self._set_status(f"Saved → {name}", WARNING)
            QMessageBox.information(self, "Saved", f"Data written to:\n{name}")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    # ── Helpers ────────────────────────────────────────────────────────────

    def _update_run_buttons(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.cmb_waveform.setEnabled(not running)

    def _update_connect_buttons(self, connected: bool):
        self.btn_connect.setEnabled(not connected)
        self.btn_disconnect.setEnabled(connected)
        self.edit_resource.setEnabled(not connected)

    def _set_status(self, text: str, color: str = TEXT_SEC):
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {color};")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait()
        if self._smu:
            try:
                self._smu.disable_all()
            except Exception:
                pass
            self._smu.close()
        super().closeEvent(event)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window,     QColor(DARK_BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT_PRI))
    app.setPalette(palette)

    win = SMUCombinedApp()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()