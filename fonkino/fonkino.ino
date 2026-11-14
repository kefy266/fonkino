#include <SPI.h>
#include <MFRC522.h>

#define SS_PIN 10
#define RST_PIN 9

MFRC522 rfid(SS_PIN, RST_PIN);

unsigned long lastStatusMs = 0;
String lastUid = "";
unsigned long lastScanMs = 0;

bool isValidVersion(byte v) {
  return (v != 0x00 && v != 0xFF && v != 0xEE && v != 0xA8);
}

void initRfid() {
  SPI.begin();
  rfid.PCD_Init();
  delay(40);
  rfid.PCD_SetAntennaGain(rfid.RxGain_max);
  rfid.PCD_AntennaOn();
}

void printHexBuf(const byte* buf, byte len) {
  for (byte i = 0; i < len; i++) {
    if (buf[i] < 0x10) Serial.print('0');
    Serial.print(buf[i], HEX);
    if (i < len - 1) Serial.print(' ');
  }
}

void printAsciiSafe(const byte* buf, byte len) {
  for (byte i = 0; i < len; i++) {
    byte c = buf[i];
    if (c >= 32 && c <= 126 && c != '"' && c != '\\') {
      Serial.print((char)c);
    } else if (c >= 32 && c <= 126) {
      Serial.print('.');
    }
  }
}

const __FlashStringHelper* describeSak(byte sak) {
  switch (sak) {
    case 0x08: return F("NXP MIFARE Classic 1K (1024 Byte, 16 Sektor)");
    case 0x18: return F("NXP MIFARE Classic 4K (4096 Byte, 40 Sektor)");
    case 0x09: return F("NXP MIFARE Mini (320 Byte, 5 Sektor)");
    case 0x00: return F("MIFARE Ultralight / NTAG213/215/216 (NFC Etiket)");
    case 0x20: return F("ISO/IEC 14443-4 Smart Card (EMV Banka/Kredi Karti /DESFire)");
    case 0x28: return F("SmartMX Hibrit Cip: ISO/IEC 14443-4 (EMV Kredi Karti) + MIFARE 1K");
    case 0x38: return F("SmartMX Hibrit Cip: ISO/IEC 14443-4 (EMV) + MIFARE 4K");
    default:   return F("Ozel / Karma ISO14443A PICC Cip");
  }
}

void emitCardEvent(String uidStr, String typeName, byte sak) {
  uidStr.toUpperCase();
  Serial.print(F("RFID Okundu -> UID: "));
  Serial.print(uidStr);
  Serial.print(F(" ("));
  Serial.print(typeName);
  Serial.println(F(")"));

  Serial.print(F("{\"event\":\"card\",\"uid\":\""));
  Serial.print(uidStr);
  Serial.print(F("\",\"cardType\":\""));
  Serial.print(typeName);
  Serial.print(F("\",\"sak\":"));
  Serial.print(sak);
  Serial.println(F("}"));
}

void deepInspectCard(String uidStr, byte sak) {
  byte block0[18];
  byte block4[18];
  bool b0Ok = false;
  bool b4Ok = false;

  byte atsBuf[64];
  byte atsLen = 0;
  bool atsOk = false;

  byte emvBuf[64];
  byte emvLen = 0;
  bool emvOk = false;

  // 1) Eger kart ISO/IEC 14443-4 destekliyorsa (SAK 0x20, 0x28, 0x38 -> Kredi/Banka Karti)
  if (sak & 0x20) {
    // RATS (Request for Answer To Select): E0 50 + CRC_A
    byte ratsCmd[4] = {0xE0, 0x50, 0x00, 0x00};
    if (rfid.PCD_CalculateCRC(ratsCmd, 2, &ratsCmd[2]) == MFRC522::STATUS_OK) {
      atsLen = sizeof(atsBuf);
      if (rfid.PCD_TransceiveData(ratsCmd, 4, atsBuf, &atsLen, NULL, 0, true) == MFRC522::STATUS_OK && atsLen > 2) {
        atsOk = true;
        atsLen -= 2; // Son 2 byte CRC_A

        // EMV Contactless PPSE Sorgusu: SELECT "2PAY.SYS.DDF01"
        byte ppseCmd[23] = {
          0x02, // I-Block PCB
          0x00, 0xA4, 0x04, 0x00, 0x0E,
          '2','P','A','Y','.','S','Y','S','.','D','D','F','0','1',
          0x00,
          0x00, 0x00 // CRC_A
        };
        if (rfid.PCD_CalculateCRC(ppseCmd, 21, &ppseCmd[21]) == MFRC522::STATUS_OK) {
          emvLen = sizeof(emvBuf);
          if (rfid.PCD_TransceiveData(ppseCmd, 23, emvBuf, &emvLen, NULL, 0, true) == MFRC522::STATUS_OK && emvLen > 3) {
            emvOk = true;
            emvLen -= 2; // Son 2 byte CRC_A
          }
        }
      }
    }
  }

  // 2) Eger MIFARE Classic veya Ultralight ise Blok 0 ve Blok 4 oku
  if (sak == 0x00) {
    // Ultralight / NTAG: Sayfa 0..3 ve Sayfa 4..7
    byte sz = sizeof(block0);
    if (rfid.MIFARE_Read(0, block0, &sz) == MFRC522::STATUS_OK) b0Ok = true;
    sz = sizeof(block4);
    if (rfid.MIFARE_Read(4, block4, &sz) == MFRC522::STATUS_OK) b4Ok = true;
  } else if ((sak & 0x08) || (sak & 0x18)) {
    // Eger RATS gonderildiyse MIFARE auth icin karti yeniden sec
    if (sak & 0x20) {
      byte atqa[2];
      byte atqaSz = sizeof(atqa);
      rfid.PICC_HaltA();
      if (rfid.PICC_WakeupA(atqa, &atqaSz) == MFRC522::STATUS_OK) {
        rfid.PICC_ReadCardSerial();
      }
    }
    MFRC522::MIFARE_Key key;
    for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

    if (rfid.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, 3, &key, &(rfid.uid)) == MFRC522::STATUS_OK) {
      byte sz = sizeof(block0);
      if (rfid.MIFARE_Read(0, block0, &sz) == MFRC522::STATUS_OK) b0Ok = true;
    }
    if (rfid.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, 7, &key, &(rfid.uid)) == MFRC522::STATUS_OK) {
      byte sz = sizeof(block4);
      if (rfid.MIFARE_Read(4, block4, &sz) == MFRC522::STATUS_OK) b4Ok = true;
    }
  }

  Serial.print(F("{\"event\":\"inspect\",\"uid\":\""));
  Serial.print(uidStr);
  Serial.print(F("\",\"sak\":\"0x"));
  if (sak < 0x10) Serial.print('0');
  Serial.print(sak, HEX);
  Serial.print(F("\",\"uidSize\":"));
  Serial.print(rfid.uid.size);
  Serial.print(F(",\"chipArch\":\""));
  Serial.print(describeSak(sak));
  Serial.print(F("\",\"block0\":\""));
  if (b0Ok) printHexBuf(block0, 16);
  Serial.print(F("\",\"block4Hex\":\""));
  if (b4Ok) printHexBuf(block4, 16);
  Serial.print(F("\",\"block4Ascii\":\""));
  if (b4Ok) printAsciiSafe(block4, 16);
  Serial.print(F("\",\"atsHex\":\""));
  if (atsOk) printHexBuf(atsBuf, atsLen);
  Serial.print(F("\",\"emvHex\":\""));
  if (emvOk) printHexBuf(emvBuf, emvLen);
  Serial.print(F("\",\"emvAscii\":\""));
  if (emvOk) printAsciiSafe(emvBuf, emvLen);
  Serial.println(F("\"}"));
}

void sendStatusJson() {
  byte v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
  byte a = rfid.PCD_ReadRegister(MFRC522::TxControlReg);

  if (isValidVersion(v) && ((a & 0x03) != 0x03)) {
    initRfid();
    v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
    a = rfid.PCD_ReadRegister(MFRC522::TxControlReg);
  } else if (!isValidVersion(v)) {
    rfid.PCD_Init();
    rfid.PCD_SetAntennaGain(rfid.RxGain_max);
    rfid.PCD_AntennaOn();
    v = rfid.PCD_ReadRegister(MFRC522::VersionReg);
    a = rfid.PCD_ReadRegister(MFRC522::TxControlReg);
  }

  bool ok = isValidVersion(v);

  Serial.print(F("{\"event\":\"status\",\"version\":\"0x"));
  if (v < 0x10) Serial.print('0');
  Serial.print(v, HEX);
  Serial.print(F("\",\"antenna\":\"0x"));
  if (a < 0x10) Serial.print('0');
  Serial.print(a, HEX);
  Serial.print(F("\",\"ok\":"));
  Serial.print(ok ? F("true") : F("false"));
  Serial.print(F(",\"uptime\":"));
  Serial.print(millis() / 1000);
  Serial.println('}');
}

void setup() {
  Serial.begin(9600);
  delay(150);
  initRfid();
  Serial.println(F("RFID Okuyucu hazir. Kartinizi yaklastirin..."));
  sendStatusJson();
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "STATUS" || cmd == "JSON") {
      sendStatusJson();
    } else if (cmd == "INIT" || cmd == "RESET") {
      initRfid();
      sendStatusJson();
    } else if (cmd.startsWith("SIM:")) {
      String simUid = cmd.substring(4);
      simUid.trim();
      if (simUid.length() == 0) simUid = "A1:B2:C3:D4";
      emitCardEvent(simUid, "SIMULATED CARD", 8);
    }
  }

  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String uidStr = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
      uidStr += String(rfid.uid.uidByte[i], HEX);
      if (i < rfid.uid.size - 1) uidStr += ":";
    }
    uidStr.toUpperCase();

    byte sak = rfid.uid.sak;
    MFRC522::PICC_Type piccType = rfid.PICC_GetType(sak);
    String typeName = String(rfid.PICC_GetTypeName(piccType));
    if (sak == 0x28) typeName = "SmartMX EMV + MIFARE 1K";
    else if (sak == 0x20) typeName = "ISO 14443-4 Smart Card (EMV)";

    if (uidStr != lastUid || (millis() - lastScanMs > 900)) {
      lastUid = uidStr;
      lastScanMs = millis();
      emitCardEvent(uidStr, typeName, sak);
      deepInspectCard(uidStr, sak);
    }

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    delay(120);
  }

  if (millis() - lastStatusMs >= 2500) {
    lastStatusMs = millis();
    sendStatusJson();
  }
}
