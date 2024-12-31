# ui.py
import os, time, re, json, threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from tkinter import font as tkfont

from ai_utils import (
    generate_patterns,
    optimize_with_ai,
    parse_response,
    simple_pattern,
    simple_animation,
    visualize_pattern,
    is_symmetric,
    mirror_pattern,
    mirror_animation
)
from serial_utils import send_frame, send_animation

# Constants
SAVED_PATTERNS_DIR = "saved_patterns"
LED_DIAMETER       = 30
LED_SPACING        = 5
ACTIVE_COLOR       = "#FF0000"
INACTIVE_COLOR     = "#330000"
FRAME_DELAY_MS     = 100
MAX_ANIMATION_FRAMES = 10

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def save_data(data, name=None, overwrite=False):
    os.makedirs(SAVED_PATTERNS_DIR, exist_ok=True)
    nm = clean_filename(name) + '.json' if name else f"{data['type']}_{int(time.time())}.json"
    path = os.path.join(SAVED_PATTERNS_DIR, nm)
    if os.path.exists(path) and not overwrite:
        return None
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return path
    except:
        return None

def load_saved(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text   = text
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)
        self.tw = None

    def show(self, e=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.configure(bg="#333")
        self.tw.wm_geometry(f"+{x}+{y}")
        lb = tk.Label(
            self.tw,
            text=self.text,
            justify='left',
            bg="#333",
            fg="white",
            relief='solid',
            borderwidth=1,
            wraplength=300,
            font=("Helvetica", 10)
        )
        lb.pack(ipadx=1)

    def hide(self, e=None):
        if self.tw:
            self.tw.destroy()
        self.tw = None

class AnimationManager:
    def __init__(self, canvas, update_func):
        self.canvas         = canvas
        self.update_leds    = update_func
        self.playing        = False
        self.stop_flag      = threading.Event()

    def start(self, frames):
        if self.playing:
            self.stop()
        self.playing = True
        self.stop_flag.clear()
        threading.Thread(target=self._play, args=(frames,), daemon=True).start()

    def _play(self, frames):
        while self.playing:
            for f in frames:
                if self.stop_flag.is_set():
                    break
                self.canvas.after(0, lambda ff=f: self.update_leds(ff, animation=True))
                time.sleep(FRAME_DELAY_MS / 1000.0)
        self.playing = False
        self.stop_flag.clear()

    def stop(self):
        if self.playing:
            self.stop_flag.set()

class LEDMatrixApp:
    def __init__(self, master, serial_conn, logger=None):
        self.master = master
        # Modern-ish background, same style
        self.master.title("LED Matrix")
        self.master.configure(bg="#121212")

        # Store references
        self.serial_conn = serial_conn
        self.log_fn = logger if logger else self.log

        # Our internal state
        self.current_pattern     = None
        self.current_animation   = None
        self.current_file        = None
        self.is_animation        = False
        self.refinement_iterations = 0
        self.max_refinement_iterations = 3
        self.currently_refining  = False

        # Build UI
        self.create_ui()
        self.create_preview()
        self.anim_manager = AnimationManager(self.canvas, self.update_leds)

    def create_ui(self):
        # Main container frame
        self.main_frame = ttk.Frame(self.master, padding="20")
        self.main_frame.grid(sticky='NSEW')

        # Fonts for styling
        self.title_font  = tkfont.Font(family="Helvetica", size=18, weight="bold")
        self.label_font  = tkfont.Font(family="Helvetica", size=12)
        self.button_font = tkfont.Font(family="Helvetica", size=12, weight="bold")

        # Title row
        ttk.Label(
            self.main_frame,
            text="LED Matrix",
            font=self.title_font,
            foreground="#bb86fc"
        ).grid(row=0, column=0, columnspan=2, sticky='w')

        # Description label + entry
        ttk.Label(
            self.main_frame,
            text="Description:",
            font=self.label_font
        ).grid(row=1, column=0, sticky='w')
        self.desc_entry = ttk.Entry(self.main_frame, width=60)
        self.desc_entry.grid(row=1, column=1, sticky='w')
        self.desc_entry.bind('<KeyRelease>', self.toggle_buttons)

        # Button row
        self.btn_frame = ttk.Frame(self.main_frame)
        self.btn_frame.grid(row=2, column=0, columnspan=2, pady=(10,10), sticky='w')

        self.gen_single_btn = ttk.Button(
            self.btn_frame, text="Generate Single",
            command=self.gen_single, state='disabled'
        )
        self.gen_single_btn.grid(row=0, column=0, padx=(0,20), sticky='w')
        Tooltip(self.gen_single_btn, "Generate a single LED pattern.")

        self.gen_anim_btn = ttk.Button(
            self.btn_frame, text="Generate Anim",
            command=self.gen_animation, state='disabled'
        )
        self.gen_anim_btn.grid(row=0, column=1, padx=(0,20), sticky='w')
        Tooltip(self.gen_anim_btn, "Generate an animation.")

        self.publish_btn = ttk.Button(
            self.btn_frame, text="Publish",
            command=self.publish_current, state='disabled'
        )
        self.publish_btn.grid(row=0, column=2, padx=(0,20), sticky='w')

        self.edit_btn = ttk.Button(
            self.btn_frame, text="Edit",
            command=self.edit_current, state='disabled'
        )
        self.edit_btn.grid(row=0, column=3, padx=(0,20), sticky='w')

        self.optimize_btn = ttk.Button(
            self.btn_frame, text="Optimize",
            command=self.optimize_current, state='disabled'
        )
        self.optimize_btn.grid(row=0, column=4, padx=(0,20), sticky='w')

        self.exit_btn = ttk.Button(
            self.btn_frame, text="Exit",
            command=lambda: self.master.quit()
        )
        self.exit_btn.grid(row=0, column=5, padx=(100,0), sticky='e')

        # Logs label
        ttk.Label(
            self.main_frame, text="Logs:", font=self.label_font
        ).grid(row=3, column=0, sticky='w')

        # scrolledtext for logs
        self.log_area = scrolledtext.ScrolledText(
            self.main_frame, width=80, height=25,
            state='disabled', wrap='word', bg="#000", fg="#fff"
        )
        self.log_area.grid(row=4, column=0, columnspan=2, sticky='nsew')
        self.main_frame.rowconfigure(4, weight=1)
        self.main_frame.columnconfigure(1, weight=1)

    def create_preview(self):
        lf = ttk.LabelFrame(self.main_frame, text="Preview", padding="10")
        lf.grid(row=5, column=0, columnspan=2, sticky='n')

        w = LED_DIAMETER * 8 + LED_SPACING * 9
        h = LED_DIAMETER * 8 + LED_SPACING * 9
        self.canvas = tk.Canvas(lf, width=w, height=h, bg="#000")
        self.canvas.pack()
        self.leds = []
        for r in range(8):
            row=[]
            for c in range(8):
                x1 = LED_SPACING + c*(LED_DIAMETER+LED_SPACING)
                y1 = LED_SPACING + r*(LED_DIAMETER+LED_SPACING)
                x2,y2 = x1+LED_DIAMETER, y1+LED_DIAMETER
                cc = self.canvas.create_oval(x1,y1,x2,y2,fill="#330000",outline="")
                row.append(cc)
            self.leds.append(row)

    def log(self, msg, lv="info"):
        self.log_area.config(state='normal')
        tm = time.strftime('%Y-%m-%d %H:%M:%S')
        color = {
            "error":"#cf6679",
            "success":"#03dac6",
            "warning":"#ffb74d",
            "info":"#fff"
        }.get(lv, "#fff")
        self.log_area.insert(tk.END, f"{tm} - {msg}\n", (lv,))
        self.log_area.tag_config(lv, foreground=color)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def disable_all_buttons(self):
        for b in (
            self.gen_single_btn, self.gen_anim_btn,
            self.publish_btn, self.edit_btn, self.optimize_btn
        ):
            b.configure(state='disabled')

    def enable_buttons(self):
        # re-enable if we have patterns/animations
        if self.current_pattern or self.current_animation:
            self.edit_btn.configure(state='normal')
            self.publish_btn.configure(state='normal')
            self.optimize_btn.configure(state='normal')
        self.gen_single_btn.configure(state='normal')
        self.gen_anim_btn.configure(state='normal')

    def update_leds(self, pattern, animation=False):
        for r, byte in enumerate(pattern):
            bits = bin(byte)[2:].zfill(8)
            for c, b in enumerate(bits):
                col = ACTIVE_COLOR if b=='1' else INACTIVE_COLOR
                self.canvas.itemconfig(self.leds[r][c], fill=col)

    # ================ KEEP ALL LOGIC FROM OLD UI ================
    #
    # We'll now integrate your existing logic (refinements, blocking,
    # generation, etc.) from your prior script.

    def toggle_buttons(self, e=None):
        if self.currently_refining:
            return
        st = 'normal' if self.desc_entry.get().strip() else 'disabled'
        self.gen_single_btn.configure(state=st)
        self.gen_anim_btn.configure(state=st)

    # The rest of your logic from your big script:
    # gen_single, generate_single_pattern, gen_animation, ...
    # We'll show the key points. You can copy in full detail.

    def gen_single(self):
        if self.currently_refining: return
        d = self.desc_entry.get().strip()
        if not d:
            messagebox.showwarning("Input Needed","Enter a description.")
            return
        self.disable_all_buttons()
        self.log("Generating single...", "info")
        threading.Thread(target=self.generate_single_pattern, args=(d,), daemon=True).start()

    def generate_single_pattern(self, desc):
        from ai_utils import generate_patterns, visualize_pattern, is_symmetric
        try:
            pat = generate_patterns(desc, logger=self.log)
        except FileNotFoundError as e:
            self.log(str(e), "error")
            self.enable_buttons()
            return
        self.current_pattern   = pat.copy()
        self.current_animation = None
        self.is_animation      = False
        self.current_file      = None
        self.refinement_iterations = 0

        self.update_leds(pat)
        vis = visualize_pattern(pat)
        self.log(f"Visual Pattern:\n{vis}", "info")
        if is_symmetric(pat):
            self.log("The pattern is symmetric.","success")
        else:
            self.log("The pattern lacks symmetry.","warning")
        if pat:
            self.log(f"Pattern: {pat}","success")
            send_frame(self.serial_conn, pat, logger=self.log, update_preview=self.update_leds)
            self.log("Pattern sent.","success")
            self.evaluate_pattern(desc, pat)
            self.after_generation()
        else:
            self.log("Failed to generate.","error")
        self.enable_buttons()

    def gen_animation(self):
        if self.currently_refining: return
        d = self.desc_entry.get().strip()
        if not d:
            messagebox.showwarning("Input Needed","Enter description.")
            return
        self.disable_all_buttons()
        self.log("Generating animation...", "info")
        threading.Thread(target=self.generate_animation_patterns,args=(d,),daemon=True).start()

    def generate_animation_patterns(self, desc):
        from ai_utils import generate_patterns
        try:
            frames=generate_patterns(desc, animation=True, frame_count=5, logger=self.log)
        except FileNotFoundError as e:
            self.log(str(e),"error")
            self.enable_buttons()
            return
        self.current_animation = [f.copy() for f in frames] if frames else None
        self.current_pattern   = None
        self.is_animation      = bool(frames)
        self.current_file      = None
        self.refinement_iterations = 0
        if frames:
            self.log(f"Generated {len(frames)} frames.","success")
            self.anim_manager.stop()
            self.anim_manager.start(frames)
            send_animation(self.serial_conn,frames,logger=self.log)
            self.log("Animation sent.","success")
            self.evaluate_animation(desc, frames)
            self.after_generation()
        else:
            self.log("Failed to generate animation.","error")
        self.enable_buttons()

    def evaluate_pattern(self, prompt, pattern):
        # same logic from your original
        import re
        try:
            sf = os.path.join(SCRIPT_DIR,"prompts","system_evaluate_pattern.txt")
            uf = os.path.join(SCRIPT_DIR,"prompts","user_evaluate_pattern.txt")
            with open(sf,'r',encoding='utf-8')as f:
                sp=f.read()
            with open(uf,'r',encoding='utf-8')as f:
                up=f.read()
            up=up.format(prompt=prompt, pattern='\n'.join('B'+bin(r)[2:].zfill(8) for r in pattern))

            from ai_utils import safe_chat_completion
            msgs=[{"role":"system","content":sp},{"role":"user","content":up}]
            ev=safe_chat_completion("hf:meta-llama/Meta-Llama-3.1-405B-Instruct",msgs,logger=self.log)
            if ev:
                self.log(f"Evaluation:\n{ev}","info")
                m=re.search(r'Score:\s*(\d+)/10',ev)
                if m:
                    sc=int(m.group(1))
                    if sc<9 and self.refinement_iterations<self.max_refinement_iterations:
                        fb=ev.split('\n',1)[1].strip() if'\n'in ev else ev
                        self.refine_pattern(pattern, fb)
                else:
                    self.log("Could not parse evaluation score.","warning")
            else:
                self.log("Evaluation failed.","error")
        except FileNotFoundError as e:
            self.log(str(e),"error")

    def evaluate_animation(self, prompt, frames):
        import re
        try:
            frs=[]
            for fr in frames:
                lines=['B'+bin(r)[2:].zfill(8) for r in fr]
                frs.append("\n".join(lines))
            joined="\n\n--- Next Frame ---\n\n".join(frs)
            sf=os.path.join(SCRIPT_DIR,"prompts","system_evaluate_pattern.txt")
            uf=os.path.join(SCRIPT_DIR,"prompts","user_evaluate_pattern.txt")
            with open(sf,'r',encoding='utf-8')as f:
                sp=f.read()
            with open(uf,'r',encoding='utf-8')as f:
                up=f.read()
            up=up.format(prompt=prompt,pattern=joined)

            from ai_utils import safe_chat_completion
            msgs=[{"role":"system","content":sp},{"role":"user","content":up}]
            ev=safe_chat_completion("hf:meta-llama/Meta-Llama-3.1-405B-Instruct",msgs,logger=self.log)
            if ev:
                self.log(f"Evaluation:\n{ev}","info")
                m=re.search(r'Score:\s*(\d+)/10',ev)
                if m:
                    sc=int(m.group(1))
                    if sc<9 and self.refinement_iterations<self.max_refinement_iterations:
                        fb=ev.split('\n',1)[1].strip() if'\n'in ev else ev
                        self.refine_animation(prompt, fb)
                else:
                    self.log("Could not parse evaluation score.","warning")
            else:
                self.log("Evaluation failed.","error")
        except FileNotFoundError as e:
            self.log(str(e),"error")

    def refine_pattern(self, pattern, feedback):
        if self.refinement_iterations>=self.max_refinement_iterations:
            self.log("Max refinement attempts reached.","warning")
            return
        self.disable_all_buttons()
        self.log("Refining pattern...","info")
        self.currently_refining=True
        threading.Thread(target=self.refine_pattern_thread,args=(pattern,feedback),daemon=True).start()

    def refine_pattern_thread(self, pattern, feedback):
        from ai_utils import safe_chat_completion, parse_response
        try:
            spath=os.path.join(SCRIPT_DIR,"prompts","system_generate_pattern.txt")
            upath=os.path.join(SCRIPT_DIR,"prompts","user_refine_pattern.txt")
            with open(spath,'r',encoding='utf-8') as f:
                sp=f.read()
            with open(upath,'r',encoding='utf-8') as f:
                up=f.read()
            up=up.format(
                pattern="\n".join('B'+bin(r)[2:].zfill(8) for r in pattern),
                feedback=feedback
            )
            msgs=[{"role":"system","content":sp},{"role":"user","content":up}]
            rr=safe_chat_completion("hf:meta-llama/Meta-Llama-3.1-405B-Instruct",msgs,logger=self.log)
            if rr:
                arr=parse_response(rr,self.log)
                if arr and len(arr)==8:
                    self.log(f"Refined Pattern: {arr}","success")
                    self.update_leds(arr)
                    send_frame(self.serial_conn, arr, logger=self.log, update_preview=self.update_leds)
                    self.log("Refined pattern sent.","success")
                    self.evaluate_pattern(self.desc_entry.get().strip(), arr)
                    self.refinement_iterations+=1
                else:
                    self.log("Failed to parse refined pattern. Using original.","error")
            else:
                self.log("Refinement failed. Using original.","error")
        except FileNotFoundError as e:
            self.log(str(e),"error")
        finally:
            self.currently_refining=False
            self.enable_buttons()

    def refine_animation(self, prompt, feedback):
        if self.refinement_iterations>=self.max_refinement_iterations:
            self.log("Max refinement attempts reached.","warning")
            return
        self.disable_all_buttons()
        self.log("Refining animation...","info")
        self.currently_refining=True
        threading.Thread(target=self.refine_animation_thread,args=(prompt,feedback),daemon=True).start()

    def refine_animation_thread(self, prompt, feedback):
        from ai_utils import generate_patterns
        try:
            desc=f"{prompt} with {feedback.lower()}"
            frames=generate_patterns(desc,animation=True,frame_count=5,logger=self.log)
            if frames:
                self.current_animation=[f.copy() for f in frames]
                self.log(f"Refined {len(frames)} frames.","success")
                self.anim_manager.stop()
                self.anim_manager.start(frames)
                send_animation(self.serial_conn, frames, logger=self.log)
                self.log("Refined animation sent.","success")
                self.evaluate_animation(desc, frames)
                self.refinement_iterations+=1
            else:
                self.log("Failed to generate refined animation.","error")
        except FileNotFoundError as e:
            self.log(str(e),"error")
        finally:
            self.currently_refining=False
            self.enable_buttons()

    def after_generation(self):
        self.publish_btn.configure(state='normal')
        self.edit_btn.configure(state='normal')
        self.optimize_btn.configure(state='normal')

    def optimize_current(self):
        if not self.current_pattern and not self.current_animation:
            self.log("Nothing to optimize.","error")
            return
        if self.currently_refining:
            return
        self.disable_all_buttons()
        self.log("Optimizing...","info")
        threading.Thread(target=self.perform_optimization,daemon=True).start()

    def perform_optimization(self):
        from ai_utils import optimize_with_ai
        try:
            if self.is_animation and self.current_animation:
                op=optimize_with_ai(self.current_animation,is_animation=True,logger=self.log)
                if op!=self.current_animation:
                    self.current_animation=op
                    self.log("Animation optimized.","success")
                    send_animation(self.serial_conn,self.current_animation,logger=self.log)
                else:
                    self.log("No change.","info")
            elif self.current_pattern:
                op=optimize_with_ai(self.current_pattern,is_animation=False,logger=self.log)
                if op!=self.current_pattern:
                    self.current_pattern=op
                    self.log("Pattern optimized.","success")
                    send_frame(self.serial_conn,self.current_pattern,logger=self.log,update_preview=self.update_leds)
                else:
                    self.log("No change.","info")
        except FileNotFoundError as e:
            self.log(str(e),"error")
        except Exception as e:
            self.log(f"Optimization failed: {e}","error")
        finally:
            self.after_generation()
            self.enable_buttons()

    def publish_current(self):
        if not self.current_file:
            self.log("No file loaded to publish","error")
            return
        published=False
        if self.current_animation:
            try:
                dat={'type':'animation','patterns':self.current_animation}
                with open(self.current_file,'w',encoding='utf-8') as f:
                    json.dump(dat,f,indent=4)
                self.log("Animation file updated","success")
                send_animation(self.serial_conn,self.current_animation,logger=self.log)
                self.log("Animation published","success")
                published=True
            except Exception as e:
                self.log(str(e),"error")
        if self.current_pattern:
            try:
                dat={'type':'single','pattern':self.current_pattern}
                with open(self.current_file,'w',encoding='utf-8') as f:
                    json.dump(dat,f,indent=4)
                self.log("Pattern file updated","success")
                send_frame(self.serial_conn,self.current_pattern,logger=self.log,update_preview=self.update_leds)
                self.log("Pattern published","success")
                published=True
            except Exception as e:
                self.log(str(e),"error")
        if not published:
            self.log("Nothing to publish","error")

    def edit_current(self):
        if self.is_animation:
            self.edit_animation()
        elif self.current_pattern:
            self.edit_pattern()

    def edit_pattern(self):
        if not self.current_pattern:
            self.log("No pattern to edit.","error")
            return
        self.edit_pattern_window()

    def edit_pattern_window(self):
        ed=tk.Toplevel(self.master)
        ed.title("Edit Pattern")
        ed.geometry("500x550")
        ed.configure(bg="#121212")
        ed.resizable(False,False)
        canvas=tk.Canvas(ed,width=LED_DIAMETER*8+LED_SPACING*9,height=LED_DIAMETER*8+LED_SPACING*9,bg="#000")
        canvas.pack(pady=20)
        circles=[]
        for r in range(8):
            rowc=[]
            for c in range(8):
                x1=LED_SPACING+c*(LED_DIAMETER+LED_SPACING)
                y1=LED_SPACING+r*(LED_DIAMETER+LED_SPACING)
                x2,y2=x1+LED_DIAMETER,y1+LED_DIAMETER
                bit=self.current_pattern[r] & (1<<(7-c))
                col=ACTIVE_COLOR if bit else INACTIVE_COLOR
                cir=canvas.create_oval(x1,y1,x2,y2,fill=col,outline="")
                rowc.append(cir)
            circles.append(rowc)
        def toggle_led(e):
            x,y=e.x,e.y
            for rr in range(8):
                for cc in range(8):
                    co=canvas.coords(circles[rr][cc])
                    if co[0]<=x<=co[2] and co[1]<=y<=co[3]:
                        cur=canvas.itemcget(circles[rr][cc],"fill")
                        new=INACTIVE_COLOR if cur==ACTIVE_COLOR else ACTIVE_COLOR
                        canvas.itemconfig(circles[rr][cc],fill=new)
                        if new==ACTIVE_COLOR:
                            self.current_pattern[rr]|=(1<<(7-cc))
                        else:
                            self.current_pattern[rr]&=~(1<<(7-cc))
                        break
        canvas.bind("<Button-1>",toggle_led)

        bf=ttk.Frame(ed)
        bf.pack(pady=10)

        def redraw_pattern():
            for rr in range(8):
                bits=bin(self.current_pattern[rr])[2:].zfill(8)
                for cc,b in enumerate(bits):
                    cl=ACTIVE_COLOR if b=='1' else INACTIVE_COLOR
                    canvas.itemconfig(circles[rr][cc],fill=cl)
        def mirror_h():
            self.current_pattern=mirror_pattern(self.current_pattern,horizontal=True)
            redraw_pattern()
        def mirror_v():
            self.current_pattern=mirror_pattern(self.current_pattern,horizontal=False)
            redraw_pattern()

        ttk.Button(bf,text="Mirror Horizontal",command=mirror_h).grid(row=0,column=0,padx=5)
        ttk.Button(bf,text="Mirror Vertical",command=mirror_v).grid(row=0,column=1,padx=5)
        ttk.Button(ed,text="Save",command=lambda:self.save_edited_pattern(ed)).pack(pady=10)

    def save_edited_pattern(self,window):
        self.log("Saving edited pattern...","info")
        threading.Thread(target=self.perform_save_edited_pattern,args=(window,),daemon=True).start()

    def perform_save_edited_pattern(self,window):
        from serial_utils import send_frame
        try:
            send_frame(self.serial_conn,self.current_pattern,logger=self.log,update_preview=self.update_leds)
            self.log("Edited pattern sent.","success")
            if self.current_file and os.path.exists(self.current_file):
                data={'type':'single','pattern':self.current_pattern}
                with open(self.current_file,'w',encoding='utf-8')as f:
                    json.dump(data,f,indent=4)
                self.log("Pattern file updated.","success")
            else:
                self.log("Pattern updated in device but not saved to disk. Use 'File -> Save As...' to save.","info")
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
        ed=tk.Toplevel(self.master)
        ed.title("Edit Animation")
        ed.geometry("600x750")
        ed.configure(bg="#121212")
        ed.resizable(False,False)

        sf=ttk.Frame(ed,padding="10")
        sf.pack(fill='x')
        ttk.Label(sf,text="Select Frame:").pack(side='left',padx=(0,10))
        frame_var=tk.IntVar(value=0)

        def update_canvas(idx):
            p=self.current_animation[idx]
            for rr in range(8):
                bits=bin(p[rr])[2:].zfill(8)
                for cc,b in enumerate(bits):
                    col=ACTIVE_COLOR if b=='1' else INACTIVE_COLOR
                    canvas.itemconfig(circles[rr][cc],fill=col)

        for i in range(len(self.current_animation)):
            ttk.Radiobutton(sf,text=f"Frame {i+1}",
                            variable=frame_var,value=i,
                            command=lambda: update_canvas(frame_var.get())).pack(side='left')

        canvas=tk.Canvas(ed,width=LED_DIAMETER*8+LED_SPACING*9,height=LED_DIAMETER*8+LED_SPACING*9,bg="#000")
        canvas.pack(pady=20)
        circles=[]
        for r in range(8):
            rowc=[]
            for c in range(8):
                x1=LED_SPACING+c*(LED_DIAMETER+LED_SPACING)
                y1=LED_SPACING+r*(LED_DIAMETER+LED_SPACING)
                x2,y2=x1+LED_DIAMETER,y1+LED_DIAMETER
                bit=self.current_animation[0][r] & (1<<(7-c))
                col=ACTIVE_COLOR if bit else INACTIVE_COLOR
                cir=canvas.create_oval(x1,y1,x2,y2,fill=col,outline="")
                rowc.append(cir)
            circles.append(rowc)

        def toggle_led(e):
            idx=frame_var.get()
            x,y=e.x,e.y
            for rr in range(8):
                for cc in range(8):
                    co=canvas.coords(circles[rr][cc])
                    if co[0]<=x<=co[2] and co[1]<=y<=co[3]:
                        cur=canvas.itemcget(circles[rr][cc],"fill")
                        new=INACTIVE_COLOR if cur==ACTIVE_COLOR else ACTIVE_COLOR
                        canvas.itemconfig(circles[rr][cc],fill=new)
                        if new==ACTIVE_COLOR:
                            self.current_animation[idx][rr]|=(1<<(7-cc))
                        else:
                            self.current_animation[idx][rr]&=~(1<<(7-cc))
                        break
        canvas.bind("<Button-1>",toggle_led)

        bf=ttk.Frame(ed)
        bf.pack(pady=10)

        def redraw_animation():
            idx=frame_var.get()
            p=self.current_animation[idx]
            for rr in range(8):
                bits=bin(p[rr])[2:].zfill(8)
                for cc,b in enumerate(bits):
                    col=ACTIVE_COLOR if b=='1'else INACTIVE_COLOR
                    canvas.itemconfig(circles[rr][cc],fill=col)

        def mirror_h():
            self.current_animation=mirror_animation(self.current_animation,horizontal=True)
            redraw_animation()
        def mirror_v():
            self.current_animation=mirror_animation(self.current_animation,horizontal=False)
            redraw_animation()

        ttk.Button(bf,text="Mirror Horizontal",command=mirror_h).grid(row=0,column=0,padx=5)
        ttk.Button(bf,text="Mirror Vertical",command=mirror_v).grid(row=0,column=1,padx=5)
        ttk.Button(ed,text="Save",command=lambda:self.save_edited_animation(ed)).pack(pady=10)

        def init_canvas_on_start():
            update_canvas(0)
        init_canvas_on_start()

    def save_edited_animation(self,window):
        self.log("Saving edited animation...","info")
        threading.Thread(target=self.perform_save_edited_animation,args=(window,),daemon=True).start()

    def perform_save_edited_animation(self,window):
        try:
            send_animation(self.serial_conn,self.current_animation,logger=self.log)
            self.log("Edited animation sent.","success")
            if self.current_file and os.path.exists(self.current_file):
                data={'type':'animation','patterns':self.current_animation}
                with open(self.current_file,'w',encoding='utf-8')as f:
                    json.dump(data,f,indent=4)
                self.log("Animation file updated.","success")
            else:
                self.log("Animation updated in device but not saved to disk. Use 'File -> Save As...' to save.","info")
        except Exception as e:
            self.log(f"Failed to save edited animation: {e}","error")
        finally:
            window.destroy()

    def publish_current(self):
        if not self.current_file:
            self.log("No file loaded to publish","error")
            return
        published=False
        if self.current_animation:
            try:
                d={'type':'animation','patterns':self.current_animation}
                with open(self.current_file,'w',encoding='utf-8')as f:
                    json.dump(d,f,indent=4)
                self.log("Animation file updated", "success")
                send_animation(self.serial_conn,self.current_animation,logger=self.log)
                self.log("Animation published","success")
                published=True
            except Exception as e:
                self.log(str(e),"error")
        if self.current_pattern:
            try:
                d={'type':'single','pattern':self.current_pattern}
                with open(self.current_file,'w',encoding='utf-8')as f:
                    json.dump(d,f,indent=4)
                self.log("Pattern file updated","success")
                send_frame(self.serial_conn,self.current_pattern,logger=self.log,update_preview=self.update_leds)
                self.log("Pattern published","success")
                published=True
            except Exception as e:
                self.log(str(e),"error")
        if not published:
            self.log("Nothing to publish","error")

    def optimize_current(self):
        if not self.current_pattern and not self.current_animation:
            self.log("No pattern or animation to optimize.","error")
            return
        if self.currently_refining: return
        self.disable_all_buttons()
        self.log("Optimizing..","info")
        threading.Thread(target=self.perform_optimization,daemon=True).start()

    def perform_optimization(self):
        from ai_utils import optimize_with_ai
        try:
            if self.is_animation and self.current_animation:
                op=optimize_with_ai(self.current_animation,is_animation=True,logger=self.log)
                if op!=self.current_animation:
                    self.current_animation=op
                    self.log("Animation optimized.","success")
                    send_animation(self.serial_conn,self.current_animation,logger=self.log)
                else:
                    self.log("No change.","info")
            elif self.current_pattern:
                op=optimize_with_ai(self.current_pattern,is_animation=False,logger=self.log)
                if op!=self.current_pattern:
                    self.current_pattern=op
                    self.log("Pattern optimized.","success")
                    send_frame(self.serial_conn,self.current_pattern,logger=self.log,update_preview=self.update_leds)
                else:
                    self.log("No change.","info")
        except Exception as e:
            self.log(f"Optimization failed: {e}","error")
        finally:
            self.after_generation()
            self.enable_buttons()

    def after_generation(self):
        self.publish_btn.configure(state='normal')
        self.edit_btn.configure(state='normal')
        self.optimize_btn.configure(state='normal')

    def edit_current(self):
        if self.is_animation:
            self.edit_animation()
        elif self.current_pattern:
            self.edit_pattern()

    def load_ui(self):
        if self.currently_refining:
            return
        w=tk.Toplevel(self.master)
        w.title("Browse Saved")
        w.geometry("800x600")
        w.configure(bg="#121212")
        w.resizable(False,False)
        fr=ttk.Frame(w,padding="10")
        fr.pack(fill='both',expand=True)

        pf=ttk.LabelFrame(fr,text="Patterns",padding="10")
        pf.pack(side='left',fill='both',expand=True,padx=(0,10))
        af=ttk.LabelFrame(fr,text="Animations",padding="10")
        af.pack(side='right',fill='both',expand=True,padx=(10,0))

        p_scroll=ttk.Scrollbar(pf,orient='vertical')
        p_scroll.pack(side='right',fill='y')
        self.p_list=tk.Listbox(pf,font=self.label_font,bg="#000",fg="#fff",yscrollcommand=p_scroll.set)
        self.p_list.pack(side='left',fill='both',expand=True)
        p_scroll.config(command=self.p_list.yview)

        a_scroll=ttk.Scrollbar(af,orient='vertical')
        a_scroll.pack(side='right',fill='y')
        self.a_list=tk.Listbox(af,font=self.label_font,bg="#000",fg="#fff",yscrollcommand=a_scroll.set)
        self.a_list.pack(side='left',fill='both',expand=True)
        a_scroll.config(command=self.a_list.yview)

        fs=[f for f in os.listdir(SAVED_PATTERNS_DIR) if f.endswith('.json')]
        if not fs:
            messagebox.showinfo("No Files","No saved files found.")
            w.destroy()
            return

        for f in fs:
            p=os.path.join(SAVED_PATTERNS_DIR,f)
            try:
                data=load_saved(p)
                if data.get('type')=='single':
                    self.p_list.insert(tk.END,f)
                elif data.get('type')=='animation':
                    self.a_list.insert(tk.END,f)
            except:
                pass

        ttk.Label(fr,text="Selecting loads immediately.").pack(fill='both',expand=False,pady=(10,0))
        self.p_list.bind('<<ListboxSelect>>',lambda e:self.load_selection('single',self.p_list,w))
        self.a_list.bind('<<ListboxSelect>>',lambda e:self.load_selection('animation',self.a_list,w))

    def load_selection(self, t, listbox, window):
        sel=listbox.curselection()
        if not sel:
            return
        fname=listbox.get(sel[0])
        path=os.path.join(SAVED_PATTERNS_DIR,fname)
        try:
            data=load_saved(path)
            if data.get('type')!=t:
                self.log(f"Type mismatch for '{fname}'","error")
                return
            self.anim_manager.stop()
            if t=='single':
                self.current_pattern=data['pattern'].copy()
                self.current_animation=None
                self.is_animation=False
                self.update_leds(self.current_pattern)
            else:
                self.current_animation=[fr.copy() for fr in data['patterns']]
                self.current_pattern=None
                self.is_animation=True
                self.anim_manager.start(self.current_animation)
            self.current_file=path
            self.refinement_iterations=0
            self.after_generation()
            self.log(f"Loaded '{fname}'","success")
        except Exception as e:
            self.log(f"Failed to load '{fname}': {e}","error")

    def save_as(self):
        if not self.current_pattern and not self.current_animation:
            messagebox.showwarning("Nothing to Save","No pattern or animation to save.")
            return
        ft=[('JSON Files','*.json')]
        fn=filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=ft,
            initialdir=SAVED_PATTERNS_DIR,
            title="Save As..."
        )
        if not fn:
            return
        try:
            if self.current_animation:
                dat={'type':'animation','patterns':self.current_animation}
            else:
                dat={'type':'single','pattern':self.current_pattern}

            with open(fn,'w',encoding='utf-8')as f:
                json.dump(dat,f,indent=4)
            self.current_file=fn
            self.log(f"Saved to '{fn}'","success")
        except Exception as e:
            self.log(f"Failed to save: {e}","error")

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