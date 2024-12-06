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
import queue
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('led_matrix_app.log'),
        logging.StreamHandler()
    ]
)

# LED Matrix Constants
LED_DIAMETER = 30
LED_SPACING = 5
ACTIVE_COLOR = "#FF0000"
INACTIVE_COLOR = "#330000"
FRAME_DELAY_MS = 500
MAX_ANIMATION_FRAMES = 10

# Load environment variables
load_dotenv()

def find_arduino_port():
    patterns = ['/dev/cu.usbserial*', '/dev/ttyUSB*', '/dev/ttyACM*', 'COM3', 'COM4']
    ports = []
    for pattern in patterns:
        ports += glob.glob(pattern)
    if not ports:
        raise SerialException("No Arduino serial ports found. Check connection.")
    if len(ports) > 1:
        raise SerialException("Multiple serial ports found. Specify the correct one.")
    return ports[0]

class SerialException(Exception):
    pass

USE_MOCK = os.getenv('USE_MOCK_SERIAL', 'false').lower() in ['true', '1', 'yes']

if USE_MOCK:
    try:
        from mock_serial import MockSerial as SerialPort
        logging.info("MockSerial enabled for testing.")
    except ImportError:
        logging.error("MockSerial module missing.")
        sys.exit(1)
else:
    SerialPort = serial.Serial

def initialize_serial_connection():
    if USE_MOCK:
        ser = SerialPort(port='COM3', baudrate=9600, timeout=1)
    else:
        arduino_port = find_arduino_port()
        logging.info(f"Connecting to Arduino on {arduino_port}")
        try:
            ser = SerialPort(port=arduino_port, baudrate=9600, timeout=1)
        except serial.SerialException as e:
            raise SerialException(f"Connection failed: {e}")
        time.sleep(2)
    logging.info("Serial connection established.")
    return ser

api_key = os.getenv('GLHF_API_KEY')
if not api_key:
    logging.error("GLHF_API_KEY not set.")
    sys.exit(1)

openai.api_key = api_key
openai.api_base = 'https://glhf.chat/api/openai/v1'

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]',"", name)

def generate_patterns(prompt, animation=False, frame_count=5, logger=None):
    attempts, patterns = 0, []
    while attempts < 3:
        try:
            if not animation:
                response = openai.ChatCompletion.create(
                    model='hf:meta-llama/Meta-Llama-3.1-405B-Instruct',
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": f"Generate exactly 8 integers between 0 and 255 for '{prompt}'. Provide only the list separated by commas."}
                    ]
                )
                raw = response.choices[0].message.content.strip()
                if logger:
                    logger(f"AI Response: {raw}")
                raw = re.sub(r'[\[\]]', '', raw)
                nums = [int(n) for n in re.split(r'[,\s]+', raw) if n.isdigit()]
                if len(nums) >= 8 and all(0 <= n <= 255 for n in nums):
                    return nums[:8]
                if logger:
                    logger(f"Attempt {attempts + 1}: Invalid pattern. Retrying...")
            else:
                temp_patterns = []
                for i in range(frame_count):
                    resp = openai.ChatCompletion.create(
                        model='hf:meta-llama/Meta-Llama-3.1-405B-Instruct',
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": f"Generate exactly 8 integers between 0 and 255 for frame {i+1} of '{prompt}'. Provide only the list separated by commas."}
                        ]
                    )
                    raw_frame = resp.choices[0].message.content.strip()
                    if logger:
                        logger(f"AI Response Frame {i+1}: {raw_frame}")
                    raw_frame = re.sub(r'[\[\]]', '', raw_frame)
                    nums_frame = [int(n) for n in re.split(r'[,\s]+', raw_frame) if n.isdigit()]
                    if len(nums_frame) >= 8 and all(0 <= n <= 255 for n in nums_frame):
                        temp_patterns.append(nums_frame[:8])
                    else:
                        if logger:
                            logger(f"Attempt {attempts + 1}: Invalid frame {i+1}. Retrying animation...")
                        temp_patterns = []
                        break
                if temp_patterns:
                    return temp_patterns
        except openai.error.OpenAIError as e:
            if logger:
                logger(f"OpenAI Error: {e}")
            return None
        attempts += 1
    if logger:
        logger("Failed to generate patterns after multiple attempts.")
    return None

def send_single_frame(ser, pattern, logger=None, update_preview=None):
    if len(pattern) != 8:
        if logger:
            logger("Pattern must have 8 integers.")
        return
    try:
        ser.write(bytes([0xFF]))
        ser.flush()
        for byte in pattern:
            ser.write(bytes([byte]))
        ser.write(bytes([0xFE]))
        ser.flush()
        time.sleep(0.1)
        start = time.time()
        ack = False
        while not ack and (time.time() - start) < 5:
            if ser.in_waiting:
                response = ser.readline().decode().strip()
                if logger:
                    logger(f"Serial Ack: {response}")
                if response == "Pattern received.":
                    ack = True
        if not ack and logger:
            logger("No acknowledgment for single pattern.")
        if update_preview:
            update_preview(pattern, animation=False)
    except serial.SerialException as e:
        if logger:
            logger(f"Serial Error: {e}")

class AnimationManager:
    def __init__(self, canvas, update_func):
        self.canvas = canvas
        self.update_leds = update_func
        self.queue = queue.Queue()
        self.playing = False
        self.stop_flag = threading.Event()

    def start(self, frames):
        if self.playing:
            self.stop()
        for frame in frames:
            self.queue.put(frame)
        self.playing = True
        self.stop_flag.clear()
        threading.Thread(target=self._play, daemon=True).start()

    def _play(self):
        try:
            while not self.stop_flag.is_set() and not self.queue.empty():
                frame = self.queue.get()
                self.canvas.after(0, lambda f=frame: self._update_frame(f))
                time.sleep(FRAME_DELAY_MS / 1000)
        except Exception as e:
            logging.error(f"Animation error: {e}")
        finally:
            self.playing = False
            self.stop_flag.clear()

    def _update_frame(self, frame):
        self.update_leds(frame, animation=True)

    def stop(self):
        if self.playing:
            self.stop_flag.set()
            logging.info("Animation stopped.")

def send_animation(ser, frames, logger=None, animator=None):
    count = len(frames)
    if count == 0:
        if logger:
            logger("No frames to send.")
        return
    if count > MAX_ANIMATION_FRAMES:
        if logger:
            logger(f"Frames exceed maximum of {MAX_ANIMATION_FRAMES}.")
        return
    try:
        ser.write(bytes([0xFA]))
        ser.flush()
        ser.write(bytes([count]))
        ser.flush()
        for frame in frames:
            for byte in frame:
                ser.write(bytes([byte]))
        ser.write(bytes([0xFB]))
        ser.flush()
        time.sleep(0.1)
        start = time.time()
        ack = False
        while not ack and (time.time() - start) < 5:
            if ser.in_waiting:
                response = ser.readline().decode().strip()
                if logger:
                    logger(f"Serial Ack: {response}")
                if response in ["Animation received.", "Invalid end marker received."]:
                    ack = True
        if not ack and logger:
            logger("No acknowledgment for animation.")
        if animator:
            animator.start(frames)
    except serial.SerialException as e:
        if logger:
            logger(f"Serial Error: {e}")

def save_single_pattern(pattern, name=None, overwrite=False):
    dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_patterns")
    os.makedirs(dir_path, exist_ok=True)
    if not name:
        name = f"pattern_{int(time.time())}.json"
    else:
        name = clean_filename(name) + '.json'
    path = os.path.join(dir_path, name)
    if os.path.exists(path) and not overwrite:
        root = tk.Tk()
        root.withdraw()
        replace = messagebox.askyesno("File Exists", f"'{name}' exists. Replace?")
        root.destroy()
        if not replace:
            return None
    data = {'type': 'single', 'pattern': pattern}
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
        return path
    except:
        return None

def save_animation_frames(frames, name=None, overwrite=False):
    dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_patterns")
    os.makedirs(dir_path, exist_ok=True)
    if not name:
        name = f"animation_{int(time.time())}.json"
    else:
        name = clean_filename(name) + '.json'
    path = os.path.join(dir_path, name)
    if os.path.exists(path) and not overwrite:
        root = tk.Tk()
        root.withdraw()
        replace = messagebox.askyesno("File Exists", f"'{name}' exists. Replace?")
        root.destroy()
        if not replace:
            return None
    data = {'type': 'animation', 'patterns': frames}
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
        return path
    except:
        return None

def load_saved(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

class LEDMatrixApp:
    def __init__(self, master):
        self.master = master
        master.title("LED Matrix Controller")
        master.geometry("1300x1000")
        master.configure(bg="#121212")

        # Fonts
        self.title_font = tkfont.Font(family="Helvetica", size=16, weight="bold")
        self.label_font = tkfont.Font(family="Helvetica", size=12)
        self.button_font = tkfont.Font(family="Helvetica", size=12, weight="bold")
        self.log_font = tkfont.Font(family="Helvetica", size=10)

        self.create_ui()

        try:
            self.serial_conn = initialize_serial_connection()
            self.log("Serial connected.", "info")
        except SerialException as e:
            messagebox.showerror("Serial Error", str(e))
            self.log(str(e), "error")
            sys.exit(1)

        self.create_led_preview()
        self.anim_manager = AnimationManager(self.canvas, self.update_leds)

        self.current_file = None

    def create_ui(self):
        frame = ttk.Frame(self.master, padding="20 20 20 20")
        frame.grid(row=0, column=0, sticky='NSEW')
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=3)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", background="#121212", foreground="#ffffff", font=self.label_font)
        style.configure("TButton",
                        background="#1f1f1f",
                        foreground="#ffffff",
                        font=self.button_font,
                        borderwidth=0,
                        focuscolor='none')
        style.map("TButton",
                  background=[('active', "#bb86fc")],
                  foreground=[('active', "#ffffff")])
        style.configure("TEntry",
                        fieldbackground="#1f1f1f",
                        foreground="#ffffff",
                        font=self.label_font,
                        borderwidth=2,
                        relief="groove")

        # Description Entry
        desc_label = ttk.Label(frame, text="Pattern Description:")
        desc_label.grid(row=0, column=0, padx=(0, 10), pady=(0, 5), sticky='w')

        self.desc_entry = ttk.Entry(frame, width=60)
        self.desc_entry.grid(row=0, column=1, padx=(0, 0), pady=(0, 5), sticky='w')
        self.desc_entry.focus()

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=2, pady=(10, 10), sticky='w')

        self.gen_single_btn = ttk.Button(btn_frame, text="Generate Single Pattern", command=self.gen_single)
        self.gen_single_btn.grid(row=0, column=0, padx=(0, 20), pady=5, sticky='w')
        self.gen_single_btn.configure(state='disabled')

        self.gen_anim_btn = ttk.Button(btn_frame, text="Generate Animation", command=self.gen_animation)
        self.gen_anim_btn.grid(row=0, column=1, padx=(0, 20), pady=5, sticky='w')
        self.gen_anim_btn.configure(state='disabled')

        self.load_btn = ttk.Button(btn_frame, text="Load Pattern/Animation", command=self.load_ui)
        self.load_btn.grid(row=0, column=2, padx=(0, 20), pady=5, sticky='w')
        self.load_btn.configure(state='disabled')

        self.edit_btn = ttk.Button(btn_frame, text="Edit", command=self.edit_current, state='disabled')
        self.edit_btn.grid(row=0, column=3, padx=(0, 20), pady=5, sticky='w')

        self.publish_btn = ttk.Button(btn_frame, text="Publish", command=self.publish_current, state='disabled')
        self.publish_btn.grid(row=0, column=4, padx=(0, 20), pady=5, sticky='w')

        exit_btn = ttk.Button(btn_frame, text="Exit", command=self.exit_app)
        exit_btn.grid(row=0, column=5, padx=(100, 0), pady=5, sticky='e')

        # Tooltips
        self.add_tooltips()

        # Keyboard Shortcuts
        self.master.bind('<Control-g>', lambda e: self.gen_single())
        self.master.bind('<Control-a>', lambda e: self.gen_animation())
        self.master.bind('<Control-l>', lambda e: self.load_ui())
        self.master.bind('<Control-e>', lambda e: self.exit_app())

        # Log Area
        log_label = ttk.Label(frame, text="Logs:")
        log_label.grid(row=2, column=0, padx=(0, 10), pady=(10, 5), sticky='w')

        self.log_area = scrolledtext.ScrolledText(frame, width=80, height=25, state='disabled', wrap='word')
        self.log_area.grid(row=3, column=0, columnspan=2, padx=(0, 0), pady=(0, 10), sticky='nsew')
        frame.rowconfigure(3, weight=1)
        frame.columnconfigure(1, weight=1)

        # Input Validation
        self.desc_entry.bind('<KeyRelease>', self.toggle_buttons)

        # Store patterns
        self.current_pattern = None
        self.current_animation = None
        self.is_animation = False

    def add_tooltips(self):
        Tooltip(self.gen_single_btn, "Generate and send a single LED pattern based on the description.")
        Tooltip(self.gen_anim_btn, "Generate and send an animation with multiple LED patterns based on the description.")
        Tooltip(self.load_btn, "Load a saved pattern or animation to display on the LED matrix.")
        Tooltip(self.edit_btn, "Edit the current pattern or animation.")
        Tooltip(self.publish_btn, "Publish the edited pattern or animation to the Arduino.")
        Tooltip(self.master, "Close the application.")

    def create_led_preview(self):
        preview_frame = ttk.LabelFrame(self.master, text="LED Matrix Preview", padding="10 10 10 10")
        preview_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0), sticky='n')

        self.canvas = tk.Canvas(preview_frame, width=LED_DIAMETER * 8 + LED_SPACING * 9,
                                height=LED_DIAMETER * 8 + LED_SPACING * 9, bg="#000000")
        self.canvas.pack()

        self.leds = []
        for row in range(8):
            row_leds = []
            for col in range(8):
                x1 = LED_SPACING + col * (LED_DIAMETER + LED_SPACING)
                y1 = LED_SPACING + row * (LED_DIAMETER + LED_SPACING)
                x2 = x1 + LED_DIAMETER
                y2 = y1 + LED_DIAMETER
                circle = self.canvas.create_oval(x1, y1, x2, y2, fill=INACTIVE_COLOR, outline="")
                row_leds.append(circle)
            self.leds.append(row_leds)

    def update_leds(self, pattern, animation=False):
        for row, byte in enumerate(pattern):
            bits = bin(byte)[2:].zfill(8)
            for col, bit in enumerate(bits):
                color = ACTIVE_COLOR if bit == '1' else INACTIVE_COLOR
                self.canvas.itemconfig(self.leds[row][col], fill=color)
        if not animation:
            self.master.update_idletasks()

    def toggle_buttons(self, event=None):
        text = self.desc_entry.get().strip()
        state = 'normal' if text else 'disabled'
        self.gen_single_btn.configure(state=state)
        self.gen_anim_btn.configure(state=state)
        self.load_btn.configure(state=state)

    def log(self, msg, level="info"):
        self.log_area.config(state='normal')
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        if level == "error":
            self.log_area.insert(tk.END, f"{timestamp} - {msg}\n", ("error",))
        elif level == "success":
            self.log_area.insert(tk.END, f"{timestamp} - {msg}\n", ("success",))
        else:
            self.log_area.insert(tk.END, f"{timestamp} - {msg}\n")
        self.log_area.tag_config("error", foreground="#cf6679")
        self.log_area.tag_config("success", foreground="#03dac6")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def gen_single(self):
        desc = self.desc_entry.get().strip()
        if not desc:
            messagebox.showwarning("Input Needed", "Enter a pattern description.")
            return
        self.disable_all_buttons()
        self.log("Generating single pattern...", "info")
        threading.Thread(target=self.generate_single_pattern, args=(desc,), daemon=True).start()

    def generate_single_pattern(self, desc):
        pattern = generate_patterns(desc, animation=False, logger=self.log)
        if pattern:
            self.log(f"Pattern: {pattern}", "success")
            self.current_pattern = pattern.copy()
            self.current_animation = None
            self.is_animation = False
            self.current_file = None
            save = messagebox.askyesno("Save Pattern", "Save this pattern?")
            if save:
                filename = clean_filename(desc) + '.json'
                saved = save_single_pattern(pattern, name=filename)
                if saved:
                    self.log(f"Pattern saved as '{filename}'.", "success")
                    self.current_file = saved
                else:
                    self.log(f"Failed to save '{filename}'.", "error")
            send_single_frame(self.serial_conn, pattern, logger=self.log, update_preview=self.update_leds)
            self.log("Pattern sent.", "success")
            self.publish_btn.configure(state='normal')
            self.edit_btn.configure(state='normal')
        else:
            self.log("Failed to generate pattern.", "error")
        self.enable_buttons()

    def gen_animation(self):
        desc = self.desc_entry.get().strip()
        if not desc:
            messagebox.showwarning("Input Needed", "Enter a pattern description.")
            return
        self.disable_all_buttons()
        self.log("Generating animation...", "info")
        threading.Thread(target=self.generate_animation_patterns, args=(desc,), daemon=True).start()

    def generate_animation_patterns(self, desc):
        frames = generate_patterns(desc, animation=True, frame_count=5, logger=self.log)
        if frames:
            self.log(f"Generated {len(frames)} frames.", "success")
            self.current_animation = [f.copy() for f in frames]
            self.current_pattern = None
            self.is_animation = True
            self.current_file = None
            save = messagebox.askyesno("Save Animation", "Save this animation?")
            if save:
                filename = clean_filename(desc) + '.json'
                saved = save_animation_frames(frames, name=filename)
                if saved:
                    self.log(f"Animation saved as '{filename}'.", "success")
                    self.current_file = saved
                else:
                    self.log(f"Failed to save '{filename}'.", "error")
            send_animation(self.serial_conn, frames, logger=self.log, animator=self.anim_manager)
            self.log("Animation sent.", "success")
            self.publish_btn.configure(state='normal')
            self.edit_btn.configure(state='normal')
        else:
            self.log("Failed to generate animation.", "error")
        self.enable_buttons()

    def disable_all_buttons(self):
        self.gen_single_btn.configure(state='disabled')
        self.gen_anim_btn.configure(state='disabled')
        self.load_btn.configure(state='disabled')
        self.edit_btn.configure(state='disabled')
        self.publish_btn.configure(state='disabled')

    def enable_buttons(self):
        text = self.desc_entry.get().strip()
        state = 'normal' if text else 'disabled'
        self.gen_single_btn.configure(state=state)
        self.gen_anim_btn.configure(state=state)
        self.load_btn.configure(state=state)

    def load_ui(self):
        load_window = tk.Toplevel(self.master)
        load_window.title("Load Pattern/Animation")
        load_window.geometry("800x600")
        load_window.resizable(False, False)

        frame = ttk.Frame(load_window, padding="10 10 10 10")
        frame.pack(fill='both', expand=True)

        patterns_frame = ttk.LabelFrame(frame, text="Saved Patterns", padding="10 10 10 10")
        patterns_frame.pack(side='left', fill='both', expand=True, padx=(0, 10))

        anims_frame = ttk.LabelFrame(frame, text="Saved Animations", padding="10 10 10 10")
        anims_frame.pack(side='right', fill='both', expand=True, padx=(10, 0))

        # Patterns Listbox
        p_list_frame = ttk.Frame(patterns_frame)
        p_list_frame.pack(fill='both', expand=True)
        p_scroll = ttk.Scrollbar(p_list_frame, orient='vertical')
        p_list = tk.Listbox(p_list_frame, font=self.label_font, yscrollcommand=p_scroll.set)
        p_scroll.config(command=p_list.yview)
        p_scroll.pack(side='right', fill='y')
        p_list.pack(side='left', fill='both', expand=True)

        # Animations Listbox
        a_list_frame = ttk.Frame(anims_frame)
        a_list_frame.pack(fill='both', expand=True)
        a_scroll = ttk.Scrollbar(a_list_frame, orient='vertical')
        a_list = tk.Listbox(a_list_frame, font=self.label_font, yscrollcommand=a_scroll.set)
        a_scroll.config(command=a_list.yview)
        a_scroll.pack(side='right', fill='y')
        a_list.pack(side='left', fill='both', expand=True)

        # Populate Listboxes
        saved_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_patterns")
        os.makedirs(saved_dir, exist_ok=True)
        files = [f for f in os.listdir(saved_dir) if f.endswith('.json')]
        for f in files:
            path = os.path.join(saved_dir, f)
            try:
                data = load_saved(path)
                if data.get('type') == 'single':
                    p_list.insert(tk.END, f)
                elif data.get('type') == 'animation':
                    a_list.insert(tk.END, f)
            except:
                continue

        if not files:
            messagebox.showinfo("No Files", "No saved patterns or animations found.")
            load_window.destroy()
            return

        # Preview Area
        preview = ttk.LabelFrame(frame, text="Preview Area", padding="10 10 10 10")
        preview.pack(fill='both', expand=False, padx=(0, 0), pady=(10, 0))
        preview_label = ttk.Label(preview, text="Preview Coming Soon", anchor='center', font=self.label_font)
        preview_label.pack(expand=True, fill='both')

        # Bind selection
        p_list.bind('<<ListboxSelect>>', lambda e: self.preview_selection(p_list, 'single'))
        a_list.bind('<<ListboxSelect>>', lambda e: self.preview_selection(a_list, 'animation'))

        # Load Buttons
        load_p_btn = ttk.Button(patterns_frame, text="Load Pattern", command=lambda: self.load_file(p_list, 'single', load_window))
        load_p_btn.pack(pady=(10, 0))

        load_a_btn = ttk.Button(anims_frame, text="Load Animation", command=lambda: self.load_file(a_list, 'animation', load_window))
        load_a_btn.pack(pady=(10, 0))

    def preview_selection(self, listbox, file_type):
        selected = listbox.curselection()
        if not selected:
            return
        filename = listbox.get(selected[0])
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_patterns", filename)
        try:
            data = load_saved(path)
            if data.get('type') != file_type:
                self.log(f"Type mismatch for '{filename}'.", "error")
                return
            if file_type == 'single':
                pattern = data.get('pattern')
                self.current_pattern = pattern.copy()
                self.current_animation = None
                self.is_animation = False
                self.current_file = path
                self.update_leds(pattern, animation=False)
                self.edit_btn.configure(state='normal')
                self.publish_btn.configure(state='normal')
            elif file_type == 'animation':
                frames = data.get('patterns')
                self.current_animation = [f.copy() for f in frames]
                self.current_pattern = None
                self.is_animation = True
                self.current_file = path
                self.anim_manager.start(frames)
                self.edit_btn.configure(state='normal')
                self.publish_btn.configure(state='normal')
        except:
            self.log(f"Failed to load '{filename}'.", "error")

    def load_file(self, listbox, file_type, window):
        selected = listbox.curselection()
        if not selected:
            messagebox.showwarning("Select File", f"Choose a {file_type} to load.")
            return
        filename = listbox.get(selected[0])
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_patterns", filename)
        try:
            data = load_saved(path)
            if data.get('type') != file_type:
                self.log(f"Type mismatch for '{filename}'.", "error")
                return
            if file_type == 'single':
                pattern = data.get('pattern')
                self.current_pattern = pattern.copy()
                self.current_animation = None
                self.is_animation = False
                self.current_file = path
                self.update_leds(pattern, animation=False)
                self.edit_btn.configure(state='normal')
                self.publish_btn.configure(state='normal')
            elif file_type == 'animation':
                frames = data.get('patterns')
                self.current_animation = [f.copy() for f in frames]
                self.current_pattern = None
                self.is_animation = True
                self.current_file = path
                self.anim_manager.start(frames)
                self.edit_btn.configure(state='normal')
                self.publish_btn.configure(state='normal')
            window.destroy()
        except:
            self.log(f"Failed to load '{filename}'.", "error")

    def edit_current(self):
        if self.is_animation:
            self.edit_animation()
        elif self.current_pattern:
            self.edit_pattern()

    def edit_pattern(self):
        edit_win = tk.Toplevel(self.master)
        edit_win.title("Edit Pattern")
        edit_win.geometry("400x400")
        edit_win.resizable(False, False)

        canvas = tk.Canvas(edit_win, width=LED_DIAMETER * 8 + LED_SPACING * 9,
                           height=LED_DIAMETER * 8 + LED_SPACING * 9, bg="#000000")
        canvas.pack(pady=20)

        circles = []
        for row in range(8):
            row_circles = []
            for col in range(8):
                x1 = LED_SPACING + col * (LED_DIAMETER + LED_SPACING)
                y1 = LED_SPACING + row * (LED_DIAMETER + LED_SPACING)
                x2 = x1 + LED_DIAMETER
                y2 = y1 + LED_DIAMETER
                bit = self.current_pattern[row] & (1 << (7 - col))
                color = ACTIVE_COLOR if bit else INACTIVE_COLOR
                circle = canvas.create_oval(x1, y1, x2, y2, fill=color, outline="")
                row_circles.append(circle)
            circles.append(row_circles)

        def toggle_led(event):
            x, y = event.x, event.y
            for r in range(8):
                for c in range(8):
                    coords = canvas.coords(circles[r][c])
                    if coords[0] <= x <= coords[2] and coords[1] <= y <= coords[3]:
                        current = canvas.itemcget(circles[r][c], "fill")
                        new = INACTIVE_COLOR if current == ACTIVE_COLOR else ACTIVE_COLOR
                        canvas.itemconfig(circles[r][c], fill=new)
                        if new == ACTIVE_COLOR:
                            self.current_pattern[r] |= (1 << (7 - c))
                        else:
                            self.current_pattern[r] &= ~(1 << (7 - c))
                        break

        canvas.bind("<Button-1>", toggle_led)

        save_btn = ttk.Button(edit_win, text="Save", command=lambda: self.save_edited_pattern(edit_win))
        save_btn.pack(pady=10)

    def save_edited_pattern(self, window):
        send_single_frame(self.serial_conn, self.current_pattern, logger=self.log, update_preview=self.update_leds)
        self.log("Edited pattern sent.", "success")
        window.destroy()

    def edit_animation(self):
        if not self.current_animation:
            self.log("No animation to edit.", "error")
            return
        edit_win = tk.Toplevel(self.master)
        edit_win.title("Edit Animation")
        edit_win.geometry("600x700")
        edit_win.resizable(False, False)

        sel_frame = ttk.Frame(edit_win, padding="10 10 10 10")
        sel_frame.pack(fill='x')

        sel_label = ttk.Label(sel_frame, text="Select Frame:")
        sel_label.pack(side='left', padx=(0, 10))

        frame_var = tk.IntVar(value=0)
        for i in range(len(self.current_animation)):
            rb = ttk.Radiobutton(sel_frame, text=f"Frame {i+1}", variable=frame_var, value=i, command=lambda: update_canvas(frame_var.get()))
            rb.pack(side='left')

        canvas = tk.Canvas(edit_win, width=LED_DIAMETER * 8 + LED_SPACING * 9,
                           height=LED_DIAMETER * 8 + LED_SPACING * 9, bg="#000000")
        canvas.pack(pady=20)

        circles = []
        for row in range(8):
            row_circles = []
            for col in range(8):
                x1 = LED_SPACING + col * (LED_DIAMETER + LED_SPACING)
                y1 = LED_SPACING + row * (LED_DIAMETER + LED_SPACING)
                x2 = x1 + LED_DIAMETER
                y2 = y1 + LED_DIAMETER
                bit = self.current_animation[0][row] & (1 << (7 - col))
                color = ACTIVE_COLOR if bit else INACTIVE_COLOR
                circle = canvas.create_oval(x1, y1, x2, y2, fill=color, outline="")
                row_circles.append(circle)
            circles.append(row_circles)

        def update_canvas(index):
            pattern = self.current_animation[index]
            for r in range(8):
                bits = bin(pattern[r])[2:].zfill(8)
                for c, bit in enumerate(bits):
                    color = ACTIVE_COLOR if bit == '1' else INACTIVE_COLOR
                    canvas.itemconfig(circles[r][c], fill=color)

        def toggle_led(event):
            x, y = event.x, event.y
            idx = frame_var.get()
            for r in range(8):
                for c in range(8):
                    coords = canvas.coords(circles[r][c])
                    if coords[0] <= x <= coords[2] and coords[1] <= y <= coords[3]:
                        current = canvas.itemcget(circles[r][c], "fill")
                        new = INACTIVE_COLOR if current == ACTIVE_COLOR else ACTIVE_COLOR
                        canvas.itemconfig(circles[r][c], fill=new)
                        if new == ACTIVE_COLOR:
                            self.current_animation[idx][r] |= (1 << (7 - c))
                        else:
                            self.current_animation[idx][r] &= ~(1 << (7 - c))
                        break

        canvas.bind("<Button-1>", toggle_led)

        save_btn = ttk.Button(edit_win, text="Save", command=lambda: self.save_edited_animation(edit_win))
        save_btn.pack(pady=10)

    def save_edited_animation(self, window):
        send_animation(self.serial_conn, self.current_animation, logger=self.log, animator=self.anim_manager)
        self.log("Edited animation sent.", "success")
        window.destroy()

    def publish_current(self):
        if not self.current_file:
            self.log("No file loaded to publish.", "error")
            return
        if self.is_animation and self.current_animation:
            try:
                data = {'type': 'animation', 'patterns': self.current_animation}
                with open(self.current_file, 'w') as f:
                    json.dump(data, f, indent=4)
                self.log(f"Animation saved to '{os.path.basename(self.current_file)}'.", "success")
            except:
                self.log("Failed to save animation.", "error")
                return
            send_animation(self.serial_conn, self.current_animation, logger=self.log, animator=self.anim_manager)
            self.log("Animation published.", "success")
        elif not self.is_animation and self.current_pattern:
            try:
                data = {'type': 'single', 'pattern': self.current_pattern}
                with open(self.current_file, 'w') as f:
                    json.dump(data, f, indent=4)
                self.log(f"Pattern saved to '{os.path.basename(self.current_file)}'.", "success")
            except:
                self.log("Failed to save pattern.", "error")
                return
            send_single_frame(self.serial_conn, self.current_pattern, logger=self.log, update_preview=self.update_leds)
            self.log("Pattern published.", "success")
        else:
            self.log("Nothing to publish.", "error")

    def exit_app(self):
        if messagebox.askokcancel("Exit", "Exit the application?"):
            try:
                self.serial_conn.close()
                self.log("Serial connection closed.", "info")
            except:
                pass
            self.master.destroy()

class Tooltip:
    def __init__(self, widget, text=''):
        self.waittime = 500
        self.wraplength = 300
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)
        self.id = None
        self.tw = None

    def show(self, event=None):
        self.schedule()

    def hide(self, event=None):
        self.unschedule()
        self.hide_tooltip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.waittime, self.create_tooltip)

    def unschedule(self):
        _id = self.id
        self.id = None
        if _id:
            self.widget.after_cancel(_id)

    def create_tooltip(self, event=None):
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tw,
            text=self.text,
            justify='left',
            background="#333333",
            foreground="white",
            relief='solid',
            borderwidth=1,
            wraplength=self.wraplength,
            font=("Helvetica", 10)
        )
        label.pack(ipadx=1)

    def hide_tooltip(self):
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()

def main():
    root = tk.Tk()
    app = LEDMatrixApp(root)
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    root.mainloop()

if __name__ == "__main__":
    main()