/**
 * RECON OS — communications-model regression test.
 *
 * Production UX fix: CommunicationsSection previously presented a manual
 * "Send" button as the primary CTA regardless of
 * AUTOMATIC_COMMUNICATIONS_ENABLED, misleadingly implying a human must
 * always send communications manually even when automation is on. This
 * locks in deriveCommunicationsPresentation()'s decision so that
 * regression can't silently come back.
 *
 * No test runner is configured in this project (no jest/vitest). Written
 * as a plain, dependency-free script using only Node's built-in `assert`
 * module — same pattern as pipeline-model.test.ts.
 */

import assert from "node:assert/strict";
import { deriveCommunicationsPresentation } from "./communications-model";

// ---------------------------------------------------------------------------
// 1. AUTOMATIC_COMMUNICATIONS_ENABLED=true -> automatic mode, manual Send
//    control demoted to a secondary fallback, never the primary CTA.
// ---------------------------------------------------------------------------
function test_automatic_enabled_demotes_manual_send_button() {
  const cp = deriveCommunicationsPresentation(true);
  assert.equal(cp.mode, "automatic");
  assert.equal(cp.showSendAsPrimary, false, "must not present Send as primary when automation is on");
  assert.match(cp.headline, /AUTOMATIC COMMUNICATIONS ENABLED/);
  assert.match(cp.detail, /automatically/i);
  console.log("PASS: test_automatic_enabled_demotes_manual_send_button");
}

// ---------------------------------------------------------------------------
// 2. AUTOMATIC_COMMUNICATIONS_ENABLED=false -> manual mode, Send remains
//    the primary control, and the UI must clearly say automation is off.
// ---------------------------------------------------------------------------
function test_automatic_disabled_keeps_manual_send_primary() {
  const cp = deriveCommunicationsPresentation(false);
  assert.equal(cp.mode, "manual");
  assert.equal(cp.showSendAsPrimary, true, "manual fallback must remain available and primary when automation is off");
  assert.match(cp.detail, /disabled/i);
  console.log("PASS: test_automatic_disabled_keeps_manual_send_primary");
}

// ---------------------------------------------------------------------------
// 3. The presentation function never claims delivery/status — it only
//    decides which control to show. Guards against a future edit
//    accidentally introducing a delivery/status claim into these strings.
// ---------------------------------------------------------------------------
function test_presentation_never_claims_delivery_or_real_mode() {
  for (const enabled of [true, false]) {
    const cp = deriveCommunicationsPresentation(enabled);
    const text = `${cp.headline} ${cp.detail}`.toLowerCase();
    assert.ok(!text.includes("delivered"), "must never claim DELIVERED");
    assert.ok(!text.includes("real delivery"), "must never claim real delivery");
    assert.ok(!text.includes("fake"), "must never mention fake mode (not observable from this data)");
  }
  console.log("PASS: test_presentation_never_claims_delivery_or_real_mode");
}

test_automatic_enabled_demotes_manual_send_button();
test_automatic_disabled_keeps_manual_send_primary();
test_presentation_never_claims_delivery_or_real_mode();
console.log("\nAll communications-model regression tests passed.");
