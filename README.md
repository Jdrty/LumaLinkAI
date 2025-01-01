LumaLink AI

This repository contains:
	1.	An Arduino sketch for driving an 8×8 LED matrix using 74HC595 shift registers.
	2.	A Python-based application that can generate, optimize, and preview LED patterns or animations—powered by AI.

Hardware Setup
	•	Components:
	•	Arduino (e.g., Arduino Uno)
	•	8×8 LED matrix
	•	74HC595 shift register
	•	TPIC6B595 shift register
	•	Appropriate resistors
	•	Breadboard and wires
	•	Pins on Arduino (as defined in Arduino.ino):
	•	SHIFT_DATA = 8
	•	SHIFT_CLOCK = 7
	•	SHIFT_LATCH = 6

Refer to any generic shift register + 8×8 LED matrix tutorial for detailed wiring diagrams if needed.

Arduino Code
	1.	Open Arduino.ino in the Arduino IDE (or your preferred environment).
	2.	Select the correct Board and Port.
	3.	Click Upload to flash the code onto the Arduino.

How It Works
	•	The Arduino listens over Serial (9600 baud) for special markers:
	•	0xFF ... 0xFE to receive a single-frame 8-row pattern.
	•	0xFA <frame_count> ... 0xFB to receive animation frames.
	•	Once the code receives a valid pattern or animation, it updates the currentDisplay buffer accordingly.
	•	Rows are scanned in quick succession, enabling the matrix to display the pattern or play the animation.

Python Environment

The Python code in this repo provides:
	•	A command-line interface and a Tkinter-based UI (ui.py) to generate and edit patterns.
	•	AI utilities for pattern generation (ai_utils.py), requiring an API key.

Installation
	1.	Python 3.7+ is recommended.
	2.	Install dependencies (create a virtual environment if you prefer):
  3.  IMPORTANT, OpenAI recently updated their library, you will need to manually install OpenAIs older library using this:
  pip install --upgrade openai==0.28
  Modify for your os/language, refer to below cmds for the rest of the setup

Windows
pip install -r requirements.txt

Mac
Install Homebrew (if not already installed)
brew install python git
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


	3.	Set your AI API key in a .env file:

GLHF_API_KEY=YOUR_KEY_HERE
(Recommended is to get from here https://glhf.chat/chat/create, else you will need to redo a lot of the AI setup)

Or export it as an environment variable in your shell.

	4.	(Optional) If you do not have a hardware Arduino connected, set USE_MOCK_SERIAL = True in serial_utils.py to simulate serial communication.

Running the UI
	1.	Power your Arduino and ensure it’s connected via USB.
	2.	Launch main.py:


	3.	Type a description (e.g., “smiley face” or “scrolling text”), then click:
	•	Generate Single to make a single-frame pattern.
	•	Generate Anim to create a multi-frame animation.
	4.	The UI sends the generated pattern or animation to your Arduino over Serial and displays it on the matrix.
	5.	Use Edit and Optimize in the UI to refine patterns or animations.

Saving & Loading Patterns
	•	Patterns and animations can be saved as JSON files in the saved_patterns folder.
	•	Use File -> Save As… in the UI to store your current pattern or animation.
	•	Use File -> Load to browse existing .json files and load them.

Troubleshooting
	•	No Serial Port Found: Check your USB connection and ensure the correct COM port / /dev/tty is available. Else add your port, you can use something like this in your shell (modify for your os/language):
  ls /dev/cu.* /dev/tty.*
  to find your ports
	•	LEDs Not Lighting: Verify wiring between the shift register, matrix, and Arduino pins.
	•	AI Not Generating Patterns: Confirm your GLHF_API_KEY is valid and that you have network access.

Enjoy exploring LED patterns and AI-driven creativity!