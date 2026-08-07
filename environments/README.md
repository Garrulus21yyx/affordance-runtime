# Runtime Environments

These assets are black-box systems used to exercise observation, grounding,
routing, execution, and independent verification. They do not import Runtime
internals and do not define recovery or authorization policy.

- `smart_room/` exposes the same devices through a React DOM surface and live
  W3C WoT Thing Descriptions. A separate control plane injects deterministic
  transport, state, and DOM failures.
- `mock_web/` contains reset-by-reload shopping, email, and forum pages for
  deterministic multi-step browser tasks.

The assets originated in `A-Modular-Action-System-Architecture` and were moved
without its mutable CognitiveMap, ContinuousInteractionManager,
RecoveryCascade, or ledger authority.
