#include <Arduino.h>
#include <NimBLEDevice.h>

static const char* DEVICE_NAME  = "ESP32_A_TEST";
static const char* SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab";

void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println("[SERVER] Init");
  NimBLEDevice::init(DEVICE_NAME);

  // Sube potencia (si tu core lo soporta, este número suele funcionar bien)
  NimBLEDevice::setPower(9);

  // Crea un servicio simple (no seguridad)
  NimBLEServer* server = NimBLEDevice::createServer();
  NimBLEService* svc = server->createService(SERVICE_UUID);
  svc->start();

  // Advertising explícito: nombre + UUID 128-bit
  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  adv->stop();

  // Advertising: SOLO el UUID (para que quepa sí o sí)
  NimBLEAdvertisementData ad;
  ad.addServiceUUID(NimBLEUUID(SERVICE_UUID));
  adv->setAdvertisementData(ad);

  // Scan Response: SOLO el nombre (active scan lo obtiene)
  NimBLEAdvertisementData sd;
  sd.setName(DEVICE_NAME);
  adv->setScanResponseData(sd);

  adv->start();
  Serial.println("[SERVER] Advertising ON (UUID en ADV, nombre en ScanRsp)");

}

void loop() {
  delay(2000);
}
