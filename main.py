# main.py - LED Matrix Controller Application

import tkinter as tk  # Loading GUI
from serial_utils import init_serial  # Loading Serial
from ui import LEDMatrixApp  # Loads App

def simple_logger(msg, lv="info"):
    # Basic logging function
    print(f"[{lv.upper()}] {msg}")

def main():
    # Initialize main window
    root = tk.Tk()
    
    try:
        # Setup serial connection
        conn = init_serial()
    except Exception as e:
        print("Serial init failed:", e)
        return
    
    # Create LED Matrix app
    app = LEDMatrixApp(root, conn, logger=simple_logger)
    
    # Clean exit handler
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    
    root.mainloop()

if __name__ == "__main__":
    main()