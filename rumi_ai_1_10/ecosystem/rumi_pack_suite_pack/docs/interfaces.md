# Interfaces

## Inputs

- `desired_workflow`: coding, research, office, browser, personal automation, release, security, or all.
- `installed_packs`: Setup pack ids already selected.
- `risk_tolerance`: low, medium, or high.
- `defaultspack_candidate`: Optional pack being evaluated for promotion.

## Outputs

- `bundle_recommendation`: Ordered setup pack ids and why they fit together.
- `overlap_explanation`: Which pack owns each surface.
- `promotion_review`: defaultspack candidate score, blockers, and required evidence.

## Required Secrets

None.
