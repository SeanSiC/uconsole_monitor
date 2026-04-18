# uConsole Monitor

Local system monitor for this uConsole-class Linux machine.

It currently provides:

- a background collector agent
- a tray/AppIndicator UI
- color health status for key dimensions
- local snapshot and event storage
- Mihomo proxy status monitoring
- battery status monitoring

## Current Scope

This project monitors the current machine only.

The current implementation covers:

- CPU
- memory
- disk
- network
- required system services
- Mihomo proxy state
- battery state

Health is reduced to:

- green: normal
- yellow: warning
- red: error
- gray: stale or unknown

## Components

### `monitor-agent`

Background collector and evaluator.

Responsibilities:

- collect raw state
- evaluate dimension health
- write SQLite history
- write `data/latest.json`

### `monitor-tray`

Tray UI for compact local status viewing.

Responsibilities:

- read `data/latest.json`
- update tray icon color
- render summary window
- open second-level alerts/changes window

## Repository Structure

- [monitor/](/home/sean/projects/uconsole_monitor/monitor)
- [config.json](/home/sean/projects/uconsole_monitor/config.json)
- [systemd/](/home/sean/projects/uconsole_monitor/systemd)
- [CURRENT_ARCHITECTURE.md](/home/sean/projects/uconsole_monitor/CURRENT_ARCHITECTURE.md)

Key modules:

- [monitor/agent/main.py](/home/sean/projects/uconsole_monitor/monitor/agent/main.py)
- [monitor/collector/system.py](/home/sean/projects/uconsole_monitor/monitor/collector/system.py)
- [monitor/evaluator/health.py](/home/sean/projects/uconsole_monitor/monitor/evaluator/health.py)
- [monitor/storage/state.py](/home/sean/projects/uconsole_monitor/monitor/storage/state.py)
- [monitor/tray/main.py](/home/sean/projects/uconsole_monitor/monitor/tray/main.py)

## Run Locally

Run one collection cycle:

```bash
python3 -m monitor.agent.main --once
```

Run the collector loop:

```bash
python3 -m monitor.agent.main
```

Run the tray UI:

```bash
python3 -m monitor.tray.main
```

## Configuration

Main config file:

- [config.json](/home/sean/projects/uconsole_monitor/config.json)

Current config includes:

- collection interval
- storage paths
- primary interface
- required services
- Mihomo controller settings
- thresholds
- UI stale timeout

## Tray Requirements

The tray currently depends on a GI AppIndicator namespace:

- `AyatanaAppIndicator3`
- or `AppIndicator3`

On Debian, this is typically provided by:

- `gir1.2-ayatanaappindicator3-0.1`

## systemd

Included unit templates:

- [systemd/monitor-agent.service](/home/sean/projects/uconsole_monitor/systemd/monitor-agent.service)
- [systemd/monitor-tray.service](/home/sean/projects/uconsole_monitor/systemd/monitor-tray.service)

The intended deployment shape is:

- system service for the agent
- user service for the tray

## GitHub CI

This repository includes a minimal GitHub Actions workflow that currently checks:

- Python source compilation with `compileall`

Workflow file:

- [.github/workflows/ci.yml](/home/sean/projects/uconsole_monitor/.github/workflows/ci.yml)

## Architecture Notes

For current implementation details, design tradeoffs, desktop integration notes, and next-iteration guidance, see:

- [CURRENT_ARCHITECTURE.md](/home/sean/projects/uconsole_monitor/CURRENT_ARCHITECTURE.md)
