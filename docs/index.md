# Documentation

`scb-check` has one user-facing README and a small set of maintainer guides.

- [README](../README.md): installation, CLI usage, configuration, and source directives.
- [Architecture](architecture.md): metrics, pipeline shape, vocabulary, and scoring-sensitive invariants.
- [Tree walking](tree-walking.md): how source becomes IR, directives, semantic context, and rule inputs.
- [Development](development.md): current implementation status and the preferred approach for common changes.
- [TSX spike](spikes/2026-11-tsx-spike.md): measured parse, clone, callable, nesting and time results for the `ts` profile, and the clone-filter decision.
- [Calibration](calibration/2026-11-rule-calibration.md): how the TypeScript rules were measured, labelled and pruned, and the pre-registered separation test.
- [Baseline](baselines/2026-11-baseline.md): numbers for two agent-written applications, A and B.

Keep this folder focused on current behavior. Put usage details in the README when users need them, and link here for maintainer context.
