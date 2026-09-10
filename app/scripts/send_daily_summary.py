from __future__ import annotations

import argparse
from datetime import date, datetime

from app.services.daily_summary import daily_summary_service


def _parse_summary_date(raw_value: str | None) -> date:
    if not raw_value or raw_value == "yesterday":
        return daily_summary_service.default_summary_date()
    if raw_value == "today":
        return daily_summary_service.local_today()
    return date.fromisoformat(raw_value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and optionally send the daily SMS activity digest.",
    )
    parser.add_argument(
        "--date",
        dest="summary_date",
        help="Summary date as YYYY-MM-DD, or 'today'/'yesterday'. Defaults to yesterday.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the digest without sending the SMS or recording send history.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Send even if a summary for the same date was already recorded.",
    )
    args = parser.parse_args()

    summary_date = _parse_summary_date(args.summary_date)
    result = daily_summary_service.send_digest(
        summary_date,
        force=args.force,
        dry_run=args.dry_run,
    )

    print(f"summary_date={result.summary_date}")
    print(f"activities_found={result.activities_found}")
    print(f"sent={result.sent}")
    print(f"skipped_reason={result.skipped_reason}")
    print("sms_body:")
    print(result.sms_body)
    if result.message_sid:
        print(f"message_sid={result.message_sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
