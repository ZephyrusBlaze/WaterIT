#include <Servo.h>

const int pumpPin = 3;      // Pump pin
const int sensorPin = A0;   // Moisture sensor pin
const int servoPin = 7;     // Servo pin

Servo myServo;

unsigned long previousMillis = 0;  // Last moisture print time
unsigned long pumpStartTime = 0;   // Pump start time
unsigned long pumpEndTime = 0;     // Pump end time
const long interval = 60000;       // Print interval (1 min)

bool pumpOn = false;               // Pump status

void setup() {
  pinMode(pumpPin, OUTPUT);
  pinMode(sensorPin, INPUT);

  myServo.attach(servoPin);
  myServo.write(0); // Initial servo position

  Serial.begin(9600);
  Serial.println("System Initialized");
}

void loop() {
  unsigned long currentMillis = millis();  // Current time

  int moistureLevel = 1023 - analogRead(sensorPin); // Read moisture

  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;
    Serial.print("Moisture Level: ");
    Serial.println(moistureLevel);
  }

  if (moistureLevel < 400 && !pumpOn) {
    digitalWrite(pumpPin, LOW);  // Turn pump on
    pumpStartTime = millis();
    pumpOn = true;
    Serial.println("Pump turned ON");
  }

  if (moistureLevel > 400 && pumpOn) {
    digitalWrite(pumpPin, HIGH); // Turn pump off
    pumpEndTime = millis();
    pumpOn = false;
    Serial.println("Pump turned OFF");

    float waterUsed = (pumpEndTime - pumpStartTime) / 1000.0 * 0.0025; // Calculate water usage
    Serial.print("Water Used: ");
    Serial.println(waterUsed, 5); // Print with precision

    delay(5000);
    myServo.write(180); // Rotate servo
    delay(5000);
    myServo.write(0); // Return servo
  }

  delay(500); // Loop delay
}
