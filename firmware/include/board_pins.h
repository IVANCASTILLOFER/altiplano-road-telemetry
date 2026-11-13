// !!! UNVERIFIED !!!  Pin map for the M5Stack Unit C6L, transcribed from a retailer's product page.
// That page assigns GPIO20/GPIO21 to BOTH the SX1262 SPI bus and the OLED, and the radio reset /
// RF-switch lines may sit behind the PI4IOE5V6408 I/O expander. Check M5Stack's official schematic
// and Arduino examples before flashing, and fix this file. Nothing here has run on hardware.
#pragma once

#define LORA_SCK 20
#define LORA_MISO 22
#define LORA_MOSI 21
#define LORA_CS 23
#define LORA_BUSY 19
#define LORA_DIO1 7        // "IRQ" on the product page
#define LORA_RST -1        // TODO: unknown (maybe via the I/O expander)
#define LORA_TCXO_V 0.0f   // TODO: depends on the module; 0 = no TCXO

// Grove port (HY2.0-4P): GPIO4 / GPIO5. Which one is SDA vs SCL: TODO confirm.
#define I2C_SDA 5
#define I2C_SCL 4

// Radio settings. Keep in sync with the gateway and with the link-budget scenario (SF10, BW125).
#define LORA_FREQ_MHZ 915.0f   // verify the allowed band/power for your country before transmitting
#define LORA_BW_KHZ 125.0f
#define LORA_SF 10
#define LORA_CR 5              // 4/5
#define LORA_SYNC_WORD 0x12    // private network
#define LORA_TX_DBM 20
