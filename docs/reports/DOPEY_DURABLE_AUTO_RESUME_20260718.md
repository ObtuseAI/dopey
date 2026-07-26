# DOPEY Durable Auto-Resume Verification

Date: 2026-07-18  
Repository: `C:\Users\CH\dopey`  
Scope: Windows Task Scheduler durability for paper-only research, scanning, validation, and evolutionary improvement  
Live authority: blocked

## Outcome

DOPEY's existing scheduled research stack now has a repository-owned, idempotent durability policy. The active tasks use the trusted hidden Windows Script Host launcher, run as the current operator with limited privilege, store no credentials, resume missed work after logon, continue on battery, wake the computer from sleep when Windows permits, prevent duplicate instances, and retry failures three times at five-minute intervals.

The post-installation acceleration cycle started automatically at `2026-07-18T20:05:01-05:00`, completed with Task Scheduler result `0`, returned to `Ready`, and scheduled its next cycle for `2026-07-18T20:20:00-05:00`.

## Installed active tasks

| Task | Calendar | Durable state |
|---|---|---|
| `DOPEY_AccelerationCycle` | Every 15 minutes plus operator logon after 45 seconds | Enabled; post-repair result `0` |
| `DOPEY_DailyRitual` | Monday-Friday at 16:45 local | Enabled; start when available |
| `DOPEY_MondayPreflight` | Monday at 08:30 local | Enabled; next scheduled 2026-07-20 |
| `DOPEY_Nightly` | Daily at 02:00 local | Enabled; next scheduled 2026-07-19 |
| `DOPEY_WeekendSoak` | Saturday at 10:00 local | Enabled; last result `0` |

`DOPEY_Intraday` remains intentionally disabled. The 15-minute acceleration cycle owns the `intraday_watch` lane during regular market hours, so enabling the legacy task would duplicate scans rather than improve durability.

## Durable settings

- `StartWhenAvailable = true`
- `WakeToRun = true`
- Starts are allowed on battery.
- Running work is not stopped on transition to battery.
- `MultipleInstances = IgnoreNew`
- `RestartCount = 3`
- `RestartInterval = PT5M`
- Execution time limit is eight hours.
- Acceleration receives an explicit current-operator logon trigger with a 45-second delay.
- Calendar triggers and exact hidden launcher actions are preserved.
- Principal remains current operator, interactive logon, limited privilege.

Because no credentials are stored, auto-resume occurs after the operator signs in to Windows. It does not attempt unattended pre-logon network access.

## Control-plane verification

- Schedule state: `available`
- Active symbol count: `200`
- Readiness: `not_action_ready`
- Paper only: `true`
- Live blocked: `true`
- Broker lanes present: `false`
- Due lanes at verification: `news_intake`, `cross_asset_intake`, `intelligence_discovery_research`, `intelligence_evidence_evaluation`

The durable scheduler does not lower evidence thresholds or change research readiness.

## Artifacts and reproduction

- Installer: `operator_tools\install_durable_research_schedule.ps1`
- Compatible acceleration installer: `operator_tools\install_acceleration_schedule.ps1`
- Verification artifact: `artifacts\dopey\scheduler\durable_schedule_installation.json`
- Hidden launcher: `operator_tools\run_scheduled_hidden.vbs`
- Launcher SHA-256: `bfffc586bc1b12ca6d332d88a742f9ca5f82e97b2d62e8176f6107c06bba44f7`

Run from an interactive PowerShell session as the `CH` operator:

```powershell
Set-Location C:\Users\CH\dopey
.\operator_tools\install_durable_research_schedule.ps1
```

The installer verifies every task action and principal against a strict allowlist before changing settings. It stops on any unknown action, principal, privilege level, missing task, or failed postcondition.

## Constitutional boundary

- No broker connection.
- No credentials stored.
- No order or cancellation tools.
- No live sizing or execution authority.
- Research and evolutionary lanes remain paper/shadow only.
- `not_action_ready` remains authoritative.
