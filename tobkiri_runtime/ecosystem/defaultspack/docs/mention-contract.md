# Mention syntax contract

Tobkiri uses one product-level `@`-mention boundary contract for the main
composer, submit-time tool and skill resolution, Company, and Subagent Team.
The parser recognizes Unicode letters and numbers and intentionally permits a
mention directly after Japanese prose:

- `調べて@web_search` selects `web_search`.
- `調べて @web_search。` selects `web_search`; terminal punctuation is not
  part of the value.
- `お願い@pm` addresses `pm` in Company and Subagent Team surfaces.

The same contract keeps literal text inert:

- `mail@example.com` is an email address, not a product mention.
- `https://example.com/@name` keeps the URL path literal.
- `@@name` and an escaped `\@name` never resolve.

Tool, skill, file, service, and agent identifiers may contain `_`, `.`, `/`,
`:`, and `-`. A dotted value adjacent to Unicode prose resolves only when it is
known to the current catalog. This permits `確認@README.md` while preventing an
unknown domain-like suffix from being reinterpreted as a mention.

## Shared implementation boundary

The canonical backend parser is `domain/mention.py`. Frontend parsing lives in
`webapp/src/lib/mentionContract.ts` because browser textareas use UTF-16 cursor
offsets, but it follows the same fixtures. Candidate opening and submit-time
resolution must use this parser rather than local regular expressions.

The canonical regression matrix is
`tests/fixtures/mention_boundaries.json`. Its packaged frontend copy at
`webapp/src/lib/fixtures/mention_boundaries.json` must remain identical so the
same behavior is tested from both repository and packaged-source layouts.

This syntax contract selects semantic identifiers only. It does not grant
execution authority, bypass approval, change the active ProfileLock or
ResolvedPlan, or provide a host fallback for PackVM execution.
