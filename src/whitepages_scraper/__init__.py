"""Scrape Whitepages.com name searches and person pages with Python."""

from .client import ScrapeError, WhitepagesScraper
from .parser import CSV_FIELDS, Person, format_phone, is_profile_url, name_search_url, parse_profile, parse_search_results

__all__ = [
    "CSV_FIELDS",
    "Person",
    "ScrapeError",
    "WhitepagesScraper",
    "format_phone",
    "is_profile_url",
    "name_search_url",
    "parse_profile",
    "parse_search_results",
]

__version__ = "0.1.0"
