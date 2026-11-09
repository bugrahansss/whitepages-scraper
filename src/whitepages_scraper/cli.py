"""Command line entry point.

    whitepages-scraper --name "John Smith" --city Seattle --state WA --pages 2 -f csv -o people.csv
    whitepages-scraper https://www.whitepages.com/name/<Name>/<City-ST>/<id>
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import List, Optional

from . import __version__
from .client import TOKEN_ENV, ScrapeError, WhitepagesScraper
from .parser import CSV_FIELDS, Person


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="whitepages-scraper",
                                description="Scrape Whitepages.com name searches and person pages into JSON or CSV.")
    p.add_argument("urls", nargs="*", help="Person page URLs to scrape")
    p.add_argument("-i", "--input", help="Text file with one person page URL per line")
    p.add_argument("-n", "--name", action="append", default=[], help='Search a name, e.g. "John Smith" (repeatable)')
    p.add_argument("--city", default="", help="City for --name searches (needs --state)")
    p.add_argument("-s", "--state", default="", help="Two-letter state code for --name searches, e.g. WA")
    p.add_argument("--pages", type=int, default=1, help="Result pages per name, 25 people each (default: 1)")
    p.add_argument("--profiles", action="store_true", help="Also open every person page found by --name (1 request each)")
    p.add_argument("--limit", type=int, default=0, help="Stop after this many people (default: no limit)")
    p.add_argument("-t", "--token", help=f"Scrape.do API token (default: ${TOKEN_ENV})")
    p.add_argument("-f", "--format", choices=("json", "csv"), default="json", help="Output format (default: json)")
    p.add_argument("-o", "--output", help="Write to this file instead of stdout")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _write(people: List[Person], fmt: str, stream) -> None:
    if fmt == "csv":
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for person in people:
            writer.writerow(person.to_row())
    else:
        json.dump([p.to_dict() for p in people], stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    urls = list(args.urls)
    if args.input:
        with open(args.input, encoding="utf-8") as handle:
            urls.extend(l.strip() for l in handle if l.strip() and not l.startswith("#"))
    if not urls and not args.name:
        print("Nothing to do. Pass person page URLs, --input FILE or --name NAME.", file=sys.stderr)
        return 2
    try:
        wp = WhitepagesScraper(token=args.token)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    people: List[Person] = []
    failures = 0
    for name in args.name:
        try:
            found = wp.search(name, args.city, args.state, args.pages)
        except (ScrapeError, ValueError) as exc:
            failures += 1
            print(f"fail  search {name!r}: {exc}", file=sys.stderr)
            continue
        print(f"found {len(found)} people for {name!r}", file=sys.stderr)
        if args.profiles:
            urls.extend(p.url for p in found if p.url and p.url not in urls)
        else:
            people.extend(found)
    if args.limit > 0:
        urls = urls[: max(0, args.limit - len(people))]
    for url in urls:
        try:
            people.append(wp.get_profile(url))
            print(f"ok    {url}", file=sys.stderr)
        except (ScrapeError, ValueError) as exc:
            failures += 1
            print(f"fail  {url}: {exc}", file=sys.stderr)
    if args.limit > 0:
        people = people[: args.limit]

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="" if args.format == "csv" else None) as handle:
            _write(people, args.format, handle)
        print(f"Saved {len(people)} people to {args.output} ({wp.credits_used} credits)", file=sys.stderr)
    else:
        _write(people, args.format, sys.stdout)
    return 1 if failures and not people else 0


if __name__ == "__main__":
    raise SystemExit(main())
