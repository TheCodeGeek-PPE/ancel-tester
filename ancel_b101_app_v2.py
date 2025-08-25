import os
import tempfile
import customtkinter as ctk
from threading import Thread
from time import sleep
from struct import unpack_from
from serial import Serial, SerialException
import serial.tools.list_ports as st

# --- Optional Dependency for Printing on Windows ---
# Please install pywin32: pip install pywin32
try:
    import win32print
    import win32api
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

# --- Constants ---
BAUD_RATE = 9600
BYTE_SEQUENCE_LENGTH = 31
WINDOW_WIDTH = 460
WINDOW_HEIGHT = 510

# --- Data Mappings ---
SELECT_INPUT_TYPES = {
    1: "CCA", 2: "DIN", 3: "JIS", 4: "EN", 5: "IEC",
    6: "GB", 7: "SAE", 8: "MCA", 9: "BCI", 10: "CA",
}
BATTERY_STATUS_TYPES = {
    0: "GOOD", 1: "GOOD, RECHARGE", 2: "BAD, REPLACE",
    3: "REPLACE", 4: "CHARGE & RETEST",
}
CRANKING_STATUS_TYPES = {1: "NORMAL", 2: "LOW"}
CHARGING_STATUS_TYPES = {0: "NO OUTPUT", 1: "LOW", 2: "NORMAL", 3: "HIGH"}


class BatteryTesterApp(ctk.CTk):
    """
    An application for reading and displaying data from the Ancel BA101 Battery Tester.
    """

    def __init__(self):
        """
        Initializes the main application window and its components.
        """
        super().__init__()

        self.title("Ancel BA101 Battery Tester")
        self.geometry(self._center_window(WINDOW_WIDTH, WINDOW_HEIGHT))
        self.grid_columnconfigure((0, 1, 2), weight=1)

        self._create_widgets()

    def _center_window(self, width, height):
        """
        Calculates the screen position to center the window.

        Args:
            width (int): The width of the window.
            height (int): The height of the window.

        Returns:
            str: The geometry string for tkinter.
        """
        scale_factor = self._get_window_scaling()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = int(((screen_width / 2) - (width / 2)) * scale_factor)
        y = int(((screen_height / 2) - (height / 1.5)) * scale_factor)
        return f"{width}x{height}+{x}+{y}"

    def _create_widgets(self):
        """
        Creates and arranges all the GUI widgets in the main window.
        """
        # --- Serial Port Selection ---
        port_label = ctk.CTkLabel(self, text="Serial Port:")
        port_label.grid(row=0, column=0, padx=20, pady=20, sticky="e")

        self.port_combobox = ctk.CTkComboBox(self, values=self._collect_comports(), width=140)
        self.port_combobox.grid(row=0, column=1, padx=20, pady=20, sticky="w")

        self.connect_button = ctk.CTkButton(self, text="Connect", command=self._connect_button_callback)
        self.connect_button.grid(row=0, column=2, padx=20, pady=20, sticky="w")

        # --- Data Display ---
        self.display_textbox = ctk.CTkTextbox(self, width=400, height=400)
        self.display_textbox.grid(row=1, column=0, padx=20, pady=0, sticky="nsew", columnspan=3)

        # --- Status and Print ---
        self.status_label = ctk.CTkLabel(self, text="Status: Not Connected", fg_color="transparent")
        self.status_label.grid(row=2, column=0, padx=20, pady=5, sticky="esw", columnspan=2)

        print_button = ctk.CTkButton(self, text="Print", command=self._print_button_callback)
        print_button.grid(row=2, column=2, padx=20, pady=5, sticky="ew")

    def _collect_comports(self):
        """
        Gathers a list of available COM ports.

        Returns:
            list: A list of COM port names, or a message if none are found.
        """
        comports = [port.name for port in st.comports()]
        return comports if comports else ["Reconnect BA101"]

    def _update_status(self, message, color="transparent"):
        """
        Updates the status label with a new message and color.

        Args:
            message (str): The message to display.
            color (str): The background color for the label.
        """
        self.status_label.configure(text=f"Status: {message}", fg_color=color)

    def _connect_button_callback(self):
        """
        Handles the event when the 'Connect' button is clicked.
        """
        selected_port = self.port_combobox.get()
        if selected_port == "Reconnect BA101":
            self._update_status("Error - Please connect the BA101 and restart.", "red")
            return

        self._update_status("Listening for data...", "transparent")
        self._start_serial_listener(selected_port)

    def _start_serial_listener(self, serial_port):
        """
        Starts the serial port listener in a separate thread to keep the GUI responsive.

        Args:
            serial_port (str): The name of the serial port to listen on.
        """
        thread = Thread(target=self._listen_serial, args=(serial_port,))
        thread.daemon = True
        thread.start()

    def _listen_serial(self, serial_port):
        """
        Listens for incoming data from the specified serial port.

        Args:
            serial_port (str): The name of the serial port.
        """
        try:
            with Serial(serial_port, BAUD_RATE, timeout=1) as ser:
                while True:
                    data = ser.read(BYTE_SEQUENCE_LENGTH)
                    if len(data) == BYTE_SEQUENCE_LENGTH:
                        parsed_data = self._parse_battery_data(data)
                        self.display_textbox.delete("1.0", ctk.END)
                        self.display_textbox.insert(ctk.END, parsed_data)
                        self._update_status("Data received successfully.", "green")
                        break  # Exit loop after receiving data
        except SerialException as e:
            self._update_status(f"Serial error: {e}", "red")

    def _parse_battery_data(self, data):
        """
        Parses the raw byte data from the battery tester.

        Args:
            data (bytes): The raw data from the serial port.

        Returns:
            str: A formatted string of the parsed battery data.
        """
        if len(data) < BYTE_SEQUENCE_LENGTH:
            return "Incomplete data received."

        def u8(offset):
            return unpack_from('>B', data, offset)[0]

        def u16(offset):
            return unpack_from('>H', data, offset)[0]

        # --- Extract values from data ---
        battery_status = BATTERY_STATUS_TYPES.get(u8(3), "UNKNOWN")
        voltage = u16(4) / 100.0
        measured_amps = u16(6)
        internal_res = u16(8) / 100.0
        health = u16(10)
        charge = u16(12)
        rated_amps = u16(14)
        select_input = SELECT_INPUT_TYPES.get(u8(16), "UNKNOWN")
        cranking_time = u16(17)
        cranking_status = CRANKING_STATUS_TYPES.get(u8(19), "UNKNOWN")
        cranking_voltage = u16(20) / 100.0
        unloaded = u16(22) / 100.0
        loaded = u16(24) / 100.0
        ripple = u16(26)
        charging_status = CHARGING_STATUS_TYPES.get(u8(28), "UNKNOWN")

        # --- Format the output string ---
        return f"""====== Battery Test ======
Status:           {battery_status}
Voltage:          {voltage:.2f}V
Charge:           {charge}%
Health:           {health}%
Rated:            {rated_amps}A
Measured:         {measured_amps}A
Standard:         {select_input}
Internal Res:     {internal_res:.2f}mΩ

====== Cranking Test ======
Cranking Time:    {cranking_time}ms
Cranking Voltage: {cranking_voltage:.2f}V
Cranking Status:  {cranking_status}

====== Charging Test ======
Loaded Voltage:   {loaded:.2f}V
Unloaded Voltage: {unloaded:.2f}V
Ripple:           {ripple}mV
Charging Status:  {charging_status}
"""

    def _print_button_callback(self):
        """
        Opens a dialog to select a printer and then prints the content.
        """
        if not PYWIN32_AVAILABLE:
            self._update_status("Printing requires 'pywin32'. Install it via pip.", "red")
            return

        content = self.display_textbox.get("1.0", ctk.END)
        if not content.strip():
            self._update_status("No content to print.", "orange")
            return

        try:
            printers = [printer[2] for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
        except Exception as e:
            self._update_status(f"Could not list printers: {e}", "red")
            return

        if not printers:
            self._update_status("No printers found on this system.", "red")
            return

        self._show_printer_dialog(printers, content)

    def _show_printer_dialog(self, printers, content):
        """
        Displays a modal dialog for printer selection, centered on the main window.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Printer")
        dialog.transient(self)  # Keep dialog on top of the main window
        dialog.grab_set()       # Make the dialog modal

        # --- Position the dialog in the center of the main window ---
        dialog_width = 350
        dialog_height = 180
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()
        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        label = ctk.CTkLabel(dialog, text="Choose a printer:")
        label.pack(padx=20, pady=10)

        combo = ctk.CTkComboBox(dialog, values=printers, width=300)
        combo.pack(padx=20, pady=5)
        try:
            default_printer = win32print.GetDefaultPrinter()
            combo.set(default_printer)
        except Exception:
            combo.set(printers[0]) # Fallback to the first printer

        def on_print():
            selected_printer = combo.get()
            dialog.destroy()
            self._execute_print(selected_printer, content)

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=20)

        print_btn = ctk.CTkButton(button_frame, text="Print", command=on_print, width=100)
        print_btn.pack(side="left", padx=10)

        cancel_btn = ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy, width=100)
        cancel_btn.pack(side="left", padx=10)


    def _execute_print(self, printer_name, content):
        """
        Sends the content to the specified printer using a temporary file.
        """
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt") as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            win32api.ShellExecute(
                0,
                "printto",
                temp_file_path,
                f'"{printer_name}"',
                ".",
                0
            )
            self._update_status(f"Print command sent to {printer_name}.", "green")
            self.after(5000, self._cleanup_temp_file, temp_file_path)

        except Exception as e:
            self._update_status(f"Printing error: {e}", "red")

    def _cleanup_temp_file(self, file_path):
        """
        Removes the temporary file after a delay.

        Args:
            file_path (str): The path to the temporary file.
        """
        if os.path.exists(file_path):
            os.remove(file_path)


if __name__ == "__main__":
    app = BatteryTesterApp()
    app.mainloop()
