#include <Arduino.h>

// Pin definitions for shift register
const uint8_t SHIFT_DATA = 8;
const uint8_t SHIFT_CLOCK = 7;
const uint8_t SHIFT_LATCH = 6;

// Display configuration
const uint8_t NUM_ROWS = 8;
const uint8_t MAX_FRAMES = 10;

// Protocol markers for serial communication
const uint8_t START_SINGLE_FRAME = 0xFF;
const uint8_t END_SINGLE_FRAME = 0xFE;
const uint8_t START_ANIMATION = 0xFA;
const uint8_t END_ANIMATION = 0xFB;
const uint8_t SET_BRIGHTNESS = 0xFC;

// Display buffers
uint8_t image[NUM_ROWS] = {0};
uint8_t animationData[MAX_FRAMES][NUM_ROWS];
uint8_t currentDisplay[NUM_ROWS] = {0};

// Animation state
volatile uint8_t animationFrames = 0;
volatile uint8_t currentFrame = 0;
volatile bool animationActive = false;

// Timing variables
unsigned long lastRowMillis = 0;
uint8_t currentRow = 0;

// Brightness control (in microseconds)
const unsigned int BRIGHTNESS_MIN = 500;
const unsigned int BRIGHTNESS_MAX = 5000;
volatile unsigned int rowOnTime = 1000;  // Default row on time

// Animation timing
unsigned long lastFrameChange = 0;
const unsigned long FRAME_INTERVAL = 500;  // 500ms per frame

/**
 * Shifts data and row information to the shift register.
 * @param row Row pattern (active high)
 * @param col Column pattern (active high)
 */
void shiftBoth(uint8_t row, uint8_t col) {
    noInterrupts();  // Disable interrupts during shift
    digitalWrite(SHIFT_LATCH, LOW);
    shiftOut(SHIFT_DATA, SHIFT_CLOCK, LSBFIRST, col);
    shiftOut(SHIFT_DATA, SHIFT_CLOCK, MSBFIRST, row);
    digitalWrite(SHIFT_LATCH, HIGH);
    interrupts();    // Re-enable interrupts
}

/**
 * Scans and updates the current row on the display.
 */
void scanRow() {
    // Turn on the current row
    shiftBoth(1 << currentRow, currentDisplay[currentRow]);
    
    // Keep the row on for rowOnTime microseconds
    delayMicroseconds(rowOnTime);
    
    // Turn off all LEDs to prevent ghosting
    shiftBoth(0, 0);
    
    // Move to the next row
    currentRow = (currentRow + 1) % NUM_ROWS;
}

/**
 * Clears the animation data and stops animation.
 */
void clearAnim() {
    noInterrupts();
    animationFrames = 0;
    currentFrame = 0;
    animationActive = false;
    interrupts();
    
    // Clear display buffer
    memset(currentDisplay, 0, NUM_ROWS);
}

/**
 * Reads exactly n bytes from Serial into buffer.
 * @param buffer Buffer to store read bytes
 * @param n Number of bytes to read
 * @return true if successful, false if timeout
 */
bool readSerial(uint8_t* buffer, uint8_t n) {
    const unsigned long timeout = 1000;  // 1 second timeout
    unsigned long startTime = millis();
    
    for (uint8_t i = 0; i < n; i++) {
        while (!Serial.available()) {
            if (millis() - startTime > timeout) {
                return false;
            }
        }
        buffer[i] = Serial.read();
    }
    return true;
}

void setup() {
    // Initialize shift register pins
    pinMode(SHIFT_DATA, OUTPUT);
    pinMode(SHIFT_CLOCK, OUTPUT);
    pinMode(SHIFT_LATCH, OUTPUT);
    
    // Reset shift register
    shiftBoth(0, 0);
    
    // Initialize serial communication
    Serial.begin(9600);
    while (!Serial) {
        ; // Wait for serial port to connect
    }
}

void loop() {
    // Handle incoming serial data
    if (Serial.available() > 0) {
        uint8_t startMarker = Serial.read();
        
        switch (startMarker) {
            case START_SINGLE_FRAME: {
                uint8_t tmp[NUM_ROWS];
                if (!readSerial(tmp, NUM_ROWS)) {
                    Serial.println(F("Error: Timeout reading frame data"));
                    break;
                }
                
                uint8_t endMarker;
                if (!readSerial(&endMarker, 1) || endMarker != END_SINGLE_FRAME) {
                    Serial.println(F("Error: Invalid end marker"));
                    break;
                }
                
                noInterrupts();
                memcpy(image, tmp, NUM_ROWS);
                memcpy(currentDisplay, tmp, NUM_ROWS);
                animationActive = false;
                interrupts();
                
                Serial.println(F("Pattern received"));
                break;
            }
            
            case START_ANIMATION: {
                uint8_t numFrames;
                if (!readSerial(&numFrames, 1) || numFrames == 0 || numFrames > MAX_FRAMES) {
                    Serial.println(F("Error: Invalid frame count"));
                    clearAnim();
                    break;
                }
                
                // Read all frame data
                for (uint8_t f = 0; f < numFrames; f++) {
                    if (!readSerial(animationData[f], NUM_ROWS)) {
                        Serial.println(F("Error: Timeout reading animation data"));
                        clearAnim();
                        return;
                    }
                }
                
                uint8_t endMarker;
                if (!readSerial(&endMarker, 1) || endMarker != END_ANIMATION) {
                    Serial.println(F("Error: Invalid animation end marker"));
                    clearAnim();
                    break;
                }
                
                noInterrupts();
                animationFrames = numFrames;
                currentFrame = 0;
                animationActive = true;
                memcpy(currentDisplay, animationData[0], NUM_ROWS);
                interrupts();
                
                lastFrameChange = millis();
                Serial.println(F("Animation received"));
                break;
            }
            
            case SET_BRIGHTNESS: {
                uint8_t brightness;
                if (!readSerial(&brightness, 1)) {
                    Serial.println(F("Error: Timeout reading brightness"));
                    break;
                }
                
                noInterrupts();
                rowOnTime = BRIGHTNESS_MIN + ((unsigned long)brightness * (BRIGHTNESS_MAX - BRIGHTNESS_MIN)) / 255;
                interrupts();
                
                Serial.println(F("Brightness adjusted"));
                break;
            }
        }
    }
    
    // Update display
    unsigned long now = millis();
    
    // Scan rows
    if (now - lastRowMillis > 0) {
        lastRowMillis = now;
        scanRow();
    }
    
    // Update animation frame if active
    if (animationActive && animationFrames > 0 && now - lastFrameChange >= FRAME_INTERVAL) {
        lastFrameChange = now;
        
        noInterrupts();
        currentFrame = (currentFrame + 1) % animationFrames;
        memcpy(currentDisplay, animationData[currentFrame], NUM_ROWS);
        interrupts();
    }
}