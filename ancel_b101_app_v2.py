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
WINDOW_HEIGHT = 550 # Increased height for the new widget
MIN_WINDOW_HEIGHT = 250 # Approximate height for controls + 4 lines of text

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
        self.minsize(WINDOW_WIDTH, MIN_WINDOW_HEIGHT) # Prevent resizing smaller than initial size
        
        # --- Configure Grid Layout ---
        self.grid_columnconfigure(0, weight=0) # Let column 0 size to its content
        self.grid_columnconfigure(1, weight=1) # Let column 1 expand
        self.grid_columnconfigure(2, weight=0) # Let column 2 size to its content
        self.grid_rowconfigure(1, weight=1) # Allow the display frame row to expand vertically

        self.latest_data = None # To store the most recently parsed data

        self._create_widgets()

    def _center_window(self, width, height):
        """
        Calculates the screen position to center the window.
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

        # --- Frame for ComboBox and Refresh button ---
        port_selection_frame = ctk.CTkFrame(self, fg_color="transparent")
        port_selection_frame.grid(row=0, column=1, padx=0, pady=20, sticky="w")

        self.port_combobox = ctk.CTkComboBox(port_selection_frame, values=self._collect_comports(), width=140)
        self.port_combobox.pack(side="left", padx=(0, 5))

        refresh_button = ctk.CTkButton(port_selection_frame, text="↻", command=self._refresh_comports_callback, width=30)
        refresh_button.pack(side="left")

        self.connect_button = ctk.CTkButton(self, text="Connect", command=self._connect_button_callback)
        self.connect_button.grid(row=0, column=2, padx=20, pady=20, sticky="w")

        # --- Display Frame (contains header, textbox, and status label) ---
        display_frame = ctk.CTkFrame(self)
        display_frame.grid(row=1, column=0, padx=20, pady=5, sticky="nsew", columnspan=3)
        display_frame.grid_rowconfigure(1, weight=1) # Allow textbox to expand
        display_frame.grid_columnconfigure(0, weight=1)

        output_label = ctk.CTkLabel(display_frame, text="Output")
        output_label.grid(row=0, column=0, padx=5, pady=2, sticky="ew")

        self.display_textbox = ctk.CTkTextbox(display_frame, corner_radius=0)
        self.display_textbox.grid(row=1, column=0, sticky="nsew")

        self.status_label = ctk.CTkLabel(display_frame, text="Status: Not Connected", fg_color="transparent", corner_radius=6)
        self.status_label.grid(row=2, column=0, padx=5, pady=5, sticky="ew")

        # --- Test View Selection and Print Button ---
        view_label = ctk.CTkLabel(self, text="Test View:")
        view_label.grid(row=2, column=0, padx=20, pady=10, sticky="e")
        
        self.view_optionmenu = ctk.CTkOptionMenu(self, values=["All Tests", "Battery Test", "Cranking Test", "Charging Test"],
                                                 command=self._update_display_view)
        self.view_optionmenu.grid(row=2, column=1, padx=20, pady=10, sticky="w")

        print_button = ctk.CTkButton(self, text="Print", command=self._print_button_callback)
        print_button.grid(row=2, column=2, padx=20, pady=10, sticky="ew")

    def _collect_comports(self):
        """
        Gathers a list of available COM ports.
        """
        comports = [port.name for port in st.comports()]
        return comports if comports else ["Reconnect BA101"]

    def _refresh_comports_callback(self):
        """
        Refreshes the list of available COM ports in the dropdown.
        """
        current_selection = self.port_combobox.get()
        new_ports = self._collect_comports()
        self.port_combobox.configure(values=new_ports)

        if current_selection in new_ports:
            self.port_combobox.set(current_selection)
        elif new_ports:
            self.port_combobox.set(new_ports[0])
        self._update_status("COM port list refreshed.", "blue")


    def _update_status(self, message, color="transparent"):
        """
        Updates the status label with a new message and color.
        """
        self.status_label.configure(text=f"Status: {message}", fg_color=color)

    def _connect_button_callback(self):
        """
        Handles the event when the 'Connect' button is clicked.
        """
        selected_port = self.port_combobox.get()
        if selected_port == "Reconnect BA101":
            self._update_status("Error - Please connect the BA101 and click Refresh.", "red")
            return

        self._update_status("Listening for data...", "transparent")
        self._start_serial_listener(selected_port)

    def _start_serial_listener(self, serial_port):
        """
        Starts the serial port listener in a separate thread to keep the GUI responsive.
        """
        thread = Thread(target=self._listen_serial, args=(serial_port,))
        thread.daemon = True
        thread.start()

    def _listen_serial(self, serial_port):
        """
        Listens for incoming data from the specified serial port.
        """
        try:
            with Serial(serial_port, BAUD_RATE, timeout=1) as ser:
                while True:
                    data = ser.read(BYTE_SEQUENCE_LENGTH)
                    if len(data) == BYTE_SEQUENCE_LENGTH:
                        self.latest_data = self._parse_battery_data(data)
                        self._update_display_view()
                        self._update_status("Data received successfully.", "green")
                        break
        except SerialException as e:
            error_str = str(e)
            if "FileNotFoundError" in error_str:
                self._update_status("Connection Error.", "red")
                self._show_error_dialog("Connection Error", "Cannot connect to the device. Please check that the device is connected and the correct COM port is selected.")
            else:
                self._update_status("Serial Error.", "red")
                self._show_error_dialog("Serial Port Error", f"An error occurred with the serial port:\n\n{e}")

    def _parse_battery_data(self, data):
        """
        Parses the raw byte data from the battery tester into a dictionary.
        """
        if len(data) < BYTE_SEQUENCE_LENGTH:
            return {"error": "Incomplete data received."}

        def u8(offset): return unpack_from('>B', data, offset)[0]
        def u16(offset): return unpack_from('>H', data, offset)[0]

        return {
            "battery_test": {
                "Status": BATTERY_STATUS_TYPES.get(u8(3), "UNKNOWN"),
                "Voltage": f"{u16(4) / 100.0:.2f}V",
                "Charge": f"{u16(12)}%",
                "Health": f"{u16(10)}%",
                "Rated": f"{u16(14)}A",
                "Measured": f"{u16(6)}A",
                "Standard": SELECT_INPUT_TYPES.get(u8(16), "UNKNOWN"),
                "Internal Res": f"{u16(8) / 100.0:.2f}mΩ",
            },
            "cranking_test": {
                "Cranking Time": f"{u16(17)}ms",
                "Cranking Voltage": f"{u16(20) / 100.0:.2f}V",
                "Cranking Status": CRANKING_STATUS_TYPES.get(u8(19), "UNKNOWN"),
            },
            "charging_test": {
                "Loaded Voltage": f"{u16(24) / 100.0:.2f}V",
                "Unloaded Voltage": f"{u16(22) / 100.0:.2f}V",
                "Ripple": f"{u16(26)}mV",
                "Charging Status": CHARGING_STATUS_TYPES.get(u8(28), "UNKNOWN"),
            }
        }

    def _format_display_data(self, view_mode):
        """
        Formats the stored data based on the selected view mode.
        """
        if not self.latest_data or "error" in self.latest_data:
            return self.latest_data.get("error", "No data available.")

        def format_section(title, data):
            header = f"====== {title} ======\n"
            lines = [f"{key:<17}: {value}" for key, value in data.items()]
            return header + "\n".join(lines)

        output_parts = []
        if view_mode in ["All Tests", "Battery Test"]:
            output_parts.append(format_section("Battery Test", self.latest_data["battery_test"]))
        if view_mode in ["All Tests", "Cranking Test"]:
            output_parts.append(format_section("Cranking Test", self.latest_data["cranking_test"]))
        if view_mode in ["All Tests", "Charging Test"]:
            output_parts.append(format_section("Charging Test", self.latest_data["charging_test"]))

        return "\n\n".join(output_parts)

    def _update_display_view(self, *args):
        """
        Updates the text box with the formatted data based on the current view selection.
        """
        view_mode = self.view_optionmenu.get()
        formatted_text = self._format_display_data(view_mode)
        self.display_textbox.delete("1.0", ctk.END)
        self.display_textbox.insert(ctk.END, formatted_text)

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
            self._update_status("Error listing printers.", "red")
            self._show_error_dialog("Printer Error", f"Could not retrieve the list of printers:\n\n{e}")
            return

        if not printers:
            self._update_status("No printers found on this system.", "red")
            return

        self._show_printer_dialog(printers, content)

    def _show_error_dialog(self, title, message):
        """
        Displays a modal error dialog, centered on the main window.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()

        # --- Position the dialog in the center of the main window ---
        dialog_width = 400
        dialog_height = 150
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()
        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        label = ctk.CTkLabel(dialog, text=message, wraplength=dialog_width - 40)
        label.pack(padx=20, pady=20, expand=True, fill="both")

        ok_button = ctk.CTkButton(dialog, text="OK", command=dialog.destroy, width=100)
        ok_button.pack(pady=10)

    def _show_printer_dialog(self, printers, content):
        """
        Displays a modal dialog for printer selection, centered on the main window.
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Printer")
        dialog.transient(self)
        dialog.grab_set()

        dialog_width, dialog_height = 350, 180
        main_x, main_y = self.winfo_x(), self.winfo_y()
        main_width, main_height = self.winfo_width(), self.winfo_height()
        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        label = ctk.CTkLabel(dialog, text="Choose a printer:")
        label.pack(padx=20, pady=10)

        combo = ctk.CTkComboBox(dialog, values=printers, width=300)
        combo.pack(padx=20, pady=5)
        try:
            combo.set(win32print.GetDefaultPrinter())
        except Exception:
            combo.set(printers[0])

        def on_print():
            self._execute_print(combo.get(), content)
            dialog.destroy()

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=20)
        ctk.CTkButton(button_frame, text="Print", command=on_print, width=100).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy, width=100).pack(side="left", padx=10)

    def _execute_print(self, printer_name, content):
        """
        Sends the content to the specified printer using a temporary file.
        """
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt") as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            win32api.ShellExecute(0, "printto", temp_file_path, f'"{printer_name}"', ".", 0)
            self._update_status(f"Print command sent to {printer_name}.", "green")
            self.after(5000, self._cleanup_temp_file, temp_file_path)

        except Exception as e:
            self._update_status("Printing Error.", "red")
            self._show_error_dialog("Printing Error", f"An error occurred while trying to print:\n\n{e}")

    def _cleanup_temp_file(self, file_path):
        """
        Removes the temporary file after a delay.
        """
        if os.path.exists(file_path):
            os.remove(file_path)


if __name__ == "__main__":
    app = BatteryTesterApp()
    app.mainloop()
