from __future__ import annotations

import logging
import time

from monitor.cli import build_common_parser
from monitor.collector.system import collect_all
from monitor.config.loader import load_config
from monitor.evaluator.health import build_snapshot
from monitor.storage.state import init_db, store_snapshot, write_latest_state


LOG = logging.getLogger("uconsole-monitor-agent")


def run_once(config: dict) -> None:
    raw = collect_all(config)
    snapshot = build_snapshot(raw, config)
    init_db(config["paths"]["db"])
    store_snapshot(config["paths"]["db"], snapshot)
    write_latest_state(config["paths"]["latest_state"], snapshot)
    LOG.info("Collected snapshot with overall status %s", snapshot.overall_status)


def main() -> int:
    parser = build_common_parser("uConsole monitor agent")
    parser.add_argument("--once", action="store_true", help="Collect once and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)

    if args.once:
        run_once(config)
        return 0

    interval = max(int(config["interval_seconds"]), 30)
    while True:
        started = time.time()
        try:
            run_once(config)
        except Exception:
            LOG.exception("Collection cycle failed")
        elapsed = time.time() - started
        time.sleep(max(interval - elapsed, 1))


if __name__ == "__main__":
    raise SystemExit(main())
