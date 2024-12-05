// PROJECT  : EEPROM
// PURPOSE  : Write ASCII font data to EEPROM for use in an LED matrix project.
// COURSE   : ICS3U-E1
// AUTHOR   : Julian Darou-Santos
// DATE     : 2024 11 21
// MCU      : ATmega328P (Standalone)
// STATUS   : Working
// REFERENCE: http://darcy.rsgc.on.ca

#include <Arduino.h> // Used to run Arduino code outside of Arduino IDE
#include "Support.h"  // Includes the font data for ASCII characters.
#include <EEPROM.h>   // Allows interaction with EEPROM memory.

void setup() {
  Serial.begin(9600);  // Initialize Serial communication at 9600 baud.
  while (!Serial)
    ;  // Wait for Serial Monitor to be ready.

  // Uncomment the following lines for testing EEPROM functionality:
  // Serial.println(EEPROM.length());  // Print EEPROM size (for debugging).
  // displayEEPROM(0, 9);             // Display first 10 EEPROM addresses.
  // clearEEPROM();                   // Clear all EEPROM data.
  // displayEEPROM(0, 9);             // Verify EEPROM is cleared.

  // Load ASCII font map into EEPROM.
  for (uint8_t ascii = 0; ascii <= 127; ascii++) {
    uint16_t baseAddress = ascii * 8;  // Calculate starting address for each ASCII character.
    for (uint8_t anodes = 0; anodes <= 7; anodes++) {
      EEPROM.write(baseAddress + anodes, font[ascii][anodes]);  // Write 8 bytes (rows) for each character.
    }
  }

  // Confirm that the write was successful by reading back data.
  Serial.println(EEPROM.read('A' * 8));  // Example: Read data for ASCII 'A'.
  Serial.println(EEPROM[520]);           // Verify data at a specific EEPROM address.
}

void clearEEPROM() {
  // Clears all data in the EEPROM by writing 0 to each address.
  for (uint16_t address = 0; address < EEPROM.length(); address++) {
    EEPROM.write(address, 0);  // Set each byte to 0.
  }
}

void displayEEPROM(uint16_t from, uint16_t to) {
  // Displays the content of EEPROM from a starting to an ending address.
  for (uint16_t address = from; address <= to; address++) {
    Serial.print("[");
    Serial.print(address);
    Serial.print("]\t");
    Serial.println(EEPROM.read(address));  // Print the value stored at each address.
  }
}

void loop() {
  // No operation in the main loop.
}