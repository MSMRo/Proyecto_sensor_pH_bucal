#include <bluefruit.h>

// Objetivo: conexión básica al servidor ESP32_A (UUID + passkey 123456)

static const char* CLIENT_NAME  = "XIAO_TEST";
static const uint32_t PASSKEY   = 123456;
static const char* SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab";
static const char* CHAR_UUID    = "abcdefab-1234-5678-1234-abcdefabcdef";
static const char* TARGET_NAME  = "ESP32_A";
static const uint32_t SEND_MS   = 1000;   // periodo de envío
static const bool     USE_WRITE_RESP = true; // usar write con response para evitar fragmentación

static const uint8_t  ADC_PIN   = A0;     // entrada analógica
static const float    VREF      = 3.3f;
static const float    ADC_RES   = 4095.0f;
static const float    DIVISOR   = 1.0f;

BLEClientService        gService(SERVICE_UUID);
BLEClientCharacteristic gChar(CHAR_UUID);

uint16_t gConnHandle = BLE_CONN_HANDLE_INVALID;
bool     gReadyToWrite = false;
uint32_t gLastSendMs   = 0;

// Imprime la MAC del anuncio
void printAddr(const ble_gap_addr_t& addr) {
  for (int i = 5; i >= 0; --i) {
    if (addr.addr[i] < 16) Serial.print("0");
    Serial.print(addr.addr[i], HEX);
    if (i) Serial.print(":");
  }
}

// Scanner: muestra todo y conecta al ver el servicio
void scan_callback(ble_gap_evt_adv_report_t* report) {
  Serial.print("[SCAN] ");
  printAddr(report->peer_addr);
  Serial.print(" rssi=");
  Serial.println(report->rssi);

  // Leer nombre si viene en ADV/ScanResp
  char name[32] = {0};
  uint8_t len = Bluefruit.Scanner.parseReportByType(report, BLE_GAP_AD_TYPE_COMPLETE_LOCAL_NAME,
                                                    (uint8_t*)name, sizeof(name) - 1);
  if (len == 0) {
    len = Bluefruit.Scanner.parseReportByType(report, BLE_GAP_AD_TYPE_SHORT_LOCAL_NAME,
                                              (uint8_t*)name, sizeof(name) - 1);
  }
  if (len) {
    name[len] = 0;
    Serial.print("   name=");
    Serial.println(name);
  }

  bool matchService = Bluefruit.Scanner.checkReportForUuid(report, BLEUuid(SERVICE_UUID));
  bool matchName = len && strcmp(name, TARGET_NAME) == 0;

  if (matchService || matchName) {
    Serial.println("[CLIENT] Target visto -> conectando");
    Bluefruit.Central.connect(report);
    return;
  }

  Bluefruit.Scanner.resume();
}

void connect_callback(uint16_t conn_handle) {
  Serial.println("[CLIENT] Conectado, descubriendo servicio/char...");
  gConnHandle = conn_handle;
  gReadyToWrite = false;

  if (!gService.discover(conn_handle) || !gChar.discover()) {
    Serial.println("[CLIENT] Servicio/char no encontrados, desconecto");
    BLEConnection* c = Bluefruit.Connection(conn_handle);
    if (c) c->disconnect();
    return;
  }

  // Si no hay bond previo, pedir pairing
  BLEConnection* c = Bluefruit.Connection(conn_handle);
  if (c && !c->bonded()) c->requestPairing();
}

void disconnect_callback(uint16_t, uint8_t reason) {
  Serial.print("[CLIENT] Desconectado reason=0x");
  Serial.println(reason, HEX);
  gConnHandle = BLE_CONN_HANDLE_INVALID;
  gReadyToWrite = false;
}

// Servidor muestra PIN; el cliente responde con el fijo
void passkey_request_callback(uint16_t conn_handle, uint8_t passkey[6]) {
  uint32_t pin = PASSKEY;
  for (int i = 5; i >= 0; --i) {
    passkey[i] = '0' + (pin % 10);
    pin /= 10;
  }
  Serial.println("[CLIENT] Passkey solicitado -> enviado 123456");
}

void pairing_complete_callback(uint16_t, uint8_t status) {
  Serial.print("[CLIENT] Pairing status=0x");
  Serial.println(status, HEX);
}

void secured_callback(uint16_t conn_handle) {
  if (conn_handle != gConnHandle) return;
  gReadyToWrite = true;
  Serial.println("[CLIENT] Enlace seguro listo");
}

void setup() {
  Serial.begin(115200);
  // No bloquear esperando consola: permite arrancar sin monitor USB
  delay(50);

  Serial.println("[CLIENT] Init Bluefruit");
  Bluefruit.begin(0, 1);
  Bluefruit.setName(CLIENT_NAME);
  Bluefruit.setTxPower(8);

  gService.begin();
  gChar.begin();

  Bluefruit.Security.setMITM(true);
  Bluefruit.Security.setIOCaps(false, false, true); // solo teclado (enviamos passkey)
  Bluefruit.Security.setPairPasskeyRequestCallback(passkey_request_callback);
  Bluefruit.Security.setPairCompleteCallback(pairing_complete_callback);
  Bluefruit.Security.setSecuredCallback(secured_callback);

  Bluefruit.Central.setConnectCallback(connect_callback);
  Bluefruit.Central.setDisconnectCallback(disconnect_callback);

  Bluefruit.Scanner.setRxCallback(scan_callback);
  // Sin filtro: algunos anuncios ponen el UUID solo en Scan Response
  // Bluefruit.Scanner.filterUuid(BLEUuid(SERVICE_UUID));
  Bluefruit.Scanner.restartOnDisconnect(true);
  Bluefruit.Scanner.setInterval(160, 80); // 100 ms / 50 ms
  Bluefruit.Scanner.useActiveScan(true);
  Bluefruit.Scanner.start(0);
}

void loop() {
  if (gConnHandle == BLE_CONN_HANDLE_INVALID) {
    delay(100);
    return;
  }

  if (!gReadyToWrite) {
    delay(100);
    return;
  }

  if (millis() - gLastSendMs >= SEND_MS) {
    int raw = analogRead(ADC_PIN);

    //float voltage = (raw * VREF) / ADC_RES / DIVISOR;
    //float phValue = 7.0f + ((2.506f - voltage) / 0.152f);

    //char msg[48];
    //snprintf(msg, sizeof(msg), "ADC:%d Voltage:%.3fV pH:%.2f", raw, voltage, phValue);

    //Serial.print("[CLIENT] ");
    //Serial.println(msg);

    // USANDO JSON
    char msg[24];
    int n = snprintf(msg, sizeof(msg), "{\"adc\":%d}\n", raw);

    Serial.print("[CLIENT] ");
    Serial.print(msg);

    uint16_t written = USE_WRITE_RESP
        ? gChar.write_resp((const uint8_t*)msg, n)
        : gChar.write((const uint8_t*)msg, n);

    Serial.print("[CLIENT] write bytes=");
    Serial.println(written);

    gLastSendMs = millis();
  }
}
