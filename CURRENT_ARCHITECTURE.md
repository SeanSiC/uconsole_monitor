# uConsole Monitor Current Architecture

## Overview

This project is a local monitoring system for the current machine.

It consists of two long-running parts:

- `monitor-agent`
  - Collects system state on a schedule
  - Evaluates health for each dimension
  - Stores snapshots and events
  - Writes the latest state to JSON for UI consumption
- `monitor-tray`
  - Runs as a tray/AppIndicator UI
  - Reads the latest state from disk
  - Renders the compact status window
  - Opens a second-level details window for alerts and recent changes

The current target machine is a Debian 13 ARM system with a Wayland `labwc` session and `wf-panel-pi`.

## Runtime Architecture

### Agent flow

The agent entry point is [monitor/agent/main.py](/home/sean/projects/uconsole_monitor/monitor/agent/main.py).

Per collection cycle it does:

1. Load config
2. Collect raw metrics with [monitor/collector/system.py](/home/sean/projects/uconsole_monitor/monitor/collector/system.py)
3. Build health states with [monitor/evaluator/health.py](/home/sean/projects/uconsole_monitor/monitor/evaluator/health.py)
4. Persist results with [monitor/storage/state.py](/home/sean/projects/uconsole_monitor/monitor/storage/state.py)
5. Write `data/latest.json`

The systemd service currently runs the agent continuously and sleeps between cycles.

### Tray flow

The tray entry point is [monitor/tray/main.py](/home/sean/projects/uconsole_monitor/monitor/tray/main.py).

It does not run collectors directly for normal refreshes.

It:

1. Reads `data/latest.json`
2. Updates the tray icon color
3. Shows the compact status window when clicked
4. Opens a details window for alerts and recent changes

The tray uses Ayatana AppIndicator on this machine.

Important interaction detail:

- the main status window can trigger a one-shot collection
- when the refresh action completes, the currently open window updates in place
- the user does not need to close and reopen the tray window to see fresh state

## Health Dimensions

The current health model exposes these dimensions:

- `cpu`
- `memory`
- `disk`
- `network`
- `services`
- `mihomo`
- `battery`

Each dimension produces:

- `status`
  - `ok`
  - `warn`
  - `error`
  - `unknown`
- `summary`
- `details`

Overall state is derived from key dimensions and written to the `overall` section of `latest.json`.

## Current Collectors

### System / CPU / Memory / Disk

Collected mainly from:

- `/proc`
- `/sys`
- `shutil.disk_usage`
- `systemctl`

Implemented in:

- [monitor/collector/system.py](/home/sean/projects/uconsole_monitor/monitor/collector/system.py)

### Network

Collected from:

- `/proc/net/dev`
- `/sys/class/net/*`
- `ip -json address show`

Primary interface is currently configured as `wlan0`.

### Services

Generic required service checks are done through:

- `systemctl show <unit>`

Current required services:

- `ssh.service`
- `NetworkManager.service`
- `wpa_supplicant.service`

### Mihomo

Hermes monitoring was removed and replaced with Mihomo monitoring.

The current Mihomo check combines:

- `mihomo.service` status from systemd
- local controller API on `127.0.0.1:9090`
- selected proxy group state
- provider node availability summary

Current data sources:

- `GET /version`
- `GET /configs`
- `GET /providers/proxies`
- `GET /proxies/Proxy`

Current config assumes:

- unit: `mihomo.service`
- controller: `http://127.0.0.1:9090`
- group: `Proxy`

### Battery

Battery collection currently prefers `UPower` and falls back to sysfs.

On this machine the battery is exposed as:

- `axp20x-battery`

Current battery fields include:

- percentage
- state
- AC/charging indicator
- health percentage
- current Wh
- full Wh
- voltage

## Storage

Implemented in [monitor/storage/state.py](/home/sean/projects/uconsole_monitor/monitor/storage/state.py).

### SQLite

Current DB path:

- [data/monitor.db](/home/sean/projects/uconsole_monitor/data/monitor.db)

Current tables:

- `snapshots`
- `dimension_states`
- `events`

### Latest state JSON

Current latest state path:

- [data/latest.json](/home/sean/projects/uconsole_monitor/data/latest.json)

The tray reads this file as its primary UI state source.

## Event Model

The project currently records events in `events`.

There are two kinds of event content in the DB today:

- old monitor-level warning/error events from earlier iterations
- newer dimension-level events used by the current details view

Recent changes shown in the tray details window are loaded from `events`, preferring dimension events.

Important note:

- event recording is functional, but still noisy for simple summary updates
- future cleanup should reduce low-signal `updated`/baseline entries if needed

## UI Structure

Implemented in [monitor/tray/main.py](/home/sean/projects/uconsole_monitor/monitor/tray/main.py).

### Tray icon

The tray icon uses icon names installed in the local icon theme:

- `uconsole-monitor-healthy`
- `uconsole-monitor-warning`
- `uconsole-monitor-error`
- `uconsole-monitor-stale`

Installed under:

- `~/.local/share/icons/hicolor/32x32/status`
- `~/.local/share/icons/hicolor/scalable/status`

### Main window

The main status window is intentionally compact and non-scrollable.

Current layout:

- top summary row
  - overall status icon
  - hostname
  - updated age
  - alert count summary
  - compact action buttons on the top-right
    - refresh icon button
    - details/warning icon button
- card grid
  - row 1: `CPU / Memory`
  - row 2: `Network / Mihomo`
  - row 3: `Disk / Battery`

Status display rules:

- dimension cards show only a color dot, not `OK/WARN/ERROR` text
- alert counts are shown at the top with colored numeric indicators
- the main window is intentionally constrained to fit the device screen without scrollbars
- long alert and change content is not shown inline on the main window

### Details window

The second-level details window contains:

- active alerts
- recent changes

This was introduced because long alert/change content overflowed the main window.

Current interaction rules:

- the main window shows only compact alert counts
- the details window is the place for full alert text and recent change history

## Config

Current main config file:

- [config.json](/home/sean/projects/uconsole_monitor/config.json)

Current config areas:

- collection interval
- DB/state paths
- primary network interface
- required services
- Mihomo monitoring settings
- thresholds
- UI stale timeout

Default values live in:

- [monitor/config/defaults.py](/home/sean/projects/uconsole_monitor/monitor/config/defaults.py)

## Systemd Integration

Current unit templates in repo:

- [systemd/monitor-agent.service](/home/sean/projects/uconsole_monitor/systemd/monitor-agent.service)
- [systemd/monitor-tray.service](/home/sean/projects/uconsole_monitor/systemd/monitor-tray.service)

Currently installed units on this machine:

- system service: `monitor-agent.service`
- user service: `monitor-tray.service`

## Desktop Integration Notes

This machine runs:

- `labwc`
- `wf-panel-pi`
- Wayland

The tray icon required extra integration work:

- ensuring `wf-panel-pi` acts as a `StatusNotifierHost`
- restoring panel startup in `~/.config/labwc/autostart`
- switching from raw icon paths to theme icon names for reliable display

Relevant file:

- [autostart](/home/sean/.config/labwc/autostart)

## Current Known Tradeoffs

- The `events` table contains historical noise from earlier iterations.
- The current Mihomo details payload stored in `latest.json` is verbose.
- The main window is optimized for compactness, not deep inspection.
- The details window is still text-heavy and could later become a richer structured view.
- The tray relies on the current desktop/session setup and AppIndicator support.

## Recommended Next Iteration Areas

### High value

- Reduce Mihomo detail payload stored in `latest.json`
- Make recent-change events less noisy
- Add a cleaner structured details window instead of raw text blocks

### Medium value

- Add explicit thresholds for Mihomo degradation
  - controller down
  - zero alive nodes
  - selected proxy unavailable
- Add retention / pruning for old SQLite snapshots and events
- Add tests for collectors and evaluator logic

### Optional

- Export a local HTTP status page
- Add notification hooks for severe state changes
- Add compact trend history for CPU, battery, and network

## File Map

- [monitor/agent/main.py](/home/sean/projects/uconsole_monitor/monitor/agent/main.py)
- [monitor/collector/system.py](/home/sean/projects/uconsole_monitor/monitor/collector/system.py)
- [monitor/evaluator/health.py](/home/sean/projects/uconsole_monitor/monitor/evaluator/health.py)
- [monitor/storage/state.py](/home/sean/projects/uconsole_monitor/monitor/storage/state.py)
- [monitor/tray/main.py](/home/sean/projects/uconsole_monitor/monitor/tray/main.py)
- [monitor/config/defaults.py](/home/sean/projects/uconsole_monitor/monitor/config/defaults.py)
- [config.json](/home/sean/projects/uconsole_monitor/config.json)
- [README.md](/home/sean/projects/uconsole_monitor/README.md)

## Current Status

At the time of writing, the current implementation supports:

- scheduled local collection
- SQLite persistence
- latest-state JSON export
- tray icon color state
- compact status window
- second-level alerts/changes view
- Mihomo proxy state monitoring
- battery state monitoring via UPower
- systemd-managed agent and tray services

This document should be updated whenever:

- a health dimension is added or removed
- tray interaction changes
- storage/event behavior changes
- deployment assumptions change
