"""Fetch Whitepages pages through the Scrape.do API.

Whitepages only answers visitors from the United States (other IPs, datacenter
ranges and most VPNs are dropped) and puts Cloudflare in front of every page,
so a plain HTTP client never gets the HTML. Sending the request through
Scrape.do with ``super=true`` and ``geoCode=us`` routes it through a US
residential IP, which clears both. Each page is 10 credits.
"""

from __future__ import annotations

import os
import re
import time
from typing import Iterator, List, Optional

import requests

from .parser import Person, is_profile_url, name_search_url, parse_profile, parse_search_results

API_URL = "https://api.scrape.do/"
TOKEN_ENV = "SCRAPEDO_TOKEN"
BLOCK_RE = re.compile(r"just a moment\.\.\.|cf-chl-|attention required|cf-turnstile", re.I)


class ScrapeError(RuntimeError):
    """Raised when a page cannot be fetched."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class WhitepagesScraper:
    """Search Whitepages by name and read person pages.

    >>> wp = WhitepagesScraper(token="YOUR_SCRAPEDO_TOKEN")
    >>> people = wp.search("John Smith", city="Seattle", state="WA")
    >>> people[0].name, people[0].age_range, people[0].phone
    >>> person = wp.get_profile(people[0].url)
    """

    def __init__(self, token: Optional[str] = None, timeout: float = 90.0, retries: int = 2,
                 session: Optional[requests.Session] = None):
        self.token = token or os.environ.get(TOKEN_ENV, "")
        if not self.token:
            raise ValueError(f"A Scrape.do API token is required. Pass token=... or set {TOKEN_ENV}.")
        self.timeout = timeout
        self.retries = max(0, retries)
        self.session = session or requests.Session()
        self.requests_made = 0

    def fetch(self, url: str) -> str:
        """Raw HTML of ``url`` from a US residential IP. Cloudflare pages are retried."""
        params = {"token": self.token, "url": url, "super": "true", "geoCode": "us"}
        last_error: Optional[ScrapeError] = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(API_URL, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = ScrapeError(f"Request failed: {exc}")
            else:
                if response.status_code == 200:
                    self.requests_made += 1
                    if not BLOCK_RE.search(response.text[:5000]):
                        return response.text
                    last_error = ScrapeError(f"Cloudflare challenge page for {url}", 200)
                else:
                    last_error = ScrapeError(f"Request for {url} failed with status {response.status_code}",
                                             status_code=response.status_code)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        break
            if attempt < self.retries:
                time.sleep(2 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def search(self, name: str, city: str = "", state: str = "", pages: int = 1) -> List[Person]:
        """People for a name search, 25 per page. Stops when a page brings nobody new."""
        people: List[Person] = []
        seen = set()
        for page in range(1, max(1, pages) + 1):
            found = parse_search_results(self.fetch(name_search_url(name, city, state, page)))
            fresh = [p for p in found if (p.url or p.name + p.address) not in seen]
            if not fresh:
                break
            for person in fresh:
                seen.add(person.url or person.name + person.address)
                people.append(person)
            if len(found) < 25:
                break
        return people

    def get_profile(self, url: str) -> Person:
        """One person page (``/name/<Name>/<City-ST>/<id>``)."""
        if not is_profile_url(url):
            raise ValueError(f"Not a Whitepages person page: {url}")
        if url.startswith("/"):
            url = "https://www.whitepages.com" + url
        return parse_profile(self.fetch(url), url=url)

    def search_profiles(self, name: str, city: str = "", state: str = "", pages: int = 1, limit: int = 0) -> Iterator[Person]:
        """Search, then open each person page (one more request per person)."""
        for person in self.search(name, city, state, pages)[: limit or None]:
            if person.url:
                yield self.get_profile(person.url)

    @property
    def credits_used(self) -> int:
        return self.requests_made * 10
