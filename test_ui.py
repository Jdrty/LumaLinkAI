import unittest
import tkinter as tk
from ui import LEDMatrixApp, ACTIVE_COLOR, INACTIVE_COLOR

class DummySerial:
    def write(self, data): pass
    def close(self): pass

class DummyLogger:
    def __call__(self, msg, lv="info"): pass

class DummyCanvas:
    def __init__(self):
        self.items = {}
    def create_oval(self, x1, y1, x2, y2, fill, outline):
        # Create a dummy LED representation
        item_id = len(self.items) + 1
        self.items[item_id] = {"fill": fill}
        return item_id
    def itemconfig(self, item_id, fill):
        if item_id in self.items:
            self.items[item_id]["fill"] = fill

class TestUILogic(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        # Use DummySerial and DummyLogger to avoid actual serial calls and logging.
        self.app = LEDMatrixApp(self.root, DummySerial(), logger=DummyLogger())
        # Replace the actual canvas with a dummy canvas for testing LED updates.
        self.dummy_canvas = DummyCanvas()
        self.app.canvas = self.dummy_canvas
        # Pre-populate dummy LEDs to simulate the grid.
        self.app.leds = [[self.dummy_canvas.create_oval(0,0,0,0, fill=INACTIVE_COLOR, outline="") 
                         for _ in range(8)] for _ in range(8)]

    def tearDown(self):
        self.root.destroy()

    def test_update_leds(self):
        # Create a pattern with alternating bits.
        pattern = [0b10101010 for _ in range(8)]
        self.app.update_leds(pattern)
        for r in range(8):
            for c in range(8):
                expected = ACTIVE_COLOR if ((pattern[r] >> (7-c)) & 1) == 1 else INACTIVE_COLOR
                item_id = self.app.leds[r][c]
                self.assertEqual(self.dummy_canvas.items[item_id]["fill"], expected)

if __name__ == '__main__':
    unittest.main()