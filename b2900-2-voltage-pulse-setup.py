"""
Keysight B2900 Series - Set Output Voltage
==========================================
Based on KtB2900 1.0.1 Python API.

Runs in simulation mode without an instrument (Simulate=True).
Change resource_name and set Simulate=False to run against real hardware.

Requires:
    pip install keysight-ktb2900
"""

import keysight_ktb2900
import datetime


# ── Configuration ─────────────────────────────────────────────────────────────

# resource_name   = "MyVisaAlias"
# resource_name = "TCPIP0::<IP_Address>::INSTR"
# resource_name = "USB0::0x0957::0x8C18::MY12345678::INSTR"
resource_name = "USB0::0x0957::0xD018::MY51142876::0::INSTR"
# resource_name = "GPIB0::23::INSTR"

idQuery = True
reset   = True
options = "QueryInstrStatus=False, Simulate=True, Trace=False"
# For real hardware, use:
# options = "QueryInstrStatus=True, Simulate=False, Trace=False"

VOLTAGE_V       = 5.0   # Desired output voltage  [V]
VOLTAGE_RANGE_V = 20.0  # Voltage range: 2, 20, or 200 V
CURRENT_NPLC    = 0.1   # Integration time in power-line cycles
PULSE_WIDTH_S = 0.1   # Pulse width  [s]  100 ms
PULSE_DELAY_S = 0.0   # Pulse delay  [s]
MEASURE_INTERVAL_S = 0.001   # Sampling interval [s]  1 ms  → 1000 points in 1 s
MEASURE_POINTS     = 1000    # Total points  (interval × points = 1 s)


# ── Models that support current auto-range + NPLC ────────────────────────────

SUPPORTED_MODELS = {
    "B2901A", "B2902A", "B2911A", "B2912A",
    "B2901B", "B2902B", "B2911B", "B2912B",
}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n  Keysight B2900 - Set Output Voltage\n")

    driver = None
    try:
        # ── Open driver ───────────────────────────────────────────────────
        driver = keysight_ktb2900.KtB2900(resource_name, idQuery, reset, options)
        print("Driver Initialized")

        # ── Identity ──────────────────────────────────────────────────────
        model    = driver.identity.instrument_model
        resource = driver.driver_operation.io_resource_descriptor
        print(f"  Model    : {model}")
        print(f"  Resource : {resource}")

        num_channels = driver.outputs.count
        print(f"  Channels : {num_channels}")

        # ── Configure every channel ───────────────────────────────────────
        for i in range(num_channels):

            # Channel list string for this channel, e.g. "(@1)" or "(@2)"
            chan_str = f"(@{i + 1})"

            # Source: voltage pulse, fixed range, set-point
            driver.outputs[i].voltage.auto_range_enabled = False
            driver.outputs[i].voltage.range              = VOLTAGE_RANGE_V
            driver.outputs[i].voltage.level              = 0.0          # base level
            driver.outputs[i].voltage.triggered_level    = VOLTAGE_V    # pulse level

            # Pulse shape and timing
            driver.outputs[i].shape       = keysight_ktb2900.OutputShape.PULSE
            driver.outputs[i].pulse_width = 0.1    # 100 ms
            driver.outputs[i].pulse_delay = 0.0    # no delay before pulse

            # # Source: voltage, fixed range, set-point
            # driver.outputs[i].voltage.auto_range_enabled = False
            # driver.outputs[i].voltage.range              = VOLTAGE_RANGE_V
            # driver.outputs[i].voltage.level              = VOLTAGE_V
            # driver.outputs[i].voltage.triggered_level    = VOLTAGE_V

            # Measurement: current compliance settings
            if model in SUPPORTED_MODELS:
                driver.measurements[i].current.auto_range_enabled = True
                driver.measurements[i].current.nplc               = CURRENT_NPLC
                driver.measurements[i].voltage.auto_range_enabled = True
                
            # Trigger: arm count and trigger count to capture MEASURE_POINTS samples
            driver.transients[i].trigger.count = MEASURE_POINTS
            driver.measurements[i].trigger.count = MEASURE_POINTS
            driver.measurements[i].trigger.delay = MEASURE_INTERVAL_S

            # Enable output
            driver.outputs[i].enabled = True
            print(f"\n  Channel {i + 1} ({chan_str}) output ON  →  {VOLTAGE_V:+.4f} V")

            # ── Trigger and fetch ─────────────────────────────────────────
            driver.trigger.initiate(chan_str)
            
            # Wait for all points to be acquired
            driver.system.wait_for_operation_complete(datetime.timedelta(seconds=10))
            
            print(f"  Points acquired: {driver.measurements[i].trace.data_count}")

            current_results = driver.measurements.fetch_array_data(
                keysight_ktb2900.MeasurementFetchType.CURRENT,
                chan_str,
            )

            voltage_results = driver.measurements.fetch_array_data(
                keysight_ktb2900.MeasurementFetchType.VOLTAGE,
                chan_str,
            )

            print(f"  Measured data ({chan_str})  —  {len(current_results)} points over 1 s:")
            for idx in range(len(current_results)):
                t = idx * MEASURE_INTERVAL_S
                print(f"    [{idx:04d}] t={t:.3f}s   V={voltage_results[idx]:+.6f} V   I={current_results[idx]:+.6e} A")
                
                
        # ── Wait before turning off ───────────────────────────────────────
        input("\nPress Enter to disable all outputs and exit...")

        for i in range(num_channels):
            driver.outputs[i].enabled = False
            print(f"  Channel {i + 1} output OFF")

        # ── Error queue ───────────────────────────────────────────────────
        print()
        while True:
            code, message = driver.utility.error_query()
            print(f"  error_query: code: {code}  message: {message}")
            if code == 0:  # 0 = No error, queue empty
                break

    except Exception as e:
        print(f"\n  Exception: {e.__class__.__name__}: {e}")

    finally:
        if driver is not None:
            driver.close()
        print("\nDone.")


if __name__ == "__main__":
    main()