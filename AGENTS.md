# HooApprove

This is an authorization boundary. Do not turn pending, failed or uncertain requests into approval.

- Human session credentials and service credentials have separate capabilities.
- Only the bound human may decide; only the originating service may consume.
- Keep all visible details and the execution payload in the immutable digest.
- Claim transactionally, once, immediately before the external side effect.
- Changed authoritative data requires a fresh request. Never reuse an old approval.
- An upstream timeout can mean success. Keep execution uncertain, do not auto-retry.
- Run service tests and native type/bundle checks for relevant changes.
- No plaintext credentials, tokens, real customer/order details or OTPs in Git or output.
- Demo mode is restricted to loopback and never represents a real upstream integration.
- Production deployment belongs in hooapps-gitops with an immutable image digest and managed secrets.
- Biometric checks in the app are a local convenience; they are not server-verifiable signatures.
