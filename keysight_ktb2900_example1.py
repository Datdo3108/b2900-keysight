"""
keysight_ktb2900 Python API Example Program

Creates a driver object, reads a few DriverIdentity interface properties, and checks
the instrument error queue.  May include additional instrument specific functionality.

Runs in simulation mode without an instrument.

Requires Python 3.6 or newer and keysight_ktb2900 Python module installed.
"""

import keysight_ktb2900
import numpy as np # For keysight_ktb2900 arrays


def main():
    """
    Edit resource_name and options as needed.  resource_name is ignored if option Simulate=true
    For this example, resource_name may be a VISA address(e.g. "TCPIP0::<IP_Address>::INSTR")
    or a VISA alias.  For more information on using VISA aliases, refer to the Keysight IO
    Libraries Connection Expert documentation.
    """
    resource_name = "MyVisaAlias"
    #resource_name = "TCPIP0::<IP_Address>::INSTR"

    #  Edit the initialization options as needed
    idQuery = True
    reset   = True
    options = "QueryInstrStatus=False, Simulate=True, Trace=False"

    try:
        print("\n  keysight_ktb2900 Python API Example1\n")

        # Call driver constructor with options
        global driver # May be used in other functions
        driver = None
        driver = keysight_ktb2900.KtB2900(resource_name, idQuery, reset, options)
        print("Driver Initialized")

        #  Print a few identity properties
        print('  identifier: ', driver.identity.identifier)
        print('  revision:   ', driver.identity.revision)
        print('  vendor:     ', driver.identity.vendor)
        print('  description:', driver.identity.description)
        print('  model:      ', driver.identity.instrument_model)
        print('  resource:   ', driver.driver_operation.io_resource_descriptor)
        print('  options:    ', driver.driver_operation.driver_setup)


        iNumberOfChannels = driver.outputs.count;
        ModelNo = driver.identity.instrument_model;
        print("ModelNo. :" + ModelNo)
        for i in range(iNumberOfChannels):
            driver.outputs[i].voltage.auto_range_enabled = False
            driver.outputs[i].voltage.range = 20.0
            driver.outputs[i].voltage.level = 2.0
            driver.outputs[i].voltage.triggered_level = 2.0
            if (ModelNo == "B2901A" or ModelNo == "B2902A" or ModelNo == "B2911A" or ModelNo == "B2912A" or ModelNo == "B2901B" or ModelNo == "B2902B" or ModelNo == "B2911B" or ModelNo == "B2912B"):
                driver.measurements[i].current.auto_range_enabled = True; #Supported Models for this property: B2901A|B, B2902A|B, B2911A|B, B2912A|B
                driver.measurements[i].current.nplc = 0.1
                driver.outputs[i].enabled = True
            chanlist = "(@1)"
            driver.trigger.initiate(chanlist)
            dResult = driver.measurements.fetch_array_data((keysight_ktb2900.MeasurementFetchType.CURRENT), "(@1)")
            print("Fixed DC data:")
            for i in range(len(dResult)):
                print("Item[" + i + "]: " + dResult[i])
            for i in range(iNumberOfChannels):
                driver.outputs["OutputChannel" + i].enabled = False



        # Check instrument for errors
        print()
        while True:
            outVal = ()
            outVal = driver.utility.error_query()
            print("  error_query: code:", outVal[0], " message:", outVal[1])
            if(outVal[0] == 0): # 0 = No error, error queue empty
                break

    except Exception as e:
        print("\n  Exception:", e.__class__.__name__, e.args)

    finally:
        if driver is not None: # Skip close() if constructor failed
            driver.close()
        input("\nDone - Press Enter to Exit")


if __name__ == "__main__":
    main()