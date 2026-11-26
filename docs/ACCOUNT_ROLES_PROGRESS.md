# Account roles: first compatible increment

This is not the complete account/permission specification. Do not deploy as a completed RBAC rollout.

Implemented:
- additive migration 0049: role references, individual overrides, account status, session IDs, registration switch and bounded administrative event records. Existing users, password verifiers, grants, ownership and quotas remain in place.
- owner-protected management of roles, accounts, registration, sessions and password reset; explicit result grants remain compatible.
- independently enforced permissions for published result listing/detail, result photos/videos and ZIP downloads. Scope levels include legacy explicit grants to avoid changing existing access.
- management UI and personal quota view reuse existing storage accounting.

Security boundary: other working and administrative APIs still use their previous owner-only checks. The seeded administrator and employee roles cover published results only; there is no delegated administration, own-batch creation/processing, or cross-owner mutation yet. No account deletion or file transfer endpoint is enabled. Storage paths embed ownership; transfer needs a separate transactional/filesystem-safe lifecycle, quota/reservation checks and recovery tests.

Validation: pure access-policy tests were executed locally against exact Git blobs. PostgreSQL integration and frontend compilation/browser tests require normal CI. No deployment or VM/load tests were run.
