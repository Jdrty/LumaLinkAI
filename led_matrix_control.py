import os
import serial
import time
import openai
import re
import sys
import glob
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from tkinter import font as tkfont
from dotenv import load_dotenv
import threading
import json

# Constants for LED Matrix
LED_SIZE = 30  # Diameter of each LED
LED_PADDING = 5  # Padding between LEDs
ON_COLOR = "#FF0000"  # Red color for ON state
OFF_COLOR = "#330000"  # Dark red for OFF state
ANIMATION_DELAY = 500  # Milliseconds between animation frames

# Load API Key from .env
load_dotenv()

# Function to find Arduino serial port
def find_arduino_port():
    # Modify this pattern based on your OS and Arduino connection
    patterns = ['/dev/cu.usbserial*', '/dev/ttyUSB*', '/dev/ttyACM*', 'COM3', 'COM4']
    ports = []
    for pattern in patterns:
        ports.extend(glob.glob(pattern))
    if not ports:
        raise SerialException("No Arduino serial ports found. Please check the connection.")
    if len(ports) > 1:
        raise SerialException("Multiple serial ports found. Please specify the correct one.")
    return ports[0]

# Custom Exception for serial errors
class SerialException(Exception):
    pass

# Import MockSerial if USE_MOCK_SERIAL is set, else use serial.Serial
USE_MOCK_SERIAL = os.getenv('USE_MOCK_SERIAL', 'false').lower() in ['true', '1', 'yes']

if USE_MOCK_SERIAL:
    try:
        from mock_serial import MockSerial as SerialClass
        print("Using MockSerial for testing.")
    except ImportError:
        print("mock_serial module not found. Please ensure it's available for testing.")
        sys.exit(1)
else:
    try:
        SerialClass = serial.Serial
    except ImportError:
        print("pyserial is not installed.")
        sys.exit(1)

# Initialize Serial Communication
def initialize_serial():
    if USE_MOCK_SERIAL:
        ser = SerialClass(port='COM3', baudrate=9600, timeout=1)  # Port name is arbitrary for mock
    else:
        arduino_port = find_arduino_port()
        print(f"Connecting to Arduino on port: {arduino_port}")
        try:
            ser = SerialClass(port=arduino_port, baudrate=9600, timeout=1)
        except serial.SerialException as e:
            raise SerialException(f"Failed to connect to {arduino_port}: {e}")
        time.sleep(2)  # Wait for the serial connection to initialize
    return ser

# API key setup
api_key = os.getenv('GLHF_API_KEY')
if not api_key:
    print("Error: GLHF_API_KEY not found in environment variables.")
    sys.exit(1)

openai.api_key = api_key
openai.api_base = 'https://glhf.chat/api/openai/v1'

# Function to sanitize filenames
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]',"", filename)

# Function to generate patterns from AI
def generate_patterns_from_ai(prompt, animation=False, num_frames=5, log_callback=None):
    max_attempts = 3
    attempt = 0
    patterns = []
    while attempt < max_attempts:
        try:
            if not animation:
                # Single frame
                response = openai.ChatCompletion.create(
                    model='hf:meta-llama/Meta-Llama-3.1-405B-Instruct',
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": (
                            "Generate exactly 8 integers between 0 and 255 (inclusive), "
                            "each representing a row of an 8x8 LED matrix pattern for '{}'. "
                            "Provide only the list of 8 integers separated by commas on a single line, "
                            "with no additional text, explanations, or characters."
                        ).format(prompt)}
                    ]
                )
                pattern_text = response.choices[0].message.content.strip()
                if log_callback:
                    log_callback(f"Raw AI Response (Attempt {attempt + 1}): {pattern_text}")

                # Process pattern
                pattern_text = re.sub(r'[\[\]]', '', pattern_text)
                numbers = re.split(r'[,\s]+', pattern_text)
                numbers = [num for num in numbers if num.isdigit()]
                if len(numbers) >= 8:
                    pattern = [int(num) for num in numbers[:8]]
                    if all(0 <= num <= 255 for num in pattern):
                        return pattern
                    else:
                        if log_callback:
                            log_callback(f"Attempt {attempt + 1}: Pattern values out of range. Retrying...")
                else:
                    if log_callback:
                        log_callback(f"Attempt {attempt + 1}: Invalid pattern received. Retrying...")
            else:
                # Animation: Generate multiple frames
                for frame_num in range(num_frames):
                    response = openai.ChatCompletion.create(
                        model='hf:meta-llama/Meta-Llama-3.1-405B-Instruct',
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": (
                                "Generate exactly 8 integers between 0 and 255 (inclusive), "
                                "each representing a row of an 8x8 LED matrix pattern for frame {} of an animation about '{}'. "
                                "Provide only the list of 8 integers separated by commas on a single line, "
                                "with no additional text, explanations, or characters."
                            ).format(frame_num + 1, prompt)}
                        ]
                    )
                    pattern_text = response.choices[0].message.content.strip()
                    if log_callback:
                        log_callback(f"Raw AI Response for Frame {frame_num + 1} (Attempt {attempt + 1}): {pattern_text}")

                    # Process pattern
                    pattern_text = re.sub(r'[\[\]]', '', pattern_text)
                    numbers = re.split(r'[,\s]+', pattern_text)
                    numbers = [num for num in numbers if num.isdigit()]
                    if len(numbers) >= 8:
                        pattern = [int(num) for num in numbers[:8]]
                        if all(0 <= num <= 255 for num in pattern):
                            patterns.append(pattern)
                        else:
                            if log_callback:
                                log_callback(f"Attempt {attempt + 1}: Pattern values out of range in frame {frame_num + 1}. Retrying...")
                            patterns = []
                            break
                    else:
                        if log_callback:
                            log_callback(f"Attempt {attempt + 1}: Invalid pattern received in frame {frame_num + 1}. Retrying...")
                        patterns = []
                        break
                if patterns:
                    return patterns
        except openai.error.OpenAIError as e:
            if log_callback:
                log_callback(f"OpenAI API error: {e}")
            return None

        attempt += 1
    if log_callback:
        log_callback("Error: Failed to generate valid pattern(s) after multiple attempts.")
    return None

# Function to send single pattern
def send_single_pattern(ser, pattern, log_callback=None, preview_callback=None):
    if len(pattern) != 8:
        if log_callback:
            log_callback("Error: Pattern must have 8 integers.")
        return
    try:
        ser.write(bytes([0xFF]))  # Start marker for single frame
        ser.flush()
        for byte in pattern:
            ser.write(bytes([byte]))
        ser.write(bytes([0xFE]))  # End marker for single frame
        ser.flush()
        time.sleep(0.1)
        # Wait for acknowledgment
        ack_received = False
        start_time = time.time()
        while not ack_received and (time.time() - start_time) < 5:  # Timeout after 5 seconds
            if ser.in_waiting:
                ack = ser.readline().decode().strip()
                if log_callback:
                    log_callback(f"Acknowledgment from serial: {ack}")
                if ack == "Pattern received.":
                    ack_received = True
        if not ack_received:
            if log_callback:
                log_callback("No acknowledgment received for single pattern.")
        # Update preview
        if preview_callback:
            preview_callback(pattern, animation=False)
    except serial.SerialException as e:
        if log_callback:
            log_callback(f"Serial communication error: {e}")

# Function to send animation
def send_animation(ser, patterns, log_callback=None, preview_callback=None):
    num_frames = len(patterns)
    if num_frames == 0:
        if log_callback:
            log_callback("Error: No frames to send.")
        return
    if num_frames > 10:
        if log_callback:
            log_callback(f"Error: Number of frames ({num_frames}) exceeds MAX_FRAMES (10).")
        return
    try:
        ser.write(bytes([0xFA]))  # Start marker for animation
        ser.flush()
        ser.write(bytes([num_frames]))  # Number of frames
        ser.flush()
        for pattern in patterns:
            for byte in pattern:
                ser.write(bytes([byte]))
        ser.write(bytes([0xFB]))  # End marker for animation
        ser.flush()
        time.sleep(0.1)
        # Wait for acknowledgment
        ack_received = False
        start_time = time.time()
        while not ack_received and (time.time() - start_time) < 5:  # Timeout after 5 seconds
            if ser.in_waiting:
                ack = ser.readline().decode().strip()
                if log_callback:
                    log_callback(f"Acknowledgment from serial: {ack}")
                if ack in ["Animation received.", "Invalid end marker received."]:
                    ack_received = True
        if not ack_received:
            if log_callback:
                log_callback("No acknowledgment received for animation.")
        # Play animation in preview
        if preview_callback:
            threading.Thread(target=play_animation_preview, args=(patterns, preview_callback), daemon=True).start()
    except serial.SerialException as e:
        if log_callback:
            log_callback(f"Serial communication error: {e}")

# Function to play animation in preview
def play_animation_preview(patterns, preview_callback):
    for pattern in patterns:
        preview_callback(pattern, animation=True)
        time.sleep(ANIMATION_DELAY / 1000)  # Convert ms to seconds

# Function to save a single pattern
def save_pattern(pattern, name=None, overwrite=False):
    # Define the directory to save patterns and animations
    script_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(script_dir, "saved_patterns")
    os.makedirs(save_dir, exist_ok=True)  # Create the directory if it doesn't exist

    if not name:
        # Generate a default name based on timestamp
        name = f"pattern_{int(time.time())}.json"
    else:
        # Sanitize filename and append .json
        name = sanitize_filename(name) + '.json'

    file_path = os.path.join(save_dir, name)

    # Check if file exists
    if os.path.exists(file_path) and not overwrite:
        # Prompt user to replace or cancel
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        replace = messagebox.askyesno("File Exists", f"The file '{name}' already exists. Do you want to replace it?")
        root.destroy()
        if not replace:
            return None  # Cancel saving

    data = {
        'type': 'single',
        'pattern': pattern
    }
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        return file_path
    except Exception as e:
        return None

# Function to save an animation
def save_animation(patterns, name=None, overwrite=False):
    # Define the directory to save patterns and animations
    script_dir = os.path.dirname(os.path.abspath(__file__))
    save_dir = os.path.join(script_dir, "saved_patterns")
    os.makedirs(save_dir, exist_ok=True)  # Create the directory if it doesn't exist

    if not name:
        # Generate a default name based on timestamp
        name = f"animation_{int(time.time())}.json"
    else:
        # Sanitize filename and append .json
        name = sanitize_filename(name) + '.json'

    file_path = os.path.join(save_dir, name)

    # Check if file exists
    if os.path.exists(file_path) and not overwrite:
        # Prompt user to replace or cancel
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        replace = messagebox.askyesno("File Exists", f"The file '{name}' already exists. Do you want to replace it?")
        root.destroy()
        if not replace:
            return None  # Cancel saving

    data = {
        'type': 'animation',
        'patterns': patterns
    }
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        return file_path
    except Exception as e:
        return None

# Function to load a saved pattern or animation
def load_saved_file(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data

# GUI Application Class
class LEDMatrixApp:
    def __init__(self, master):
        self.master = master
        master.title("LED Matrix Controller")
        master.geometry("1300x1000")
        master.resizable(True, True)

        # Define color scheme
        self.bg_color = "#121212"        # Dark background
        self.accent_color = "#bb86fc"    # Vibrant accent
        self.text_color = "#ffffff"      # White text
        self.button_color = "#1f1f1f"    # Button background
        self.entry_bg = "#1f1f1f"        # Entry background
        self.entry_fg = "#ffffff"        # Entry text
        self.error_color = "#cf6679"     # Error messages
        self.success_color = "#03dac6"   # Success messages

        master.configure(bg=self.bg_color)

        # Define fonts
        self.font_title = tkfont.Font(family="Helvetica", size=16, weight="bold")
        self.font_labels = tkfont.Font(family="Helvetica", size=12)
        self.font_buttons = tkfont.Font(family="Helvetica", size=12, weight="bold")
        self.font_log = tkfont.Font(family="Helvetica", size=10)

        # Create GUI Components first
        self.create_widgets()

        # Initialize Serial
        try:
            self.ser = initialize_serial()
            self.log("Serial connection established.", "info")
        except SerialException as e:
            messagebox.showerror("Serial Connection Error", str(e))
            self.log(str(e), "error")
            sys.exit(1)

        # Initialize LED Matrix Preview
        self.create_led_matrix_preview()

        # Initialize current file path
        self.current_file_path = None

    def create_widgets(self):
        # Main Frame
        main_frame = ttk.Frame(self.master, padding="20 20 20 20")
        main_frame.grid(row=0, column=0, sticky='NSEW')

        # Configure grid weights for responsiveness
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=3)

        # Style configuration
        style = ttk.Style()
        style.theme_use('clam')  # Use 'clam' theme as a base

        # Custom styles
        style.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=self.font_labels)
        style.configure("TButton",
                        background=self.button_color,
                        foreground=self.text_color,
                        font=self.font_buttons,
                        borderwidth=0,
                        focuscolor='none')
        style.map("TButton",
                  background=[('active', self.accent_color)],
                  foreground=[('active', self.text_color)])
        style.configure("TEntry",
                        fieldbackground=self.entry_bg,
                        foreground=self.entry_fg,
                        font=self.font_labels,
                        borderwidth=2,
                        relief="groove")
        style.configure("TScrolledText",
                        background=self.entry_bg,
                        foreground=self.text_color,
                        font=self.font_log,
                        borderwidth=2,
                        relief="groove")

        # Description Label and Entry with increased margin
        desc_label = ttk.Label(main_frame, text="Pattern Description:")
        desc_label.grid(row=0, column=0, padx=(0, 10), pady=(0, 5), sticky='w')

        self.desc_entry = ttk.Entry(main_frame, width=60)
        self.desc_entry.grid(row=0, column=1, padx=(0, 0), pady=(0, 5), sticky='w')
        self.desc_entry.focus()

        # Add border and shadow to entry (simulated with padding and background)
        self.desc_entry.configure(style="TEntry")

        # Button Frame with proper spacing and grouping
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=(10, 10), sticky='w')

        # Generate Single Pattern Button
        self.single_btn = ttk.Button(button_frame, text="Generate Single Pattern", command=self.generate_single_pattern)
        self.single_btn.grid(row=0, column=0, padx=(0, 20), pady=5, sticky='w')
        self.single_btn.configure(state='disabled')  # Initially disabled

        # Generate Animation Button
        self.animate_btn = ttk.Button(button_frame, text="Generate Animation", command=self.generate_animation)
        self.animate_btn.grid(row=0, column=1, padx=(0, 20), pady=5, sticky='w')
        self.animate_btn.configure(state='disabled')  # Initially disabled

        # Load Button (for both patterns and animations)
        self.load_btn = ttk.Button(button_frame, text="Load Pattern/Animation", command=self.load_ui)
        self.load_btn.grid(row=0, column=2, padx=(0, 20), pady=5, sticky='w')
        self.load_btn.configure(state='disabled')  # Initially disabled

        # Edit Button
        self.edit_btn = ttk.Button(button_frame, text="Edit", command=self.edit_current, state='disabled')
        self.edit_btn.grid(row=0, column=3, padx=(0, 20), pady=5, sticky='w')

        # Publish Button
        self.publish_btn = ttk.Button(button_frame, text="Publish", command=self.publish_current, state='disabled')
        self.publish_btn.grid(row=0, column=4, padx=(0, 20), pady=5, sticky='w')

        # Exit Button grouped separately
        exit_btn = ttk.Button(button_frame, text="Exit", command=self.exit_application)
        exit_btn.grid(row=0, column=5, padx=(100, 0), pady=5, sticky='e')

        # Add tooltips
        self.create_tooltip(self.single_btn, "Generate and send a single LED pattern based on the description.")
        self.create_tooltip(self.animate_btn, "Generate and send an animation with multiple LED patterns based on the description.")
        self.create_tooltip(self.load_btn, "Load a saved pattern or animation to display on the LED matrix.")
        self.create_tooltip(self.edit_btn, "Edit the current pattern or animation.")
        self.create_tooltip(self.publish_btn, "Publish the edited pattern or animation to the Arduino.")
        self.create_tooltip(exit_btn, "Close the application.")

        # Bind keyboard shortcuts
        self.master.bind('<Control-g>', lambda event: self.generate_single_pattern())
        self.master.bind('<Control-a>', lambda event: self.generate_animation())
        self.master.bind('<Control-l>', lambda event: self.load_ui())
        self.master.bind('<Control-e>', lambda event: self.exit_application())

        # Log Label
        log_label = ttk.Label(main_frame, text="Logs:")
        log_label.grid(row=2, column=0, padx=(0, 10), pady=(10, 5), sticky='w')

        # Log Text Area with scrollbar
        self.log_area = scrolledtext.ScrolledText(main_frame, width=80, height=25, state='disabled', wrap='word')
        self.log_area.grid(row=3, column=0, columnspan=2, padx=(0, 0), pady=(0, 10), sticky='nsew')

        # Configure grid to make log_area expand
        main_frame.rowconfigure(3, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Bind event to enable/disable buttons based on input
        self.desc_entry.bind('<KeyRelease>', self.check_input)

        # Initialize variables to store the last generated patterns
        self.current_pattern = None
        self.current_animation = None
        self.is_animation = False
        self.current_file_path = None  # To track the currently loaded file

    def create_led_matrix_preview(self):
        """
        Creates an 8x8 LED matrix preview using Canvas.
        """
        preview_frame = ttk.LabelFrame(self.master, text="LED Matrix Preview", padding="10 10 10 10")
        preview_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0), sticky='n')

        self.canvas = tk.Canvas(preview_frame, width=LED_SIZE * 8 + LED_PADDING * 9,
                                height=LED_SIZE * 8 + LED_PADDING * 9, bg="#000000")
        self.canvas.pack()

        # Initialize LED circles and store their references
        self.led_circles = []
        for row in range(8):
            row_circles = []
            for col in range(8):
                x1 = LED_PADDING + col * (LED_SIZE + LED_PADDING)
                y1 = LED_PADDING + row * (LED_SIZE + LED_PADDING)
                x2 = x1 + LED_SIZE
                y2 = y1 + LED_SIZE
                circle = self.canvas.create_oval(x1, y1, x2, y2, fill=OFF_COLOR, outline="")
                row_circles.append(circle)
            self.led_circles.append(row_circles)

    def update_led_matrix(self, pattern, animation=False):
        """
        Updates the LED matrix preview based on the provided pattern.
        :param pattern: List of 8 integers (0-255) representing the LED pattern.
        :param animation: Boolean indicating if the update is for animation playback.
        """
        for row, byte in enumerate(pattern):
            # Convert byte to binary string, pad with zeros to ensure 8 bits
            binary_str = bin(byte)[2:].zfill(8)
            for col, bit in enumerate(binary_str):
                color = ON_COLOR if bit == '1' else OFF_COLOR
                self.canvas.itemconfig(self.led_circles[row][col], fill=color)
        if not animation:
            self.master.update_idletasks()  # Refresh the GUI immediately

    def load_ui(self):
        """
        Opens a dedicated UI for loading patterns and animations with separate sections.
        """
        # Open a new window for loading patterns and animations
        load_window = tk.Toplevel(self.master)
        load_window.title("Load Pattern/Animation")
        load_window.geometry("800x600")
        load_window.resizable(False, False)

        # Frame for patterns and animations
        frame = ttk.Frame(load_window, padding="10 10 10 10")
        frame.pack(fill='both', expand=True)

        # Split the window into two sections: Patterns and Animations
        patterns_frame = ttk.LabelFrame(frame, text="Saved Patterns", padding="10 10 10 10")
        patterns_frame.pack(side='left', fill='both', expand=True, padx=(0, 10), pady=(0, 0))

        animations_frame = ttk.LabelFrame(frame, text="Saved Animations", padding="10 10 10 10")
        animations_frame.pack(side='right', fill='both', expand=True, padx=(10, 0), pady=(0, 0))

        # Populate Patterns Listbox
        patterns_listbox_frame = ttk.Frame(patterns_frame)
        patterns_listbox_frame.pack(fill='both', expand=True)

        patterns_scrollbar = ttk.Scrollbar(patterns_listbox_frame, orient='vertical')
        patterns_listbox = tk.Listbox(patterns_listbox_frame, font=self.font_labels, yscrollcommand=patterns_scrollbar.set)
        patterns_scrollbar.config(command=patterns_listbox.yview)
        patterns_scrollbar.pack(side='right', fill='y')
        patterns_listbox.pack(side='left', fill='both', expand=True)

        # Populate Animations Listbox
        animations_listbox_frame = ttk.Frame(animations_frame)
        animations_listbox_frame.pack(fill='both', expand=True)

        animations_scrollbar = ttk.Scrollbar(animations_listbox_frame, orient='vertical')
        animations_listbox = tk.Listbox(animations_listbox_frame, font=self.font_labels, yscrollcommand=animations_scrollbar.set)
        animations_scrollbar.config(command=animations_listbox.yview)
        animations_scrollbar.pack(side='right', fill='y')
        animations_listbox.pack(side='left', fill='both', expand=True)

        # Populate listboxes with saved patterns and animations
        script_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(script_dir, "saved_patterns")
        os.makedirs(save_dir, exist_ok=True)  # Ensure the directory exists
        files = [f for f in os.listdir(save_dir) if f.endswith('.json')]

        for file in files:
            file_path = os.path.join(save_dir, file)
            try:
                data = load_saved_file(file_path)
                file_type = data.get('type', '').lower()
                if file_type == 'single':
                    patterns_listbox.insert(tk.END, file)
                elif file_type == 'animation':
                    animations_listbox.insert(tk.END, file)
                else:
                    self.log(f"File '{file}' has unknown type '{data.get('type', 'unknown')}', skipping.", "info")
            except Exception as e:
                self.log(f"Error loading file '{file}': {e}", "error")
                continue  # Skip invalid files

        if not files:
            messagebox.showinfo("No Saved Files", "No saved patterns or animations found.")
            load_window.destroy()
            return

        # Preview Area
        preview_frame = ttk.LabelFrame(frame, text="Preview Area", padding="10 10 10 10")
        preview_frame.pack(fill='both', expand=False, padx=(0, 0), pady=(10, 0))

        preview_label = ttk.Label(preview_frame, text="Preview Area\n(Coming Soon)", anchor='center', font=self.font_labels)
        preview_label.pack(expand=True, fill='both')

        # Bind selection events to update preview
        patterns_listbox.bind('<<ListboxSelect>>', lambda event: self.update_preview(patterns_listbox, 'pattern'))
        animations_listbox.bind('<<ListboxSelect>>', lambda event: self.update_preview(animations_listbox, 'animation'))

        # Load Buttons
        load_patterns_btn = ttk.Button(patterns_frame, text="Load Selected Pattern", command=lambda: self.load_selected_file(patterns_listbox, 'single', load_window))
        load_patterns_btn.pack(pady=(10, 0))

        load_animations_btn = ttk.Button(animations_frame, text="Load Selected Animation", command=lambda: self.load_selected_file(animations_listbox, 'animation', load_window))
        load_animations_btn.pack(pady=(10, 0))

    def update_preview(self, listbox, file_type):
        """
        Updates the preview area based on the selected pattern or animation.
        :param listbox: The Listbox widget containing files.
        :param file_type: 'pattern' or 'animation'.
        """
        selected = listbox.curselection()
        if not selected:
            return
        file_name = listbox.get(selected[0])
        script_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(script_dir, "saved_patterns")
        file_path = os.path.join(save_dir, file_name)
        try:
            data = load_saved_file(file_path)
            if data['type'].lower() == 'single' and file_type == 'pattern':
                pattern = data['pattern']
                self.current_pattern = pattern.copy()
                self.current_animation = None
                self.is_animation = False
                self.current_file_path = file_path  # Store the current file path
                self.update_led_matrix(pattern, animation=False)
                self.edit_btn.configure(state='normal')
                self.publish_btn.configure(state='normal')
            elif data['type'].lower() == 'animation' and file_type == 'animation':
                patterns = data['patterns']
                self.current_animation = [p.copy() for p in patterns]
                self.current_pattern = None
                self.is_animation = True
                self.current_file_path = file_path  # Store the current file path
                # Start animation playback in preview
                self.update_led_matrix(patterns[0], animation=True)
                self.edit_btn.configure(state='normal')
                self.publish_btn.configure(state='normal')
            else:
                self.log(f"File '{file_name}' type mismatch.", "error")
        except Exception as e:
            self.log(f"Error loading file '{file_name}': {e}", "error")

    def play_animation_preview(self, patterns):
        """
        Plays the animation in the preview canvas.
        :param patterns: List of patterns representing each frame.
        """
        for pattern in patterns:
            self.update_led_matrix(pattern, animation=True)
            time.sleep(ANIMATION_DELAY / 1000)  # Convert ms to seconds

    def load_selected_file(self, listbox, file_type, window):
        selected = listbox.curselection()
        if not selected:
            messagebox.showwarning("No Selection", f"Please select a {file_type} to load.")
            return
        file_name = listbox.get(selected[0])
        script_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(script_dir, "saved_patterns")
        file_path = os.path.join(save_dir, file_name)
        try:
            data = load_saved_file(file_path)
            if data['type'].lower() == file_type:
                if file_type == 'single':
                    pattern = data['pattern']
                    self.log(f"Loading pattern from '{file_name}'.", "info")
                    self.current_pattern = pattern.copy()
                    self.current_animation = None
                    self.is_animation = False
                    self.current_file_path = file_path  # Store the current file path
                    self.update_led_matrix(pattern, animation=False)
                    self.edit_btn.configure(state='normal')
                    self.publish_btn.configure(state='normal')
                elif file_type == 'animation':
                    patterns = data['patterns']
                    self.log(f"Loading animation from '{file_name}'.", "info")
                    self.current_animation = [p.copy() for p in patterns]
                    self.current_pattern = None
                    self.is_animation = True
                    self.current_file_path = file_path  # Store the current file path
                    self.update_led_matrix(patterns[0], animation=True)
                    self.edit_btn.configure(state='normal')
                    self.publish_btn.configure(state='normal')
                window.destroy()
            else:
                self.log(f"Selected file '{file_name}' is not of type '{file_type}'.", "error")
        except Exception as e:
            self.log(f"Error loading file '{file_name}': {e}", "error")

    def create_tooltip(self, widget, text):
        tooltip = Tooltip(widget, text)

    def check_input(self, event=None):
        """Enable buttons only if there is input."""
        input_text = self.desc_entry.get().strip()
        if input_text:
            self.single_btn.configure(state='normal')
            self.animate_btn.configure(state='normal')
            self.load_btn.configure(state='normal')
        else:
            self.single_btn.configure(state='disabled')
            self.animate_btn.configure(state='disabled')
            self.load_btn.configure(state='disabled')

    def log(self, message, msg_type="info"):
        """Log messages with different colors based on type."""
        self.log_area.config(state='normal')
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        if msg_type == "error":
            self.log_area.insert(tk.END, f"{timestamp} - ", ("timestamp", "error"))
            self.log_area.insert(tk.END, f"{message}\n", ("message", "error"))
        elif msg_type == "success":
            self.log_area.insert(tk.END, f"{timestamp} - ", ("timestamp", "success"))
            self.log_area.insert(tk.END, f"{message}\n", ("message", "success"))
        else:
            self.log_area.insert(tk.END, f"{timestamp} - ", ("timestamp",))
            self.log_area.insert(tk.END, f"{message}\n", ("message",))
        self.log_area.tag_configure("timestamp", foreground=self.accent_color, font=self.font_log)
        self.log_area.tag_configure("message", foreground=self.text_color, font=self.font_log)
        self.log_area.tag_configure("error", foreground=self.error_color, font=self.font_log)
        self.log_area.tag_configure("success", foreground=self.success_color, font=self.font_log)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def generate_single_pattern(self):
        description = self.desc_entry.get().strip()
        if not description:
            messagebox.showwarning("Input Required", "Please enter a pattern description.")
            return
        # Disable buttons and show loading
        self.disable_buttons()
        self.log("Generating single pattern...", "info")
        threading.Thread(target=self.process_single_pattern, args=(description,), daemon=True).start()

    def generate_animation(self):
        description = self.desc_entry.get().strip()
        if not description:
            messagebox.showwarning("Input Required", "Please enter a pattern description.")
            return
        # Disable buttons and show loading
        self.disable_buttons()
        self.log("Generating animation...", "info")
        threading.Thread(target=self.process_animation, args=(description,), daemon=True).start()

    def process_single_pattern(self, description):
        pattern = generate_patterns_from_ai(description, animation=False, log_callback=self.log)
        if pattern:
            self.log(f"Generated pattern: {pattern}", "success")
            self.current_pattern = pattern.copy()
            self.current_animation = None
            self.is_animation = False
            self.current_file_path = None  # Reset current file path
            # Prompt user to save
            save = messagebox.askyesno("Save Pattern", "Do you want to save this pattern?")
            if save:
                filename = sanitize_filename(description) + '.json'
                saved_path = save_pattern(pattern, name=filename)
                if saved_path:
                    self.log(f"Pattern saved as '{filename}'.", "success")
                    self.current_file_path = saved_path  # Update current file path
                else:
                    self.log(f"Failed to save pattern as '{filename}'.", "error")
            # Send pattern to Arduino and update preview
            send_single_pattern(self.ser, pattern, log_callback=self.log, preview_callback=self.update_led_matrix)
            self.log("Single pattern sent successfully.", "success")
            self.publish_btn.configure(state='normal')
            self.edit_btn.configure(state='normal')
        else:
            self.log("Failed to generate single pattern. Please try again.", "error")
        self.enable_buttons()

    def process_animation(self, description):
        patterns = generate_patterns_from_ai(description, animation=True, num_frames=5, log_callback=self.log)
        if patterns:
            self.log(f"Generated {len(patterns)} frames for animation.", "success")
            self.current_animation = [p.copy() for p in patterns]
            self.current_pattern = None
            self.is_animation = True
            self.current_file_path = None  # Reset current file path
            # Prompt user to save
            save = messagebox.askyesno("Save Animation", "Do you want to save this animation?")
            if save:
                filename = sanitize_filename(description) + '.json'
                saved_path = save_animation(patterns, name=filename)
                if saved_path:
                    self.log(f"Animation saved as '{filename}'.", "success")
                    self.current_file_path = saved_path  # Update current file path
                else:
                    self.log(f"Failed to save animation as '{filename}'.", "error")
            # Send animation to Arduino and play in preview
            send_animation(self.ser, patterns, log_callback=self.log, preview_callback=self.update_led_matrix)
            self.log("Animation sent successfully.", "success")
            self.publish_btn.configure(state='normal')
            self.edit_btn.configure(state='normal')
        else:
            self.log("Failed to generate animation patterns. Please try again.", "error")
        self.enable_buttons()

    def disable_buttons(self):
        self.single_btn.configure(state='disabled')
        self.animate_btn.configure(state='disabled')
        self.load_btn.configure(state='disabled')
        self.edit_btn.configure(state='disabled')
        self.publish_btn.configure(state='disabled')

    def enable_buttons(self):
        input_text = self.desc_entry.get().strip()
        if input_text:
            self.single_btn.configure(state='normal')
            self.animate_btn.configure(state='normal')
            self.load_btn.configure(state='normal')
        # Edit and Publish buttons are enabled based on actions

    def edit_current(self):
        if self.is_animation:
            self.edit_animation()
        elif self.current_pattern:
            self.edit_single_pattern()

    def edit_single_pattern(self):
        """
        Opens a window to edit the current single pattern by toggling LEDs.
        """
        edit_window = tk.Toplevel(self.master)
        edit_window.title("Edit Single Pattern")
        edit_window.geometry("400x400")
        edit_window.resizable(False, False)

        # Create a Canvas for editing
        edit_canvas = tk.Canvas(edit_window, width=LED_SIZE * 8 + LED_PADDING * 9,
                               height=LED_SIZE * 8 + LED_PADDING * 9, bg="#000000")
        edit_canvas.pack(pady=20)

        # Initialize LED circles and store their references
        led_circles = []
        for row in range(8):
            row_circles = []
            for col in range(8):
                x1 = LED_PADDING + col * (LED_SIZE + LED_PADDING)
                y1 = LED_PADDING + row * (LED_SIZE + LED_PADDING)
                x2 = x1 + LED_SIZE
                y2 = y1 + LED_SIZE
                color = ON_COLOR if self.current_pattern[row] & (1 << (7 - col)) else OFF_COLOR
                circle = edit_canvas.create_oval(x1, y1, x2, y2, fill=color, outline="")
                row_circles.append(circle)
            led_circles.append(row_circles)

        def toggle_led(event):
            x, y = event.x, event.y
            for row in range(8):
                for col in range(8):
                    coords = edit_canvas.coords(led_circles[row][col])
                    if coords[0] <= x <= coords[2] and coords[1] <= y <= coords[3]:
                        current_color = edit_canvas.itemcget(led_circles[row][col], "fill")
                        new_color = OFF_COLOR if current_color == ON_COLOR else ON_COLOR
                        edit_canvas.itemconfig(led_circles[row][col], fill=new_color)
                        # Update the pattern
                        if new_color == ON_COLOR:
                            self.current_pattern[row] |= (1 << (7 - col))
                        else:
                            self.current_pattern[row] &= ~(1 << (7 - col))
                        break

        edit_canvas.bind("<Button-1>", toggle_led)

        # Save Button
        save_btn = ttk.Button(edit_window, text="Save Changes", command=lambda: self.save_edit_single(edit_window))
        save_btn.pack(pady=10)

    def save_edit_single(self, window):
        """
        Saves the edited single pattern and updates the preview and Arduino.
        """
        # Send the edited pattern to Arduino and update preview
        send_single_pattern(self.ser, self.current_pattern, log_callback=self.log, preview_callback=self.update_led_matrix)
        self.log("Edited single pattern published successfully.", "success")
        window.destroy()

    def edit_animation(self):
        """
        Opens a window to edit the current animation by selecting and toggling LEDs in frames.
        """
        if not self.current_animation:
            self.log("No animation to edit.", "error")
            return

        edit_window = tk.Toplevel(self.master)
        edit_window.title("Edit Animation")
        edit_window.geometry("600x700")
        edit_window.resizable(False, False)

        # Frame for selecting frames
        frame_selection = ttk.Frame(edit_window, padding="10 10 10 10")
        frame_selection.pack(fill='x')

        frame_label = ttk.Label(frame_selection, text="Select Frame to Edit:")
        frame_label.pack(side='left', padx=(0, 10))

        frame_var = tk.IntVar(value=0)
        frame_radio_buttons = []
        for i in range(len(self.current_animation)):
            rb = ttk.Radiobutton(frame_selection, text=f"Frame {i+1}", variable=frame_var, value=i)
            rb.pack(side='left')
            frame_radio_buttons.append(rb)

        # Create a Canvas for editing
        edit_canvas = tk.Canvas(edit_window, width=LED_SIZE * 8 + LED_PADDING * 9,
                               height=LED_SIZE * 8 + LED_PADDING * 9, bg="#000000")
        edit_canvas.pack(pady=20)

        # Initialize LED circles and store their references
        led_circles = []
        for row in range(8):
            row_circles = []
            for col in range(8):
                x1 = LED_PADDING + col * (LED_SIZE + LED_PADDING)
                y1 = LED_PADDING + row * (LED_SIZE + LED_PADDING)
                x2 = x1 + LED_SIZE
                y2 = y1 + LED_SIZE
                color = ON_COLOR if self.current_animation[0][row] & (1 << (7 - col)) else OFF_COLOR
                circle = edit_canvas.create_oval(x1, y1, x2, y2, fill=color, outline="")
                row_circles.append(circle)
            led_circles.append(row_circles)

        def update_canvas(frame_index):
            pattern = self.current_animation[frame_index]
            for row in range(8):
                binary_str = bin(pattern[row])[2:].zfill(8)
                for col, bit in enumerate(binary_str):
                    color = ON_COLOR if bit == '1' else OFF_COLOR
                    edit_canvas.itemconfig(led_circles[row][col], fill=color)

        def on_frame_select():
            frame_index = frame_var.get()
            update_canvas(frame_index)

        # Initialize with the first frame
        update_canvas(0)

        # Bind frame selection
        for rb in frame_radio_buttons:
            rb.configure(command=on_frame_select)

        def toggle_led(event):
            x, y = event.x, event.y
            frame_index = frame_var.get()
            for row in range(8):
                for col in range(8):
                    coords = edit_canvas.coords(led_circles[row][col])
                    if coords[0] <= x <= coords[2] and coords[1] <= y <= coords[3]:
                        current_color = edit_canvas.itemcget(led_circles[row][col], "fill")
                        new_color = OFF_COLOR if current_color == ON_COLOR else ON_COLOR
                        edit_canvas.itemconfig(led_circles[row][col], fill=new_color)
                        # Update the pattern
                        if new_color == ON_COLOR:
                            self.current_animation[frame_index][row] |= (1 << (7 - col))
                        else:
                            self.current_animation[frame_index][row] &= ~(1 << (7 - col))
                        break

        edit_canvas.bind("<Button-1>", toggle_led)

        # Save Button
        save_btn = ttk.Button(edit_window, text="Save Changes", command=lambda: self.save_edit_animation(edit_window))
        save_btn.pack(pady=10)

    def save_edit_animation(self, window):
        """
        Saves the edited animation and updates the Arduino and preview.
        """
        # Send the edited animation to Arduino and update preview
        send_animation(self.ser, self.current_animation, log_callback=self.log, preview_callback=self.update_led_matrix)
        self.log("Edited animation published successfully.", "success")
        window.destroy()

    def publish_current(self):
        """
        Publishes the current pattern or animation to the Arduino and saves it to the current file.
        """
        if self.current_file_path is None:
            self.log("No file is currently loaded to publish.", "error")
            return

        if self.is_animation and self.current_animation:
            # Save the edited animation to the existing file with overwrite
            try:
                data = {
                    'type': 'animation',
                    'patterns': self.current_animation
                }
                with open(self.current_file_path, 'w') as f:
                    json.dump(data, f, indent=4)
                self.log(f"Animation saved to '{os.path.basename(self.current_file_path)}'.", "success")
            except Exception as e:
                self.log(f"Failed to save animation: {e}", "error")
                return
            # Send to Arduino
            send_animation(self.ser, self.current_animation, log_callback=self.log, preview_callback=self.update_led_matrix)
            self.log("Animation published successfully.", "success")
        elif not self.is_animation and self.current_pattern:
            # Save the edited pattern to the existing file with overwrite
            try:
                data = {
                    'type': 'single',
                    'pattern': self.current_pattern
                }
                with open(self.current_file_path, 'w') as f:
                    json.dump(data, f, indent=4)
                self.log(f"Pattern saved to '{os.path.basename(self.current_file_path)}'.", "success")
            except Exception as e:
                self.log(f"Failed to save pattern: {e}", "error")
                return
            # Send to Arduino
            send_single_pattern(self.ser, self.current_pattern, log_callback=self.log, preview_callback=self.update_led_matrix)
            self.log("Pattern published successfully.", "success")
        else:
            self.log("No pattern or animation to publish.", "error")

    def exit_application(self):
        if messagebox.askokcancel("Exit", "Do you really want to exit?"):
            try:
                self.ser.close()
                self.log("Serial connection closed.", "info")
            except:
                pass
            self.master.destroy()

# Tooltip Class
class Tooltip:
    """
    It creates a tooltip for a given widget as the mouse goes on it.
    """
    def __init__(self, widget, text='widget info'):
        self.waittime = 500     # milliseconds
        self.wraplength = 300   # pixels
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)
        self.widget.bind("<ButtonPress>", self.on_leave)
        self.id = None
        self.tw = None

    def on_enter(self, event=None):
        self.schedule()

    def on_leave(self, event=None):
        self.unschedule()
        self.hide_tooltip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.waittime, self.show_tooltip)

    def unschedule(self):
        _id = self.id
        self.id = None
        if _id:
            self.widget.after_cancel(_id)

    def show_tooltip(self, event=None):
        x = y = 0
        try:
            x, y, cx, cy = self.widget.bbox("insert")
        except:
            x, y = 0, 0
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        # Creates a toplevel window
        self.tw = tk.Toplevel(self.widget)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tw, text=self.text, justify='left',
                         background="#333333", foreground="white",
                         relief='solid', borderwidth=1,
                         wraplength=self.wraplength, font=("Helvetica", 10))
        label.pack(ipadx=1)

    def hide_tooltip(self):
        tw = self.tw
        self.tw= None
        if tw:
            tw.destroy()

# Main Function
def main():
    root = tk.Tk()
    app = LEDMatrixApp(root)
    root.protocol("WM_DELETE_WINDOW", app.exit_application)
    root.mainloop()

if __name__ == "__main__":
    main()