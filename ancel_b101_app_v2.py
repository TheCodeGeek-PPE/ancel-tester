import os
import tempfile
import customtkinter as ctk
import tkinter as tk
from threading import Thread
from time import sleep
from struct import unpack_from
from serial import Serial, SerialException
import serial.tools.list_ports as st
import platform
import subprocess

# --- New Dependency for Image-based Preview ---
# This implementation requires the Pillow library.
# Pillow is used for the print preview feature.
# You can install it with: pip install Pillow
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow library not found. Please install it using 'pip install Pillow' for the print preview feature.")
    Image = None

# --- Platform-Specific Setup ---
OS_SYSTEM = platform.system()

PYWIN32_AVAILABLE = False
if OS_SYSTEM == "Windows":
    try:
        import win32print
        import win32api
        PYWIN32_AVAILABLE = True
    except ImportError:
        print("pywin32 not found. Printing will be disabled on Windows.")
        PYWIN32_AVAILABLE = False

LINUX_PRINTING_AVAILABLE = False
if OS_SYSTEM == "Linux":
    try:
        # Check if 'lp' command is available
        subprocess.run(['which', 'lp'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        LINUX_PRINTING_AVAILABLE = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("'lp' command not found. Printing will be disabled on Linux.")
        LINUX_PRINTING_AVAILABLE = False


# --- Constants ---
BAUD_RATE = 9600
BYTE_SEQUENCE_LENGTH = 31
WINDOW_WIDTH = 460
WINDOW_HEIGHT = 550
MIN_WINDOW_HEIGHT = 250

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
PAPER_SIZES = {
    "Letter (8.5 x 11 in)": (200, 258),
    "A4 (210 x 297 mm)": (200, 282),
    "Legal (8.5 x 14 in)": (200, 338)
}


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
        self.minsize(WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self.latest_data = None

        self._create_widgets()
        self._set_icon()

    def _set_icon(self):
        """Sets the window icon from a local file based on the OS."""
        icon_file = ""
        if OS_SYSTEM == "Windows":
            icon_file = "Icon.ico"
        elif OS_SYSTEM == "Linux":
            icon_file = "Icon.png" 

        if not icon_file:
            return

        try:
            # Get the directory where the script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(script_dir, icon_file)
            
            if os.path.exists(icon_path):
                if OS_SYSTEM == "Windows":
                    self.iconbitmap(icon_path)
                elif OS_SYSTEM == "Linux":
                    photo = tk.PhotoImage(file=icon_path)
                    self.wm_iconphoto(True, photo)
            else:
                print(f"{icon_file} not found in script directory. Skipping icon set.")
        except Exception as e:
            print(f"Error setting icon: {e}")

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

        port_selection_frame = ctk.CTkFrame(self, fg_color="transparent")
        port_selection_frame.grid(row=0, column=1, padx=0, pady=20, sticky="w")

        self.port_combobox = ctk.CTkComboBox(port_selection_frame, values=self._collect_comports(), width=140)
        self.port_combobox.pack(side="left", padx=(0, 5))

        refresh_button = ctk.CTkButton(port_selection_frame, text="↻", command=self._refresh_comports_callback, width=30)
        refresh_button.pack(side="left")

        self.connect_button = ctk.CTkButton(self, text="Connect", command=self._connect_button_callback)
        self.connect_button.grid(row=0, column=2, padx=20, pady=20, sticky="w")

        # --- Display Frame ---
        display_frame = ctk.CTkFrame(self)
        display_frame.grid(row=1, column=0, padx=20, pady=5, sticky="nsew", columnspan=3)
        display_frame.grid_rowconfigure(1, weight=1)
        display_frame.grid_columnconfigure(0, weight=1)

        output_label = ctk.CTkLabel(display_frame, text="Output")
        output_label.grid(row=0, column=0, padx=5, pady=2, sticky="ew")

        self.display_textbox = ctk.CTkTextbox(display_frame, corner_radius=0)
        self.display_textbox.grid(row=1, column=0, sticky="nsew")

        self.status_label = ctk.CTkLabel(display_frame, text="Status: Not Connected", fg_color="transparent", corner_radius=6)
        self.status_label.grid(row=2, column=0, padx=5, pady=5, sticky="ew")

        # --- Context Menu for Textbox ---
        self.context_menu = tk.Menu(self.display_textbox, tearoff=0, bg="#2B2B2B", fg="white", relief="flat")
        self.context_menu.add_command(label="Copy", command=self._copy_text)
        self.display_textbox.bind("<Button-3>", self._show_context_menu)

        # --- Controls ---
        view_label = ctk.CTkLabel(self, text="Test View:")
        view_label.grid(row=2, column=0, padx=20, pady=10, sticky="e")
        
        self.view_optionmenu = ctk.CTkOptionMenu(self, values=["All Tests", "Battery Test", "Cranking Test", "Charging Test"],
                                                 command=self._update_display_view)
        self.view_optionmenu.grid(row=2, column=1, padx=20, pady=10, sticky="w")

        print_button = ctk.CTkButton(self, text="Print", command=self._print_button_callback)
        print_button.grid(row=2, column=2, padx=20, pady=10, sticky="ew")

        if not ((OS_SYSTEM == "Windows" and PYWIN32_AVAILABLE) or (OS_SYSTEM == "Linux" and LINUX_PRINTING_AVAILABLE)):
            print_button.configure(state="disabled")

    def _show_context_menu(self, event):
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def _copy_text(self):
        try:
            selected_text = self.display_textbox.get("sel.first", "sel.last")
            if selected_text:
                self.clipboard_clear()
                self.clipboard_append(selected_text)
                self._update_status("Text copied to clipboard.", "blue")
        except tk.TclError:
            all_text = self.display_textbox.get("1.0", "end-1c")
            if all_text:
                self.clipboard_clear()
                self.clipboard_append(all_text)
                self._update_status("All text copied to clipboard.", "blue")

    def _collect_comports(self):
        comports = [port.name for port in st.comports()]
        return comports if comports else ["Reconnect BA101"]

    def _refresh_comports_callback(self):
        current_selection = self.port_combobox.get()
        new_ports = self._collect_comports()
        self.port_combobox.configure(values=new_ports)
        if current_selection in new_ports:
            self.port_combobox.set(current_selection)
        elif new_ports:
            self.port_combobox.set(new_ports[0])
        self._update_status("COM port list refreshed.", "blue")

    def _update_status(self, message, color="transparent"):
        self.status_label.configure(text=f"Status: {message}", fg_color=color)

    def _connect_button_callback(self):
        selected_port = self.port_combobox.get()
        if selected_port == "Reconnect BA101":
            self._update_status("Error - Please connect device and click Refresh.", "red")
            return
        self._update_status("Listening for data...", "transparent")
        self._start_serial_listener(selected_port)

    def _start_serial_listener(self, serial_port):
        thread = Thread(target=self._listen_serial, args=(serial_port,))
        thread.daemon = True
        thread.start()

    def _listen_serial(self, serial_port):
        try:
            with Serial(serial_port, BAUD_RATE, timeout=1) as ser:
                while True:
                    data = ser.read(BYTE_SEQUENCE_LENGTH)
                    if len(data) == BYTE_SEQUENCE_LENGTH:
                        self.latest_data = self._parse_battery_data(data)
                        self.after(0, self._update_display_view)
                        self.after(0, self._update_status, "Data received successfully.", "green")
                        break
        except SerialException as e:
            error_str = str(e)
            if "FileNotFoundError" in error_str:
                self.after(0, self._update_status, "Connection Error.", "red")
                self.after(0, self._show_error_dialog, "Connection Error", "Cannot connect. Check device and COM port selection.")
            else:
                self.after(0, self._update_status, "Serial Error.", "red")
                self.after(0, self._show_error_dialog, "Serial Port Error", f"An error occurred:\n\n{e}")

    def _parse_battery_data(self, data):
        if len(data) < BYTE_SEQUENCE_LENGTH:
            return {"error": "Incomplete data received."}
        def u8(o): return unpack_from('>B', data, o)[0]
        def u16(o): return unpack_from('>H', data, o)[0]
        return {
            "battery_test": {"Status": BATTERY_STATUS_TYPES.get(u8(3), "U"),"Voltage": f"{u16(4)/100.:.2f}V","Charge": f"{u16(12)}%","Health": f"{u16(10)}%","Rated": f"{u16(14)}A","Measured": f"{u16(6)}A","Standard": SELECT_INPUT_TYPES.get(u8(16), "U"),"Internal Res": f"{u16(8)/100.:.2f}mΩ"},
            "cranking_test": {"Cranking Time": f"{u16(17)}ms","Cranking Voltage": f"{u16(20)/100.:.2f}V","Cranking Status": CRANKING_STATUS_TYPES.get(u8(19), "U")},
            "charging_test": {"Loaded Voltage": f"{u16(24)/100.:.2f}V","Unloaded Voltage": f"{u16(22)/100.:.2f}V","Ripple": f"{u16(26)}mV","Charging Status": CHARGING_STATUS_TYPES.get(u8(28), "U")}
        }

    def _format_display_data(self, view_mode):
        if not self.latest_data or "error" in self.latest_data:
            return self.latest_data.get("error", "No data available.")
        def format_section(title, data):
            return f"====== {title} ======\n" + "\n".join([f"{k:<17}: {v}" for k, v in data.items()])
        parts = []
        if view_mode in ["All Tests", "Battery Test"]: parts.append(format_section("Battery Test", self.latest_data["battery_test"]))
        if view_mode in ["All Tests", "Cranking Test"]: parts.append(format_section("Cranking Test", self.latest_data["cranking_test"]))
        if view_mode in ["All Tests", "Charging Test"]: parts.append(format_section("Charging Test", self.latest_data["charging_test"]))
        return "\n\n".join(parts)

    def _update_display_view(self, *args):
        view_mode = self.view_optionmenu.get()
        formatted_text = self._format_display_data(view_mode)
        self.display_textbox.delete("1.0", ctk.END)
        self.display_textbox.insert(ctk.END, formatted_text)

    def _get_printers(self):
        if OS_SYSTEM == "Windows" and PYWIN32_AVAILABLE:
            return [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
        elif OS_SYSTEM == "Linux" and LINUX_PRINTING_AVAILABLE:
            try:
                return [l.split()[1] for l in subprocess.check_output(["lpstat", "-p"]).decode("utf-8").strip().split("\n")]
            except Exception as e:
                self._show_error_dialog("Printer Error", f"Could not retrieve printers:\n\n{e}")
        return []

    def _print_button_callback(self):
        if Image is None:
            self._show_error_dialog("Dependency Error", "Pillow library is not installed.\nPlease run 'pip install Pillow' to use this feature.")
            return
            
        content = self.display_textbox.get("1.0", ctk.END)
        if not content.strip():
            self._update_status("No content to print.", "orange")
            return
        printers = self._get_printers()
        if not printers:
            self._update_status("No printers found.", "red")
            return
        self._show_printer_dialog(printers, content)

    def _show_error_dialog(self, title, message):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        w, h = 400, 150
        mx, my, mw, mh = self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height()
        dialog.geometry(f"{w}x{h}+{mx+(mw-w)//2}+{my+(mh-h)//2}")
        ctk.CTkLabel(dialog, text=message, wraplength=w - 40).pack(padx=20, pady=20, expand=True, fill="both")
        ctk.CTkButton(dialog, text="OK", command=dialog.destroy, width=100).pack(pady=10)

    def _show_printer_dialog(self, printers, content):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Print Preview")
        dialog.transient(self)
        dialog.grab_set()

        w, h = 500, 400
        dialog.minsize(w, h)
        mx, my, mw, mh = self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height()
        dialog.geometry(f"{w}x{h}+{mx+(mw-w)//2}+{my+(mh-h)//2}")

        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(padx=10, pady=10, expand=True, fill="both")
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=3)
        main_frame.grid_rowconfigure(0, weight=1)

        controls_frame = ctk.CTkFrame(main_frame)
        controls_frame.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="nsew")
        
        ctk.CTkLabel(controls_frame, text="Printer:").pack(padx=10, pady=(10, 2), anchor="w")
        printer_combo = ctk.CTkComboBox(controls_frame, values=printers, width=200)
        printer_combo.pack(padx=10, pady=(0, 10), fill="x")
        if printers:
            if OS_SYSTEM == "Windows":
                try: printer_combo.set(win32print.GetDefaultPrinter())
                except: printer_combo.set(printers[0])
            else:
                printer_combo.set(printers[0])

        ctk.CTkLabel(controls_frame, text="Paper Size:").pack(padx=10, pady=(10, 2), anchor="w")
        paper_size_combo = ctk.CTkOptionMenu(controls_frame, values=list(PAPER_SIZES.keys()))
        paper_size_combo.pack(padx=10, pady=(0, 10), fill="x")
        paper_size_combo.set("Letter (8.5 x 11 in)")
        
        preview_frame = ctk.CTkFrame(main_frame, fg_color="#A9A9A9")
        preview_frame.grid(row=0, column=1, padx=0, pady=0, sticky="nsew")
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        
        paper_preview = ctk.CTkFrame(preview_frame, fg_color="white", border_width=1, border_color="black")
        paper_preview.grid(row=0, column=0, sticky="")
        paper_preview.grid_propagate(False)
        
        preview_label = ctk.CTkLabel(paper_preview, text="")
        preview_label.pack(expand=True, fill="both")

        dialog.base_preview_image = None

        def _get_monospace_font():
            """Attempts to find a common monospace font."""
            font_size = 18 # High-res font for the base image (decreased from 25)
            if OS_SYSTEM == "Windows":
                font_path = "cour.ttf" # Courier New
            elif OS_SYSTEM == "Linux":
                # Common paths for DejaVu Sans Mono
                possible_paths = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                    "/usr/share/fonts/TTF/DejaVuSansMono.ttf"
                ]
                font_path = next((path for path in possible_paths if os.path.exists(path)), None)
            else: # macOS or other
                font_path = "Courier New.ttf"
            
            try:
                return ImageFont.truetype(font_path, size=font_size)
            except (IOError, FileNotFoundError):
                return ImageFont.load_default()

        def _generate_base_image():
            """Generates a high-resolution base image of the text content."""
            HI_RES_WIDTH = 800
            base_width, base_height = PAPER_SIZES[paper_size_combo.get()]
            aspect_ratio = base_height / base_width
            HI_RES_HEIGHT = int(HI_RES_WIDTH * aspect_ratio)

            img = Image.new('RGB', (HI_RES_WIDTH, HI_RES_HEIGHT), color='white')
            draw = ImageDraw.Draw(img)
            font = _get_monospace_font()
            
            padding = int(HI_RES_WIDTH * 0.08)
            draw.text((padding, padding), content, fill='black', font=font)
            dialog.base_preview_image = img

        def _resize_preview_page(event=None):
            """Resizes the preview image smoothly."""
            if not dialog.base_preview_image:
                return

            padding = 20
            container_width = preview_frame.winfo_width() - padding
            container_height = preview_frame.winfo_height() - padding
            
            if container_width < 1 or container_height < 1:
                return

            base_width, base_height = PAPER_SIZES[paper_size_combo.get()]
            aspect_ratio = base_width / base_height

            new_width = container_width
            new_height = new_width / aspect_ratio
            if new_height > container_height:
                new_height = container_height
                new_width = new_height * aspect_ratio
            
            new_width, new_height = int(new_width), int(new_height)
            paper_preview.configure(width=new_width, height=new_height)
            
            if new_width > 0 and new_height > 0:
                resized_pil_img = dialog.base_preview_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                ctk_image = ctk.CTkImage(light_image=resized_pil_img, size=(new_width, new_height))
                preview_label.configure(image=ctk_image)
                preview_label.image = ctk_image # Keep a reference

        def _update_on_paper_change(size_key):
            """Regenerates base image and resizes preview when paper size changes."""
            _generate_base_image()
            _resize_preview_page()

        _generate_base_image()
        preview_frame.bind("<Configure>", _resize_preview_page)
        paper_size_combo.configure(command=_update_on_paper_change)
        dialog.after(100, _resize_preview_page) # Initial resize

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=10)
        
        def on_print():
            self._execute_print(printer_combo.get(), content, paper_size_combo.get())
            dialog.destroy()

        ctk.CTkButton(button_frame, text="Print", command=on_print, width=100).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy, width=100).pack(side="left", padx=10)

    def _execute_print(self, printer_name, content, paper_size_key):
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt") as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            if OS_SYSTEM == "Windows":
                win32api.ShellExecute(0, "printto", temp_file_path, f'"{printer_name}"', ".", 0)
            elif OS_SYSTEM == "Linux":
                linux_paper_size = paper_size_key.split()[0]
                subprocess.run(["lp", "-d", printer_name, "-o", f"media={linux_paper_size}", temp_file_path], check=True)

            self._update_status(f"Print command sent to {printer_name}.", "green")
            self.after(5000, self._cleanup_temp_file, temp_file_path)

        except Exception as e:
            self._update_status("Printing Error.", "red")
            self._show_error_dialog("Printing Error", f"An error occurred while printing:\n\n{e}")

    def _cleanup_temp_file(self, file_path):
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    app = BatteryTesterApp()
    app.mainloop()
