#include <Arduino.h>
#include <NimBLEDevice.h>

// ========= CONFIG =========
static const char* CLIENT_NAME = "ESP32_B";

// Debe ser el mismo UUID 128-bit que tu SERVER
static const char* SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab";

// PIN del servidor (passkey)
static const uint32_t TARGET_PIN = 123456;

// Tiempo de escaneo en MILISEGUNDOS (3 segundos = 3000 ms)
static const uint32_t SCAN_TIME_MS = 3000;
// ==========================

class ClientCB : public NimBLEClientCallbacks {
  void onConnect(NimBLEClient* pClient) override {
    Serial.println("[CLIENT] Conectado -> iniciando seguridad (pairing)...");
    NimBLEDevice::startSecurity(pClient->getConnHandle());
  }

  void onDisconnect(NimBLEClient* pClient, int reason) override {
    Serial.print("[CLIENT] Desconectado. reason=");
    Serial.println(reason);
  }

  void onPassKeyEntry(NimBLEConnInfo& connInfo) override {
    Serial.printf("[CLIENT] Servidor pide PIN -> inyectando %06u\n", (unsigned)TARGET_PIN);
    NimBLEDevice::injectPassKey(connInfo, TARGET_PIN);
  }

  void onAuthenticationComplete(NimBLEConnInfo& connInfo) override {
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
  Serial.print(SCAN_TIME_MS);
  Serial.println(" ms...");

  // Modo bloqueante: arranca y devuelve resultados al terminar
  NimBLEScanResults results = scan->getResults(SCAN_TIME_MS, false);

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

    if (hasSvc) {
      if (!gClient) {
        gClient = NimBLEDevice::createClient();
        gClient->setClientCallbacks(new ClientCB(), false);
      }

      Serial.println("[CLIENT] Conectando por dirección...");
      bool connected = gClient->connect(adv->getAddress());

      scan->clearResults();

      if (!connected) {
        Serial.println("[CLIENT] Falló connect()");
        return false;
      }

      Serial.println("[CLIENT] connect() OK");
      return true;
    }
  }

  scan->clearResults();
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println("[CLIENT] Iniciando NimBLE...");
  NimBLEDevice::init(CLIENT_NAME);

  // Si estás probando, puedes subir potencia:
  NimBLEDevice::setPower(9);

  // Si ya emparejaste antes y no te pide PIN en nuevas pruebas:
  // NimBLEDevice::deleteAllBonds();

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
