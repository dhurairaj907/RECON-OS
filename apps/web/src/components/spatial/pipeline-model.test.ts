/**
 * RECON OS — pipeline-model regression test.
 *
 * Production incident regression: deriveCasePipeline() must never claim a
 * CREATE_PAYMENT_LINK action is "AWAITING APPROVAL" when no RecoveryAction
 * exists and the strategy was never eligible to become one (MANUAL_REVIEW).
 * The Policy Engine forces NEEDS_APPROVAL for ANY MANUAL_REVIEW strategy
 * (see apps/api/services/intelligence/policy_engine.py), independent of
 * whether an action is actually proposable — this test locks in that
 * `deriveCasePipeline` no longer conflates the two.
 *
 * No test runner is currently configured in this project (no jest/vitest —
 * see package.json). This file is written as a plain, dependency-free
 * script using only Node's built-in `assert` module and the TypeScript
 * compiler already present as a devDependency, so it can be run today
 * without adding any new dependency:
 *
 *   npx tsc src/components/spatial/pipeline-model.ts src/components/spatial/pipeline-model.test.ts \
 *     --outDir /tmp/pm-test --module commonjs --target es2020 --esModuleInterop --skipLibCheck
 *   node /tmp/pm-test/pipeline-model.test.js
 *
 * If a test runner (e.g. vitest) is added to this project later, this file
 * can be adapted to it directly — the assertions themselves don't depend
 * on any framework.
 */

import assert from "node:assert/strict";
import { deriveCasePipeline, ELIGIBLE_STRATEGIES } from "./pipeline-model";
import type { IntelligenceEnvelope } from "@/lib/types";

function baseEnv(overrides: Partial<IntelligenceEnvelope>): IntelligenceEnvelope {
  return {
    case_id: "case-1",
    case_number: "RC-TEST",
    analyzed: true,
    intelligence_enabled: true,
    status: "NEEDS_APPROVAL",
    ...overrides,
  } as IntelligenceEnvelope;
}

function actionStage(stages: ReturnType<typeof deriveCasePipeline>) {
  const stage = stages.find((s) => s.key === "action");
  assert.ok(stage, "expected an 'action' pipeline stage");
  return stage!;
}

// ---------------------------------------------------------------------------
// 1. MANUAL_REVIEW + NEEDS_APPROVAL + no RecoveryAction
//    -> must NEVER claim AWAITING APPROVAL / CREATE_PAYMENT_LINK.
// ---------------------------------------------------------------------------
function test_manual_review_never_claims_payment_link_awaiting_approval() {
  assert.ok(
    !ELIGIBLE_STRATEGIES.includes("MANUAL_REVIEW"),
    "sanity check: MANUAL_REVIEW must not be in ELIGIBLE_STRATEGIES",
  );

  const env = baseEnv({
    strategy: {
      action: "MANUAL_REVIEW", params: {}, rationale: "test", confidence: 0.5,
      alternatives: [], provider: "DETERMINISTIC",
    },
    policy: {
      verdict: "NEEDS_APPROVAL", risk_level: "LOW", requires_human: true,
      reason: "test", evaluated_rules: [], violated_rules: [], allowed_actions: [],
      provider: "DETERMINISTIC",
    },
  });

  const stage = actionStage(deriveCasePipeline(env, null, "DETECTED"));

  assert.notEqual(stage.value, "AWAITING APPROVAL", "must not fabricate an awaiting-approval action");
  assert.notEqual(stage.sub, "CREATE_PAYMENT_LINK", "must not fabricate a CREATE_PAYMENT_LINK action");
  assert.equal(stage.value, "MANUAL REVIEW REQUIRED");
  assert.equal(stage.sub, "NO AUTOMATED ACTION");
  assert.equal(stage.status, "blocked");

  console.log("PASS: test_manual_review_never_claims_payment_link_awaiting_approval");
}

// ---------------------------------------------------------------------------
// 2. Eligible strategy (SEND_PAYMENT_LINK) + NEEDS_APPROVAL + no RecoveryAction
//    -> legitimate approval state must still render correctly (unchanged).
// ---------------------------------------------------------------------------
function test_eligible_strategy_needs_approval_still_renders_awaiting_approval() {
  assert.ok(
    ELIGIBLE_STRATEGIES.includes("SEND_PAYMENT_LINK"),
    "sanity check: SEND_PAYMENT_LINK must be in ELIGIBLE_STRATEGIES",
  );

  const env = baseEnv({
    strategy: {
      action: "SEND_PAYMENT_LINK", params: {}, rationale: "test", confidence: 0.7,
      alternatives: [], provider: "DETERMINISTIC",
    },
    policy: {
      // e.g. amount exceeds the auto-approval ceiling — a genuine
      // high-value hold on an otherwise fully actionable strategy.
      verdict: "NEEDS_APPROVAL", risk_level: "MEDIUM", requires_human: true,
      reason: "test", evaluated_rules: [], violated_rules: [], allowed_actions: [],
      provider: "DETERMINISTIC",
    },
  });

  const stage = actionStage(deriveCasePipeline(env, null, "DETECTED"));

  assert.equal(stage.value, "AWAITING APPROVAL");
  assert.equal(stage.sub, "CREATE_PAYMENT_LINK");
  assert.equal(stage.status, "blocked");

  console.log("PASS: test_eligible_strategy_needs_approval_still_renders_awaiting_approval");
}

// ---------------------------------------------------------------------------
// 3. REJECTED verdict is untouched by this fix, regardless of strategy.
// ---------------------------------------------------------------------------
function test_rejected_verdict_unaffected() {
  const env = baseEnv({
    strategy: {
      action: "MANUAL_REVIEW", params: {}, rationale: "test", confidence: 0.5,
      alternatives: [], provider: "DETERMINISTIC",
    },
    policy: {
      verdict: "REJECTED", risk_level: "HIGH", requires_human: true,
      reason: "test", evaluated_rules: [], violated_rules: [], allowed_actions: [],
      provider: "DETERMINISTIC",
    },
  });

  const stage = actionStage(deriveCasePipeline(env, null, "DETECTED"));
  assert.equal(stage.value, "NO ACTION");
  assert.equal(stage.status, "rejected");

  console.log("PASS: test_rejected_verdict_unaffected");
}

test_manual_review_never_claims_payment_link_awaiting_approval();
test_eligible_strategy_needs_approval_still_renders_awaiting_approval();
test_rejected_verdict_unaffected();
console.log("\nAll pipeline-model regression tests passed.");
