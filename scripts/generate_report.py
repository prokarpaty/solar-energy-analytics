import os
import json
import argparse

from pathlib import Path
from datetime import datetime, timedelta

from ha_client import collect_report, TZ


REPORT_NAMES = {
    "daily": "Щоденний",
    "weekly": "Щотижневий",
    "monthly": "Щомісячний",
    "quarterly": "Щоквартальний",
    "yearly": "Річний"
}


ENERGY_NAMES = {
    "production": "Генерація",
    "consumption": "Споживання",
    "grid_import": "Імпорт",
    "grid_export": "Експорт",
    "battery_charge": "Заряд АКБ",
    "battery_discharge": "Розряд АКБ",
    "inverter_losses": "Втрати інвертора"
}


def main():
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

    print(f"Generating {args.type} report")

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
    print(f"{REPORT_NAMES[args.type]} звіт")
    print(f"Період: {start.date()} — {last_date}")
    print("=" * 65)

    for key, item in data["energy"].items():

        value = item["total"]

        formatted = (
            f"{value:.2f} кВт·год"
            if value is not None
            else "Неповні дані"
        )

        print(
            f"{ENERGY_NAMES[key]:22} "
            f"{formatted:22} "
            f"({item['coverage']:.1f}%) "
            f"[{item.get('status', 'unknown')}]"
        )

    print("=" * 65)

    print(f"Measurement sensors: {len(data['measurements'])}")
    print(f"Report saved: {output}")
    print(f"File size: {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
