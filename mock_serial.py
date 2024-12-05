# mock_serial.py
import time
import threading

class MockSerial:
    def __init__(self, port, baudrate=9600, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.in_buffer = []
        self.out_buffer = []
        self.is_open = True
        print(f"MockSerial initialized on port {port} with baudrate {baudrate}.")

    def write(self, data):
        print(f"MockSerial writing data: {data}")
        # Simulate immediate acknowledgment
        threading.Thread(target=self._simulate_ack, args=(data,)).start()

    def _simulate_ack(self, data):
        time.sleep(0.5)  # Simulate processing delay
        if data[0] == 0xFF and data[-1] == 0xFE:
            self.in_buffer.append(b"Pattern received.\n")
        elif data[0] == 0xFA and data[-1] == 0xFB:
            self.in_buffer.append(b"Animation received.\n")
        else:
            self.in_buffer.append(b"Unknown command received.\n")

    def read(self, size=1):
        if self.in_buffer:
            data = self.in_buffer.pop(0)
            return data
        return b''

    def readline(self):
        if self.in_buffer:
            data = self.in_buffer.pop(0)
            return data
        return b''

    def close(self):
        self.is_open = False
        print("MockSerial connection closed.")

    @property
    def in_waiting(self):
        return len(self.in_buffer) > 0