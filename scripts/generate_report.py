import os
import json
import argparse
from localization import Localizer

from pathlib import Path
from datetime import datetime, timedelta

from ha_client import collect_report, TZ


REPORT_NAMES = {'daily': 'daily',
 'weekly': 'weekly',
 'monthly': 'monthly',
 'quarterly': 'quarterly',
 'yearly': 'yearly'}




def main():
    loc = Localizer()
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--type",
        choices=REPORT_NAMES.keys(),
        default="daily"
    )

    parser.add_argument(
        "--as-of",
        type=lambda value: datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=TZ),
        default=None,
        help="Reference date in Europe/Kyiv (YYYY-MM-DD)"
    )

    args = parser.parse_args()

    if args.as_of and args.as_of.date() > datetime.now(TZ).date():
        parser.error("--as-of cannot be a future date")

    print(loc.text("cli.generating", period=loc.text("period." + args.type)))

    data = collect_report(args.type, now=args.as_of)

    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])

    last_date = end.date() - timedelta(days=1)

    filename = (
        f"solar-{args.type}-"
        f"{start.date()}_{last_date}"
    )

    directory = Path(
        os.environ.get(
            "REPORT_DIRECTORY", "/app/reports"
        )
    ) / args.type

    directory.mkdir(parents=True, exist_ok=True)

    output = directory / f"{filename}.json"

    temporary = output.with_suffix(".json.tmp")

    temporary.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        ),
        encoding="utf-8"
    )

    temporary.replace(output)

    print("\n" + "=" * 65)
    print(loc.text("report." + args.type))
    print(loc.text("cli.period", start=start.date(), end=last_date))
    print("=" * 65)

    for key, item in data["energy"].items():

        value = item["total"]

        formatted = (
            f"{loc.number(value)} {loc.text('unit.energy')}"
            if value is not None
            else loc.text("status.partial")
        )

        print(
            f"{loc.text('energy.' + key):22} "
            f"{formatted:22} "
            f"({loc.number(item['coverage'], 1)}%) "
            f"[{loc.text('status.' + item['status']) if item.get('status') in ('complete','recovered','partial','unavailable') else loc.text('cli.unknown')}]"
        )

    print("=" * 65)

    print(loc.text("cli.sensors", count=len(data["measurements"])))
    print(loc.text("cli.saved", path=output))
    print(loc.text("cli.size", size=loc.number(output.stat().st_size, 0)))


if __name__ == "__main__":
    main()
