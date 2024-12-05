# Project Overview
- As a base, it uses an 8x8 LED matrix controlled by two different 555 shift registers
- Using an Arduino Nano, it has the ability to display patterns on the matrix with 8 integers ranging from 0-255
- The previous Arduino script interfaces with a python script that interfaces with OpenAI
- OpenAI generates 8 integers that will replace the integers inside the Arduino script
- Saving/Loading features are integrated through json files that the script reads from inside your project directory
- If there are details you need to fix in the animation you can edit the matrix in real time with a dynamic interface
- Complete frontend in TKinter
# Non Functional/Needs fixing
- There is an animation feature but they are very buggy and must be improved
- Animations flash to blank before resuming every frame for an unknown reason
# To Run Files
- You will need your own API key stored in a ".env" file in the project directory with this format:
  GLHF_API_KEY=*YOUR_API_KEY_HERE*
- Heres a good place to get yours for no cost: https://glhf.chat/users/settings/api
- Ensure you have all libraries downloaded:
  pip install openai
  pip install pyserial
  pip install glob2
- If your using python 3.7 put pip3 instead of pip!
# Future Planning
- Will likely change to a 16x16 matrix
- Change shift registers for better design and functionality, likely use MAX7219 chip
- Make the frontend more visually appealing
