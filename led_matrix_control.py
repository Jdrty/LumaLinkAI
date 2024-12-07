import os
import re
import sys
import glob
import time
import json
import random
import threading
import serial
import openai
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from tkinter import font as tkfont
from dotenv import load_dotenv

# Constants
LED_DIAMETER = 30
LED_SPACING = 5
ACTIVE_COLOR = "#FF0000"
INACTIVE_COLOR = "#330000"
FRAME_DELAY_MS = 100
MAX_ANIMATION_FRAMES = 10
SAVED_PATTERNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_patterns")

# Toggle Mock Serial
USE_MOCK_SERIAL = True

# Load environment variables
load_dotenv()
api_key = os.getenv('GLHF_API_KEY')
if not api_key:
    raise ValueError("GLHF_API_KEY not set in environment.")

# OpenAI Configuration
openai.api_key = api_key
openai.api_base = "https://glhf.chat/api/openai/v1"

class MockSerial:
    def __init__(self, *args, **kwargs):
        self.in_waiting = 0
        self.received_data = []
        print("[MockSerial] Initialized mock serial connection.")

    def write(self, data):
        print(f"[MockSerial] Writing data: {data}")
        self.received_data.extend(data)
        if data[0] == 0xFF and len(data) == 10:
            self.received_data = []
            threading.Timer(0.5, self.mock_ack).start()
        elif data[0] == 0xFA:
            self.received_data = []
            threading.Timer(0.5, self.mock_ack_animation).start()

    def mock_ack(self):
        print("[MockSerial] Mock Acknowledgment: Pattern received.")

    def mock_ack_animation(self):
        print("[MockSerial] Mock Acknowledgment: Animation received.")

    def readline(self):
        return b"Pattern received.\n"

    def flush(self):
        pass

    def close(self):
        print("[MockSerial] Closing mock serial connection.")

def find_arduino_port():
    patterns = ['/dev/cu.usbserial*', '/dev/ttyUSB*', '/dev/ttyACM*', 'COM3', 'COM4']
    ports = []
    for pattern in patterns:
        ports += glob.glob(pattern)
    if not ports:
        raise Exception("No Arduino serial ports found.")
    if len(ports) > 1:
        raise Exception("Multiple serial ports found.")
    return ports[0]

def initialize_serial_connection():
    if USE_MOCK_SERIAL:
        return MockSerial()
    try:
        arduino_port = find_arduino_port()
        ser = serial.Serial(port=arduino_port, baudrate=9600, timeout=1)
        time.sleep(2)  # Allow time for Arduino to reset
        return ser
    except Exception as e:
        if USE_MOCK_SERIAL:
            print(f"[Error] {e}. Switching to MockSerial.")
            return MockSerial()
        else:
            raise e

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]',"", name)

def simple_symmetrical_pattern():
    return [(1 << (7 - i)) | (1 << i) for i in range(8)]

def simple_symmetrical_animation(frames=5):
    return [simple_symmetrical_pattern() for _ in range(frames)]

def parse_ai_response_to_numbers(raw, logger):
    raw = raw.replace('[', '').replace(']', '')
    nums = [n for n in re.split(r'[,\s]+', raw) if n.isdigit()]
    if len(nums) < 8:
        if logger:
            logger("AI response doesn't contain enough integers.")
        return None
    nums_int = [int(x) for x in nums[:8]]
    if len(nums_int) == 8 and all(0 <= n <= 255 for n in nums_int):
        return nums_int
    return None

def safe_chat_completion(model, messages, logger=None, stream=False):
    try:
        completion = openai.ChatCompletion.create(model=model, messages=messages, stream=stream)
        if stream:
            content = ""
            for chunk in completion:
                if 'delta' in chunk.choices[0] and chunk.choices[0].delta.get('content'):
                    content += chunk.choices[0].delta.content
            return content.strip()
        else:
            if completion and completion.choices and completion.choices[0].message:
                return completion.choices[0].message.content.strip()
            else:
                if logger:
                    logger("Invalid response structure from AI.")
                return None
    except Exception as e:
        if logger:
            logger(f"OpenAI API call error: {e}")
        return None

def generate_patterns(prompt, animation=False, frame_count=5, logger=None, optimize=False):
    system_content = (
        "You are a helpful assistant. The user wants a visually meaningful 8x8 LED pattern. "
        "Each of the 8 integers is a decimal representation of 8 bits (LEDs on/off). "
        "Do not provide extra text or brackets, only 8 integers (0-255) separated by commas."
    )
    if optimize:
        system_content += " Make the pattern symmetrical, simple, and visually appealing."

    base_model = "hf:meta-llama/Meta-Llama-3.1-405B-Instruct"
    attempts = 0
    while attempts < 3:
        if not animation:
            user_content = (
                f"Description: '{prompt}'\n\n"
                "Generate 8 integers (0-255) for a visually meaningful 8x8 LED pattern, only 8 integers separated by commas."
            )
            response = safe_chat_completion(base_model, [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ], logger=logger)
            if response:
                nums = parse_ai_response_to_numbers(response, logger)
                if nums:
                    return nums
                else:
                    if logger:
                        logger(f"Attempt {attempts+1}: Invalid single pattern.")
            else:
                if logger:
                    logger(f"Attempt {attempts+1}: No AI response.")
        else:
            frames_list = []
            success = True
            for i in range(frame_count):
                user_content = (
                    f"Description: '{prompt}' (Frame {i+1})\n\n"
                    "Generate 8 integers (0-255) for this animation frame, only 8 integers separated by commas."
                )
                response = safe_chat_completion(base_model, [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ], logger=logger)
                if response:
                    nums_frame = parse_ai_response_to_numbers(response, logger)
                    if nums_frame:
                        frames_list.append(nums_frame)
                        if logger:
                            logger(f"Generated Frame {i+1}: {nums_frame}")
                    else:
                        success = False
                        break
                else:
                    success = False
                    break
            if success and len(frames_list) == frame_count:
                return frames_list
        attempts += 1
    if logger:
        logger("Failed to generate patterns, using fallback.")
    return simple_symmetrical_animation(frame_count) if animation else simple_symmetrical_pattern()

def optimize_with_ai(current_data, is_animation=False, logger=None):
    system_content = (
        "User provided a pattern/animation. Optimize it to be symmetrical, simple, appealing. "
        "Output only 8 integers per frame (0-255), separated by commas, no extra text."
    )

    base_model = "hf:meta-llama/Meta-Llama-3.1-405B-Instruct"
    attempts = 0
    if is_animation:
        frame_count = len(current_data)
        while attempts < 3:
            optimized_frames = []
            success = True
            for i, frame in enumerate(current_data):
                user_msg = (
                    f"Original frame {i+1}: {frame}\n"
                    "Optimize this frame. Only 8 integers (0-255) separated by commas."
                )
                response = safe_chat_completion(base_model, [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_msg}
                ], logger=logger)
                if response:
                    nums = parse_ai_response_to_numbers(response, logger)
                    if nums and nums != frame:
                        optimized_frames.append(nums)
                        if logger:
                            logger(f"Optimized Frame {i+1}: {nums}")
                    else:
                        success = False
                        break
                else:
                    success = False
                    break
            if success and len(optimized_frames) == frame_count:
                return optimized_frames
            attempts += 1
        if logger:
            logger("Failed to optimize animation, using fallback.")
        return simple_symmetrical_animation(frame_count)
    else:
        while attempts < 3:
            user_msg = (
                f"Original pattern: {current_data}\n"
                "Optimize it, only 8 integers separated by commas."
            )
            response = safe_chat_completion(base_model, [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_msg}
            ], logger=logger)
            if response:
                nums = parse_ai_response_to_numbers(response, logger)
                if nums and nums != current_data:
                    if logger:
                        logger(f"Optimized Pattern: {nums}")
                    return nums
            attempts += 1
        if logger:
            logger("Failed to optimize pattern, using fallback.")
        return simple_symmetrical_pattern()

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
        start = time.time()
        ack = False
        while not ack and (time.time() - start) < 5:
            if hasattr(ser, 'in_waiting') and ser.in_waiting:
                response = ser.readline().decode().strip()
                if logger:
                    logger(f"Serial Ack: {response}")
                if response == "Pattern received.":
                    ack = True
        if not ack and logger:
            logger("No acknowledgment for single pattern.")
        if update_preview:
            update_preview(pattern, animation=False)
            if hasattr(ser, 'flushInput'):
                ser.flushInput()
            ser.master.update_idletasks()
    except Exception as e:
        if logger:
            logger(f"Serial Error: {e}")

def send_animation(ser, frames, logger=None, animator=None):
    # Only send frames, do not start/stop animator here
    count = len(frames)
    if count == 0:
        if logger:
            logger("No frames to send.")
        return
    if count > MAX_ANIMATION_FRAMES:
        if logger:
            logger(f"Frames exceed max {MAX_ANIMATION_FRAMES}.")
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
    except Exception as e:
        if logger:
            logger(f"Serial Error: {e}")

def save_single_pattern(pattern, name=None, overwrite=False):
    os.makedirs(SAVED_PATTERNS_DIR, exist_ok=True)
    name = clean_filename(name) + '.json' if name else f"pattern_{int(time.time())}.json"
    path = os.path.join(SAVED_PATTERNS_DIR, name)
    if os.path.exists(path) and not overwrite:
        replace = messagebox.askyesno("File Exists", f"'{name}' exists. Replace?")
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
    os.makedirs(SAVED_PATTERNS_DIR, exist_ok=True)
    name = clean_filename(name) + '.json' if name else f"animation_{int(time.time())}.json"
    path = os.path.join(SAVED_PATTERNS_DIR, name)
    if os.path.exists(path) and not overwrite:
        replace = messagebox.askyesno("File Exists", f"'{name}' exists. Replace?")
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

def mirror_pattern_horizontal(pattern):
    return [int(bin(row)[2:].zfill(8)[::-1], 2) for row in pattern]

def mirror_pattern_vertical(pattern):
    return pattern[::-1]

def mirror_animation_horizontal(frames):
    return [mirror_pattern_horizontal(frame) for frame in frames]

def mirror_animation_vertical(frames):
    return frames[::-1]

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
        if self.id:
            self.widget.after_cancel(self.id)
        self.id = None

    def create_tooltip(self, event=None):
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.configure(bg="#333333")
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
        if self.tw:
            self.tw.destroy()
        self.tw = None

class AnimationManager:
    def __init__(self, canvas, update_func):
        self.canvas = canvas
        self.update_leds = update_func
        self.playing = False
        self.stop_flag = threading.Event()

    def start(self, frames):
        if self.playing:
            self.stop()
        self.playing = True
        self.stop_flag.clear()
        threading.Thread(target=self._play, args=(frames,), daemon=True).start()

    def _play(self, frames):
        try:
            while self.playing:
                for frame in frames:
                    if self.stop_flag.is_set():
                        break
                    self.canvas.after(0, lambda f=frame: self._update_frame(f))
                    time.sleep(FRAME_DELAY_MS / 1000.0)
        finally:
            self.playing = False
            self.stop_flag.clear()

    def _update_frame(self, frame):
        self.update_leds(frame, animation=True)
        self.canvas.master.update_idletasks()

    def stop(self):
        if self.playing:
            self.stop_flag.set()

class LEDMatrixApp:
    def __init__(self, master):
        self.master = master
        master.title("LED Matrix Controller")
        master.geometry("1400x800")
        master.configure(bg="#121212")

        self.menu_bar = tk.Menu(master, background="#1f1f1f", foreground="#ffffff", tearoff=0)
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.exit_app)
        self.menu_bar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(self.menu_bar, tearoff=0)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", "LED Matrix Controller\nVersion 1.0"))
        self.menu_bar.add_cascade(label="Help", menu=help_menu)

        master.config(menu=self.menu_bar)

        self.title_font = tkfont.Font(family="Helvetica", size=18, weight="bold")
        self.label_font = tkfont.Font(family="Helvetica", size=12)
        self.button_font = tkfont.Font(family="Helvetica", size=12, weight="bold")

        self.create_ui()

        try:
            self.serial_conn = initialize_serial_connection()
            self.log("Serial connected.", "info")
        except Exception as e:
            messagebox.showerror("Serial Error", str(e))
            self.log(str(e), "error")
            sys.exit(1)

        self.create_led_preview()
        self.anim_manager = AnimationManager(self.canvas, self.update_leds)

        self.current_file = None
        self.current_pattern = None
        self.current_animation = None
        self.is_animation = False

    def create_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", background="#121212", foreground="#ffffff", font=self.label_font)
        style.configure("TButton", background="#1f1f1f", foreground="#ffffff", font=self.button_font, borderwidth=0, focuscolor='none')
        style.map("TButton", background=[('active', "#bb86fc")], foreground=[('active', "#ffffff")])
        style.configure("TEntry", fieldbackground="#1f1f1f", foreground="#ffffff", font=self.label_font, borderwidth=2, relief="groove")

        main_frame = ttk.Frame(self.master, padding="20 20 20 20")
        main_frame.grid(row=0, column=0, sticky='NSEW')
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=3)

        header_label = ttk.Label(main_frame, text="LED Matrix Controller", font=self.title_font, foreground="#bb86fc")
        header_label.grid(row=0, column=0, columnspan=2, pady=(0,10), sticky='w')

        desc_label = ttk.Label(main_frame, text="Pattern Description:")
        desc_label.grid(row=1, column=0, padx=(0, 10), pady=(0, 5), sticky='w')

        self.desc_entry = ttk.Entry(main_frame, width=60)
        self.desc_entry.grid(row=1, column=1, padx=(0, 0), pady=(0, 5), sticky='w')
        self.desc_entry.focus()
        self.desc_entry.bind('<KeyRelease>', self.toggle_buttons)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 10), sticky='w')

        self.gen_single_btn = ttk.Button(btn_frame, text="Generate Single Pattern", command=self.gen_single, state='disabled')
        self.gen_single_btn.grid(row=0, column=0, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.gen_single_btn, "Generate a single LED pattern.")

        self.gen_anim_btn = ttk.Button(btn_frame, text="Generate Animation", command=self.gen_animation, state='disabled')
        self.gen_anim_btn.grid(row=0, column=1, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.gen_anim_btn, "Generate an animation with multiple frames.")

        self.load_btn = ttk.Button(btn_frame, text="Browse Saved", command=self.load_ui)
        self.load_btn.grid(row=0, column=2, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.load_btn, "Browse and select a saved pattern/animation.")

        self.edit_btn = ttk.Button(btn_frame, text="Edit", command=self.edit_current, state='disabled')
        self.edit_btn.grid(row=0, column=3, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.edit_btn, "Edit the current pattern/animation.")

        self.publish_btn = ttk.Button(btn_frame, text="Publish", command=self.publish_current, state='disabled')
        self.publish_btn.grid(row=0, column=4, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.publish_btn, "Publish the current pattern/animation.")

        self.optimize_btn = ttk.Button(btn_frame, text="Optimize with AI", command=self.optimize_current, state='disabled')
        self.optimize_btn.grid(row=0, column=5, padx=(0,20), pady=5, sticky='w')
        Tooltip(self.optimize_btn, "Optimize the current pattern/animation.")

        self.mood_btn = ttk.Button(btn_frame, text="Mood Mode", command=self.open_mood_mode, state='normal')
        self.mood_btn.grid(row=0, column=6, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.mood_btn, "Generate patterns/animations based on mood.")

        exit_btn = ttk.Button(btn_frame, text="Exit", command=self.exit_app)
        exit_btn.grid(row=0, column=7, padx=(100, 0), pady=5, sticky='e')
        Tooltip(exit_btn, "Exit the application.")

        self.master.bind('<Control-g>', lambda e: self.gen_single())
        self.master.bind('<Control-a>', lambda e: self.gen_animation())
        self.master.bind('<Control-l>', lambda e: self.load_ui())
        self.master.bind('<Control-e>', lambda e: self.exit_app())

        log_label = ttk.Label(main_frame, text="Logs:")
        log_label.grid(row=3, column=0, padx=(0, 10), pady=(10, 5), sticky='w')

        self.log_area = scrolledtext.ScrolledText(main_frame, width=80, height=25, state='disabled', wrap='word', background="#000000", foreground="#ffffff")
        self.log_area.grid(row=4, column=0, columnspan=2, padx=(0, 0), pady=(0, 10), sticky='nsew')
        main_frame.rowconfigure(4, weight=1)
        main_frame.columnconfigure(1, weight=1)

    def create_led_preview(self):
        preview_frame = ttk.LabelFrame(self.master, text="LED Matrix Preview", padding="10 10 10 10")
        preview_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0), sticky='n')
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

    def disable_all_buttons(self):
        self.gen_single_btn.configure(state='disabled')
        self.gen_anim_btn.configure(state='disabled')
        self.edit_btn.configure(state='disabled')
        self.publish_btn.configure(state='disabled')
        self.optimize_btn.configure(state='disabled')
        self.mood_btn.configure(state='disabled')

    def enable_buttons(self):
        text = self.desc_entry.get().strip()
        state = 'normal' if text else 'disabled'
        self.gen_single_btn.configure(state=state)
        self.gen_anim_btn.configure(state=state)
        self.mood_btn.configure(state='normal')

    def gen_single(self):
        desc = self.desc_entry.get().strip()
        if not desc:
            messagebox.showwarning("Input Needed", "Enter a pattern description.")
            return
        self.disable_all_buttons()
        self.log("Generating single pattern...", "info")
        threading.Thread(target=self.generate_single_pattern, args=(desc,), daemon=True).start()

    def generate_single_pattern(self, desc):
        pattern = generate_patterns(desc, animation=False, logger=self.log, optimize=False)
        self.current_pattern = pattern.copy()
        self.current_animation = None
        self.is_animation = False
        self.current_file = None

        self.update_leds(pattern, animation=False)
        if pattern:
            self.log(f"Pattern: {pattern}", "success")
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
            self.optimize_btn.configure(state='normal')
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
        frames = generate_patterns(desc, animation=True, frame_count=5, logger=self.log, optimize=False)
        self.current_animation = [f.copy() for f in frames] if frames else None
        self.current_pattern = None
        self.is_animation = True if frames else False
        self.current_file = None

        if frames:
            self.log(f"Generated {len(frames)} frames.", "success")
            # Stop any current animation
            self.anim_manager.stop()
            # Start the new animation once
            self.anim_manager.start(frames)

            save = messagebox.askyesno("Save Animation", "Save this animation?")
            if save:
                filename = clean_filename(desc) + '.json'
                saved = save_animation_frames(frames, name=filename)
                if saved:
                    self.log(f"Animation saved as '{filename}'.", "success")
                    self.current_file = saved
                else:
                    self.log(f"Failed to save '{filename}'.", "error")

            send_animation(self.serial_conn, frames, logger=self.log)
            self.log("Animation sent.", "success")
            self.publish_btn.configure(state='normal')
            self.edit_btn.configure(state='normal')
            self.optimize_btn.configure(state='normal')
        else:
            self.log("Failed to generate animation.", "error")
        self.enable_buttons()

    def optimize_current(self):
        if not self.current_pattern and not self.current_animation:
            self.log("No pattern or animation to optimize.", "error")
            return
        self.disable_all_buttons()
        self.optimize_btn.configure(state='disabled')
        self.log("Optimizing with AI...", "info")
        threading.Thread(target=self.perform_optimization, daemon=True).start()

    def perform_optimization(self):
        try:
            # We do not restart the animation automatically here to avoid overlap
            if self.is_animation and self.current_animation:
                optimized = optimize_with_ai(self.current_animation, is_animation=True, logger=self.log)
                if optimized != self.current_animation:
                    self.current_animation = optimized
                    self.log("Animation optimized.", "success")
                    # Do not start animation again here to prevent overlap
                    send_animation(self.serial_conn, self.current_animation, logger=self.log)
                else:
                    self.log("No optimization change.", "info")
            elif self.current_pattern:
                optimized = optimize_with_ai(self.current_pattern, is_animation=False, logger=self.log)
                if optimized != self.current_pattern:
                    self.current_pattern = optimized
                    self.log("Pattern optimized.", "success")
                    send_single_frame(self.serial_conn, self.current_pattern, logger=self.log, update_preview=self.update_leds)
                else:
                    self.log("No optimization change.", "info")
        except Exception as e:
            self.log(f"Optimization failed: {e}", "error")
        finally:
            self.edit_btn.configure(state='normal')
            self.publish_btn.configure(state='normal')
            self.optimize_btn.configure(state='normal')
            self.enable_buttons()

    def load_ui(self):
        load_window = tk.Toplevel(self.master)
        load_window.title("Browse Saved Patterns/Animations")
        load_window.geometry("800x600")
        load_window.configure(bg="#121212")
        load_window.resizable(False, False)

        frame = ttk.Frame(load_window, padding="10 10 10 10")
        frame.pack(fill='both', expand=True)

        patterns_frame = ttk.LabelFrame(frame, text="Saved Patterns", padding="10 10 10 10")
        patterns_frame.pack(side='left', fill='both', expand=True, padx=(0, 10))

        anims_frame = ttk.LabelFrame(frame, text="Saved Animations", padding="10 10 10 10")
        anims_frame.pack(side='right', fill='both', expand=True, padx=(10, 0))

        p_list_frame = ttk.Frame(patterns_frame)
        p_list_frame.pack(fill='both', expand=True)
        p_scroll = ttk.Scrollbar(p_list_frame, orient='vertical')
        self.p_list = tk.Listbox(p_list_frame, font=self.label_font, yscrollcommand=p_scroll.set, background="#000000", fg="#ffffff")
        p_scroll.config(command=self.p_list.yview)
        p_scroll.pack(side='right', fill='y')
        self.p_list.pack(side='left', fill='both', expand=True)

        a_list_frame = ttk.Frame(anims_frame)
        a_list_frame.pack(fill='both', expand=True)
        a_scroll = ttk.Scrollbar(a_list_frame, orient='vertical')
        self.a_list = tk.Listbox(a_list_frame, font=self.label_font, yscrollcommand=a_scroll.set, background="#000000", fg="#ffffff")
        a_scroll.config(command=self.a_list.yview)
        a_scroll.pack(side='right', fill='y')
        self.a_list.pack(side='left', fill='both', expand=True)

        os.makedirs(SAVED_PATTERNS_DIR, exist_ok=True)
        files = [f for f in os.listdir(SAVED_PATTERNS_DIR) if f.endswith('.json')]
        for f in files:
            path = os.path.join(SAVED_PATTERNS_DIR, f)
            try:
                data = load_saved(path)
                if data.get('type') == 'single':
                    self.p_list.insert(tk.END, f)
                elif data.get('type') == 'animation':
                    self.a_list.insert(tk.END, f)
            except:
                continue

        if not files:
            messagebox.showinfo("No Files", "No saved patterns or animations found.")
            load_window.destroy()
            return

        preview = ttk.LabelFrame(frame, text="Select an item to load", padding="10 10 10 10")
        preview.pack(fill='both', expand=False, padx=(0, 0), pady=(10, 0))

        preview_label = ttk.Label(preview, text="Selecting a pattern or animation will load it immediately.")
        preview_label.pack(expand=True, fill='both')

        self.p_list.bind('<<ListboxSelect>>', lambda e: self.load_selection('single', self.p_list, load_window))
        self.a_list.bind('<<ListboxSelect>>', lambda e: self.load_selection('animation', self.a_list, load_window))

    def load_selection(self, file_type, listbox, window):
        selected = listbox.curselection()
        if not selected:
            return
        filename = listbox.get(selected[0])
        path = os.path.join(SAVED_PATTERNS_DIR, filename)
        try:
            data = load_saved(path)
            if data.get('type') != file_type:
                self.log(f"Type mismatch for '{filename}'.", "error")
                return

            # Stop current animation before loading a new one
            self.anim_manager.stop()

            if file_type == 'single':
                pattern = data.get('pattern')
                self.current_pattern = pattern.copy()
                self.current_animation = None
                self.is_animation = False
                self.current_file = path
                self.update_leds(pattern, animation=False)
            else:
                frames = data.get('patterns')
                self.current_animation = [f.copy() for f in frames]
                self.current_pattern = None
                self.is_animation = True
                self.current_file = path
                # Start the new animation once
                self.anim_manager.stop()
                self.anim_manager.start(frames)

            self.edit_btn.configure(state='normal')
            self.publish_btn.configure(state='normal')
            self.optimize_btn.configure(state='normal')
            self.log(f"Loaded '{filename}' successfully.", "success")

        except Exception as e:
            self.log(f"Failed to load '{filename}': {e}", "error")

    def edit_current(self):
        if self.is_animation:
            self.edit_animation()
        elif self.current_pattern:
            self.edit_pattern()

    def edit_pattern(self):
        if not self.current_pattern:
            self.log("No pattern to edit.", "error")
            return
        self.edit_pattern_window()

    def edit_pattern_window(self):
        edit_win = tk.Toplevel(self.master)
        edit_win.title("Edit Pattern")
        edit_win.geometry("500x550")
        edit_win.configure(bg="#121212")
        edit_win.resizable(False, False)

        canvas = tk.Canvas(edit_win, width=LED_DIAMETER * 8 + LED_SPACING * 9,
                           height=LED_DIAMETER * 8 + LED_SPACING * 9, bg="#000000")
        canvas.pack(pady=20)

        circles = []
        for r in range(8):
            row_circles = []
            for c in range(8):
                x1 = LED_SPACING + c*(LED_DIAMETER+LED_SPACING)
                y1 = LED_SPACING + r*(LED_DIAMETER+LED_SPACING)
                x2 = x1+LED_DIAMETER
                y2 = y1+LED_DIAMETER
                bit = self.current_pattern[r] & (1<<(7-c))
                color = ACTIVE_COLOR if bit else INACTIVE_COLOR
                cir = canvas.create_oval(x1,y1,x2,y2,fill=color,outline="")
                row_circles.append(cir)
            circles.append(row_circles)

        def toggle_led(event):
            x,y = event.x,event.y
            for rr in range(8):
                for cc in range(8):
                    co = canvas.coords(circles[rr][cc])
                    if co[0]<=x<=co[2] and co[1]<=y<=co[3]:
                        current = canvas.itemcget(circles[rr][cc],"fill")
                        new = INACTIVE_COLOR if current==ACTIVE_COLOR else ACTIVE_COLOR
                        canvas.itemconfig(circles[rr][cc],fill=new)
                        if new==ACTIVE_COLOR:
                            self.current_pattern[rr]|=(1<<(7-cc))
                        else:
                            self.current_pattern[rr]&=~(1<<(7-cc))
                        break

        canvas.bind("<Button-1>",toggle_led)

        btn_frame = ttk.Frame(edit_win)
        btn_frame.pack(pady=10)

        def redraw_pattern():
            for rr in range(8):
                bits=bin(self.current_pattern[rr])[2:].zfill(8)
                for cc,bit in enumerate(bits):
                    col=ACTIVE_COLOR if bit=='1' else INACTIVE_COLOR
                    canvas.itemconfig(circles[rr][cc],fill=col)

        def mirror_h():
            self.current_pattern=mirror_pattern_horizontal(self.current_pattern)
            redraw_pattern()

        def mirror_v():
            self.current_pattern=mirror_pattern_vertical(self.current_pattern)
            redraw_pattern()

        ttk.Button(btn_frame,text="Mirror Horizontal",command=mirror_h).grid(row=0,column=0,padx=5)
        ttk.Button(btn_frame,text="Mirror Vertical",command=mirror_v).grid(row=0,column=1,padx=5)

        ttk.Button(edit_win,text="Save",command=lambda:self.save_edited_pattern(edit_win)).pack(pady=10)

    def save_edited_pattern(self, window):
        self.log("Saving edited pattern...", "info")
        threading.Thread(target=self.perform_save_edited_pattern, args=(window,), daemon=True).start()

    def perform_save_edited_pattern(self, window):
        try:
            send_single_frame(self.serial_conn, self.current_pattern, logger=self.log, update_preview=self.update_leds)
            self.log("Edited pattern sent.", "success")
            if self.current_file and os.path.exists(self.current_file):
                data = {'type':'single','pattern':self.current_pattern}
                with open(self.current_file,'w') as f:
                    json.dump(data,f,indent=4)
                self.log("Pattern saved.", "success")
            else:
                save = messagebox.askyesno("Save Edited Pattern","Save?")
                if save:
                    filename=clean_filename("edited_pattern")+'.json'
                    saved = save_single_pattern(self.current_pattern,name=filename)
                    if saved:
                        self.log("Edited pattern saved.", "success")
                        self.current_file=saved
                    else:
                        self.log("Failed to save edited pattern.", "error")
                else:
                    self.log("Edited pattern not saved.","info")
        except Exception as e:
            self.log(f"Failed to save edited pattern: {e}","error")
        finally:
            window.destroy()

    def edit_animation(self):
        if not self.current_animation:
            self.log("No animation to edit.","error")
            return
        self.edit_animation_window()

    def edit_animation_window(self):
        edit_win=tk.Toplevel(self.master)
        edit_win.title("Edit Animation")
        edit_win.geometry("600x750")
        edit_win.configure(bg="#121212")
        edit_win.resizable(False,False)

        sel_frame=ttk.Frame(edit_win,padding="10 10 10 10")
        sel_frame.pack(fill='x')

        sel_label=ttk.Label(sel_frame,text="Select Frame:")
        sel_label.pack(side='left',padx=(0,10))

        frame_var=tk.IntVar(value=0)

        def update_canvas(index):
            pattern=self.current_animation[index]
            for rr in range(8):
                bits=bin(pattern[rr])[2:].zfill(8)
                for cc,bit in enumerate(bits):
                    col=ACTIVE_COLOR if bit=='1' else INACTIVE_COLOR
                    canvas.itemconfig(circles[rr][cc],fill=col)

        for i in range(len(self.current_animation)):
            ttk.Radiobutton(sel_frame,text=f"Frame {i+1}",variable=frame_var,value=i,command=lambda:update_canvas(frame_var.get())).pack(side='left')

        canvas=tk.Canvas(edit_win,width=LED_DIAMETER*8+LED_SPACING*9,
                         height=LED_DIAMETER*8+LED_SPACING*9,bg="#000000")
        canvas.pack(pady=20)

        circles=[]
        for row in range(8):
            row_circles=[]
            for col in range(8):
                x1=LED_SPACING+col*(LED_DIAMETER+LED_SPACING)
                y1=LED_SPACING+row*(LED_DIAMETER+LED_SPACING)
                x2=x1+LED_DIAMETER
                y2=y1+LED_DIAMETER
                color=ACTIVE_COLOR if self.current_animation[0][row]&(1<<(7-col))else INACTIVE_COLOR
                cir=canvas.create_oval(x1,y1,x2,y2,fill=color,outline="")
                row_circles.append(cir)
            circles.append(row_circles)

        def toggle_led(event):
            x,y=event.x,event.y
            idx=frame_var.get()
            for rr in range(8):
                for cc in range(8):
                    co=canvas.coords(circles[rr][cc])
                    if co[0]<=x<=co[2] and co[1]<=y<=co[3]:
                        current=canvas.itemcget(circles[rr][cc],"fill")
                        new=INACTIVE_COLOR if current==ACTIVE_COLOR else ACTIVE_COLOR
                        canvas.itemconfig(circles[rr][cc],fill=new)
                        if new==ACTIVE_COLOR:
                            self.current_animation[idx][rr]|=(1<<(7-cc))
                        else:
                            self.current_animation[idx][rr]&=~(1<<(7-cc))
                        break

        canvas.bind("<Button-1>",toggle_led)

        btn_frame=ttk.Frame(edit_win)
        btn_frame.pack(pady=10)

        def mirror_h():
            self.current_animation=mirror_animation_horizontal(self.current_animation)
            update_canvas(frame_var.get())

        def mirror_v():
            self.current_animation=mirror_animation_vertical(self.current_animation)
            update_canvas(frame_var.get())

        ttk.Button(btn_frame,text="Mirror Horizontal",command=mirror_h).grid(row=0,column=0,padx=5)
        ttk.Button(btn_frame,text="Mirror Vertical",command=mirror_v).grid(row=0,column=1,padx=5)

        ttk.Button(edit_win,text="Save",command=lambda:self.save_edited_animation(edit_win)).pack(pady=10)

        def update_canvas_on_init():
            update_canvas(0)
        update_canvas_on_init()

    def save_edited_animation(self, window):
        self.log("Saving edited animation...","info")
        threading.Thread(target=self.perform_save_edited_animation,args=(window,),daemon=True).start()

    def perform_save_edited_animation(self, window):
        try:
            send_animation(self.serial_conn,self.current_animation,logger=self.log)
            self.log("Edited animation sent.","success")
            if self.current_file and os.path.exists(self.current_file):
                data={'type':'animation','patterns':self.current_animation}
                with open(self.current_file,'w') as f:
                    json.dump(data,f,indent=4)
                self.log("Animation saved.","success")
            else:
                save=messagebox.askyesno("Save Edited Animation","Save?")
                if save:
                    filename=clean_filename("edited_animation")+'.json'
                    saved=save_animation_frames(self.current_animation,name=filename)
                    if saved:
                        self.log("Edited animation saved.","success")
                        self.current_file=saved
                    else:
                        self.log("Failed to save edited animation.","error")
                else:
                    self.log("Edited animation not saved.","info")
        except Exception as e:
            self.log(f"Failed to save edited animation: {e}","error")
        finally:
            window.destroy()

    def publish_current(self):
        if not self.current_file:
            self.log("No file loaded to publish.","error")
            return
        if self.is_animation and self.current_animation:
            try:
                data={'type':'animation','patterns':self.current_animation}
                with open(self.current_file,'w') as f:
                    json.dump(data,f,indent=4)
                self.log("Animation saved.","success")
            except Exception as e:
                self.log(f"Failed to save animation: {e}","error")
                return
            send_animation(self.serial_conn,self.current_animation,logger=self.log)
            self.log("Animation published.","success")
        elif not self.is_animation and self.current_pattern:
            try:
                data={'type':'single','pattern':self.current_pattern}
                with open(self.current_file,'w') as f:
                    json.dump(data,f,indent=4)
                self.log("Pattern saved.","success")
            except Exception as e:
                self.log(f"Failed to save pattern: {e}","error")
                return
            send_single_frame(self.serial_conn,self.current_pattern,logger=self.log,update_preview=self.update_leds)
            self.log("Pattern published.","success")
        else:
            self.log("Nothing to publish.","error")

    def exit_app(self):
        if messagebox.askokcancel("Exit","Exit the application?"):
            try:
                if self.anim_manager.playing:
                    self.anim_manager.stop()
                self.serial_conn.close()
                self.log("Serial connection closed.","info")
            except:
                pass
            self.master.destroy()

    def open_mood_mode(self):
        mood_window=tk.Toplevel(self.master)
        mood_window.title("AI-Powered Mood Matrix")
        mood_window.geometry("500x400")
        mood_window.configure(bg="#121212")
        mood_window.resizable(False,False)

        frame=ttk.Frame(mood_window,padding="20 20 20 20")
        frame.pack(fill='both',expand=True)

        mood_label=ttk.Label(frame,text="Select a Mood or Enter Custom Description:")
        mood_label.pack(pady=(0,10),anchor='w')

        predefined_moods=["Calm","Excited","Sad","Happy","Angry","Romantic","Mysterious"]
        self.mood_var=tk.StringVar()
        self.mood_combobox=ttk.Combobox(frame,textvariable=self.mood_var,values=predefined_moods,state='readonly')
        self.mood_combobox.pack(fill='x',pady=(0,10))
        self.mood_combobox.set("Select a Mood")

        custom_label=ttk.Label(frame,text="Or Enter a Custom Description:")
        custom_label.pack(pady=(10,5),anchor='w')

        self.custom_desc_entry=ttk.Entry(frame,width=50)
        self.custom_desc_entry.pack(fill='x',pady=(0,10))
        self.custom_desc_entry.bind('<KeyRelease>',self.toggle_mood_buttons)

        btn_frame=ttk.Frame(frame)
        btn_frame.pack(pady=10)

        self.gen_mood_pattern_btn=ttk.Button(btn_frame,text="Generate Pattern",command=lambda:self.gen_mood_pattern(mood_window),state='disabled')
        self.gen_mood_pattern_btn.grid(row=0,column=0,padx=(0,20))
        Tooltip(self.gen_mood_pattern_btn,"Generate a single pattern for the mood.")

        self.gen_mood_anim_btn=ttk.Button(btn_frame,text="Generate Animation",command=lambda:self.gen_mood_animation(mood_window),state='disabled')
        self.gen_mood_anim_btn.grid(row=0,column=1,padx=(20,0))
        Tooltip(self.gen_mood_anim_btn,"Generate an animation for the mood.")

    def toggle_mood_buttons(self,event=None):
        mood=self.mood_var.get()
        custom_desc=self.custom_desc_entry.get().strip()
        if mood!="Select a Mood":
            self.gen_mood_pattern_btn.configure(state='normal')
            self.gen_mood_anim_btn.configure(state='normal')
            self.custom_desc_entry.delete(0,tk.END)
        elif custom_desc:
            self.gen_mood_pattern_btn.configure(state='normal')
            self.gen_mood_anim_btn.configure(state='normal')
        else:
            self.gen_mood_pattern_btn.configure(state='disabled')
            self.gen_mood_anim_btn.configure(state='disabled')

    def get_mood_description(self):
        mood=self.mood_var.get()
        custom_desc=self.custom_desc_entry.get().strip()
        if mood!="Select a Mood":
            return mood.lower()
        elif custom_desc:
            return custom_desc
        else:
            return None

    def gen_mood_pattern(self,window):
        desc=self.get_mood_description()
        if not desc:
            messagebox.showwarning("Input Needed","Select a mood or enter a description.")
            return
        self.disable_all_buttons()
        self.log(f"Generating pattern for mood: '{desc}'","info")
        threading.Thread(target=self.generate_mood_pattern,args=(desc,window),daemon=True).start()

    def generate_mood_pattern(self,desc,window):
        pattern=generate_patterns(desc,animation=False,logger=self.log,optimize=True)
        self.current_pattern=pattern.copy()
        self.current_animation=None
        self.is_animation=False
        self.current_file=None

        self.update_leds(pattern,animation=False)
        if pattern:
            self.log(f"Mood Pattern: {pattern}","success")
            save=messagebox.askyesno("Save Pattern","Save this mood pattern?")
            if save:
                filename=clean_filename(f"mood_{desc}")+'.json'
                saved=save_single_pattern(pattern,name=filename)
                if saved:
                    self.log(f"Mood pattern saved as '{filename}'.","success")
                    self.current_file=saved
                else:
                    self.log(f"Failed to save '{filename}'.","error")
            send_single_frame(self.serial_conn,pattern,logger=self.log,update_preview=self.update_leds)
            self.log("Mood pattern sent.","success")
            self.publish_btn.configure(state='normal')
            self.edit_btn.configure(state='normal')
            self.optimize_btn.configure(state='normal')
        else:
            self.log("Failed to generate mood pattern.","error")
        self.enable_buttons()
        window.destroy()

    def gen_mood_animation(self,window):
        desc=self.get_mood_description()
        if not desc:
            messagebox.showwarning("Input Needed","Select a mood or enter a description.")
            return
        self.disable_all_buttons()
        self.log(f"Generating animation for mood: '{desc}'","info")
        threading.Thread(target=self.generate_mood_animation,args=(desc,window),daemon=True).start()

    def generate_mood_animation(self,desc,window):
        frames=generate_patterns(desc,animation=True,frame_count=5,logger=self.log,optimize=True)
        self.current_animation=[f.copy() for f in frames]if frames else None
        self.current_pattern=None
        self.is_animation=True if frames else False
        self.current_file=None
        if frames:
            self.log(f"Generated {len(frames)} frames for mood animation.","success")
            # Stop old animation first
            self.anim_manager.stop()
            # Start new animation once
            self.anim_manager.start(frames)

            save=messagebox.askyesno("Save Animation","Save this mood animation?")
            if save:
                filename=clean_filename(f"mood_{desc}")+'.json'
                saved=save_animation_frames(frames,name=filename)
                if saved:
                    self.log(f"Mood animation saved as '{filename}'.","success")
                    self.current_file=saved
                else:
                    self.log("Failed to save.","error")

            send_animation(self.serial_conn,frames,logger=self.log)
            self.log("Mood animation sent.","success")
            self.publish_btn.configure(state='normal')
            self.edit_btn.configure(state='normal')
            self.optimize_btn.configure(state='normal')
        else:
            self.log("Failed to generate mood animation.","error")
        self.enable_buttons()
        window.destroy()

def main():
    root = tk.Tk()
    app = LEDMatrixApp(root)
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    root.mainloop()

if __name__=="__main__":
    main()