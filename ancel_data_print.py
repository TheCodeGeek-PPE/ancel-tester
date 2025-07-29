import serial
import struct
import time
import argparse
import sys

# Configuration
BAUD_RATE = 9600
BYTE_SEQUENCE_LENGTH = 31  # Expected length of message

def parse_battery_data(data):
    if len(data) < BYTE_SEQUENCE_LENGTH:
        return "Incomplete data received."

    def u8(offset):
        return struct.unpack_from('>B', data, offset)[0]
    
    def u16(offset):
        return struct.unpack_from('>H', data, offset)[0]

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
    print(f"Opening serial port {serial_port} at {baud_rate} baud...")
    try:
        with serial.Serial(serial_port, baud_rate, timeout=1) as ser:
            print("Listening for data... Press Ctrl+C to stop.\n")
            while True:
                data = ser.read(BYTE_SEQUENCE_LENGTH)
                if len(data) == BYTE_SEQUENCE_LENGTH:
                    print(parse_battery_data(data))
                time.sleep(1)
    except serial.SerialException as e:
        print(f"Serial error: {e}")


if __name__ == "__main__":
    print("Ancel BA101 Battery Tester serial data parser.")
    parser = argparse.ArgumentParser(description="Battery data parser from serial port.")
    parser.add_argument("serial_port", nargs="?", help="Serial port to listen to (e.g.: /dev/ttyUSB0, COM3).")
    args = parser.parse_args()

    if not args.serial_port:
        print("Error: Serial port argument is required.")
        parser.print_help()
        sys.exit(1)

    try:
        listen_serial(args.serial_port)
    except KeyboardInterrupt:
        print("\nStopped by user.")
