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
from datetime import timedelta
import numpy as np
import asyncio


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

VOLTAGE_V       = 2.0   # Desired output voltage  [V]
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
        
        # ── Generate ramp waveform ─────────────────────────────────────
        sample_rate = 10          # Hz
        dt = 1.0 / sample_rate   # 0.1 s
        total_time = 2.0         # seconds
        num_points = int(total_time * sample_rate)  # 20 points

        # Create waveform: 0→0.3 (first 10), then 0.3→1 (next 10)
        v1 = np.linspace(5, 2, num_points // 2, endpoint=False)
        v2 = np.linspace(2, 1, num_points // 2)
        voltage_profile = np.concatenate((v1, v2))
        
        # voltage_profile = np.array([2.0, 1.6, 1.1])
                
        # ── Configure every channel ───────────────────────────────────────
        for i in range(num_channels):

            # Channel list string for this channel, e.g. "(@1)" or "(@2)"
            chan_str = f"(@{i + 1})"

            # Output setup
            driver.outputs[i].voltage.auto_range_enabled = False
            driver.outputs[i].voltage.range              = VOLTAGE_RANGE_V
            # driver.outputs[i].voltage.level              = VOLTAGE_V
            driver.outputs[i].voltage.triggered_level    = VOLTAGE_V      # Trigger to set single value
            driver.outputs[i].type                       = keysight_ktb2900.OutputType.VOLTAGE
            driver.outputs[i].enabled = True
            
            # Measurement: current compliance settings
            # if model in SUPPORTED_MODELS:
            #     driver.measurements[i].current.auto_range_enabled = True
            #     driver.measurements[i].current.nplc               = CURRENT_NPLC
                
            # Transient setups
            driver.transients[i].voltage.configure_list(voltage_profile)
            driver.transients[i].voltage.mode = keysight_ktb2900.TransientCurrentVoltageMode.LIST
            
            # driver.transients[i].arm.source   = keysight_ktb2900.ArmTriggerSource.TIMER
            # driver.transients[i].arm.bypass   = keysight_ktb2900.ArmTriggerBypass.ONCE  # skip arm wait on first pass
            # driver.transients[i].arm.timer      = timedelta(milliseconds=100)
            # driver.transients[i].arm.count      = len(voltage_profile)
            
            driver.transients[i].trigger.source = keysight_ktb2900.ArmTriggerSource.TIMER
            driver.transients[i].trigger.timer  = timedelta(milliseconds=5)
            driver.transients[i].trigger.count  = len(voltage_profile)
            # driver.transients[i].trigger.trigger_output_enabled  = True
            # # driver.transients[i].trigger.bypass = keysight_ktb2900.ArmTriggerBypass.OFF
            # # driver.transients[i].trigger.continuous_enabled  = True


            query_list = driver.transients[i].voltage.query_list()
            print("Query list   :", query_list)
            timer = driver.transients[i].trigger.timer
            print("Timer: ", timer)
            
            # Measurements setups
            # driver.measurements[i].arm.source     = keysight_ktb2900.ArmTriggerSource.AINT
            driver.measurements[i].trigger.source = keysight_ktb2900.ArmTriggerSource.TIMER  # waits for transient output trigger
            driver.measurements[i].trigger.count  = 101
            driver.measurements[i].trigger.timer  = timedelta(milliseconds=1)
                
            print(f"\n  Channel {i + 1} ({chan_str}) output ON  →  {VOLTAGE_V:+.4f} V")

            time_0 = time.time()
            # driver.transients.arm_immediate(chan_str)
            # driver.transients.initiate(chan_str)            
            driver.trigger.initiate(chan_str)
            
            ctime = time.time() - time_0
            print(f"Task finished in:\t {ctime:.4f}s")
            
            # Get measurements data
            current_results = driver.measurements.fetch_array_data(
                keysight_ktb2900.MeasurementFetchType.CURRENT,
                chan_str,
            )
            
            voltage_results = driver.measurements.fetch_array_data(
                keysight_ktb2900.MeasurementFetchType.VOLTAGE,
                chan_str,
            )

            print(f"  Measured current data ({chan_str}):")
            # for idx, val in enumerate(current_results):
            #     print(f"    [{idx}]:\t {val:.6e} A")
            for idx, val in enumerate(voltage_results):
                print(f"    [{idx}]:\t {val:.6e} V")
                




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