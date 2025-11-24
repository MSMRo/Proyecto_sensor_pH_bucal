#define SensorPin A0  // Pin ADC donde está conectado el sensor
#define VREF 3.3      // Voltaje de referencia del ADC en XIAO NRF
#define ADC_RES 1023.0 // Resolución ADC de 10 bits (0-1023)
#define DIVISOR 1.0    // Factor del divisor de tensión

#include <Adafruit_TinyUSB.h> 
#include <bluefruit.h>  // Asegurar que la librería está bien incluida

float voltage, phValue;

// Definir el objeto BLE UART correctamente
BLEUart bleuart;  

void setup() {
    Serial.begin(115200);

    // Configurando PIN
    pinMode(SensorPin, INPUT);

    while (!Serial);  
    Serial.println("Iniciando BLE...");

    Bluefruit.begin();
    Bluefruit.setName("XIAO_BLE");

    // Inicializar UART BLE
    bleuart.begin();

    // Configurar advertising con el servicio UART
    Bluefruit.Advertising.addService(bleuart);
    Bluefruit.Advertising.start();

    Serial.println("BLE Advertise iniciado...");
}

void loop() {
    int sensorValue = analogRead(SensorPin);  // Leer ADC (0-1023)
    voltage = (sensorValue * VREF) / ADC_RES; // Convertir a voltaje medido

    // Conversión de voltaje real a pH
    // Arduino Vref 5
    //phValue = 7 + ((2.586 - voltage) / 0.17); 

    // Xiao Vref 3.3
    phValue = 7 + ((2.506 - voltage) / 0.152);

    // Mostrar valores en el monitor serial
    Serial.print("ADC Value: "); Serial.print(sensorValue);
    Serial.print(" | Measured Voltage: "); Serial.print(voltage, 3);
    Serial.print("V | pH: "); Serial.println(phValue, 2);

    if (Bluefruit.connected()) {  // Verifica si hay conexión BLE
        bleuart.println("Mensaje desde Xiao Seeed nRF52840");
        // Mostrar valores en el monitor serial
        bleuart.print("ADC Value: "); bleuart.print(sensorValue);
        bleuart.print(" | Measured Voltage: "); bleuart.print(voltage, 3);
        bleuart.print("V | pH: "); bleuart.println(phValue, 2);

        
        Serial.println("Mensaje enviado por BLE.");
        delay(2000);  // Enviar cada 1 segundo
    }
    delay(2000);
}
