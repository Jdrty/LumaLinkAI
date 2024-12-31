# main.py
import tkinter as tk
from serial_utils import init_serial
from ui import LEDMatrixApp

def simple_logger(msg, lv="info"):
    print(f"[{lv.upper()}] {msg}")

def main():
    root = tk.Tk()
    try:
        conn = init_serial()
    except Exception as e:
        print("Serial init failed:", e)
        return
    # Pass logger if you want
    app = LEDMatrixApp(root, conn, logger=simple_logger)
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    root.mainloop()

if __name__=="__main__":
    main()