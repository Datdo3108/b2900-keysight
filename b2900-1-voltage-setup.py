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


# ── Configuration ─────────────────────────────────────────────────────────────

# resource_name   = "MyVisaAlias"
# resource_name = "TCPIP0::<IP_Address>::INSTR"
# resource_name = "USB0::0x0957::0x8C18::MY12345678::INSTR"
resource_name = "USB0::0x0957::0xD018::MY51142876::0::INSTR"
# resource_name = "USB0::0x2A8D::0x9501::MY61390609::0::INSTR"
# resource_name = "GPIB0::23::INSTR"

idQuery = True
reset   = True
# options = "DriverSetup=Model:B2912A, QueryInstrStatus=False, Simulate=True, Trace=False"
# For real hardware, use:
options = "QueryInstrStatus=True, Simulate=False, Trace=True"

VOLTAGE_V       = 0.04   # Desired output voltage  [V]
VOLTAGE_RANGE_V = 20.0  # Voltage range: 2, 20, or 200 V
CURRENT_NPLC    = 0.1   # Integration time in power-line cycles


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
        
        print(f"  Driver setup : {driver.driver_operation.driver_setup}")

        num_channels = driver.outputs.count
        print(f"  Channels : {num_channels}")
                
        # ── Configure every channel ───────────────────────────────────────
        for i in range(num_channels):

            # Channel list string for this channel, e.g. "(@1)" or "(@2)"
            chan_str = f"(@{i + 1})"

            # Source: voltage, fixed range, set-point
            driver.outputs[i].voltage.auto_range_enabled = False
            driver.outputs[i].voltage.range              = VOLTAGE_RANGE_V
            driver.outputs[i].voltage.level              = VOLTAGE_V
            driver.outputs[i].voltage.triggered_level    = VOLTAGE_V

            # Measurement: current compliance settings
            if model in SUPPORTED_MODELS:
                driver.measurements[i].current.auto_range_enabled = True
                driver.measurements[i].current.nplc               = CURRENT_NPLC

            # Enable output
            driver.outputs[i].enabled = True
            print(f"\n  Channel {i + 1} ({chan_str}) output ON  →  {VOLTAGE_V:+.4f} V")

            # ── Trigger and fetch ─────────────────────────────────────────
            driver.trigger.initiate(chan_str)

            current_results = driver.measurements.fetch_array_data(
                keysight_ktb2900.MeasurementFetchType.CURRENT,
                chan_str,
            )
            
            voltage_results = driver.measurements.fetch_array_data(
                keysight_ktb2900.MeasurementFetchType.VOLTAGE,
                chan_str,
            )

            print(f"  Measured current data ({chan_str}):")
            for idx, val in enumerate(current_results):
                print(f"    [{idx}]: {val:.6e} A")
            for idx, val in enumerate(voltage_results):
                print(f"    [{idx}]: {val:.6e} V")

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