# uConsole Monitor

Local monitor agent and tray UI for this machine.

## Features

- Collects host metrics every 5 minutes by default
- Stores history in SQLite and writes `data/latest.json`
- Evaluates health as `ok`, `warn`, `error`, or `unknown`
- Shows tray icon state with AppIndicator when the GI namespace is installed
- Checks Mihomo proxy state through `mihomo.service` and the local controller API

## Run

```bash
python3 -m monitor.agent.main --once
python3 -m monitor.agent.main
python3 -m monitor.tray.main
```

## Config

Default config lives in [config.json](/home/sean/projects/uconsole_monitor/config.json). Edit the Mihomo controller settings, interfaces, thresholds, and paths there as needed.

## Tray dependency

The tray requires one of these GI namespaces:

- `AyatanaAppIndicator3`
- `AppIndicator3`

On Debian this is usually provided by packages such as `gir1.2-ayatanaappindicator3-0.1` or a compatible AppIndicator package.

## systemd

Templates are under [systemd/monitor-agent.service](/home/sean/projects/uconsole_monitor/systemd/monitor-agent.service) and [systemd/monitor-tray.service](/home/sean/projects/uconsole_monitor/systemd/monitor-tray.service).
