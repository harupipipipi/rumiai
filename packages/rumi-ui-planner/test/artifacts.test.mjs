import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";
import { findLeafBudgetViolations, splitUntilLeafBudget } from "../src/index.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

test("tracked Inbox blueprint has no over-budget leaves after planning", () => {
  const constitution = JSON.parse(fs.readFileSync(path.join(repoRoot, ".rumi/ui/constitution.json"), "utf8"));
  const blueprint = JSON.parse(fs.readFileSync(path.join(repoRoot, ".rumi/ui/blueprints/inbox.ui-tree.json"), "utf8"));
  const config = defineRumiFrontend(constitution);
  const planned = splitUntilLeafBudget(blueprint, config);

  assert.deepEqual(findLeafBudgetViolations(planned, config), []);
});
