# main.py

import tkinter as tk # Loading GUI
from serial_utils import init_serial # Loading Serial
from ui import LEDMatrixApp # Loads App

def simple_logger(msg, lv="info"):
    # Logs messages to the console with the specified level
    print(f"[{lv.upper()}] {msg}")

def main():
    # Initialize the main Tkinter window
    root = tk.Tk()
    
    try:
        # Attempt to establish a serial connection
        conn = init_serial()
    except Exception as e:
        # Print error message if serial initialization fails
        print("Serial init failed:", e)
        return
    
    # Create the LED Matrix application instance with the logger
    app = LEDMatrixApp(root, conn, logger=simple_logger)
    
    # Ensure the application exits properly when the window is closed
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    
    # Start the Tkinter event loop
    root.mainloop()

if __name__ == "__main__":
    # Run the main function when the script is executed
    main()