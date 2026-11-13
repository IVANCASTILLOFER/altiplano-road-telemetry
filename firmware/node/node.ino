// Road node: wake -> read SHT4x (air T/RH) + MLX90614 (road surface IR temp) -> one LoRa packet -> deep sleep.
// UNTESTED: not compiled, not run on hardware. See firmware/include/board_pins.h.
// Libraries: RadioLib, Adafruit SHT4x, Adafruit MLX90614.
#include <Adafruit_MLX90614.h>
#include <Adafruit_SHT4x.h>
#include <RadioLib.h>
#include <SPI.h>
#include <Wire.h>

#include "../include/board_pins.h"
#include "../include/packet.h"

#define NODE_ID 1
#define REPORT_INTERVAL_S 600

RTC_DATA_ATTR uint16_t seq = 0;  // survives deep sleep

SX1262 radio = new Module(LORA_CS, LORA_DIO1, LORA_RST, LORA_BUSY);
Adafruit_SHT4x sht4;
Adafruit_MLX90614 mlx;

void sleepNow() {
  esp_sleep_enable_timer_wakeup((uint64_t)REPORT_INTERVAL_S * 1000000ULL);
  esp_deep_sleep_start();
}

void setup() {
  Wire.begin(I2C_SDA, I2C_SCL);
  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_CS);

  roadtel::Reading r{};
  r.node_id = NODE_ID;
  r.seq = seq++;
  r.battery_mv = 0;  // TODO: needs a voltage divider/ADC or a fuel gauge on the real board

  sensors_event_t hum, temp;
  if (sht4.begin()) {
    sht4.getEvent(&hum, &temp);
    r.air_c100 = (int16_t)lroundf(temp.temperature * 100.0f);
    r.rh_c100 = (uint16_t)lroundf(constrain(hum.relative_humidity, 0.0f, 100.0f) * 100.0f);
  }  // else: air values stay 0; a real build should flag this

  if (mlx.begin()) {
    r.surface_c100 = (int16_t)lroundf(mlx.readObjectTempC() * 100.0f);
  } else {
    r.flags |= roadtel::FLAG_SURFACE_FAULT;  // the gateway falls back to air T - 2 C
  }

  uint8_t buf[roadtel::PACKET_LEN];
  roadtel::encode(r, buf);

  if (radio.begin(LORA_FREQ_MHZ, LORA_BW_KHZ, LORA_SF, LORA_CR, LORA_SYNC_WORD, LORA_TX_DBM, 8, LORA_TCXO_V) ==
      RADIOLIB_ERR_NONE) {
    radio.transmit(buf, sizeof buf);
    radio.sleep();
  }
  sleepNow();
}

void loop() {}
