# ai_utils.py - AI-powered pattern generation for LED matrix
import os
import re
import time
import openai
from dotenv import load_dotenv

# Core configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(SCRIPT_DIR, "prompts")

# API setup
load_dotenv()
API_KEY = os.getenv('GLHF_API_KEY')
if not API_KEY:
    raise ValueError("GLHF_API_KEY not set in environment.")

openai.api_key = API_KEY
openai.api_base = "https://glhf.chat/api/openai/v1"

def load_prompt(filename):
    # Load prompt template from file
    path = os.path.join(PROMPTS_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def parse_response(raw, logger=None):
    # Extract and convert binary pattern from AI response
    lines = re.findall(r'B[01]{8}', raw.replace(',', ''))
    if len(lines) < 8:
        if logger:
            logger("Could not find 8 binary lines.")
        return None
        
    vals = []
    for b in lines[:8]:
        x = int(b[1:], 2)
        vals.append(x)
    return vals

def safe_chat_completion(model, messages, logger=None, stream=False):
    # Handle API calls with error management
    try:
        resp = openai.ChatCompletion.create(model=model, messages=messages, stream=stream)
        if stream:
            return "".join(chunk.choices[0].delta.get('content', '') for chunk in resp).strip()
        else:
            return resp.choices[0].message.content.strip()
    except Exception as e:
        if logger:
            logger(f"API error: {e}")
        return None

def simple_pattern():
    # Default X-pattern for fallback
    return [
        int('10000001', 2),
        int('01000010', 2),
        int('00100100', 2),
        int('00011000', 2),
        int('00011000', 2),
        int('00100100', 2),
        int('01000010', 2),
        int('10000001', 2),
    ]

def simple_animation(frame_count=5):
    # Generate repeated X-patterns
    return [simple_pattern() for _ in range(frame_count)]

def generate_patterns(prompt, animation=False, frame_count=5, logger=None, optimize=False):
    # Generate LED patterns using Llama-3.1
    system_prompt = load_prompt('system_generate_pattern.txt')
    if optimize:
        system_prompt += "\n" + load_prompt('system_optimize.txt')
    model = "hf:meta-llama/Meta-Llama-3.1-405B-Instruct"
    
    if not animation:
        user_prompt = load_prompt('user_generate_pattern.txt').format(prompt=prompt)
        for _ in range(3):
            response = safe_chat_completion(model, [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], logger=logger)
            if response:
                pattern = parse_response(response, logger)
                if pattern:
                    return pattern
        if logger:
            logger("Using fallback single pattern.")
        return simple_pattern()
    else:
        frames = []
        user_prompt_template = load_prompt('user_generate_animation.txt')
        for i in range(frame_count):
            user_prompt = user_prompt_template.format(prompt=prompt, frame_number=i+1)
            frame_received = False
            for _ in range(3):
                response = safe_chat_completion(model, [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ], logger=logger)
                if response:
                    frame = parse_response(response, logger)
                    if frame:
                        frames.append(frame)
                        frame_received = True
                        break
            if not frame_received:
                if logger:
                    logger(f"Frame {i+1} fallback.")
                frames.append(simple_pattern())
        return frames

def optimize_with_ai(data, is_animation=False, logger=None):
    # Optimize patterns using AI suggestions
    system_prompt = load_prompt('system_optimize.txt')
    model = "hf:meta-llama/Meta-Llama-3.1-405B-Instruct"
    
    if is_animation:
        optimized_frames = []
        for i, frame in enumerate(data):
            user_prompt = load_prompt('user_optimize_animation.txt').format(
                frame_number=i+1,
                frame_data=",".join(str(b) for b in frame)
            )
            response = safe_chat_completion(model, [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], logger=logger)
            if response:
                optimized_frame = parse_response(response, logger)
                if optimized_frame and optimized_frame != frame:
                    optimized_frames.append(optimized_frame)
                else:
                    return simple_animation(len(data))
            else:
                return simple_animation(len(data))
        if len(optimized_frames) == len(data):
            return optimized_frames
        return simple_animation(len(data))
    else:
        user_prompt = load_prompt('user_optimize_pattern.txt').format(
            pattern=",".join(str(b) for b in data)
        )
        response = safe_chat_completion(model, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], logger=logger)
        if response:
            optimized_pattern = parse_response(response, logger)
            if optimized_pattern and optimized_pattern != data:
                return optimized_pattern
        return simple_pattern()

def visualize_pattern(pattern):
    # Convert binary pattern to ASCII visualization
    visual = ""
    for row in pattern:
        bits = bin(row)[2:].zfill(8)
        visual += "".join('█' if b == '1' else '•' for b in bits) + "\n"
    return visual

def is_symmetric(pattern):
    # Check pattern symmetry
    for row in pattern:
        binary = bin(row)[2:].zfill(8)
        if binary != binary[::-1]:
            return False
    return pattern == pattern[::-1]

def mirror_pattern(pattern, horizontal=True):
    # Mirror pattern on current axis
    if horizontal:
        return [int(bin(row)[2:].zfill(8)[::-1], 2) for row in pattern]
    else:
        return pattern[::-1]

def mirror_animation(frames, horizontal=True):
    # Mirror all frames in animation
    return [mirror_pattern(frame, horizontal) for frame in frames]