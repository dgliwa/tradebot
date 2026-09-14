# Step 5: Reliable automation

## Objective

Run the complete local shadow workflow after every completed trading session without duplicate activity or silent failure.

## Work

1. Define a single daily orchestration service:
   - Determine the effective market session
   - Ingest required sources
   - Validate coverage
   - Create strategy run
   - Compute recommendations
   - Generate or settle shadow orders at the appropriate time
   - Update marks and benchmark
   - Generate report
2. Add a market-calendar-aware foreground scheduler that can run under any host process supervisor.
3. Add a run lock and deterministic run key to prevent overlap and duplicates.
4. Persist structured stage status, duration, diagnostics, and retryability.
5. Retry transient source failures without retrying validation failures.
6. Add a health/status command and a nonzero process exit on incomplete runs.
7. Document backup, restore, clock/timezone, and operational recovery procedures.
8. Optionally notify the user when a run succeeds, fails, or needs approval.

## Tests

- Re-running a completed week is a no-op.
- A crash can resume without repeating committed stages.
- Holiday weeks choose the intended session.
- Concurrent invocations cannot create duplicate work.
- Failed ingestion prevents downstream recommendations and orders.
- Scheduler tests use a controlled clock.

## Suggested commits

1. `feat: orchestrate the daily shadow pipeline`
2. `feat: make daily runs resumable and idempotent`
3. `feat: schedule market-calendar-aware runs`
4. `docs: add shadow operations runbook`

## Exit criteria

The service can complete repeated daily local-shadow cycles unattended with no duplicate orders, unexplained gaps, or manual database repair.

## Not included

Live money or automatic strategy tuning.
