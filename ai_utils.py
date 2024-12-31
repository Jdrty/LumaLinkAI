# ai_utils.py
import os, re, time
import openai
from dotenv import load_dotenv

# Keep a local scriptdir for loading prompts
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(SCRIPT_DIR, "prompts")

load_dotenv()
API_KEY = os.getenv('GLHF_API_KEY')
if not API_KEY:
    raise ValueError("GLHF_API_KEY not set in environment.")

openai.api_key = API_KEY
openai.api_base = "https://glhf.chat/api/openai/v1"

def load_prompt(filename):
    p = os.path.join(PROMPTS_DIR, filename)
    with open(p, 'r', encoding='utf-8') as f:
        return f.read()

def parse_response(raw, logger=None):
    lines = re.findall(r'B[01]{8}', raw.replace(',',''))
    if len(lines)<8:
        if logger: logger("Could not find 8 binary lines.")
        return None
    vals=[]
    for b in lines[:8]:
        x=int(b[1:],2)
        vals.append(x)
    return vals

def safe_chat_completion(model, messages, logger=None, stream=False):
    try:
        resp=openai.ChatCompletion.create(model=model,messages=messages,stream=stream)
        if stream:
            return "".join(chunk.choices[0].delta.get('content','') for chunk in resp).strip()
        else:
            return resp.choices[0].message.content.strip()
    except Exception as e:
        if logger: logger(f"API error: {e}")
        return None

def simple_pattern():
    return [
        int('10000001',2),
        int('01000010',2),
        int('00100100',2),
        int('00011000',2),
        int('00011000',2),
        int('00100100',2),
        int('01000010',2),
        int('10000001',2),
    ]

def simple_animation(fr=5):
    return [simple_pattern() for _ in range(fr)]

def generate_patterns(prompt, animation=False, frame_count=5, logger=None, optimize=False):
    sp = load_prompt('system_generate_pattern.txt')
    if optimize:
        sp+="\n"+load_prompt('system_optimize.txt')
    model="hf:meta-llama/Meta-Llama-3.1-405B-Instruct"
    if not animation:
        up=load_prompt('user_generate_pattern.txt').format(prompt=prompt)
        for _ in range(3):
            r=safe_chat_completion(model, [{"role":"system","content":sp},{"role":"user","content":up}], logger=logger)
            if r:
                arr=parse_response(r, logger)
                if arr:return arr
        if logger: logger("Using fallback single pattern.")
        return simple_pattern()
    else:
        frames=[]
        up=load_prompt('user_generate_animation.txt')
        for i in range(frame_count):
            userc=up.format(prompt=prompt, frame_number=i+1)
            got=False
            for _ in range(3):
                resp=safe_chat_completion(model, [{"role":"system","content":sp},{"role":"user","content":userc}], logger=logger)
                if resp:
                    arr=parse_response(resp, logger)
                    if arr:
                        frames.append(arr)
                        got=True
                        break
            if not got:
                if logger: logger(f"Frame {i+1} fallback.")
                frames.append(simple_pattern())
        return frames

def optimize_with_ai(data, is_animation=False, logger=None):
    sp=load_prompt('system_optimize.txt')
    model="hf:meta-llama/Meta-Llama-3.1-405B-Instruct"
    if is_animation:
        newf=[]
        for i,fr in enumerate(data):
            up=load_prompt('user_optimize_animation.txt')
            msg=up.format(frame_number=i+1,frame_data=",".join(str(b) for b in fr))
            resp=safe_chat_completion(model, [{"role":"system","content":sp},{"role":"user","content":msg}], logger=logger)
            if resp:
                arr=parse_response(resp, logger)
                if arr and arr!=fr:
                    newf.append(arr)
                else:
                    return simple_animation(len(data))
            else:
                return simple_animation(len(data))
        if len(newf)==len(data):
            return newf
        return simple_animation(len(data))
    else:
        up=load_prompt('user_optimize_pattern.txt')
        msg=up.format(pattern=",".join(str(b) for b in data))
        resp=safe_chat_completion(model, [{"role":"system","content":sp},{"role":"user","content":msg}], logger=logger)
        if resp:
            arr=parse_response(resp, logger)
            if arr and arr!=data:
                return arr
        return simple_pattern()

def visualize_pattern(pattern):
    gv=""
    for row in pattern:
        bits=bin(row)[2:].zfill(8)
        gv+="".join('█' if b=='1' else '•' for b in bits)+"\n"
    return gv

def is_symmetric(pattern):
    for row in pattern:
        s=bin(row)[2:].zfill(8)
        if s!=s[::-1]:
            return False
    return pattern==pattern[::-1]

def mirror_pattern(p,horizontal=True):
    if horizontal:
        return [int(bin(r)[2:].zfill(8)[::-1],2) for r in p]
    else:
        return p[::-1]

def mirror_animation(frames,horizontal=True):
    return [mirror_pattern(f,horizontal) for f in frames]