#include <Arduino.h>
#include <NimBLEDevice.h>

// ======== CONFIG ========
static const char* DEVICE_NAME  = "ESP32_A";
static const uint32_t PASSKEY   = 123456;

// UUIDs 128-bit (deben coincidir en ambos)
static const char* SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab";
static const char* CHAR_UUID    = "abcdefab-1234-5678-1234-abcdefabcdef";

// 1 = borra bonds en cada arranque (solo para prueba)
// 0 = modo normal (recomendado luego)
#define RESET_BONDS_ON_BOOT 1
// ========================

class ServerCB : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, NimBLEConnInfo& ci) override {
    Serial.print("[SERVER] Conectado: ");
    Serial.println(ci.getAddress().toString().c_str());

    // Forzar seguridad apenas conecta (inicia pairing si hace falta)
    NimBLEDevice::startSecurity(ci.getConnHandle());
  }

  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
    Serial.print("[SERVER] Desconectado reason=");
    Serial.println(reason);

    // Volver a anunciar para reconexión automática
    NimBLEDevice::startAdvertising();
  }

  uint32_t onPassKeyDisplay() override {
    Serial.printf("[SERVER] PIN solicitado -> %06u\n", (unsigned)PASSKEY);
    return PASSKEY;
  }

  void onAuthenticationComplete(NimBLEConnInfo&) override {
    Serial.println("[SERVER] Pairing/Auth terminado");
  }
};

void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println("[SERVER] Init NimBLE");
  NimBLEDevice::init(DEVICE_NAME);
  NimBLEDevice::setPower(9);

#if RESET_BONDS_ON_BOOT
  Serial.println("[SERVER] Borrando bonds...");
  NimBLEDevice::deleteAllBonds();
  delay(200);
#endif

  // bonding=true, mitm=true => passkey / protección MITM
  NimBLEDevice::setSecurityAuth(true, true, false);
  NimBLEDevice::setSecurityPasskey(PASSKEY);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);

  NimBLEServer* server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCB());

  NimBLEService* svc = server->createService(SERVICE_UUID);

  // Característica segura: obliga cifrado + autenticación
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

  // Advertising robusto:
  // - ADV: UUID (para que quepa siempre)
  // - ScanRsp: nombre (para que lo vea el central en active scan)
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
