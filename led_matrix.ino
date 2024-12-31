#include <Arduino.h>

#define SHIFT_DATA 8
#define SHIFT_CLOCK 7
#define SHIFT_LATCH 6
#define NUM_ROWS 8
#define MAX_FRAMES 10

#define START_SINGLE_FRAME 0xFF
#define END_SINGLE_FRAME 0xFE
#define START_ANIMATION 0xFA
#define END_ANIMATION 0xFB

uint8_t image[NUM_ROWS]={0,0,0,0,0,0,0,0};
uint8_t animationData[MAX_FRAMES][NUM_ROWS];
uint8_t currentDisplay[NUM_ROWS]={0,0,0,0,0,0,0,0};
uint8_t animationFrames=0;
uint8_t currentFrame=0;
bool animationActive=false;

unsigned long lastRowMillis=0;
unsigned long rowInterval=0; 
uint8_t currentRow=0;

unsigned long lastFrameChange=0;
unsigned long frameInterval=500; // half second per frame

void shiftBoth(uint8_t r, uint8_t c){
  digitalWrite(SHIFT_LATCH,LOW);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK,LSBFIRST,c);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK,MSBFIRST,r);
  digitalWrite(SHIFT_LATCH,HIGH);
}
void scanRow(){
  shiftBoth(1<<currentRow,currentDisplay[currentRow]);
  delayMicroseconds(200);
  shiftBoth(0,0);
  currentRow++;
  if(currentRow>=NUM_ROWS)currentRow=0;
}
void clearAnim(){
  animationFrames=0;
  currentFrame=0;
  animationActive=false;
}
void setup(){
  pinMode(SHIFT_DATA,OUTPUT);
  pinMode(SHIFT_CLOCK,OUTPUT);
  pinMode(SHIFT_LATCH,OUTPUT);
  digitalWrite(SHIFT_LATCH,LOW);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK,MSBFIRST,0x00);
  shiftOut(SHIFT_DATA, SHIFT_CLOCK,MSBFIRST,0x00);
  digitalWrite(SHIFT_LATCH,HIGH);
  Serial.begin(9600);
  while(!Serial){}
  for(int i=0;i<NUM_ROWS;i++){
    currentDisplay[i]=image[i];
  }
}
void loop(){
  if(Serial.available()>0){
    byte startMarker=Serial.read();
    if(startMarker==START_SINGLE_FRAME){
      uint8_t tmp[NUM_ROWS];
      bool valid=true;
      for(int i=0;i<NUM_ROWS;i++){
        while(Serial.available()==0){}
        tmp[i]=Serial.read();
      }
      while(Serial.available()==0){}
      byte endMarker=Serial.read();
      if(endMarker!=END_SINGLE_FRAME)valid=false;
      if(valid){
        for(int i=0;i<NUM_ROWS;i++){
          image[i]=tmp[i];
          currentDisplay[i]=tmp[i];
        }
        animationActive=false;
        Serial.println("Pattern received.");
      }
    } else if(startMarker==START_ANIMATION){
      while(Serial.available()==0){}
      byte nf=Serial.read();
      if(nf==0||nf>MAX_FRAMES)clearAnim();
      else{
        animationFrames=nf;
        for(byte f=0;f<animationFrames;f++){
          for(int j=0;j<NUM_ROWS;j++){
            while(Serial.available()==0){}
            animationData[f][j]=Serial.read();
          }
        }
        while(Serial.available()==0){}
        byte endMarker=Serial.read();
        if(endMarker!=END_ANIMATION)clearAnim();
        else{
          animationActive=true;
          currentFrame=0;
          for(int row=0;row<NUM_ROWS;row++){
            currentDisplay[row]=animationData[0][row];
          }
          Serial.println("Animation received.");
          lastFrameChange=millis();
        }
      }
    }
  }
  unsigned long now=millis();
  if(now-lastRowMillis>0){
    lastRowMillis=now;
    scanRow();
  }
  if(animationActive&&animationFrames>0){
    if(now-lastFrameChange>=frameInterval){
      lastFrameChange=now;
      currentFrame=(currentFrame+1)%animationFrames;
      for(int r=0;r<NUM_ROWS;r++){
        currentDisplay[r]=animationData[currentFrame][r];
      }
    }
  }
}