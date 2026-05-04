import keysight_ktb2900
import time
from datetime import timedelta
import numpy as np

# ── Configuration ─────────────────────────────────────────────────────────────
resource_name = "USB0::0x0957::0xD018::MY51142876::0::INSTR"
idQuery = True
reset   = True
options = "QueryInstrStatus=True, Simulate=False, Trace=False"

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
        vendor = driver.identity.vendor
        supported_models = driver.identity.get_supported_instrument_models()
        print(f"  Model    : {model}")
        print(f"  Resource : {resource}")
        print(f"  Vendor   : {vendor}")
        print(f"  Driver setup    : {driver.driver_operation.driver_setup}")
        print(f"  Supported model : {supported_models}")

        num_channels = driver.outputs.count
        print(f"  Channels : {num_channels}")
        print(f"  Len channels: {len(driver.outputs)}")         # same as .count
        
        # ── Generate ramp waveform ─────────────────────────────────────
        sample_rate = 10          # Hz
        dt = 1.0 / sample_rate   # 0.1 s
        total_time = 2.0         # seconds
        num_points = int(total_time * sample_rate)  # 20 points

        # Create waveform: 0→0.3 (first 10), then 0.3→1 (next 10)
        v1 = np.linspace(5, 2, num_points // 2, endpoint=False)
        v2 = np.linspace(2, 1, num_points // 2)
        voltage_profile = np.concatenate((v1, v2))
                        
        # ── Configure every channel ───────────────────────────────────────
        for i in range(num_channels):

            # Channel list string for this channel, e.g. "(@1)" or "(@2)"
            chan_str = f"(@{i + 1})"

            # Output setup
            driver.outputs[i].voltage.auto_range_enabled = False
            driver.outputs[i].voltage.range              = VOLTAGE_RANGE_V
            driver.outputs[i].type                       = keysight_ktb2900.OutputType.VOLTAGE
            driver.outputs[i].enabled = True
            
            if model in SUPPORTED_MODELS:
                driver.measurements[i].current.auto_range_enabled = True
                driver.measurements[i].current.nplc               = CURRENT_NPLC
                
            # Transient setups
            driver.transients[i].voltage.configure_list(voltage_profile)
            driver.transients[i].voltage.mode = keysight_ktb2900.TransientCurrentVoltageMode.LIST
            
            driver.transients[i].trigger.source = keysight_ktb2900.ArmTriggerSource.TIMER
            driver.transients[i].trigger.timer  = timedelta(milliseconds=5)
            driver.transients[i].trigger.count  = len(voltage_profile)

            query_list = driver.transients[i].voltage.query_list()
            print("Query list   :", query_list)
            timer = driver.transients[i].trigger.timer
            print("Timer: ", timer)
            
            driver.measurements[i].trigger.source = keysight_ktb2900.ArmTriggerSource.TIMER  # waits for transient output trigger
            driver.measurements[i].trigger.count  = 101
            driver.measurements[i].trigger.timer  = timedelta(milliseconds=1)
                
            print(f"\n  Channel {i + 1} ({chan_str}) output ON")

            time_0 = time.time()         
            
            for i in range(2):
                driver.trigger.initiate(chan_str)
                
                ctime = time.time() - time_0
                print(f"Trigger task finished in    :\t {ctime:.6f}s")
                
                # Get measurements data
                current_results = driver.measurements.fetch_array_data(
                    keysight_ktb2900.MeasurementFetchType.CURRENT,
                    chan_str,
                )
                
                voltage_results = driver.measurements.fetch_array_data(
                    keysight_ktb2900.MeasurementFetchType.VOLTAGE,
                    chan_str,
                )
                
                ctime = time.time() - time_0
                print(f"Data fetch finished in      :\t {ctime:.6f}s")

                print(f"  Measured current data ({chan_str}):")
                # for idx, val in enumerate(current_results):
                #     print(f"    [{idx}]:\t {val:.6e} A")
                for idx, val in enumerate(voltage_results):
                    print(f"    [{idx}]:\t {val:.6e} V")
                    
                ctime = time.time() - time_0
                print(f"Print out finished in       :\t {ctime:.6f}s")


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