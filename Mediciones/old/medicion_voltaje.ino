#define SensorPin A0  // Pin ADC donde está conectado el sensor
#define VREF 3.3      // Voltaje de referencia del ADC en XIAO NRF
#define ADC_RES 1023.0 // Resolución ADC de 10 bits (0-1023)
#include <Adafruit_TinyUSB.h>

float voltaje, entrada_A0, phValue;


void setup()  {
  Serial.begin(115200);
}
 
void loop() {
  entrada_A0 = analogRead(SensorPin);
  voltaje = (entrada_A0 * VREF) / ADC_RES;
  Serial.print("Voltaje: ");
  Serial.print(voltaje,3);

  phValue = 7 + ((2.500 - voltaje) / 0.04);
  Serial.print(" V | pH: ");
  Serial.println(phValue,3);
  delay(1500);
}

