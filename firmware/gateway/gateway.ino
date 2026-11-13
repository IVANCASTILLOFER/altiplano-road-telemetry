// LoRa -> USB-serial bridge. Prints one line per packet:  RX,<hex>,<rssi dBm>,<snr dB>
// The Python side (`roadtel serial --port COMx`) validates the CRC, de-duplicates and stores.
// UNTESTED: not compiled, not run on hardware. See firmware/include/board_pins.h.
#include <RadioLib.h>
#include <SPI.h>

#include "../include/board_pins.h"
#include "../include/packet.h"

SX1262 radio = new Module(LORA_CS, LORA_DIO1, LORA_RST, LORA_BUSY);

void setup() {
  Serial.begin(115200);
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);
  if (radio.begin(LORA_FREQ_MHZ, LORA_BW_KHZ, LORA_SF, LORA_CR, LORA_SYNC_WORD, LORA_TX_DBM, 8, LORA_TCXO_V) !=
      RADIOLIB_ERR_NONE) {
    Serial.println("ERR,radio init");
    while (true) delay(1000);
  }
}

void loop() {
  uint8_t buf[roadtel::PACKET_LEN];
  int state = radio.receive(buf, sizeof buf);  // blocks until a packet or timeout
  if (state == RADIOLIB_ERR_NONE) {
    Serial.print("RX,");
    for (size_t i = 0; i < radio.getPacketLength() && i < sizeof buf; i++) {
      if (buf[i] < 0x10) Serial.print('0');
      Serial.print(buf[i], HEX);
    }
    Serial.printf(",%.1f,%.1f\n", radio.getRSSI(), radio.getSNR());
  }
  // RADIOLIB_ERR_CRC_MISMATCH / RX_TIMEOUT are simply ignored; the LoRa CRC already dropped the frame.
}
