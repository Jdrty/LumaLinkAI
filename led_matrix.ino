#include <Arduino.h> // This is because I'm not in the arduino IDE, IGNORE

// Pin definitions for shift register
#define SHIFT_DATA 8
#define SHIFT_CLOCK 7
#define SHIFT_LATCH 6

// Display configuration
#define NUM_ROWS 8
#define MAX_FRAMES 10

// Protocol markers for serial communication
#define START_SINGLE_FRAME 0xFF
#define END_SINGLE_FRAME   0xFE
#define START_ANIMATION    0xFA
#define END_ANIMATION      0xFB

// Display buffers
uint8_t image[NUM_ROWS] = {0, 0, 0, 0, 0, 0, 0, 0};
uint8_t animationData[MAX_FRAMES][NUM_ROWS];
uint8_t currentDisplay[NUM_ROWS] = {0, 0, 0, 0, 0, 0, 0, 0};

// Animation state
uint8_t animationFrames = 0;
uint8_t currentFrame = 0;
bool animationActive = false;

// Timing variables for row scanning
unsigned long lastRowMillis = 0;
unsigned long rowInterval = 0; 
uint8_t currentRow = 0;

// Increase this time to make each row stay on longer (in microseconds).
// The longer each row stays lit, the brighter the LEDs will appear.
unsigned int rowOnTime = 1000; // 1000 is good enough for me but it can go larger without issues

// Timing variables for frame changes in animation
unsigned long lastFrameChange = 0;
unsigned long frameInterval = 500; // 500 ms per frame

/**
 * Shifts data and row information to the shift register.
 * @param r Row pattern
 * @param c Column pattern
 */
void shiftBoth(uint8_t r, uint8_t c) {
  digitalWrite(SHIFT_LATCH, LOW);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK, LSBFIRST, c);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK, MSBFIRST, r);
  digitalWrite(SHIFT_LATCH, HIGH);
}

/**
 * Scans and updates the current row on the display.
 * Increasing rowOnTime will give each row more time lit, 
 * making the display appear brighter.
 */
void scanRow() {
  // Turn on the current row
  shiftBoth(1 << currentRow, currentDisplay[currentRow]);

  // Keep the row on for rowOnTime microseconds
  delayMicroseconds(rowOnTime);

  // Turn off the row before moving on
  shiftBoth(0, 0);

  // Move to the next row
  currentRow = (currentRow + 1) % NUM_ROWS;
}

/**
 * Clears the current animation data and stops animation.
 */
void clearAnim() {
  animationFrames = 0;
  currentFrame = 0;
  animationActive = false;
}

void setup() {
  // Initialize shift register pins
  pinMode(SHIFT_DATA, OUTPUT);
  pinMode(SHIFT_CLOCK, OUTPUT);
  pinMode(SHIFT_LATCH, OUTPUT);
  
  // Reset shift register
  digitalWrite(SHIFT_LATCH, LOW);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK, MSBFIRST, 0x00);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK, MSBFIRST, 0x00);
  digitalWrite(SHIFT_LATCH, HIGH);
  
  // Initialize serial communication
  Serial.begin(9600);
  while (!Serial) {} // Wait for serial port
  
  // Load initial image into display buffer
  for(int i = 0; i < NUM_ROWS; i++) {
    currentDisplay[i] = image[i];
  }
}

void loop() {
  // Handle incoming serial data
  if (Serial.available() > 0) {
    byte startMarker = Serial.read();
    
    // Handle single frame update
    if (startMarker == START_SINGLE_FRAME) {
      uint8_t tmp[NUM_ROWS];
      bool valid = true;
      
      // Read image data
      for(int i = 0; i < NUM_ROWS; i++) {
        while(Serial.available() == 0) {}
        tmp[i] = Serial.read();
      }
      
      // Verify end marker
      while(Serial.available() == 0) {}
      byte endMarker = Serial.read();
      if(endMarker != END_SINGLE_FRAME) valid = false;
      
      // Update display if data is valid
      if(valid){
        for(int i = 0; i < NUM_ROWS; i++) {
          image[i] = tmp[i];
          currentDisplay[i] = tmp[i];
        }
        animationActive = false; // Stop any ongoing animation
        Serial.println("Pattern received.");
      }
    
    // Handle animation update
    } else if (startMarker == START_ANIMATION) {
      while(Serial.available() == 0) {}
      byte nf = Serial.read(); // Number of frames
      
      if(nf == 0 || nf > MAX_FRAMES) {
        clearAnim(); // Invalid frame count
      }
      else {
        animationFrames = nf;
        
        // Read animation frames
        for(byte f = 0; f < animationFrames; f++) {
          for(int j = 0; j < NUM_ROWS; j++) {
            while(Serial.available() == 0) {}
            animationData[f][j] = Serial.read();
          }
        }
        
        // Verify end marker
        while(Serial.available() == 0) {}
        byte endMarker = Serial.read();
        if(endMarker != END_ANIMATION) {
          clearAnim();
        }
        else {
          animationActive = true;
          currentFrame = 0;
          
          // Initialize display with first frame
          for(int row = 0; row < NUM_ROWS; row++) {
            currentDisplay[row] = animationData[0][row];
          }
          Serial.println("Animation received.");
          lastFrameChange = millis();
        }
      }
    }
  }
  
  unsigned long now = millis();
  
  // Update row scanning
  // We scan a row as often as possible, 
  // but you could also use a fixed interval, idk it doesn't really matter
  if(now - lastRowMillis > 0) {
    lastRowMillis = now;
    scanRow();
  }
  
  // Handle animation frame changes
  if(animationActive && animationFrames > 0) {
    if(now - lastFrameChange >= frameInterval) {
      lastFrameChange = now;
      currentFrame = (currentFrame + 1) % animationFrames;
      
      // Update display with the new frame
      for(int r = 0; r < NUM_ROWS; r++) {
        currentDisplay[r] = animationData[currentFrame][r];
      }
    }
  }
}