from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from monitor.cli import build_common_parser
from monitor.config.loader import load_config
from monitor.storage.state import load_latest_state, load_recent_events


def load_indicator():
    for namespace in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(namespace, "0.1")
            return __import__(f"gi.repository.{namespace}", fromlist=[namespace])
        except (ImportError, ValueError):
            continue
    return None


def format_age(updated_at: str | None) -> str:
    if not updated_at:
        return "never"
    try:
        dt = datetime.fromisoformat(updated_at)
    except ValueError:
        return updated_at
    delta = datetime.now(dt.tzinfo) - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


class TrayApp:
    def __init__(self, config: dict):
        self.config = config
        self.indicator_module = load_indicator()
        if self.indicator_module is None:
            raise RuntimeError("AppIndicator library is not installed")
        self.icon_dir = Path(config["paths"]["icon_dir"])
        self.state_path = config["paths"]["latest_state"]
        self.db_path = config["paths"]["db"]
        self.stale_after = int(config["ui"]["stale_after_seconds"])
        self.details_window: Gtk.Window | None = None
        self.logs_window: Gtk.Window | None = None
        self.details_labels: dict[str, Gtk.Label] = {}
        self.logs_label: Gtk.Label | None = None
        self.details_button: Gtk.Button | None = None

        self.indicator = self.indicator_module.Indicator.new(
            "uconsole-monitor",
            "uconsole-monitor-stale",
            self.indicator_module.IndicatorCategory.SYSTEM_SERVICES,
        )
        self.indicator.set_status(self.indicator_module.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self._build_menu())

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        open_item = Gtk.MenuItem(label="Open Status")
        open_item.connect("activate", lambda *_: self.show_details())
        menu.append(open_item)

        refresh_item = Gtk.MenuItem(label="Refresh Now")
        refresh_item.connect("activate", lambda *_: self.run_agent_once())
        menu.append(refresh_item)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def run_agent_once(self) -> None:
        subprocess.Popen([sys.executable, "-m", "monitor.agent.main", "--once"])

    def build_details_window(self) -> Gtk.Window:
        window = Gtk.Window(title="uConsole Monitor")
        window.set_default_size(540, 330)
        window.connect("delete-event", self.on_delete_window)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_border_width(12)
        window.add(root)
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.pack_start(container, True, True, 0)

        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        container.pack_start(header_row, False, False, 0)

        header = Gtk.Label(xalign=0)
        header.set_selectable(True)
        header.set_line_wrap(True)
        header.set_use_markup(True)
        header.set_hexpand(True)
        header_row.pack_start(header, True, True, 0)
        self.details_labels["overall"] = header

        details_button = Gtk.Button(label="Details")
        details_button.connect("clicked", lambda *_: self.show_logs())
        header_row.pack_end(details_button, False, False, 0)
        self.details_button = details_button

        grid = Gtk.Grid()
        grid.set_column_spacing(14)
        grid.set_row_spacing(10)
        grid.set_column_homogeneous(True)
        container.pack_start(grid, True, True, 0)

        cards = [
            ("cpu", 0, 0),
            ("memory", 1, 0),
            ("network", 0, 1),
            ("mihomo", 1, 1),
            ("disk", 0, 2),
            ("battery", 1, 2),
        ]
        for key, col, row in cards:
            frame = Gtk.Frame()
            frame.set_shadow_type(Gtk.ShadowType.IN)
            frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            frame_box.set_border_width(10)
            frame.add(frame_box)

            label = Gtk.Label(xalign=0)
            label.set_selectable(True)
            label.set_line_wrap(True)
            label.set_use_markup(True)
            frame_box.pack_start(label, False, False, 0)
            self.details_labels[key] = label
            grid.attach(frame, col, row, 1, 1)

        button = Gtk.Button(label="Refresh")
        button.connect("clicked", lambda *_: self.run_agent_once())
        root.pack_end(button, False, False, 0)

        return window

    def build_logs_window(self) -> Gtk.Window:
        window = Gtk.Window(title="uConsole Monitor Details")
        window.set_default_size(620, 480)
        window.connect("delete-event", self.on_delete_window)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_border_width(12)
        window.add(root)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        root.pack_start(scroller, True, True, 0)

        label = Gtk.Label(xalign=0)
        label.set_selectable(True)
        label.set_line_wrap(True)
        label.set_use_markup(True)
        scroller.add(label)
        self.logs_label = label

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda *_: window.hide())
        root.pack_end(close_button, False, False, 0)

        return window

    def on_delete_window(self, window: Gtk.Window, *_args) -> bool:
        window.hide()
        return True

    def show_details(self) -> None:
        if self.details_window is None:
            self.details_window = self.build_details_window()
        self.update_from_state()
        self.details_window.show_all()
        self.details_window.present()

    def show_logs(self) -> None:
        if self.logs_window is None:
            self.logs_window = self.build_logs_window()
        self.update_from_state()
        self.logs_window.show_all()
        self.logs_window.present()

    def current_status(self, state: dict | None) -> str:
        if not state:
            return "stale"
        updated_at = state.get("updated_at")
        try:
            updated_dt = datetime.fromisoformat(updated_at)
        except (TypeError, ValueError):
            return "stale"
        age = (datetime.now(updated_dt.tzinfo) - updated_dt).total_seconds()
        if age > self.stale_after:
            return "stale"
        return state.get("overall", {}).get("status", "stale")

    def icon_name_for_status(self, status: str) -> str:
        mapping = {
            "ok": "uconsole-monitor-healthy",
            "warn": "uconsole-monitor-warning",
            "error": "uconsole-monitor-error",
            "unknown": "uconsole-monitor-stale",
            "stale": "uconsole-monitor-stale",
        }
        return mapping.get(status, "uconsole-monitor-stale")

    def update_from_state(self) -> bool:
        state = load_latest_state(self.state_path)
        status = self.current_status(state)
        self.indicator.set_icon_full(self.icon_name_for_status(status), status)
        self.indicator.set_title(f"uConsole Monitor ({status})")

        if self.details_window is None:
            return True

        if not state:
            self.details_labels["overall"].set_markup("<b>No state file yet.</b>")
            for key in ("cpu", "memory", "disk", "network", "mihomo", "battery"):
                self.details_labels[key].set_markup("")
            if self.logs_label:
                self.logs_label.set_markup("")
            return True

        overall = state.get("overall", {})
        host = state.get("host", {})
        warnings = state.get("warnings", [])
        errors = state.get("errors", [])
        alert_summary = self.alert_summary_markup(len(errors), len(warnings))
        self.details_labels["overall"].set_markup(
            f"<span size='large'><b>{self.status_badge(overall.get('status', 'unknown'), show_text=False)} uConsole Monitor</b></span>\n"
            f"<b>Host</b>: {GLib.markup_escape_text(host.get('hostname', 'unknown'))}    "
            f"<b>Updated</b>: {format_age(state.get('updated_at'))}\n"
            f"{alert_summary}"
        )
        order = ("cpu", "memory", "disk", "network", "mihomo", "battery")
        for key in order:
            dim = state.get("dimensions", {}).get(key, {})
            extra = self.extra_line(key, dim.get("details", {}))
            text = (
                f"{self.status_badge(dim.get('status', 'unknown'), show_text=False)} "
                f"<b>{key.upper()}</b>\n"
                f"{GLib.markup_escape_text(dim.get('summary', ''))}"
            )
            if extra:
                text += f"\n<small>{GLib.markup_escape_text(extra)}</small>"
            self.details_labels[key].set_markup(text)
        if self.logs_label:
            events = load_recent_events(self.db_path, limit=10)
            sections = []
            if errors or warnings:
                lines = []
                for item in errors[:10]:
                    lines.append(f"• ERROR: {item}")
                for item in warnings[:10]:
                    lines.append(f"• WARN: {item}")
                sections.append("<b>Alerts</b>\n" + GLib.markup_escape_text("\n".join(lines)))
            else:
                sections.append("<b>Alerts</b>\nNo active warnings or errors.")
            if events:
                lines = []
                for event in events:
                    timestamp = self.short_time(event["created_at"])
                    dimension = event["dimension_name"].upper()
                    severity = event["severity"].upper()
                    lines.append(f"{timestamp}  {dimension:<8} {severity:<5}  {event['message']}")
                sections.append("<b>Recent Changes</b>\n" + GLib.markup_escape_text("\n".join(lines)))
            else:
                sections.append("<b>Recent Changes</b>\nNo recent changes recorded.")
            self.logs_label.set_markup("\n\n".join(sections))
        return True

    def extra_line(self, key: str, details: dict) -> str:
        if key == "cpu":
            load1 = details.get("load_1")
            load5 = details.get("load_5")
            freq = details.get("freq_mhz")
            parts = []
            if load1 is not None:
                parts.append(f"load1 {load1:.2f}")
            if load5 is not None:
                parts.append(f"load5 {load5:.2f}")
            if freq is not None:
                parts.append(f"{freq:.0f} MHz")
            return " | ".join(parts)
        if key == "memory":
            available = details.get("available_bytes")
            swap_used = details.get("swap_used_bytes")
            parts = []
            if available is not None:
                parts.append(f"available {self.fmt_bytes(available)}")
            if swap_used is not None:
                parts.append(f"swap {self.fmt_bytes(swap_used)}")
            return " | ".join(parts)
        if key == "disk":
            mounts = details.get("mounts", [])
            return " | ".join(
                f"{mount.get('mountpoint')} free {self.fmt_bytes(int(mount.get('free_bytes', 0)))}"
                for mount in mounts[:2]
            )
        if key == "network":
            interfaces = details.get("interfaces", [])
            primary = interfaces[0] if interfaces else {}
            parts = []
            if primary.get("rx_bytes") is not None and primary.get("tx_bytes") is not None:
                parts.append(
                    f"rx {self.fmt_bytes(int(primary.get('rx_bytes', 0)))}"
                )
                parts.append(f"tx {self.fmt_bytes(int(primary.get('tx_bytes', 0)))}")
            if primary.get("mac"):
                parts.append(primary["mac"])
            return " | ".join(parts)
        if key == "mihomo":
            service = details.get("service", {})
            group = details.get("group", {})
            providers = details.get("providers", {})
            parts = []
            if service.get("active_state"):
                parts.append(f"{service.get('active_state')}/{service.get('sub_state')}")
            if group.get("current"):
                parts.append(f"group {group.get('current')}")
            if providers:
                alive = sum(item.get("alive", 0) for item in providers.values())
                total = sum(item.get("total", 0) for item in providers.values())
                parts.append(f"nodes {alive}/{total}")
            return " | ".join(parts)
        if key == "battery":
            parts = []
            if details.get("energy_wh") is not None and details.get("energy_full_wh") is not None:
                parts.append(f"{details['energy_wh']:.1f}/{details['energy_full_wh']:.1f} Wh")
            if details.get("voltage_v") is not None:
                parts.append(f"{details['voltage_v']:.2f} V")
            if details.get("health_pct") is not None:
                parts.append(f"health {details['health_pct']:.0f}%")
            return " | ".join(parts)
        return ""

    def fmt_bytes(self, num: int) -> str:
        units = ["B", "KiB", "MiB", "GiB", "TiB"]
        value = float(num)
        for unit in units:
            if value < 1024.0 or unit == units[-1]:
                return f"{value:.1f}{unit}"
            value /= 1024.0
        return f"{num}B"

    def status_badge(self, status: str, show_text: bool = True) -> str:
        color = {
            "ok": "#2e9f47",
            "warn": "#d6a600",
            "error": "#c73a35",
            "unknown": "#6f7782",
            "stale": "#6f7782",
        }.get(status, "#6f7782")
        if show_text:
            return f"<span foreground='{color}'>●</span> <span foreground='{color}'><b>{status.upper()}</b></span>"
        return f"<span foreground='{color}' size='large'>●</span>"

    def alert_summary_markup(self, error_count: int, warn_count: int) -> str:
        if error_count == 0 and warn_count == 0:
            return "<span foreground='#2e9f47'>●</span> No alerts"
        parts = []
        if error_count:
            parts.append(f"<span foreground='#c73a35'><b>● {error_count}</b></span>")
        if warn_count:
            parts.append(f"<span foreground='#d6a600'><b>● {warn_count}</b></span>")
        return "  ".join(parts)

    def short_time(self, iso_text: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_text)
            return dt.strftime("%H:%M")
        except ValueError:
            return iso_text[:5]


def main() -> int:
    parser = build_common_parser("uConsole monitor tray")
    args = parser.parse_args()
    config = load_config(args.config)
    try:
        app = TrayApp(config)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    app.update_from_state()
    GLib.timeout_add_seconds(15, app.update_from_state)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
