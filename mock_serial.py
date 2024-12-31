# mock_serial.py

import time
import threading

class MockSerial:
    # Initialize the mock serial connection with given parameters
    def __init__(self, port, baudrate=9600, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.in_buffer = []   # Buffer to store incoming data
        self.out_buffer = []  # Buffer to store outgoing data (not used here)
        self.is_open = True
        print(f"MockSerial initialized on port {port} with baudrate {baudrate}.")

    # Simulate writing data to the serial port
    def write(self, data):
        print(f"MockSerial writing data: {data}")
        # Start a new thread to simulate acknowledgment after a delay
        threading.Thread(target=self._simulate_ack, args=(data,)).start()

    # Private method to simulate an acknowledgment based on the received data
    def _simulate_ack(self, data):
        time.sleep(0.5)  # Simulate processing delay
        if data[0] == 0xFF and data[-1] == 0xFE:
            # If data starts with 0xFF and ends with 0xFE, acknowledge pattern received
            self.in_buffer.append(b"Pattern received.\n")
        elif data[0] == 0xFA and data[-1] == 0xFB:
            # If data starts with 0xFA and ends with 0xFB, acknowledge animation received
            self.in_buffer.append(b"Animation received.\n")
        else:
            # For any other data, acknowledge unknown command
            self.in_buffer.append(b"Unknown command received.\n")

    # Simulate reading a specific number of bytes from the serial port
    def read(self, size=1):
        if self.in_buffer:
            data = self.in_buffer.pop(0)
            return data
        return b''

    # Simulate reading a line from the serial port
    def readline(self):
        if self.in_buffer:
            data = self.in_buffer.pop(0)
            return data
        return b''

    # Simulate closing the serial connection
    def close(self):
        self.is_open = False
        print("MockSerial connection closed.")

    # Property to check if there is data waiting in the input buffer
    @property
    def in_waiting(self):
        return len(self.in_buffer) > 0