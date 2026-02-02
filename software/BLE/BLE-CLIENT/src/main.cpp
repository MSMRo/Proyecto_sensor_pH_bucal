#include <Arduino.h>
#include <NimBLEDevice.h>

// ======== CONFIG ========
static const char* CLIENT_NAME  = "ESP32_B";
static const uint32_t PASSKEY   = 123456;

static const char* SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab";
static const char* CHAR_UUID    = "abcdefab-1234-5678-1234-abcdefabcdef";

static const uint32_t SCAN_MS   = 3000;

static const uint8_t  ADC_PIN   = 34;      // GPIO34 (solo entrada)
static const float    VREF      = 3.3f;    // Voltaje de referencia esperado
static const float    ADC_RES   = 4095.0f; // ESP32 ADC 12 bits (0–4095)
static const float    DIVISOR   = 1.0f;    // Ajusta si usas divisor de tensión
static const uint32_t SEND_MS   = 1000;    // Periodo de envío en ms

// 1 = borra bonds (solo prueba), 0 = normal
#define RESET_BONDS_ON_BOOT 0
// ========================

static NimBLEClient* gClient = nullptr;
static bool gHelloSent = false;
static uint32_t gLastSendMs = 0;

class ClientCB : public NimBLEClientCallbacks {
  void onConnect(NimBLEClient*) override {
    Serial.println("[CLIENT] Conectado (esperando seguridad)...");
    gHelloSent = false;
    // IMPORTANTE: deja que el SERVER inicie la seguridad.
    // (evita carreras/dobles startSecurity)
  }

  void onDisconnect(NimBLEClient*, int reason) override {
    Serial.print("[CLIENT] Desconectado reason=");
    Serial.println(reason);
    gHelloSent = false;
  }

  void onPassKeyEntry(NimBLEConnInfo& ci) override {
    Serial.printf("[CLIENT] Servidor pide PIN -> inyectando %06u\n", (unsigned)PASSKEY);
    NimBLEDevice::injectPassKey(ci, PASSKEY);
  }

  void onAuthenticationComplete(NimBLEConnInfo&) override {
    Serial.println("[CLIENT] Pairing/Auth terminado");
  }
};

bool sendPhSample() {
  if (!gClient || !gClient->isConnected()) return false;

  NimBLERemoteService* svc = gClient->getService(NimBLEUUID(SERVICE_UUID));
  if (!svc) { gClient->disconnect(); return false; }

  NimBLERemoteCharacteristic* ch = svc->getCharacteristic(NimBLEUUID(CHAR_UUID));
  if (!ch) { gClient->disconnect(); return false; }

  int raw = analogRead(ADC_PIN);                // 0–4095
  float voltage = (raw * VREF) / ADC_RES / DIVISOR;
  float phValue = 7.0f + ((2.506f - voltage) / 0.152f); // fórmula del ejemplo (Xiao 3.3 V)

  char msg[96];
  snprintf(msg, sizeof(msg),
           "ADC:%d Voltage:%.3fV pH:%.2f", raw, voltage, phValue);

  Serial.print("[CLIENT] ");
  Serial.println(msg);

  bool ok = ch->writeValue((uint8_t*)msg, strlen(msg), true); // write with response
  if (ok) gLastSendMs = millis();
  return ok;
}

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
    return true;
  }

  scan->clearResults();
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println("[CLIENT] Init NimBLE");
  NimBLEDevice::init(CLIENT_NAME);
  NimBLEDevice::setPower(9);

#if RESET_BONDS_ON_BOOT
  Serial.println("[CLIENT] Borrando bonds...");
  NimBLEDevice::deleteAllBonds();
  delay(200);
#endif

  analogReadResolution(12);
  analogSetPinAttenuation(ADC_PIN, ADC_11db); // rango ~0–3.3 V
  NimBLEDevice::setSecurityAuth(true, true, false);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_KEYBOARD_ONLY);

  Serial.println("[CLIENT] Listo");
}

void loop() {
  if (!gClient || !gClient->isConnected()) {
    scanAndConnect();
    delay(300);
    return;
  }

  // Primer envío verifica que ya se pueda escribir (enlace seguro/listo)
  if (!gHelloSent) {
    gHelloSent = sendPhSample();
    if (!gHelloSent) {
      Serial.println("[CLIENT] Aún no se puede escribir (esperando seguridad). Reintentando...");
    }
    delay(300);
    return;
  }

  // Envíos periódicos
  if (millis() - gLastSendMs >= SEND_MS) {
    sendPhSample();
  }

  delay(50);
}
