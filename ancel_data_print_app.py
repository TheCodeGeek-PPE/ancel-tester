from serial import Serial, SerialException
import serial.tools.list_ports as st
from struct import unpack_from
from time import sleep
from argparse import ArgumentParser
from sys import exit
import customtkinter as ctk
from threading import Thread    # For threading the serial listener
import os
import tempfile

# TODO: Code Cleanup

# Configuration
BAUD_RATE = 9600
BYTE_SEQUENCE_LENGTH = 31  # Expected length of message
W_WIDTH = 460   # Window Width
W_HEIGHT = 510  # Window Height

# Collect Active Comports
# If none found display "Reconnect BA101"
def CollectComports():
    comports = []
    for port in st.comports():
        comports.append(port.name)
    if not comports:
        comports.append("Reconnect BA101")
    return comports

# Center window function
def CenterWindowToDisplay(Screen: ctk, width: int, height: int, scale_factor: float = 1.0):
    """Centers the window to the main display/monitor"""
    screen_width = Screen.winfo_screenwidth()
    screen_height = Screen.winfo_screenheight()
    x = int(((screen_width/2) - (width/2)) * scale_factor)
    y = int(((screen_height/2) - (height/1.5)) * scale_factor)
    return f"{width}x{height}+{x}+{y}"

# Handle the connect button press
def ConnectButtonCallback():
    # If nothing is connected show error message
    if port.get() == "Reconnect BA101":
        UpdateStatus("Error - Please connect the BA101 and restart the app.", "red")
        return
    else:
        UpdateStatus("Listening for data...", "transparent")
        try:
            ThreadedSerialListener(port.get())
        except SerialException as e:
            print(f"Serial error: {e}")

# Start the serial listener in a separate thread
# This keeps the GUI responsive
def ThreadedSerialListener(serial_port):
    thread = Thread(target=listen_serial, args=(serial_port,))
    thread.daemon = True  # Allow program to exit even if thread is running
    thread.start()

def UpdateStatus(message: str, color: str = "transparent"):
    status_label.configure(text=f"Status: {message}", fg_color=color)

def print_text_content(text_widget):
    content = text_widget.get("1.0", ctk.END)  # Get all text from the Text widget
    if content.strip():  # Check if there's content to print
        try:
            # Create a temporary file to hold the content
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt") as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            # Use os.startfile to print the temporary file (Windows specific)
            os.startfile(temp_file_path, "print")
            print(f"Printing initiated for: {temp_file_path}")
        except Exception as e:
            print(f"Error during printing: {e}")
        finally:
            sleep(5)  # Wait a bit to ensure the print job is sent
            # Clean up the temporary file
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    else:
        print("No content to print.")

def PrintButtonCallback():
    print_text_content(display)
    UpdateStatus("Print command sent to printer.", "green")

# Create the main window
app = ctk.CTk()
app.geometry(CenterWindowToDisplay(app, W_WIDTH, W_HEIGHT, app._get_window_scaling()))
app.title("Ancel BA101 Battery Tester")
app.grid_columnconfigure((0, 1, 2), weight=1)
port_label = ctk.CTkLabel(app, text="Serial Port:")
port_label.grid(row=0, column=0, padx=20, pady=20, sticky="e")
port = ctk.CTkComboBox(app, values=CollectComports(), width=140)
port.grid(row=0, column=1, padx=20, pady=20, sticky="w")
button = ctk.CTkButton(app, text="Connect", command=ConnectButtonCallback)
button.grid(row=0, column=2, padx=20, pady=20, sticky="w")
display = ctk.CTkTextbox(app, width=400, height=400)
display.grid(row=1, column=0, padx=20, pady=0, sticky="nsew", columnspan=3)
status_label = ctk.CTkLabel(app, text="Status: Not Connected", fg_color="transparent")
status_label.grid(row=2, column=0, padx=20, pady=5, sticky="esw", columnspan=2)
print_button = ctk.CTkButton(app, text="Print", command=PrintButtonCallback)
print_button.grid(row=2, column=2, padx=20, pady=5, sticky="ew")

def parse_battery_data(data):
    if len(data) < BYTE_SEQUENCE_LENGTH:
        return "Incomplete data received."

    def u8(offset):
        return unpack_from('>B', data, offset)[0]
    
    def u16(offset):
        return unpack_from('>H', data, offset)[0]

    # Lookup table for select_input
    select_input_types = {
        1: "CCA",
        2: "DIN",
        3: "JIS",
        4: "EN",
        5: "IEC",
        6: "GB",
        7: "SAE",
        8: "MCA",
        9: "BCI",
        10: "CA",
    }

    # Lookup table for battery_status
    battery_status_types = {
        0: "GOOD",
        1: "GOOD, RECHARGE",
        2: "BAD, REPLACE",
        3: "REPLACE",
        4: "CHARGE & RETEST",
    }

    # Lookup table for cranking_status
    cranking_status_types = {
        1: "NORMAL",
        2: "LOW",
    }

    # Lookup table for charging_status
    charging_status_types = {
        0: "NO OUTPUT",
        1: "LOW",
        2: "NORMAL",
        3: "HIGH",
    }

    # Parsing values
    battery_status = u8(3)
    voltage = u16(4)
    measured_amps = u16(6)
    internal_res = u16(8)
    health = u16(10)
    charge = u16(12)
    rated_amps = u16(14)
    select_input = u8(16)
    cranking_time = u16(17)
    cranking_status = u8(19)
    cranking_voltage = u16(20)
    unloaded = u16(22)
    loaded = u16(24)
    ripple = u16(26)
    charging_status = u8(28)

    # Translate using the lookup table
    select_input_type = select_input_types.get(select_input, "UNKNOWN")
    battery_status_type = battery_status_types.get(battery_status, "UNKNOWN")
    cranking_status_type = cranking_status_types.get(cranking_status, "UNKNOWN")
    charging_status_type = charging_status_types.get(charging_status, "UNKNOWN")

    result = f"""====== Battery Test ======
Status:             {battery_status_type}
Voltage:            {voltage / 100:.2f}V
Charge:             {charge}%
Health:             {health}%
Rated:              {rated_amps}A
Measured:           {measured_amps}A
Standard:           {select_input_type}
Internal Res:       {internal_res / 100:.2f}mΩ

====== Cranking Test ======
Cranking Time:      {cranking_time}ms
Cranking Voltage:   {cranking_voltage / 100:.2f}V
Cranking Status:    {cranking_status_type}

====== Charging Test ======
Loaded Voltage:     {loaded / 100:.2f}V
Unloaded Voltage:   {unloaded / 100:.2f}V
Ripple:             {ripple}mV
Charging Status:    {charging_status_type}
"""
    return result


def listen_serial(serial_port, baud_rate=BAUD_RATE):
    #print(f"Opening serial port {serial_port} at {baud_rate} baud...")
    try:
        with Serial(serial_port, baud_rate, timeout=1) as ser:
            #print("Listening for data... Press Ctrl+C to stop.\n")
            while True:
                data = ser.read(BYTE_SEQUENCE_LENGTH)
                if len(data) == BYTE_SEQUENCE_LENGTH:
                    #print(parse_battery_data(data))
                    # Close the connection after data receipt
                    ser.close()
                    # Update the display with parsed data
                    display.delete("1.0", ctk.END)
                    display.insert(ctk.END, parse_battery_data(data))
                    UpdateStatus("Data received successfully.", "green")
    except SerialException as e:
        print(f"Serial error: {e}")

# Main entry point
if __name__ == "__main__":
    print("Ancel BA101 Battery Tester serial data parser.")

    # Display window
    app.mainloop()

    # Create a command line argument parser
    parser = ArgumentParser(description="Battery data parser from serial port.")
    # Add an argument for the serial port
    parser.add_argument("serial_port", nargs="?", help="Serial port to listen to (e.g.: /dev/ttyUSB0, COM3).")
    # Parse the command line arguments
    args = parser.parse_args()

    # Check if serial port argument is provided
    #if not args.serial_port:
    if port.get() == "":
        #print("Error: Serial port argument is required.")
        status_label.configure(text="Status: Error - Serial port argument is required.")
        parser.print_help()
        exit(1)

    # Start listening to the serial port
    try:
        listen_serial(args.serial_port)
    # Handle keyboard interrupt to stop the program gracefully
    except KeyboardInterrupt:
        print("\nStopped by user.")
