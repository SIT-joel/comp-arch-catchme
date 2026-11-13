// Queue selection facade: external W25Q when the shield is present,
// internal-flash queue otherwise (board 2, radio-only). Implemented in
// catch_me_app.ino after both queues exist.

#pragma once

#include "records.h"

bool q_external();                                    // W25Q shield present
bool q_push(const TelemetryRecord& rec);
uint16_t q_pending();
bool q_full();
bool q_peek(uint16_t offset, TelemetryRecord* out);
void q_acknowledge(uint16_t n);
