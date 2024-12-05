#include <Arduino.h> // Used to run Arduino code outside of Arduino IDE

// Pin Definitions
#define SHIFT_DATA 8   // A0
#define SHIFT_CLOCK 7  // A1
#define SHIFT_LATCH 6  // A2

// Matrix Dimensions
#define NUM_ROWS 8
#define NUM_COLS 8
#define MAX_FRAMES 10  // Maximum number of animation frames

// Markers
#define START_SINGLE_FRAME 0xFF
#define END_SINGLE_FRAME 0xFE
#define START_ANIMATION 0xFA
#define END_ANIMATION 0xFB

// Image Data (Single Frame)
uint8_t image[NUM_ROWS] = {0, 0, 0, 0, 0, 0, 0, 0};

// Animation Data
uint8_t animationFrames = 0;
uint8_t currentFrame = 0;
uint8_t animationData[MAX_FRAMES][NUM_ROWS];
bool animationReceived = false;

// Function to update the shift registers for a single row
void singleRow(uint8_t row, uint8_t columns) {
  digitalWrite(SHIFT_LATCH, LOW);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK, LSBFIRST, columns);     // Set columns
  shiftOut(SHIFT_DATA, SHIFT_CLOCK, MSBFIRST, 1 << row);    // Set row
  digitalWrite(SHIFT_LATCH, HIGH);
}

// Function to display a single frame
void displayFrame(uint8_t frame[]) {
  for (uint8_t i = 0; i < NUM_ROWS; i++) {
    singleRow(i, frame[i]); // Display each row with its corresponding pattern
    delay(1); // Short delay for persistence of vision
  }
}

// Function to display the entire image (static)
void displayImage() {
  displayFrame(image);
}

// Function to display animation frames
void displayAnimation() {
  if (animationReceived && animationFrames > 0) {
    displayFrame(animationData[currentFrame]);
    currentFrame = (currentFrame + 1) % animationFrames;
    delay(100); // Delay between frames (adjust as needed)
  }
}

// Function to clear animation data
void clearAnimation() {
  animationFrames = 0;
  currentFrame = 0;
  animationReceived = false;
}

void setup() {
  // Initialize Shift Register Pins as Outputs
  pinMode(SHIFT_DATA, OUTPUT);
  pinMode(SHIFT_CLOCK, OUTPUT);
  pinMode(SHIFT_LATCH, OUTPUT);

  // Initialize Shift Registers to a known state (All LEDs off)
  digitalWrite(SHIFT_LATCH, LOW);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK, MSBFIRST, 0x00); // Columns off
  shiftOut(SHIFT_DATA, SHIFT_CLOCK, MSBFIRST, 0x00); // Rows off
  digitalWrite(SHIFT_LATCH, HIGH);

  // Initialize Serial Communication
  Serial.begin(9600);
  while (!Serial) {
    ; // Wait for serial port to connect. Needed for native USB
  }
  Serial.println("Arduino ready to receive patterns.");
}

void loop() {
  // Check if data is available on the serial port
  if (Serial.available() > 0) {
    byte startMarker = Serial.read();
    Serial.print("Start marker received: 0x");
    Serial.println(startMarker, HEX);
    
    if (startMarker == START_SINGLE_FRAME) {
      // Handle single frame
      byte receivedPattern[NUM_ROWS];
      bool valid = true;

      for (int i = 0; i < NUM_ROWS; i++) {
        while (Serial.available() == 0) { /* Wait */ }
        receivedPattern[i] = Serial.read();
        Serial.print("Frame ");
        Serial.print(i + 1);
        Serial.print(" byte received: 0x");
        Serial.println(receivedPattern[i], HEX);
      }

      while (Serial.available() == 0) { /* Wait */ }
      byte endMarker = Serial.read();
      Serial.print("End marker received: 0x");
      Serial.println(endMarker, HEX);
      
      if (endMarker != END_SINGLE_FRAME) {
        Serial.println("Invalid end marker received for single frame.");
        valid = false;
      }

      if (valid) {
        // Update the image array
        for (int i = 0; i < NUM_ROWS; i++) {
          image[i] = receivedPattern[i];
        }
        Serial.println("Pattern received.");
      }
    }
    else if (startMarker == START_ANIMATION) {
      // Handle animation
      while (Serial.available() == 0) { /* Wait */ }
      byte num_frames = Serial.read();
      Serial.print("Number of frames received: ");
      Serial.println(num_frames);

      if (num_frames == 0 || num_frames > MAX_FRAMES) {
        Serial.println("Invalid number of frames.");
        clearAnimation();
      }
      else {
        animationFrames = num_frames;
        for (byte f = 0; f < animationFrames; f++) {
          for (int j = 0; j < NUM_ROWS; j++) {
            while (Serial.available() == 0) { /* Wait */ }
            animationData[f][j] = Serial.read();
            Serial.print("Frame ");
            Serial.print(f + 1);
            Serial.print(", Row ");
            Serial.print(j + 1);
            Serial.print(" byte received: 0x");
            Serial.println(animationData[f][j], HEX);
          }
        }

        while (Serial.available() == 0) { /* Wait */ }
        byte endMarker = Serial.read();
        Serial.print("End marker received: 0x");
        Serial.println(endMarker, HEX);
        
        if (endMarker != END_ANIMATION) {
          Serial.println("Invalid end marker for animation.");
          clearAnimation();
        }
        else {
          animationReceived = true;
          Serial.println("Animation received.");
        }
      }
    }
    else {
      Serial.println("Unknown start marker received.");
    }
  }

  // Display either static image or animation
  if (animationReceived && animationFrames > 0) {
    displayAnimation();
  }
  else {
    displayImage();
  }
}