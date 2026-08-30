#!/usr/bin/env python3
"""Generate db/init/20_seed_ct_logs.sql from the Chrome/CT log list.

ct_monitor reads the log list from the `ct_log` table (certwatch.GetConfig),
so that table must be seeded. This script downloads the Chromium log list
and generates one INSERT ... ON CONFLICT DO NOTHING per log.

Usage:
    python scripts/generate_ct_log_seed.py
    python scripts/generate_ct_log_seed.py --active-patterns "Argon2026h2,Xenon2026h2"

The ct_log.TYPE column is 'rfc6962' for classic logs and 'static' for tiled
(Sunlight) logs.  For static logs, ct_log.URL is the monitoring_url and
SUBMISSION_URL is the submission_url (ct_monitor uses /checkpoint and note.go).
"""

import argparse
import json
import sys
import urllib.request

DEFAULT_URL = "https://www.gstatic.com/ct/log_list/v3/all_logs_list.json"
DEFAULT_OUT = "db/init/20_seed_ct_logs.sql"

# States in which the log accepts/keeps queryable data.
ACTIVE_STATES = {"usable", "qualified"}


def sql_str(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="URL of the log list JSON")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output SQL file path")
    parser.add_argument(
        "--active-patterns",
        default=None,
        help="Comma-separated substrings of the description field; only logs "
        "containing them are marked as active",
    )
    args = parser.parse_args()

    patterns = [p for p in (args.active_patterns or "").split(",") if p]

    with urllib.request.urlopen(args.url, timeout=60) as resp:
        data = json.load(resp)

    rows = []
    log_id = 0
    for operator in data.get("operators", []):
        op_name = operator["name"]
        entries = operator.get("logs", []) + operator.get("tiled_logs", [])
        for entry in entries:
            log_id += 1
            description = entry.get("description", "")
            pubkey_b64 = entry.get("key", "")
            mmd = entry.get("mmd")
            log_type = entry.get("log_type")
            state = next(iter((entry.get("state") or {}).keys()), None)
            submission_url = entry.get("submission_url")
            monitoring_url = entry.get("monitoring_url")
            url = entry.get("url") or monitoring_url or ""

            is_test = log_type in ("test", "monitoring_only")
            if submission_url:
                entry_type = "static"
                main_url = monitoring_url or submission_url
            else:
                entry_type = "rfc6962"
                main_url = url

            active = (not is_test) and ((state in ACTIVE_STATES) or (state is None))
            if patterns:
                active = active and any(p in description for p in patterns)

            rows.append(
                (
                    log_id,
                    description,
                    op_name,
                    entry_type,
                    main_url,
                    submission_url,  # None for classic logs
                    mmd,
                    pubkey_b64,
                    active,
                    is_test,
                )
            )

    if not rows:
        print("error: no logs found in the log list", file=sys.stderr)
        return 1

    lines = [
        "-- ============================================================",
        "-- Seed of the ct_log table, generated automatically.",
        "-- Source: " + args.url,
        f"-- Regenerate with: python scripts/generate_ct_log_seed.py --active-patterns {args.active_patterns or '<all active/usable>'}",
        "-- ============================================================",
        "",
    ]
    for (
        rid,
        desc,
        op_name,
        entry_type,
        main_url,
        submission_url,
        mmd,
        pubkey_b64,
        active,
        is_test,
    ) in rows:
        sub_sql = sql_str(submission_url) if submission_url else "NULL"
        mmd_sql = str(mmd) if mmd is not None else "NULL"
        lines.append(
            "INSERT INTO ct_log (ID, OPERATOR, TYPE, URL, SUBMISSION_URL, NAME, "
            "PUBLIC_KEY, IS_ACTIVE, IS_TEST_LOG, MMD_IN_SECONDS) VALUES ("
            f"{rid}, "
            f"{sql_str(op_name)}, "
            f"{sql_str(entry_type)}, "
            f"{sql_str(main_url)}, "
            f"{sub_sql}, "
            f"{sql_str(desc)}, "
            f"decode({sql_str(pubkey_b64)}, 'base64'), "
            f"{'TRUE' if active else 'FALSE'}, "
            f"{'TRUE' if is_test else 'FALSE'}, "
            f"{mmd_sql}"
            ") ON CONFLICT DO NOTHING;"
        )

    lines.append("")
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    active_count = sum(1 for r in rows if r[8])
    print(f"OK: {len(rows)} logs, {active_count} active -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())