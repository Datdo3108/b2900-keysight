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
import time
import numpy as np


# ── Configuration ─────────────────────────────────────────────────────────────

# resource_name   = "MyVisaAlias"
# resource_name = "TCPIP0::<IP_Address>::INSTR"
# resource_name = "USB0::0x0957::0x8C18::MY12345678::INSTR"
resource_name = "USB0::0x0957::0xD018::MY51142876::0::INSTR"
# resource_name = "GPIB0::23::INSTR"

idQuery = True
reset   = True
# options = "DriverSetup=Model:B2912A, QueryInstrStatus=False, Simulate=True, Trace=False"
# For real hardware, use:
options = "QueryInstrStatus=True, Simulate=False, Trace=False"

VOLTAGE_V       = 5.0   # Desired output voltage  [V]
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
            driver.outputs[i].voltage.level              = 0
            # driver.outputs[i].voltage.triggered_level    = VOLTAGE_V      # Trigger to set single value

            # Measurement: current compliance settings
            if model in SUPPORTED_MODELS:
                driver.measurements[i].current.auto_range_enabled = True
                driver.measurements[i].current.nplc               = CURRENT_NPLC

            # Enable output
            driver.outputs[i].enabled = True
            print(f"\n  Channel {i + 1} ({chan_str}) output ON  →  {VOLTAGE_V:+.4f} V")
            
            # ── Generate ramp waveform ─────────────────────────────────────
            sample_rate = 10          # Hz
            dt = 1.0 / sample_rate   # 0.1 s
            total_time = 2.0         # seconds
            num_points = int(total_time * sample_rate)  # 20 points

            # Create waveform: 0→0.3 (first 10), then 0.3→1 (next 10)
            v1 = np.linspace(0.0, 0.3, num_points // 2, endpoint=False)
            v2 = np.linspace(0.3, 1.0, num_points // 2)
            voltage_profile = np.concatenate((v1, v2))


            # ── Apply waveform ─────────────────────────────────────────────
            measured_v = []
            measured_i = []
            
            time_0 = time.time()

            for step, v in enumerate(voltage_profile):

                # Set voltage
                # driver.outputs[i].voltage.level = float(v)
                driver.outputs[i].voltage.triggered_level = float(v)

                # Trigger measurement
                driver.trigger.initiate(chan_str)

                i_val = driver.measurements.fetch_array_data(
                    keysight_ktb2900.MeasurementFetchType.CURRENT,
                    chan_str,
                )
                v_val = driver.measurements.fetch_array_data(
                    keysight_ktb2900.MeasurementFetchType.VOLTAGE,
                    chan_str,
                )

                measured_i.append(i_val)
                measured_v.append(v_val)

                ctime = time.time() - time_0
                print('Time stamp    : ', ctime)
                # print(f"[{step:02d}] Set={v:.3e} V | Meas={v_val:.6e} V | I={i_val:.6e} A")
                print(f"Time   : {ctime:.3f}", "\tSet V   : ", v, "\tMeasure V   :", v_val, "\tMeasure I   :", i_val)


                # time.sleep(dt)   # enforce 10 Hz

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