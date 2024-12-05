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
