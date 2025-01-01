LumaLink AI

This repository contains:
	1.	Arduino Sketch: For driving an 8×8 LED matrix using 74HC595 shift registers.
	2.	Python Application: Generates, optimizes, and previews LED patterns or animations—powered by AI.

Hardware Setup

Components:
	•	Arduino (e.g., Arduino Uno)
	•	8×8 LED matrix
	•	74HC595 shift register
	•	TPIC6B595 shift register
	•	Appropriate resistors
	•	Breadboard and wires

Arduino Pin Configuration:
	•	SHIFT_DATA = 8
	•	SHIFT_CLOCK = 7
	•	SHIFT_LATCH = 6

Refer to a generic shift register + 8×8 LED matrix tutorial for detailed wiring diagrams.

Arduino Code
	1.	Open Arduino.ino in the Arduino IDE (or your preferred environment).
	2.	Select the correct Board and Port.
	3.	Click Upload to flash the code onto the Arduino.

How It Works
	•	The Arduino listens over Serial (9600 baud) for special markers:
	•	0xFF ... 0xFE to receive a single-frame 8-row pattern.
	•	0xFA <frame_count> ... 0xFB to receive animation frames.
	•	Once a valid pattern or animation is received, it updates the currentDisplay buffer.
	•	Rows are scanned rapidly to display the pattern or animation on the matrix.

Python Environment

The Python code provides:
	•	A Command-Line Interface and a Tkinter-based UI (ui.py) to generate and edit patterns.
	•	AI utilities for pattern generation (ai_utils.py), requiring an API key.

Installation
	1.	Python 3.7+ is recommended.
	2.	Install dependencies (use a virtual environment if preferred):
Important: OpenAI recently updated their library. Install the required version using:

pip install --upgrade openai==0.28


	3.	Install dependencies for your operating system:

Windows

pip install -r requirements.txt

macOS
	1.	Install Homebrew (if not already installed):

brew install python git


	2.	Install requirements:

pip3 install -r requirements.txt



Ubuntu/Debian

sudo apt update
sudo apt install -y python3 python3-pip git
pip3 install -r requirements.txt
sudo apt install -y arduino

Fedora/RHEL/CentOS

sudo dnf install -y python3 python3-pip git
pip3 install -r requirements.txt
sudo dnf install -y arduino

Arch Linux/Manjaro

sudo pacman -Syu python python-pip git
pip install -r requirements.txt
sudo pacman -Syu arduino

	4.	Set your AI API key in a .env file:

GLHF_API_KEY=YOUR_KEY_HERE

Alternatively, export it as an environment variable in your shell. Recommended API key source: GLHF Chat.

	5.	(Optional) If you don’t have hardware connected, set USE_MOCK_SERIAL = True in serial_utils.py to simulate serial communication.

Running the UI
	1.	Power your Arduino and ensure it’s connected via USB.
	2.	Launch the Python application:

python main.py


	3.	In the UI:
	•	Type a description (e.g., “smiley face” or “scrolling text”).
	•	Click:
	•	Generate Single: To create a single-frame pattern.
	•	Generate Anim: To generate a multi-frame animation.
	4.	The UI sends the pattern or animation to your Arduino over Serial and displays it on the matrix.
	5.	Use Edit and Optimize to refine patterns or animations.

Saving & Loading Patterns
	•	Save patterns/animations as JSON files in the saved_patterns folder.
	•	Use File -> Save As… in the UI to save your current pattern/animation.
	•	Use File -> Load to browse and load existing .json files.

Troubleshooting

Common Issues
	•	No Serial Port Found:
	•	Check USB connections and ensure the correct COM port or /dev/tty is available.
	•	Use the following command to find your port (modify for your OS):

ls /dev/cu.* /dev/tty.*


	•	LEDs Not Lighting:
	•	Verify wiring between the shift register, matrix, and Arduino pins.
	•	AI Not Generating Patterns:
	•	Confirm your GLHF_API_KEY is valid and ensure you have network access.