// Over-the-air packet encoder: byte-for-byte the same layout as src/roadtel/packet.py.
// Frozen test vector (see tests/test_packet.py::test_known_vector):
//   Reading{node=1, seq=2, air=+1.00C, rh=50.00%, surf=-1.00C, batt=3900mV, flags=0}
//   -> 1001000200641388ff9c0f3c8ad8
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace roadtel {

constexpr uint8_t VERSION = 1;
constexpr size_t PACKET_LEN = 14;
constexpr uint8_t FLAG_SURFACE_FAULT = 0x1;
constexpr uint8_t FLAG_LOW_BATTERY = 0x2;

struct Reading {
  uint8_t node_id;
  uint16_t seq;
  int16_t air_c100;      // centi-degC
  uint16_t rh_c100;      // centi-percent
  int16_t surface_c100;  // centi-degC
  uint16_t battery_mv;
  uint8_t flags;
};

// CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF. crc16("123456789") == 0x29B1
inline uint16_t crc16(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}

inline void put16(uint8_t *p, uint16_t v) {
  p[0] = (uint8_t)(v >> 8);
  p[1] = (uint8_t)(v & 0xFF);
}

inline void encode(const Reading &r, uint8_t out[PACKET_LEN]) {
  out[0] = (uint8_t)((VERSION << 4) | (r.flags & 0x0F));
  out[1] = r.node_id;
  put16(out + 2, r.seq);
  put16(out + 4, (uint16_t)r.air_c100);
  put16(out + 6, r.rh_c100);
  put16(out + 8, (uint16_t)r.surface_c100);
  put16(out + 10, r.battery_mv);
  put16(out + 12, crc16(out, 12));
}

}  // namespace roadtel
