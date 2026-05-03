"""
Keysight B2900 Source-Measure Unit — Object-Oriented Controller
================================================================
Usage example at the bottom of this file (under `if __name__ == "__main__"`).
"""

import time
from datetime import timedelta

import numpy as np
import keysight_ktb2900


# ── Constants ──────────────────────────────────────────────────────────────────

SUPPORTED_MODELS = {
    "B2901A", "B2902A", "B2911A", "B2912A",
    "B2901B", "B2902B", "B2911B", "B2912B",
}


# ── Channel wrapper ────────────────────────────────────────────────────────────

class B2900Channel:
    """Represents a single SMU channel and its configuration."""

    def __init__(self, driver, index: int, model: str):
        self._driver = driver
        self.index = index               # 0-based index
        self.number = index + 1          # 1-based channel number
        self.chan_str = f"(@{self.number})"
        self._model = model

    # ── Output configuration ───────────────────────────────────────────────

    def configure_voltage_output(
        self,
        voltage_range: float = 20.0,
        current_nplc: float = 0.1,
    ) -> None:
        """Set up the channel as a voltage source."""
        output = self._driver.outputs[self.index]
        output.voltage.auto_range_enabled = False
        output.voltage.range = voltage_range
        output.type = keysight_ktb2900.OutputType.VOLTAGE

        if self._model in SUPPORTED_MODELS:
            meas = self._driver.measurements[self.index]
            meas.current.auto_range_enabled = True
            meas.current.nplc = current_nplc

    def enable(self) -> None:
        """Enable (turn on) this channel's output."""
        self._driver.outputs[self.index].enabled = True
        print(f"  Channel {self.number} ({self.chan_str}) output ON")

    def disable(self) -> None:
        """Disable (turn off) this channel's output."""
        self._driver.outputs[self.index].enabled = False
        print(f"  Channel {self.number} ({self.chan_str}) output OFF")

    # ── Transient / list configuration ────────────────────────────────────

    def configure_voltage_list(
        self,
        voltage_profile: np.ndarray,
        trigger_source: keysight_ktb2900.ArmTriggerSource = keysight_ktb2900.ArmTriggerSource.TIMER,
        trigger_timer_ms: float = 5.0,
    ) -> None:
        """Load a voltage list waveform and configure the transient trigger."""
        transient = self._driver.transients[self.index]
        transient.voltage.configure_list(voltage_profile)
        transient.voltage.mode = keysight_ktb2900.TransientCurrentVoltageMode.LIST

        transient.trigger.source = trigger_source
        transient.trigger.timer = timedelta(milliseconds=trigger_timer_ms)
        transient.trigger.count = len(voltage_profile)

        query = transient.voltage.query_list()
        print(f"  Channel {self.number} — query list : {query}")
        print(f"  Channel {self.number} — timer      : {transient.trigger.timer}")

    def configure_measurement_trigger(
        self,
        trigger_source: keysight_ktb2900.ArmTriggerSource = keysight_ktb2900.ArmTriggerSource.TIMER,
        count: int = 101,
        timer_ms: float = 1.0,
    ) -> None:
        """Configure the measurement trigger for this channel."""
        meas = self._driver.measurements[self.index]
        meas.trigger.source = trigger_source
        meas.trigger.count = count
        meas.trigger.timer = timedelta(milliseconds=timer_ms)

    # ── Trigger & fetch ───────────────────────────────────────────────────

    def initiate(self) -> float:
        """Arm and trigger this channel. Returns elapsed time (seconds)."""
        t0 = time.time()
        self._driver.trigger.initiate(self.chan_str)
        elapsed = time.time() - t0
        print(f"  Channel {self.number} — trigger finished in {elapsed:.6f}s")
        return elapsed

    def fetch_current(self) -> np.ndarray:
        """Fetch the current measurement array for this channel."""
        return self._driver.measurements.fetch_array_data(
            keysight_ktb2900.MeasurementFetchType.CURRENT,
            self.chan_str,
        )

    def fetch_voltage(self) -> np.ndarray:
        """Fetch the voltage measurement array for this channel."""
        return self._driver.measurements.fetch_array_data(
            keysight_ktb2900.MeasurementFetchType.VOLTAGE,
            self.chan_str,
        )

    def print_voltage_results(self, results: np.ndarray) -> None:
        print(f"  Measured voltage data ({self.chan_str}):")
        for idx, val in enumerate(results):
            print(f"    [{idx}]:\t {val:.6e} V")

    def print_current_results(self, results: np.ndarray) -> None:
        print(f"  Measured current data ({self.chan_str}):")
        for idx, val in enumerate(results):
            print(f"    [{idx}]:\t {val:.6e} A")


# ── Instrument wrapper ─────────────────────────────────────────────────────────

class B2900Controller:
    """
    High-level controller for a Keysight B2900-series SMU.

    Parameters
    ----------
    resource_name : str
        VISA resource string (e.g. ``"USB0::0x0957::...::INSTR"``).
    id_query : bool
        Run an identity query on open (recommended).
    reset : bool
        Reset the instrument on open.
    options : str
        Driver option string.
    """

    def __init__(
        self,
        resource_name: str,
        id_query: bool = True,
        reset: bool = True,
        options: str = "QueryInstrStatus=True, Simulate=False, Trace=False",
    ):
        self._resource_name = resource_name
        self._id_query = id_query
        self._reset = reset
        self._options = options
        self._driver = None
        self.channels: list[B2900Channel] = []

    # ── Context-manager support ───────────────────────────────────────────

    def __enter__(self) -> "B2900Controller":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the driver connection and discover channels."""
        self._driver = keysight_ktb2900.KtB2900(
            self._resource_name, self._id_query, self._reset, self._options
        )
        print("Driver initialized")
        self._print_identity()
        self._build_channels()

    def close(self) -> None:
        """Close the driver connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            print("Driver closed")

    def _print_identity(self) -> None:
        d = self._driver
        print(f"  Model           : {d.identity.instrument_model}")
        print(f"  Resource        : {d.driver_operation.io_resource_descriptor}")
        print(f"  Vendor          : {d.identity.vendor}")
        print(f"  Driver setup    : {d.driver_operation.driver_setup}")
        print(f"  Supported models: {d.identity.get_supported_instrument_models()}")

    def _build_channels(self) -> None:
        model = self._driver.identity.instrument_model
        n = self._driver.outputs.count
        self.channels = [B2900Channel(self._driver, i, model) for i in range(n)]
        print(f"  Channels        : {n}")

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def model(self) -> str:
        return self._driver.identity.instrument_model

    @property
    def num_channels(self) -> int:
        return len(self.channels)

    # ── Error queue ───────────────────────────────────────────────────────

    def drain_error_queue(self) -> None:
        """Print and drain the instrument error queue."""
        print()
        while True:
            code, message = self._driver.utility.error_query()
            print(f"  error_query: code={code}  message={message}")
            if code == 0:
                break

    # ── Convenience: disable all outputs ──────────────────────────────────

    def disable_all(self) -> None:
        for ch in self.channels:
            ch.disable()


# ── Waveform helpers ───────────────────────────────────────────────────────────

class VoltageWaveform:
    """Factory for common voltage profile shapes."""

    @staticmethod
    def ramp(
        v_start: float,
        v_mid: float,
        v_end: float,
        num_points: int = 20,
    ) -> np.ndarray:
        """
        Two-segment linear ramp: v_start → v_mid → v_end.

        Parameters
        ----------
        v_start, v_mid, v_end : float
            Voltage values in volts.
        num_points : int
            Total number of points (split evenly between the two segments).
        """
        half = num_points // 2
        seg1 = np.linspace(v_start, v_mid, half, endpoint=False)
        seg2 = np.linspace(v_mid, v_end, half)
        return np.concatenate((seg1, seg2))

    @staticmethod
    def constant(voltage: float, num_points: int = 20) -> np.ndarray:
        return np.full(num_points, voltage)

    @staticmethod
    def sine(
        amplitude: float,
        offset: float = 0.0,
        num_points: int = 100,
    ) -> np.ndarray:
        t = np.linspace(0, 2 * np.pi, num_points, endpoint=False)
        return offset + amplitude * np.sin(t)


# ── Example usage ──────────────────────────────────────────────────────────────

def main():
    print("\n  Keysight B2900 — OOP Controller Demo\n")

    RESOURCE  = "USB0::0x0957::0xD018::MY51142876::0::INSTR"
    V_RANGE   = 20.0   # V
    NPLC      = 0.1

    # Build a two-segment ramp: 5 V → 2 V → 1 V over 20 points
    voltage_profile = VoltageWaveform.ramp(
        v_start=5.0, v_mid=2.0, v_end=1.0, num_points=20
    )

    try:
        with B2900Controller(RESOURCE) as smu:

            for ch in smu.channels:
                # 1. Configure output
                ch.configure_voltage_output(voltage_range=V_RANGE, current_nplc=NPLC)
                ch.enable()

                # 2. Load waveform & trigger settings
                ch.configure_voltage_list(
                    voltage_profile,
                    trigger_timer_ms=5.0,
                )
                ch.configure_measurement_trigger(count=101, timer_ms=1.0)

                # 3. Fire
                ch.initiate()

                # 4. Collect results
                t0 = time.time()
                current_data = ch.fetch_current()
                voltage_data = ch.fetch_voltage()
                print(f"  Fetch completed in {time.time() - t0:.6f}s")

                ch.print_voltage_results(voltage_data)
                # ch.print_current_results(current_data)  # uncomment if needed

            input("\nPress Enter to disable all outputs and exit...")
            smu.disable_all()
            smu.drain_error_queue()

    except Exception as exc:
        print(f"\n  Exception: {exc.__class__.__name__}: {exc}")

    print("\nDone.")


if __name__ == "__main__":
    main()