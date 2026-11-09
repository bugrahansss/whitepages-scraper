# Whitepages Scraper

[![PyPI](https://img.shields.io/pypi/v/whitepages-scraper)](https://pypi.org/project/whitepages-scraper/)
[![Python](https://img.shields.io/pypi/pyversions/whitepages-scraper)](https://pypi.org/project/whitepages-scraper/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Scrape [Whitepages.com](https://www.whitepages.com) people search into structured data. Search a name (optionally in a state or city) and get every person on the result pages with their **current address, phone numbers, age range, neighborhood, previous locations and relatives**, then open person pages for **associates** and the rest. JSON or CSV.

```bash
pip install whitepages-scraper
export SCRAPEDO_TOKEN=your_token
whitepages-scraper --name "John Smith" --city Seattle --state WA --pages 2 -f csv -o people.csv
```

## What is in the way

```python
import requests

requests.get("https://www.whitepages.com/name/John-Smith/Seattle-WA")
# outside the US: the connection is dropped; from a datacenter IP: Cloudflare challenge
```

1. **US only.** Visitors outside the United States, datacenter IPs and most VPNs are dropped without an error page.
2. **Cloudflare.** Every page sits behind Cloudflare's bot checks, so a plain HTTP client gets a challenge instead of HTML.

This package fetches every page through [Scrape.do](https://scrape.do/?utm_source=github&utm_medium=readme&utm_campaign=whitepages-scraper) with `super=true&geoCode=us` (a US residential IP): about 3 seconds and 10 credits per page.

## Where the data is

Whitepages renders on the server and publishes the people on each page as schema.org JSON-LD:

* **Search pages** carry an `ItemList` with up to **25 `Person` items**: full name, the current street address, phone numbers, `Age Range`, `Neighborhood` and `Previous Location` properties, relatives (`relatedTo`) and the person page URL. The visible cards mask phones ("(206) \*\*\* \*\*\*\*"); the JSON-LD has the full number. In a live test, one Seattle search page had 25 people, 25 addresses and 15 phone numbers in one request.
* **Person pages** carry one `Person` with phones under `contactPoint`, relatives and associates (`knows`). The address is often only in the HTML (`.address-line1`, `.address-line2`) and the age range in the text ("is in their 60s"); the parser reads both.
* **Pagination** is `?page=2`, `?page=3`, 25 people each.

Ages are ranges ("40s", "80+"), never exact. Free pages show the current phone at most; phone history, emails and background reports are behind Whitepages' paid tier and are not scraped.

## Python

```python
from whitepages_scraper import WhitepagesScraper

wp = WhitepagesScraper(token="YOUR_SCRAPEDO_TOKEN")  # or set SCRAPEDO_TOKEN

people = wp.search("John Smith", city="Seattle", state="WA", pages=2)
for p in people[:3]:
    print(p.name, p.age_range, p.address, p.city, p.phone, p.relatives)

person = wp.get_profile(people[0].url)
print(person.associates, person.phones)
print(wp.credits_used)
```

## Command line

```bash
# Name search: 25 people per page, no extra requests
whitepages-scraper --name "Mary Johnson" --state TX --pages 2 -f csv -o mary.csv

# Open every person page found (one more request each)
whitepages-scraper --name "John Smith" --city Seattle --state WA --profiles --limit 10

# Person page URLs
whitepages-scraper "https://www.whitepages.com/name/<Name>/<City-ST>/<id>"
```

## Fields

`name`, `first_name`, `middle_name`, `last_name`, `age_range`, `address`, `city`, `state`, `zip_code`, `neighborhood`, `phones`, `aliases`, `relatives`, `associates`, `previous_locations`, `url`.

## Use it responsibly

This is personal data about real people. Whitepages is not a consumer reporting agency: don't use this data for decisions about employment, housing, credit or insurance (the FCRA regulates those in the US). Honor opt-out requests, follow the privacy laws that apply to you (CCPA, GDPR) and Whitepages' terms, and keep request rates modest.

## Also available

- **No-code:** [Whitepages Scraper on Apify](https://apify.com/scrapedo/whitepages-scraper)
- **Browser demo:** [Hugging Face Space](https://huggingface.co/spaces/bugrahans/whitepages-scraper)
- **Full guide:** [Whitepages.com Scraping: Bypass Cloudflare and Extract People Data](https://scrape.do/blog/white-pages-scraping/?utm_source=github&utm_medium=readme&utm_campaign=whitepages-scraper)

## Tests

```bash
python -m unittest discover -s tests
```

The fixtures are fictional people (Jane Doe, 555 numbers); the tests never hit the network.

## License

MIT
