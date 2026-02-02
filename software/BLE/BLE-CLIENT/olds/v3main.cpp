#include <Arduino.h>
#include <NimBLEDevice.h>

// ======== CONFIG ========
static const char* CLIENT_NAME  = "ESP32_B";
static const uint32_t PASSKEY   = 123456;

static const char* SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab";
static const char* CHAR_UUID    = "abcdefab-1234-5678-1234-abcdefabcdef";

static const uint32_t SCAN_MS   = 3000;

// 1 = borra bonds en cada arranque (solo para prueba)
// 0 = modo normal (recomendado luego)
#define RESET_BONDS_ON_BOOT 1
// ========================

class ClientCB : public NimBLEClientCallbacks {
  void onConnect(NimBLEClient* c) override {
    Serial.println("[CLIENT] Conectado -> iniciando seguridad (pairing)...");
    NimBLEDevice::startSecurity(c->getConnHandle());
  }

  void onDisconnect(NimBLEClient*, int reason) override {
    Serial.print("[CLIENT] Desconectado reason=");
    Serial.println(reason);
  }

  void onPassKeyEntry(NimBLEConnInfo& ci) override {
    Serial.printf("[CLIENT] Servidor pide PIN -> inyectando %06u\n", (unsigned)PASSKEY);
    NimBLEDevice::injectPassKey(ci, PASSKEY);
  }

  void onAuthenticationComplete(NimBLEConnInfo&) override {
    Serial.println("[CLIENT] Pairing/Auth terminado");
  }
};

static NimBLEClient* gClient = nullptr;

bool scanAndConnect() {
  NimBLEScan* scan = NimBLEDevice::getScan();
  scan->setActiveScan(true);
  scan->setInterval(45);
  scan->setWindow(15);

  scan->setMaxResults(50);
  scan->clearResults();

  Serial.print("[CLIENT] Escaneando ");
  Serial.print(SCAN_MS);
  Serial.println(" ms...");

  // OJO: en tu caso, el tiempo es en MILISEGUNDOS
  NimBLEScanResults results = scan->getResults(SCAN_MS, false);

  int count = results.getCount();
  Serial.print("[CLIENT] Encontrados: ");
  Serial.println(count);

  NimBLEUUID targetSvc(SERVICE_UUID);

  for (int i = 0; i < count; i++) {
    const NimBLEAdvertisedDevice* adv = results.getDevice(i);
    if (!adv) continue;

    bool hasSvc = adv->isAdvertisingService(targetSvc);

    Serial.print(" - ");
    Serial.print(adv->getAddress().toString().c_str());
    Serial.print(" | name=");
    Serial.print(adv->haveName() ? adv->getName().c_str() : "(none)");
    Serial.print(" | hasSvc=");
    Serial.println(hasSvc ? "YES" : "NO");

    if (!hasSvc) continue;

    if (!gClient) {
      gClient = NimBLEDevice::createClient();
      gClient->setClientCallbacks(new ClientCB(), false);
    }

    Serial.println("[CLIENT] Conectando por dirección...");
    bool ok = gClient->connect(adv->getAddress());
    scan->clearResults();

    if (!ok) {
      Serial.println("[CLIENT] Falló connect()");
      return false;
    }

    Serial.println("[CLIENT] connect() OK");

    // === Acceso a característica segura para forzar el PIN ===
    NimBLERemoteService* svc = gClient->getService(NimBLEUUID(SERVICE_UUID));
    if (!svc) {
      Serial.println("[CLIENT] No pude obtener el servicio remoto.");
      return true;
    }

    NimBLERemoteCharacteristic* ch = svc->getCharacteristic(NimBLEUUID(CHAR_UUID));
    if (!ch) {
      Serial.println("[CLIENT] No pude obtener la característica remota.");
      return true;
    }

    Serial.println("[CLIENT] Leyendo característica segura (debe disparar PIN si no hay bond)...");
    std::string val = ch->readValue();
    Serial.print("[CLIENT] Valor leído: ");
    Serial.println(val.c_str());

    Serial.println("[CLIENT] Escribiendo en característica segura...");
    const char* msg = "PING";
    bool w = ch->writeValue((uint8_t*)msg, strlen(msg), true);
    Serial.print("[CLIENT] writeValue ok = ");
    Serial.println(w ? "true" : "false");

    return true;
  }

  scan->clearResults();
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println("[CLIENT] Iniciando NimBLE...");
  NimBLEDevice::init(CLIENT_NAME);
  NimBLEDevice::setPower(9);

#if RESET_BONDS_ON_BOOT
  Serial.println("[CLIENT] Borrando bonds...");
  NimBLEDevice::deleteAllBonds();
  delay(200);
#endif

  NimBLEDevice::setSecurityAuth(true, true, false);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_KEYBOARD_ONLY);

  Serial.println("[CLIENT] Listo");
}

void loop() {
  if (!gClient || !gClient->isConnected()) {
    scanAndConnect();
  }
  delay(2000);
}
