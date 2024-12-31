# serial_utils.py
import os, sys, glob, time, threading
import serial

USE_MOCK_SERIAL = False  # Toggle this if you want to test without real Arduino.

class MockSerial:
    def __init__(self):
        self.received_data=[]
        print("[MockSerial] Initialized")

    def write(self, data):
        print("[MockSerial] Writing:", data)
        if data and data[0] in (0xFF, 0xFA):
            threading.Timer(0.5,self.mock_ack,args=(data[0],)).start()

    def mock_ack(self, t):
        print(f"[MockSerial] Ack: {'Pattern' if t==0xFF else 'Animation'}")

    def readline(self):
        return b"Pattern received.\n"

    def flush(self):
        pass

    def close(self):
        print("[MockSerial] Closing")

def find_arduino_port():
    patterns = ['/dev/cu.usbserial*','/dev/ttyUSB*','/dev/ttyACM*','COM3','COM4']
    ports = []
    for pat in patterns:
        ports+=glob.glob(pat)
    if not ports:
        raise Exception("No Arduino port found.")
    if len(ports)>1:
        raise Exception("Multiple ports found.")
    return ports[0]

def init_serial():
    global USE_MOCK_SERIAL
    if USE_MOCK_SERIAL:
        return MockSerial()
    try:
        port = find_arduino_port()
        ser = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)
        return ser
    except Exception as e:
        if USE_MOCK_SERIAL:
            print("[Error]", e, "Using MockSerial anyway.")
            return MockSerial()
        else:
            raise e

def send_frame(ser, pattern, logger=None, update_preview=None):
    if len(pattern)!=8:
        if logger: logger("Pattern must have exactly 8 bytes.")
        return
    try:
        ser.write(bytes([0xFF]))
        for b in pattern:
            ser.write(bytes([b]))
        ser.write(bytes([0xFE]))
        if update_preview:
            update_preview(pattern, animation=False)
    except Exception as e:
        if logger:
            logger(f"Serial error: {e}")

def send_animation(ser, frames, logger=None, max_frames=10):
    c = len(frames)
    if c<1 or c>max_frames:
        if logger: logger(f"Animation must have 1..{max_frames} frames.")
        return
    try:
        ser.write(bytes([0xFA, c]))
        for fr in frames:
            for b in fr:
                ser.write(bytes([b]))
        ser.write(bytes([0xFB]))
    except Exception as e:
        if logger:
            logger(f"Serial error: {e}")