# serial_utils.py - Handles serial communication with LED matrix hardware
import os
import sys
import glob
import time
import threading
import serial

# Enable mock mode for testing without hardware
USE_MOCK_SERIAL = True

class MockSerial:
    def __init__(self):
        self.received_data = []
        print("[MockSerial] Initialized")

    def write(self, data):
        print("[MockSerial] Writing:", data)
        # Acknowledgment for pattern/animation commands
        if data and data[0] in (0xFF, 0xFA):
            threading.Timer(0.5, self.mock_ack, args=(data[0],)).start()

    def mock_ack(self, marker):
        ack_type = "Pattern" if marker == 0xFF else "Animation"
        print(f"[MockSerial] Ack: {ack_type}")

    def readline(self):
        return b"Pattern received.\n"

    def flush(self):
        pass

    def close(self):
        print("[MockSerial] Closing")

def find_arduino_port():
    # Search common serial port patterns across operating systems
    patterns = [
        '/dev/cu.usbserial*',
        '/dev/ttyUSB*',
        '/dev/ttyACM*',
        'COM3',
        'COM4'
    ]
    ports = []
    for pat in patterns:
        ports += glob.glob(pat)
    
    if not ports:
        raise Exception("No Arduino port found.")
    if len(ports) > 1:
        raise Exception("Multiple ports found.")
    return ports[0]

def init_serial():
    # Set up serial connection or fallback to mock mode
    global USE_MOCK_SERIAL
    if USE_MOCK_SERIAL:
        return MockSerial()
        
    try:
        port = find_arduino_port()
        ser = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)  # Arduino reset delay
        return ser
    except Exception as e:
        if USE_MOCK_SERIAL:
            print("[Error]", e, "Using MockSerial anyway.")
            return MockSerial()
        else:
            raise e

def send_frame(ser, pattern, logger=None, update_preview=None):
    # Protocol: 0xFF (start) + 8 bytes (pattern) + 0xFE (end)
    if len(pattern) != 8:
        if logger:
            logger("Pattern must have exactly 8 bytes.")
        return
        
    try:
        ser.write(bytes([0xFF]))  # Start marker
        for b in pattern:
            ser.write(bytes([b]))
        ser.write(bytes([0xFE]))  # End marker
        
        if update_preview:
            update_preview(pattern, animation=False)
    except Exception as e:
        if logger:
            logger(f"Serial error: {e}")

def send_animation(ser, frames, logger=None, max_frames=10):
    # Protocol: 0xFA (start) + frame_count + frames + 0xFB (end)
    frame_count = len(frames)
    if frame_count < 1 or frame_count > max_frames:
        if logger:
            logger(f"Animation must have between 1 and {max_frames} frames.")
        return
        
    try:
        ser.write(bytes([0xFA, frame_count]))
        for frame in frames:
            for byte in frame:
                ser.write(bytes([byte]))
        ser.write(bytes([0xFB]))
    except Exception as e:
        if logger:
            logger(f"Serial error: {e}")