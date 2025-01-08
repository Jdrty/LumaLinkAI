# serial_utils.py

import os # Allows Script to Manage Directories in Operating System
import sys # Allows System Interaction
import glob # File Pattern Matching
import time # Time Utils for Delays
import threading # Concurrency control
import serial # Allows Script to Access Serial Ports

# Toggle this if you want to test without a real Arduino
USE_MOCK_SERIAL = True

class MockSerial:
    # Initialize the mock serial connection
    def __init__(self):
        self.received_data = []
        print("[MockSerial] Initialized")

    # Simulate writing data to the serial port
    def write(self, data):
        print("[MockSerial] Writing:", data)
        # If the data starts with a pattern or animation marker, send an acknowledgment after 0.5 seconds
        if data and data[0] in (0xFF, 0xFA):
            threading.Timer(0.5, self.mock_ack, args=(data[0],)).start()

    # Mock acknowledgment callback
    def mock_ack(self, marker):
        ack_type = "Pattern" if marker == 0xFF else "Animation"
        print(f"[MockSerial] Ack: {ack_type}")

    # Mock reading a line from the serial port
    def readline(self):
        return b"Pattern received.\n"

    # Mock flushing the serial buffer (no operation)
    def flush(self):
        pass

    # Mock closing the serial connection
    def close(self):
        print("[MockSerial] Closing")

def find_arduino_port():
    # Define possible serial port patterns for different operating systems
    patterns = ['/dev/cu.usbserial*', '/dev/ttyUSB*', '/dev/ttyACM*', 'COM3', 'COM4']
    ports = []
    for pat in patterns:
        ports += glob.glob(pat)
    if not ports:
        raise Exception("No Arduino port found.")
    if len(ports) > 1:
        raise Exception("Multiple ports found.")
    return ports[0]

def init_serial():
    # Initialize the serial connection, using MockSerial if enabled
    global USE_MOCK_SERIAL
    if USE_MOCK_SERIAL:
        return MockSerial()
    try:
        port = find_arduino_port()
        ser = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)  # Wait for the serial connection to initialize
        return ser
    except Exception as e:
        if USE_MOCK_SERIAL:
            print("[Error]", e, "Using MockSerial anyway.")
            return MockSerial()
        else:
            raise e

def send_frame(ser, pattern, logger=None, update_preview=None):
    # Send a single frame pattern to the serial device
    if len(pattern) != 8:
        if logger:
            logger("Pattern must have exactly 8 bytes.")
        return
    try:
        ser.write(bytes([0xFF]))  # Start single frame marker
        for b in pattern:
            ser.write(bytes([b]))  # Write each byte of the pattern
        ser.write(bytes([0xFE]))  # End single frame marker
        if update_preview:
            update_preview(pattern, animation=False)
    except Exception as e:
        if logger:
            logger(f"Serial error: {e}")

def send_animation(ser, frames, logger=None, max_frames=10):
    # Send an animation consisting of multiple frames to the serial device
    frame_count = len(frames)
    if frame_count < 1 or frame_count > max_frames:
        if logger:
            logger(f"Animation must have between 1 and {max_frames} frames.")
        return
    try:
        ser.write(bytes([0xFA, frame_count]))  # Start animation marker and frame count
        for frame in frames:
            for byte in frame:
                ser.write(bytes([byte]))  # Write each byte of the frame
        ser.write(bytes([0xFB]))  # End animation marker
    except Exception as e:
        if logger:
            logger(f"Serial error: {e}")