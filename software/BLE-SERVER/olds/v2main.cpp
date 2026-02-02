#include <Arduino.h>
#include <NimBLEDevice.h>

static const char* DEVICE_NAME  = "ESP32_A";
static const uint32_t PASSKEY   = 123456;

static const char* SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab";
static const char* CHAR_UUID    = "abcdefab-1234-5678-1234-abcdefabcdef";

class ServerCB : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, NimBLEConnInfo& ci) override {
    Serial.print("[SERVER] Conectado: ");
    Serial.println(ci.getAddress().toString().c_str());

    // Dispara pairing/seguridad al conectar
    NimBLEDevice::startSecurity(ci.getConnHandle());
  }

  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
    Serial.print("[SERVER] Desconectado reason=");
    Serial.println(reason);
    NimBLEDevice::startAdvertising();
  }

  uint32_t onPassKeyDisplay() override {
    Serial.printf("[SERVER] PIN solicitado -> %06u\n", (unsigned)PASSKEY);
    return PASSKEY;
  }

  void onAuthenticationComplete(NimBLEConnInfo& ci) override {
    Serial.println("[SERVER] Pairing/Auth terminado");
  }
};

void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println("[SERVER] Init NimBLE");
  NimBLEDevice::init(DEVICE_NAME);
  NimBLEDevice::setPower(9);

  // Si estás probando y ya quedó bond guardado:
  // NimBLEDevice::deleteAllBonds();

  // bonding=true, mitm=true (para passkey), sc=false (ok)
  NimBLEDevice::setSecurityAuth(true, true, false);
  NimBLEDevice::setSecurityPasskey(PASSKEY);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);

  NimBLEServer* server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCB());

  NimBLEService* svc = server->createService(SERVICE_UUID);

  // Característica que EXIGE cifrado (y auth) => fuerza pairing real
  NimBLECharacteristic* ch = svc->createCharacteristic(
    CHAR_UUID,
    NIMBLE_PROPERTY::READ |
    NIMBLE_PROPERTY::WRITE |
    NIMBLE_PROPERTY::READ_ENC |
    NIMBLE_PROPERTY::WRITE_ENC |
    NIMBLE_PROPERTY::READ_AUTHEN |
    NIMBLE_PROPERTY::WRITE_AUTHEN
  );
  ch->setValue("SECURE_OK");

  svc->start();

  // Advertising robusto: UUID en ADV, nombre en Scan Response
  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  adv->stop();

  NimBLEAdvertisementData ad;
  ad.addServiceUUID(NimBLEUUID(SERVICE_UUID));
  adv->setAdvertisementData(ad);

  NimBLEAdvertisementData sd;
  sd.setName(DEVICE_NAME);
  adv->setScanResponseData(sd);

  adv->start();
  Serial.println("[SERVER] Advertising ON (UUID en ADV, nombre en ScanRsp)");
}

void loop() {}
