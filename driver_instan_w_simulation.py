import keysight_ktb2900
import numpy as np # For keysight_ktb2900 arrays


def main():
   # Edit resource_name and options as needed.  resource_name is ignored if option Simulate=True
   resource_name = "MyVisaAlias"
   #resource_name = "TCPIP0::127.0.0.1::INSTR"
   id_query = False
   reset = False
   options = "Simulate=True, QueryInstrStatus=True"

   try:
      # Call driver constructor with options
      driver = None
      driver = keysight_ktb2900.KtB2900(resource_name, id_query, reset, options)
      print("Driver Initialized")


      print('  description:', driver.identity.description)


   except Exception as e:
      print("\n  Exception:", e.__class__.__name__, e.args)

   finally:
      if driver is not None: # Skip close() if constructor failed
         driver.close()
      input("\nDone - Press Enter to Exit")


if __name__ == "__main__":
   main()