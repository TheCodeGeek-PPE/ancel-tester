# Ancel BA101 Battery Tester serial data parser app

The Ancel BA101 lead-acid Battery Tester is an easy to use and versatile lead-acid battery tester for car, UPS or other similar batteries. The tester has a mini-USB serial output port which can be used to log and report the measured test data. Unfortunately the software that it comes with is proprietary, closed source, runs only on Windows and it cannot be downloaded without making an account on the Ancel website.

This repo builds on [ancel-tester](https://github.com/SilverGreen93/ancel-tester) written by [SilverGreen93](https://github.com/SilverGreen93), which proposes a platform agnostic python3 script which connects to a serial port, receives the data from the Ancel BA101 Battery Tester and displays it in the terminal so that it can be logged and/or printed as needed. It has been included for reference. He did the hard part, so give him some credit.

This app will detect active COM ports on the computer, simplifying COM port selection.

It can be run directly on Windows and Linux (not tested).

Read the Ancel BA101 manual here: [Ancel_BA101_User_manual.pdf](Ancel_BA101_User_manual.pdf)

Official Ancel product page: [https://www.ancel.com/products/ancel-ba101](https://www.ancel.com/products/ancel-ba101)

## Requirements

- Python 3 installed
- Python 3 serial library: `pip install pyserial`
- Python 3 customtkinter library: `pip install customtkinter`

## How to use

1. Connect Ancel BA101 via USB cable to PC.
2. Execute the Python script `ancel_data_print_app.py` and select the COM port from the combobox.
3. Click Connect
4. The script will wait for data to be received.
5. On the Ancel BA101 tester, go to Print Data and press Enter.
6. The data will be displayed in the Window. Copy the output and paste it into a text file for printing. Close the program as you would any other, or click Connect to reconnect to the BA101.

Example:

<img width="462" height="542" alt="image" src="https://github.com/user-attachments/assets/11f6ae6b-88c5-4f58-aeca-ad9ca298d177" />


## Known Bugs
- The status label doesn't properly indicate that the app is connected to the BA101 even when it is. Continue to select *Print Data* on the device, and the data will transfer.
  I think this is because the serial listener is tying things up so that the interface can't update.
  (This may have been fixed by starting the serial listener in it's own thread, I will test Monday, August 25th 2025)

## Serial data format specification

The data format specification was not provided by Ancel, but was manually reverse engineered. Some values might be not right.

| Offset | Raw data example | Decoded data example | Meaning |
| --- | --- | --- | --- |
| 0 | E6 7C | - | Initial marker (?) |
| 2 | 1A | - | ?? |
| 3 | 00 | GOOD | Battery status<br>00: GOOD<br>01: GOOD, RECHARGE<br>02: BAD, REPLACE<br>03: REPLACE<br>04: CHARGE & RETEST |
| 4 | 05 14 | 1300 | Battery voltage x 0.01V |
| 6 | 00 C3 | 195 | Measured amps |
| 8 | 06 1D | 1565 | Internal resistance x 0.01mΩ |
| 10 | 00 64 | 100 | Health percentage |
| 12 | 00 64 | 100 | Charge percentage |
| 14 | 00 87 | 135 | Rated amps (A) |
| 16 | 0A | CA | Selected measuring standard<br>01: CCA<br>02: DIN<br>03: JIS<br>04: EN<br>05: IEC<br>06: GB<br>07: SAE<br>08: MCA<br>09: BCI<br>0A: CA |
| 17 | 01 2C | 300 | Cranking time (ms) |
| 19 | 01 | NORMAL | Cranking status<br>01: NORMAL<br>02: LOW |
| 20 | 03 E8 | 1000 | Cranking voltage x 0.01V |
| 22 | 05 AA | 1450 | Unloaded voltage x 0.01V |
| 24 | 05 6E | 1390 | Loaded voltage x 0.01V |
| 26 | 00 0C | 12 | Ripple (mV) |
| 28 | 01 | LOW | Charging status<br>00: NO OUTPUT<br>01: LOW<br>02: NORMAL<br>03: HIGH |
| 29 | FE 7F | - | Final marker (?) |









