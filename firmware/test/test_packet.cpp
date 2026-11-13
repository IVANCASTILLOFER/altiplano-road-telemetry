// Host-side check that the firmware encoder matches the Python wire format.
//   docker run --rm -v "$PWD/firmware":/fw -w /fw gcc:13 sh -c "g++ -std=c++11 -Iinclude test/test_packet.cpp -o /tmp/t && /tmp/t"
#include <stdio.h>
#include <string.h>

#include "packet.h"

int main() {
  const uint8_t check[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  if (roadtel::crc16(check, sizeof check) != 0x29B1) {
    puts("FAIL: crc16 check value");
    return 1;
  }
  roadtel::Reading r{1, 2, 100, 5000, -100, 3900, 0};
  uint8_t out[roadtel::PACKET_LEN];
  roadtel::encode(r, out);
  const uint8_t expected[] = {0x10, 0x01, 0x00, 0x02, 0x00, 0x64, 0x13, 0x88, 0xff, 0x9c, 0x0f, 0x3c, 0x8a, 0xd8};
  if (memcmp(out, expected, sizeof expected) != 0) {
    puts("FAIL: known vector");
    return 1;
  }
  puts("OK");
  return 0;
}
