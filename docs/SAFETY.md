# Safety Boundaries

## Current Safety Model

This platform is currently constrained to:

- research and validation
- paper trading simulation
- live-safe signal generation

## Explicit Non-Goals (Current Phase)

- No live broker order placement
- No order modification/cancellation workflows in production accounts
- No unattended production trading runtime

## Execution Interface Status

- `src/execution/execution_interface.py` is placeholder-only.
- It exists to preserve clean architecture for a future live execution phase.
- It does not submit broker orders in current runtime paths.

## Operational Guardrails

- Paper trading is explicit opt-in (`--paper-trading`).
- Live-safe pipeline is explicit opt-in (`--live-signals`) and supports safe single-run mode.
- Realtime engine defaults are OFF unless explicitly enabled.
- Test suite enforces non-execution behavior for placeholder/live-safe paths.
- Runtime mode policies are centralized in `src/runtime/run_profiles.py`.
- Shared safety enforcement is centralized in `src/runtime/safety_guards.py`.
- Shared runner validation is centralized in `src/runtime/runner_validation.py`.
- Runner artifacts include `run_manifest.json` for mode/provider/output traceability.

## Documentation Integrity

When adding capabilities, update this file and README to avoid overstating live-trading readiness.
