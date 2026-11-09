"""Search one name in one city, then open every person page and save a CSV.

    export SCRAPEDO_TOKEN=...
    python examples/search_to_csv.py
"""

import csv

from whitepages_scraper import CSV_FIELDS, WhitepagesScraper

wp = WhitepagesScraper()  # reads SCRAPEDO_TOKEN

people = wp.search("John Smith", city="Seattle", state="WA", pages=2)
print(f"{len(people)} people on the search pages")

# The search pages already carry address, phone and age range.
# Open the person pages only when you need associates or the HTML-only address.
detailed = [wp.get_profile(p.url) for p in people[:5] if p.url]

with open("people.csv", "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(p.to_row() for p in people)

print(f"saved people.csv, {wp.credits_used} credits used")
