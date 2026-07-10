import test from "node:test";
import assert from "node:assert/strict";

import {
  browserApprovalTokenizedPath,
  browserAuthorityApprovalPath,
} from "./authorityApprovalBrowserToken";

test("browser approval token helper tokenizes only root-relative same-origin paths without a browser origin", () => {
  assert.equal(
    browserApprovalTokenizedPath("/finger-recording?authority_approved=1", "tok/en"),
    "/finger-recording?authority_approved=1&browser_approval_token=tok%2Fen",
  );
  assert.equal(
    browserApprovalTokenizedPath("/finger-recording?browser_approval_token=existing", "tok/en"),
    "/finger-recording?browser_approval_token=existing",
  );
});

test("browser approval token helper never appends a credential to external or ambiguous destinations", () => {
  assert.equal(
    browserApprovalTokenizedPath("https://attacker.example/collect", "secret-token"),
    "https://attacker.example/collect",
  );
  assert.equal(
    browserApprovalTokenizedPath("//attacker.example/collect", "secret-token"),
    "//attacker.example/collect",
  );
  assert.equal(
    browserApprovalTokenizedPath("javascript:alert(1)", "secret-token"),
    "javascript:alert(1)",
  );
  assert.equal(
    browserApprovalTokenizedPath("finger-recording?authority_approved=1", "secret-token"),
    "finger-recording?authority_approved=1",
  );
});

test("browser approval path drops an external return target before serializing the approval URL", () => {
  assert.equal(
    browserAuthorityApprovalPath("auth-1", "tok-1", "https://attacker.example/after"),
    "/approval?request_id=auth-1&browser_approval_token=tok-1",
  );
  assert.equal(
    browserAuthorityApprovalPath("auth-1", "tok-1", "//attacker.example/after"),
    "/approval?request_id=auth-1&browser_approval_token=tok-1",
  );
  assert.equal(
    browserAuthorityApprovalPath("auth-1", "tok-1", "/ambient-debug?authority_approved=1"),
    "/approval?request_id=auth-1&browser_approval_token=tok-1&return_to=%2Fambient-debug%3Fauthority_approved%3D1",
  );
});
