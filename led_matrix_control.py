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
SAVED_PATTERNS_DIR = "saved_patterns"

USE_MOCK_SERIAL = True

# Load environment variables
load_dotenv()
API_KEY = os.getenv('GLHF_API_KEY')
if not API_KEY:
    raise ValueError("GLHF_API_KEY not set in environment.")

# OpenAI Configuration
openai.api_key = API_KEY
openai.api_base = "https://glhf.chat/api/openai/v1"

class MockSerial:
    def __init__(self):
        self.received_data = []
        print("[MockSerial] Initialized.")

    def write(self, data):
        print(f"[MockSerial] Writing: {data}")
        if data[0] in (0xFF, 0xFA):
            threading.Timer(0.5, self.mock_ack, args=(data[0],)).start()

    def mock_ack(self, type):
        print(f"[MockSerial] Ack: {'Pattern' if type == 0xFF else 'Animation'} received.")

    def readline(self):
        return b"Pattern received.\n"

    def flush(self):
        pass

    def close(self):
        print("[MockSerial] Closing.")

def find_arduino_port():
    patterns = ['/dev/cu.usbserial*', '/dev/ttyUSB*', '/dev/ttyACM*', 'COM3', 'COM4']
    ports = [p for pattern in patterns for p in glob.glob(pattern)]
    if not ports:
        raise Exception("No Arduino port found.")
    if len(ports) > 1:
        raise Exception("Multiple ports found.")
    return ports[0]

def init_serial():
    if USE_MOCK_SERIAL:
        return MockSerial()
    try:
        port = find_arduino_port()
        ser = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)  # Allow time for Arduino to reset
        return ser
    except Exception as e:
        if USE_MOCK_SERIAL:
            print(f"[Error] {e}. Using MockSerial.")
            return MockSerial()
        else:
            raise e

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def simple_pattern():
    return [(1 << (7 - i)) | (1 << i) for i in range(8)]

def simple_animation(frames=5):
    return [simple_pattern() for _ in range(frames)]

def parse_response(raw, logger):
    nums = [int(n) for n in re.findall(r'\d+', raw) if 0 <= int(n) <= 255]
    return nums[:8] if len(nums) >= 8 else None

def safe_chat_completion(model, messages, logger=None, stream=False):
    try:
        completion = openai.ChatCompletion.create(model=model, messages=messages, stream=stream)
        if stream:
            return "".join(chunk.choices[0].delta.get('content', '') for chunk in completion).strip()
        else:
            return completion.choices[0].message.content.strip() if completion and completion.choices else None
    except Exception as e:
        if logger:
            logger(f"API error: {e}")
        return None

def generate_patterns(prompt, animation=False, frame_count=5, logger=None, optimize=False):
    system_content = (
        "Generate a visually meaningful 8x8 LED pattern. "
        "Output 8 integers (0-255) separated by commas, no extra text."
    )
    if optimize:
        system_content += " Optimize for symmetry and simplicity."

    model = "hf:meta-llama/Meta-Llama-3.1-405B-Instruct"
    for attempt in range(3):
        if not animation:
            user_content = f"Description: '{prompt}'. Generate pattern."
            response = safe_chat_completion(model, [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ], logger=logger)
            if response:
                nums = parse_response(response, logger)
                if nums:
                    return nums
                logger(f"Attempt {attempt+1}: Invalid pattern.")
        else:
            frames = []
            for i in range(frame_count):
                user_content = f"Description: '{prompt}' (Frame {i+1}). Generate frame."
                response = safe_chat_completion(model, [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ], logger=logger)
                if response:
                    nums = parse_response(response, logger)
                    if nums:
                        frames.append(nums)
                    else:
                        break
            if len(frames) == frame_count:
                return frames
        logger(f"Attempt {attempt+1}: Failed.")
    logger("Using fallback.")
    return simple_animation(frame_count) if animation else simple_pattern()

def optimize_with_ai(data, is_animation=False, logger=None):
    system_content = (
        "Optimize pattern/animation for symmetry and simplicity. "
        "Output 8 integers (0-255) per frame, separated by commas, no extra text."
    )
    model = "hf:meta-llama/Meta-Llama-3.1-405B-Instruct"
    if is_animation:
        optimized_frames = []
        for i, frame in enumerate(data):
            user_msg = f"Original frame {i+1}: {frame}. Optimize."
            response = safe_chat_completion(model, [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_msg}
            ], logger=logger)
            if response:
                nums = parse_response(response, logger)
                if nums and nums != frame:
                    optimized_frames.append(nums)
                else:
                    return simple_animation(len(data))
        return optimized_frames if len(optimized_frames) == len(data) else simple_animation(len(data))
    else:
        user_msg = f"Original: {data}. Optimize."
        response = safe_chat_completion(model, [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_msg}
        ], logger=logger)
        if response:
            nums = parse_response(response, logger)
            return nums if nums and nums != data else simple_pattern()
        return simple_pattern()

def send_frame(ser, pattern, logger=None, update_preview=None):
    if len(pattern) != 8:
        if logger:
            logger("Pattern must have 8 integers.")
        return
    try:
        ser.write(bytes([0xFF]))
        for byte in pattern:
            ser.write(bytes([byte]))
        ser.write(bytes([0xFE]))
        if update_preview:
            update_preview(pattern, animation=False)
    except Exception as e:
        if logger:
            logger(f"Serial error: {e}")

def send_animation(ser, frames, logger=None):
    count = len(frames)
    if not 0 < count <= MAX_ANIMATION_FRAMES:
        if logger:
            logger(f"Frames must be 1-{MAX_ANIMATION_FRAMES}.")
        return
    try:
        ser.write(bytes([0xFA, count]))
        for frame in frames:
            for byte in frame:
                ser.write(bytes([byte]))
        ser.write(bytes([0xFB]))
    except Exception as e:
        if logger:
            logger(f"Serial error: {e}")

def save_data(data, name=None, overwrite=False):
    os.makedirs(SAVED_PATTERNS_DIR, exist_ok=True)
    name = clean_filename(name) + '.json' if name else f"{data['type']}_{int(time.time())}.json"
    path = os.path.join(SAVED_PATTERNS_DIR, name)
    if os.path.exists(path) and not overwrite:
        if not messagebox.askyesno("File Exists", f"'{name}' exists. Replace?"):
            return None
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
        return path
    except:
        return None

def load_saved(path):
    with open(path, 'r') as f:
        return json.load(f)

def mirror_pattern(pattern, horizontal=True):
    if horizontal:
        return [int(bin(row)[2:].zfill(8)[::-1], 2) for row in pattern]
    return pattern[::-1]

def mirror_animation(frames, horizontal=True):
    return [mirror_pattern(frame, horizontal) for frame in frames]

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)
        self.id = None
        self.tw = None

    def show(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
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
            wraplength=300,
            font=("Helvetica", 10)
        )
        label.pack(ipadx=1)

    def hide(self, event=None):
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
        while self.playing:
            for frame in frames:
                if self.stop_flag.is_set():
                    break
                self.canvas.after(0, lambda f=frame: self._update_frame(f))
                time.sleep(FRAME_DELAY_MS / 1000.0)
        self.playing = False
        self.stop_flag.clear()

    def _update_frame(self, frame):
        self.update_leds(frame, animation=True)

    def stop(self):
        if self.playing:
            self.stop_flag.set()

class LEDMatrixApp:
    def __init__(self, master):
        self.master = master
        master.title("LED Matrix Controller")
        master.geometry("1400x800")
        master.configure(bg="#121212")

        self.menu_bar = tk.Menu(master, tearoff=0, bg="#1f1f1f", fg="#ffffff")
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
            self.serial_conn = init_serial()
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

        main_frame = ttk.Frame(self.master, padding="20")
        main_frame.grid(sticky='NSEW')
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        ttk.Label(main_frame, text="LED Matrix Controller", font=self.title_font, foreground="#bb86fc").grid(row=0, column=0, columnspan=2, pady=(0,10), sticky='w')
        ttk.Label(main_frame, text="Pattern Description:").grid(row=1, column=0, pady=(0, 5), sticky='w')

        self.desc_entry = ttk.Entry(main_frame, width=60)
        self.desc_entry.grid(row=1, column=1, pady=(0, 5), sticky='w')
        self.desc_entry.bind('<KeyRelease>', self.toggle_buttons)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 10), sticky='w')

        self.gen_single_btn = ttk.Button(btn_frame, text="Generate Single", command=self.gen_single, state='disabled')
        self.gen_single_btn.grid(row=0, column=0, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.gen_single_btn, "Generate a single LED pattern.")

        self.gen_anim_btn = ttk.Button(btn_frame, text="Generate Animation", command=self.gen_animation, state='disabled')
        self.gen_anim_btn.grid(row=0, column=1, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.gen_anim_btn, "Generate an animation.")

        self.load_btn = ttk.Button(btn_frame, text="Browse Saved", command=self.load_ui)
        self.load_btn.grid(row=0, column=2, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.load_btn, "Browse saved patterns/animations.")

        self.edit_btn = ttk.Button(btn_frame, text="Edit", command=self.edit_current, state='disabled')
        self.edit_btn.grid(row=0, column=3, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.edit_btn, "Edit current pattern/animation.")

        self.publish_btn = ttk.Button(btn_frame, text="Publish", command=self.publish_current, state='disabled')
        self.publish_btn.grid(row=0, column=4, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.publish_btn, "Publish current pattern/animation.")

        self.optimize_btn = ttk.Button(btn_frame, text="Optimize with AI", command=self.optimize_current, state='disabled')
        self.optimize_btn.grid(row=0, column=5, padx=(0,20), pady=5, sticky='w')
        Tooltip(self.optimize_btn, "Optimize current pattern/animation.")

        self.mood_btn = ttk.Button(btn_frame, text="Mood Mode", command=self.open_mood_mode, state='normal')
        self.mood_btn.grid(row=0, column=6, padx=(0, 20), pady=5, sticky='w')
        Tooltip(self.mood_btn, "Generate based on mood.")

        exit_btn = ttk.Button(btn_frame, text="Exit", command=self.exit_app)
        exit_btn.grid(row=0, column=7, padx=(100, 0), pady=5, sticky='e')
        Tooltip(exit_btn, "Exit.")

        self.master.bind('<Control-g>', lambda e: self.gen_single())
        self.master.bind('<Control-a>', lambda e: self.gen_animation())
        self.master.bind('<Control-l>', lambda e: self.load_ui())
        self.master.bind('<Control-e>', lambda e: self.exit_app())

        ttk.Label(main_frame, text="Logs:").grid(row=3, column=0, pady=(10, 5), sticky='w')

        self.log_area = scrolledtext.ScrolledText(main_frame, width=80, height=25, state='disabled', wrap='word', bg="#000000", fg="#ffffff")
        self.log_area.grid(row=4, column=0, columnspan=2, pady=(0, 10), sticky='nsew')
        main_frame.rowconfigure(4, weight=1)
        main_frame.columnconfigure(1, weight=1)

    def create_led_preview(self):
        preview_frame = ttk.LabelFrame(self.master, text="LED Preview", padding="10")
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
                x2, y2 = x1 + LED_DIAMETER, y1 + LED_DIAMETER
                circle = self.canvas.create_oval(x1, y1, x2, y2, fill=INACTIVE_COLOR, outline="")
                row_leds.append(circle)
            self.leds.append(row_leds)

    def update_leds(self, pattern, animation=False):
        for row, byte in enumerate(pattern):
            bits = bin(byte)[2:].zfill(8)
            for col, bit in enumerate(bits):
                color = ACTIVE_COLOR if bit == '1' else INACTIVE_COLOR
                self.canvas.itemconfig(self.leds[row][col], fill=color)

    def toggle_buttons(self, event=None):
        state = 'normal' if self.desc_entry.get().strip() else 'disabled'
        self.gen_single_btn.configure(state=state)
        self.gen_anim_btn.configure(state=state)

    def log(self, msg, level="info"):
        self.log_area.config(state='normal')
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        color = {"error": "#cf6679", "success": "#03dac6"}.get(level, "#ffffff")
        self.log_area.insert(tk.END, f"{timestamp} - {msg}\n", (level,))
        self.log_area.tag_config(level, foreground=color)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def disable_all_buttons(self):
        for btn in (self.gen_single_btn, self.gen_anim_btn, self.edit_btn, self.publish_btn, self.optimize_btn, self.mood_btn):
            btn.configure(state='disabled')

    def enable_buttons(self):
        self.toggle_buttons()
        self.mood_btn.configure(state='normal')

    def gen_single(self):
        desc = self.desc_entry.get().strip()
        if not desc:
            messagebox.showwarning("Input Needed", "Enter description.")
            return
        self.disable_all_buttons()
        self.log("Generating single...", "info")
        threading.Thread(target=self.generate_single_pattern, args=(desc,), daemon=True).start()

    def generate_single_pattern(self, desc):
        pattern = generate_patterns(desc, logger=self.log)
        self.current_pattern = pattern.copy()
        self.current_animation = None
        self.is_animation = False
        self.current_file = None

        self.update_leds(pattern)
        if pattern:
            self.log(f"Pattern: {pattern}", "success")
            if messagebox.askyesno("Save Pattern", "Save?"):
                filename = clean_filename(desc) + '.json'
                saved = save_data({'type': 'single', 'pattern': pattern}, name=filename)
                if saved:
                    self.log(f"Saved as '{filename}'.", "success")
                    self.current_file = saved
                else:
                    self.log(f"Failed to save '{filename}'.", "error")
            send_frame(self.serial_conn, pattern, logger=self.log, update_preview=self.update_leds)
            self.log("Pattern sent.", "success")
            self.after_generation()
        else:
            self.log("Failed to generate.", "error")
        self.enable_buttons()

    def gen_animation(self):
        desc = self.desc_entry.get().strip()
        if not desc:
            messagebox.showwarning("Input Needed", "Enter description.")
            return
        self.disable_all_buttons()
        self.log("Generating animation...", "info")
        threading.Thread(target=self.generate_animation_patterns, args=(desc,), daemon=True).start()

    def generate_animation_patterns(self, desc):
        frames = generate_patterns(desc, animation=True, frame_count=5, logger=self.log)
        self.current_animation = [f.copy() for f in frames] if frames else None
        self.current_pattern = None
        self.is_animation = bool(frames)
        self.current_file = None

        if frames:
            self.log(f"Generated {len(frames)} frames.", "success")
            self.anim_manager.stop()
            self.anim_manager.start(frames)

            if messagebox.askyesno("Save Animation", "Save?"):
                filename = clean_filename(desc) + '.json'
                saved = save_data({'type': 'animation', 'patterns': frames}, name=filename)
                if saved:
                    self.log(f"Saved as '{filename}'.", "success")
                    self.current_file = saved
                else:
                    self.log(f"Failed to save '{filename}'.", "error")

            send_animation(self.serial_conn, frames, logger=self.log)
            self.log("Animation sent.", "success")
            self.after_generation()
        else:
            self.log("Failed to generate.", "error")
        self.enable_buttons()

    def after_generation(self):
        self.publish_btn.configure(state='normal')
        self.edit_btn.configure(state='normal')
        self.optimize_btn.configure(state='normal')

    def optimize_current(self):
        if not self.current_pattern and not self.current_animation:
            self.log("Nothing to optimize.", "error")
            return
        self.disable_all_buttons()
        self.log("Optimizing...", "info")
        threading.Thread(target=self.perform_optimization, daemon=True).start()

    def perform_optimization(self):
        try:
            if self.is_animation and self.current_animation:
                optimized = optimize_with_ai(self.current_animation, is_animation=True, logger=self.log)
                if optimized != self.current_animation:
                    self.current_animation = optimized
                    self.log("Animation optimized.", "success")
                    send_animation(self.serial_conn, self.current_animation, logger=self.log)
                else:
                    self.log("No change.", "info")
            elif self.current_pattern:
                optimized = optimize_with_ai(self.current_pattern, is_animation=False, logger=self.log)
                if optimized != self.current_pattern:
                    self.current_pattern = optimized
                    self.log("Pattern optimized.", "success")
                    send_frame(self.serial_conn, self.current_pattern, logger=self.log, update_preview=self.update_leds)
                else:
                    self.log("No change.", "info")
        except Exception as e:
            self.log(f"Optimization failed: {e}", "error")
        finally:
            self.after_generation()
            self.enable_buttons()

    def load_ui(self):
        load_window = tk.Toplevel(self.master)
        load_window.title("Browse Saved")
        load_window.geometry("800x600")
        load_window.configure(bg="#121212")
        load_window.resizable(False, False)

        frame = ttk.Frame(load_window, padding="10")
        frame.pack(fill='both', expand=True)

        patterns_frame = ttk.LabelFrame(frame, text="Patterns", padding="10")
        patterns_frame.pack(side='left', fill='both', expand=True, padx=(0, 10))

        anims_frame = ttk.LabelFrame(frame, text="Animations", padding="10")
        anims_frame.pack(side='right', fill='both', expand=True, padx=(10, 0))

        self.p_list = tk.Listbox(patterns_frame, font=self.label_font, bg="#000000", fg="#ffffff")
        self.p_list.pack(side='left', fill='both', expand=True)
        ttk.Scrollbar(patterns_frame, orient='vertical', command=self.p_list.yview).pack(side='right', fill='y')
        self.p_list.config(yscrollcommand=self.p_list.yview)

        self.a_list = tk.Listbox(anims_frame, font=self.label_font, bg="#000000", fg="#ffffff")
        self.a_list.pack(side='left', fill='both', expand=True)
        ttk.Scrollbar(anims_frame, orient='vertical', command=self.a_list.yview).pack(side='right', fill='y')
        self.a_list.config(yscrollcommand=self.a_list.yview)

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
            messagebox.showinfo("No Files", "No saved files found.")
            load_window.destroy()
            return

        ttk.Label(frame, text="Selecting loads immediately.").pack(fill='both', expand=False, pady=(10, 0))

        self.p_list.bind('<<ListboxSelect>>', lambda e: self.load_selection('single', self.p_list, load_window))
        self.a_list.bind('<<ListboxSelect>>', lambda e: self.load_selection('animation', self.a_list, load_window))

    def load_selection(self, type, listbox, window):
        selected = listbox.curselection()
        if not selected:
            return
        filename = listbox.get(selected[0])
        path = os.path.join(SAVED_PATTERNS_DIR, filename)
        try:
            data = load_saved(path)
            if data.get('type') != type:
                self.log(f"Type mismatch for '{filename}'.", "error")
                return

            self.anim_manager.stop()

            if type == 'single':
                self.current_pattern = data.get('pattern').copy()
                self.current_animation = None
                self.is_animation = False
                self.update_leds(self.current_pattern)
            else:
                self.current_animation = [f.copy() for f in data.get('patterns')]
                self.current_pattern = None
                self.is_animation = True
                self.anim_manager.start(self.current_animation)

            self.current_file = path
            self.after_generation()
            self.log(f"Loaded '{filename}'.", "success")

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
                x1, y1 = LED_SPACING + c*(LED_DIAMETER+LED_SPACING), LED_SPACING + r*(LED_DIAMETER+LED_SPACING)
                x2, y2 = x1+LED_DIAMETER, y1+LED_DIAMETER
                bit = self.current_pattern[r] & (1<<(7-c))
                color = ACTIVE_COLOR if bit else INACTIVE_COLOR
                cir = canvas.create_oval(x1,y1,x2,y2,fill=color,outline="")
                row_circles.append(cir)
            circles.append(row_circles)

        def toggle_led(event):
            x, y = event.x, event.y
            for rr in range(8):
                for cc in range(8):
                    co = canvas.coords(circles[rr][cc])
                    if co[0] <= x <= co[2] and co[1] <= y <= co[3]:
                        current = canvas.itemcget(circles[rr][cc], "fill")
                        new = INACTIVE_COLOR if current == ACTIVE_COLOR else ACTIVE_COLOR
                        canvas.itemconfig(circles[rr][cc], fill=new)
                        if new == ACTIVE_COLOR:
                            self.current_pattern[rr] |= (1 << (7 - cc))
                        else:
                            self.current_pattern[rr] &= ~(1 << (7 - cc))
                        break

        canvas.bind("<Button-1>", toggle_led)

        btn_frame = ttk.Frame(edit_win)
        btn_frame.pack(pady=10)

        def redraw_pattern():
            for rr in range(8):
                bits = bin(self.current_pattern[rr])[2:].zfill(8)
                for cc, bit in enumerate(bits):
                    col = ACTIVE_COLOR if bit == '1' else INACTIVE_COLOR
                    canvas.itemconfig(circles[rr][cc], fill=col)

        def mirror_h():
            self.current_pattern = mirror_pattern(self.current_pattern, horizontal=True)
            redraw_pattern()

        def mirror_v():
            self.current_pattern = mirror_pattern(self.current_pattern, horizontal=False)
            redraw_pattern()

        ttk.Button(btn_frame, text="Mirror Horizontal", command=mirror_h).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Mirror Vertical", command=mirror_v).grid(row=0, column=1, padx=5)

        ttk.Button(edit_win, text="Save", command=lambda: self.save_edited_pattern(edit_win)).pack(pady=10)

    def save_edited_pattern(self, window):
        self.log("Saving edited pattern...", "info")
        threading.Thread(target=self.perform_save_edited_pattern, args=(window,), daemon=True).start()

    def perform_save_edited_pattern(self, window):
        try:
            send_frame(self.serial_conn, self.current_pattern, logger=self.log, update_preview=self.update_leds)
            self.log("Edited pattern sent.", "success")
            if self.current_file and os.path.exists(self.current_file):
                data = {'type': 'single', 'pattern': self.current_pattern}
                with open(self.current_file, 'w') as f:
                    json.dump(data, f, indent=4)
                self.log("Pattern saved.", "success")
            else:
                save = messagebox.askyesno("Save Edited Pattern", "Save?")
                if save:
                    filename = clean_filename("edited_pattern") + '.json'
                    saved = save_data({'type': 'single', 'pattern': self.current_pattern}, name=filename)
                    if saved:
                        self.log("Edited pattern saved.", "success")
                        self.current_file = saved
                    else:
                        self.log("Failed to save edited pattern.", "error")
                else:
                    self.log("Edited pattern not saved.", "info")
        except Exception as e:
            self.log(f"Failed to save edited pattern: {e}", "error")
        finally:
            window.destroy()

    def edit_animation(self):
        if not self.current_animation:
            self.log("No animation to edit.", "error")
            return
        self.edit_animation_window()

    def edit_animation_window(self):
        edit_win = tk.Toplevel(self.master)
        edit_win.title("Edit Animation")
        edit_win.geometry("600x750")
        edit_win.configure(bg="#121212")
        edit_win.resizable(False, False)

        sel_frame = ttk.Frame(edit_win, padding="10")
        sel_frame.pack(fill='x')

        sel_label = ttk.Label(sel_frame, text="Select Frame:")
        sel_label.pack(side='left', padx=(0,10))

        frame_var = tk.IntVar(value=0)

        def update_canvas(index):
            pattern = self.current_animation[index]
            for rr in range(8):
                bits = bin(pattern[rr])[2:].zfill(8)
                for cc, bit in enumerate(bits):
                    col = ACTIVE_COLOR if bit == '1' else INACTIVE_COLOR
                    canvas.itemconfig(circles[rr][cc], fill=col)

        for i in range(len(self.current_animation)):
            ttk.Radiobutton(sel_frame, text=f"Frame {i+1}", variable=frame_var, value=i, command=lambda: update_canvas(frame_var.get())).pack(side='left')

        canvas = tk.Canvas(edit_win, width=LED_DIAMETER*8 + LED_SPACING*9,
                           height=LED_DIAMETER*8 + LED_SPACING*9, bg="#000000")
        canvas.pack(pady=20)

        circles = []
        for row in range(8):
            row_circles = []
            for col in range(8):
                x1 = LED_SPACING + col*(LED_DIAMETER+LED_SPACING)
                y1 = LED_SPACING + row*(LED_DIAMETER+LED_SPACING)
                x2, y2 = x1 + LED_DIAMETER, y1 + LED_DIAMETER
                color = ACTIVE_COLOR if self.current_animation[0][row] & (1 << (7 - col)) else INACTIVE_COLOR
                cir = canvas.create_oval(x1, y1, x2, y2, fill=color, outline="")
                row_circles.append(cir)
            circles.append(row_circles)

        def toggle_led(event):
            x, y = event.x, event.y
            idx = frame_var.get()
            for rr in range(8):
                for cc in range(8):
                    co = canvas.coords(circles[rr][cc])
                    if co[0] <= x <= co[2] and co[1] <= y <= co[3]:
                        current = canvas.itemcget(circles[rr][cc], "fill")
                        new = INACTIVE_COLOR if current == ACTIVE_COLOR else ACTIVE_COLOR
                        canvas.itemconfig(circles[rr][cc], fill=new)
                        if new == ACTIVE_COLOR:
                            self.current_animation[idx][rr] |= (1 << (7 - cc))
                        else:
                            self.current_animation[idx][rr] &= ~(1 << (7 - cc))
                        break

        canvas.bind("<Button-1>", toggle_led)

        btn_frame = ttk.Frame(edit_win)
        btn_frame.pack(pady=10)

        def redraw_animation():
            for rr in range(8):
                bits = bin(self.current_animation[frame_var.get()][rr])[2:].zfill(8)
                for cc, bit in enumerate(bits):
                    col = ACTIVE_COLOR if bit == '1' else INACTIVE_COLOR
                    canvas.itemconfig(circles[rr][cc], fill=col)

        def mirror_h():
            self.current_animation = mirror_animation(self.current_animation, horizontal=True)
            redraw_animation()

        def mirror_v():
            self.current_animation = mirror_animation(self.current_animation, horizontal=False)
            redraw_animation()

        ttk.Button(btn_frame, text="Mirror Horizontal", command=mirror_h).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Mirror Vertical", command=mirror_v).grid(row=0, column=1, padx=5)

        ttk.Button(edit_win, text="Save", command=lambda: self.save_edited_animation(edit_win)).pack(pady=10)

        def update_canvas_on_init():
            update_canvas(0)
        update_canvas_on_init()

    def save_edited_animation(self, window):
        self.log("Saving edited animation...", "info")
        threading.Thread(target=self.perform_save_edited_animation, args=(window,), daemon=True).start()

    def perform_save_edited_animation(self, window):
        try:
            send_animation(self.serial_conn, self.current_animation, logger=self.log)
            self.log("Edited animation sent.", "success")
            if self.current_file and os.path.exists(self.current_file):
                data = {'type': 'animation', 'patterns': self.current_animation}
                with open(self.current_file, 'w') as f:
                    json.dump(data, f, indent=4)
                self.log("Animation saved.", "success")
            else:
                save = messagebox.askyesno("Save Edited Animation", "Save?")
                if save:
                    filename = clean_filename("edited_animation") + '.json'
                    saved = save_data({'type': 'animation', 'patterns': self.current_animation}, name=filename)
                    if saved:
                        self.log("Edited animation saved.", "success")
                        self.current_file = saved
                    else:
                        self.log("Failed to save edited animation.", "error")
                else:
                    self.log("Edited animation not saved.", "info")
        except Exception as e:
            self.log(f"Failed to save edited animation: {e}", "error")
        finally:
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
                self.log("Animation saved.", "success")
            except Exception as e:
                self.log(f"Failed to save animation: {e}", "error")
                return
            send_animation(self.serial_conn, self.current_animation, logger=self.log)
            self.log("Animation published.", "success")
        elif not self.is_animation and self.current_pattern:
            try:
                data = {'type': 'single', 'pattern': self.current_pattern}
                with open(self.current_file, 'w') as f:
                    json.dump(data, f, indent=4)
                self.log("Pattern saved.", "success")
            except Exception as e:
                self.log(f"Failed to save pattern: {e}", "error")
                return
            send_frame(self.serial_conn, self.current_pattern, logger=self.log, update_preview=self.update_leds)
            self.log("Pattern published.", "success")
        else:
            self.log("Nothing to publish.", "error")

    def exit_app(self):
        if messagebox.askokcancel("Exit", "Exit the application?"):
            try:
                if self.anim_manager.playing:
                    self.anim_manager.stop()
                self.serial_conn.close()
                self.log("Serial connection closed.", "info")
            except:
                pass
            self.master.destroy()

    def open_mood_mode(self):
        mood_window = tk.Toplevel(self.master)
        mood_window.title("Mood Mode")
        mood_window.geometry("500x400")
        mood_window.configure(bg="#121212")
        mood_window.resizable(False, False)

        frame = ttk.Frame(mood_window, padding="20")
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text="Select a Mood or Enter Custom Description:", font=self.label_font, background="#121212", foreground="#ffffff").pack(pady=(0,10), anchor='w')

        predefined_moods = ["Calm", "Excited", "Sad", "Happy", "Angry", "Romantic", "Mysterious"]
        self.mood_var = tk.StringVar()
        self.mood_combobox = ttk.Combobox(frame, textvariable=self.mood_var, values=predefined_moods, state='readonly')
        self.mood_combobox.pack(fill='x', pady=(0,10))
        self.mood_combobox.set("Select a Mood")

        ttk.Label(frame, text="Or Enter a Custom Description:", font=self.label_font, background="#121212", foreground="#ffffff").pack(pady=(10,5), anchor='w')

        self.custom_desc_entry = ttk.Entry(frame, width=50)
        self.custom_desc_entry.pack(fill='x', pady=(0,10))
        self.custom_desc_entry.bind('<KeyRelease>', self.toggle_mood_buttons)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)

        self.gen_mood_pattern_btn = ttk.Button(btn_frame, text="Generate Pattern", command=lambda: self.gen_mood_pattern(mood_window), state='disabled')
        self.gen_mood_pattern_btn.grid(row=0, column=0, padx=(0,20))
        Tooltip(self.gen_mood_pattern_btn, "Generate a single pattern for the mood.")

        self.gen_mood_anim_btn = ttk.Button(btn_frame, text="Generate Animation", command=lambda: self.gen_mood_animation(mood_window), state='disabled')
        self.gen_mood_anim_btn.grid(row=0, column=1, padx=(20,0))
        Tooltip(self.gen_mood_anim_btn, "Generate an animation for the mood.")

    def toggle_mood_buttons(self, event=None):
        mood = self.mood_var.get()
        custom_desc = self.custom_desc_entry.get().strip()
        if mood != "Select a Mood":
            self.gen_mood_pattern_btn.configure(state='normal')
            self.gen_mood_anim_btn.configure(state='normal')
            self.custom_desc_entry.delete(0, tk.END)
        elif custom_desc:
            self.gen_mood_pattern_btn.configure(state='normal')
            self.gen_mood_anim_btn.configure(state='normal')
        else:
            self.gen_mood_pattern_btn.configure(state='disabled')
            self.gen_mood_anim_btn.configure(state='disabled')

    def get_mood_description(self):
        mood = self.mood_var.get()
        custom_desc = self.custom_desc_entry.get().strip()
        if mood != "Select a Mood":
            return mood.lower()
        elif custom_desc:
            return custom_desc
        else:
            return None

    def gen_mood_pattern(self, window):
        desc = self.get_mood_description()
        if not desc:
            messagebox.showwarning("Input Needed", "Select a mood or enter a description.")
            return
        self.disable_all_buttons()
        self.log(f"Generating pattern for mood: '{desc}'", "info")
        threading.Thread(target=self.generate_mood_pattern, args=(desc, window), daemon=True).start()

    def generate_mood_pattern(self, desc, window):
        pattern = generate_patterns(desc, logger=self.log)
        self.current_pattern = pattern.copy()
        self.current_animation = None
        self.is_animation = False
        self.current_file = None

        self.update_leds(pattern)
        if pattern:
            self.log(f"Mood Pattern: {pattern}", "success")
            if messagebox.askyesno("Save Pattern", "Save?"):
                filename = clean_filename(f"mood_{desc}") + '.json'
                saved = save_data({'type': 'single', 'pattern': pattern}, name=filename)
                if saved:
                    self.log(f"Mood pattern saved as '{filename}'.", "success")
                    self.current_file = saved
                else:
                    self.log(f"Failed to save '{filename}'.", "error")
            send_frame(self.serial_conn, pattern, logger=self.log, update_preview=self.update_leds)
            self.log("Mood pattern sent.", "success")
            self.after_generation()
        else:
            self.log("Failed to generate mood pattern.", "error")
        self.enable_buttons()
        window.destroy()

    def gen_mood_animation(self, window):
        desc = self.get_mood_description()
        if not desc:
            messagebox.showwarning("Input Needed", "Select a mood or enter a description.")
            return
        self.disable_all_buttons()
        self.log(f"Generating animation for mood: '{desc}'", "info")
        threading.Thread(target=self.generate_mood_animation, args=(desc, window), daemon=True).start()

    def generate_mood_animation(self, desc, window):
        frames = generate_patterns(desc, animation=True, frame_count=5, logger=self.log)
        self.current_animation = [f.copy() for f in frames] if frames else None
        self.current_pattern = None
        self.is_animation = True if frames else False
        self.current_file = None

        if frames:
            self.log(f"Generated {len(frames)} frames for mood animation.", "success")
            self.anim_manager.stop()
            self.anim_manager.start(frames)

            if messagebox.askyesno("Save Animation", "Save?"):
                filename = clean_filename(f"mood_{desc}") + '.json'
                saved = save_data({'type': 'animation', 'patterns': frames}, name=filename)
                if saved:
                    self.log(f"Mood animation saved as '{filename}'.", "success")
                    self.current_file = saved
                else:
                    self.log("Failed to save.", "error")

            send_animation(self.serial_conn, frames, logger=self.log)
            self.log("Mood animation sent.", "success")
            self.after_generation()
        else:
            self.log("Failed to generate mood animation.", "error")
        self.enable_buttons()
        window.destroy()

def main():
    root = tk.Tk()
    app = LEDMatrixApp(root)
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    root.mainloop()

if __name__ == "__main__":
    main()