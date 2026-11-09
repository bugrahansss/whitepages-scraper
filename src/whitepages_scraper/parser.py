"""Parse Whitepages.com name search pages and person pages.

Whitepages renders its pages on the server and publishes the people on them as
schema.org JSON-LD for search engines:

* A **name search page** (``/name/John-Smith/Seattle-WA``) carries one ``ItemList``
  block with up to 25 ``Person`` items: full name, current street address, phone
  numbers, an age range, the neighborhood, previous locations, relatives and the
  link to the person page. The visible cards mask the phone ("(206) *** ****");
  the JSON-LD block does not.
* A **person page** (``/name/John-Smith/Seattle-WA/PAbc123XyZ9``) carries one
  ``Person`` block with phones under ``contactPoint``, relatives (``relatedTo``) and
  associates (``knows``). Its current address is often only in the HTML
  (``.address-line1`` and ``.address-line2``), and the age range is in the text
  ("John Smith is in their 60s").

Ages are ranges ("60s", "80+"), never exact, and free pages show at most the
current phone; phone history and emails are behind Whitepages' paid tier.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup

BASE_URL = "https://www.whitepages.com"
PROFILE_RE = re.compile(r"^(?:https?://(?:www\.)?whitepages\.com)?/name/[^/?#]+/[^/?#]+/[A-Za-z0-9]{8,14}/?(?:[?#].*)?$")
AGE_TEXT_RE = re.compile(r"\bin (?:their|his|her) (\d{2}s|\d{2}\+)", re.I)
AGE_RANGE_RE = re.compile(r"^\d{2}(?:s|\+)$")
CITY_LINE_RE = re.compile(r"^\s*(.+?),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?\s*$")


@dataclass
class Person:
    """One person from a Whitepages search result or person page."""

    name: str = ""
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    age_range: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    neighborhood: str = ""
    phones: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    relatives: List[str] = field(default_factory=list)
    associates: List[str] = field(default_factory=list)
    previous_locations: List[str] = field(default_factory=list)
    url: str = ""

    @property
    def phone(self) -> str:
        return self.phones[0] if self.phones else ""

    @property
    def profile_id(self) -> str:
        match = re.search(r"/([A-Za-z0-9]{8,14})/?$", self.url.split("?")[0])
        return match.group(1) if match else ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_row(self, separator: str = " | ") -> Dict[str, Any]:
        row = self.to_dict()
        for key in ("phones", "aliases", "relatives", "associates", "previous_locations"):
            row[key] = separator.join(row[key])
        return row


CSV_FIELDS = [
    "name", "first_name", "middle_name", "last_name", "age_range", "address", "city", "state", "zip_code",
    "neighborhood", "phones", "aliases", "relatives", "associates", "previous_locations", "url",
]


# --------------------------------------------------------------------------- helpers


def _squash(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _unique(values: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for value in values:
        value = _squash(value)
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _names(values: Any) -> List[str]:
    return _unique(v.get("name", "") if isinstance(v, dict) else str(v) for v in _as_list(values))


def format_phone(value: str) -> str:
    """Normalize ``+1-206-555-0142`` and similar to ``(206) 555-0142``; masked numbers return ""."""
    value = _squash(value)
    if not value or "*" in value:
        return ""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return value
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def absolute_url(url: str) -> str:
    url = _squash(url)
    if url.startswith("/"):
        url = BASE_URL + url
    return url.split("#")[0]


def _slug(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9'.]+", text or "")
    return "-".join(w.replace("'", "").replace(".", "") for w in words if w.strip("'."))


def name_search_url(name: str, city: str = "", state: str = "", page: int = 1) -> str:
    """Build a name search URL: ``/name/John-Smith``, ``/name/John-Smith/WA`` or ``/name/John-Smith/Seattle-WA``.

    ``page`` adds ``?page=N`` (25 people per page).
    """
    slug = _slug(name)
    if not slug or not re.search(r"[A-Za-z]", slug):
        raise ValueError(f"Not a name: {name!r}")
    state = (state or "").strip().upper()
    if state and not re.fullmatch(r"[A-Z]{2}", state):
        raise ValueError(f"State must be a two-letter code like WA, got {state!r}")
    if city and not state:
        raise ValueError("A city needs a state, e.g. city='Seattle', state='WA'")
    url = f"{BASE_URL}/name/{quote(slug)}"
    if city:
        url += f"/{quote(_slug(city))}-{state}"
    elif state:
        url += f"/{state}"
    if page and int(page) > 1:
        url += f"?page={int(page)}"
    return url


def iter_jsonld(soup: BeautifulSoup) -> Iterable[Dict[str, Any]]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        for item in _as_list(data):
            if isinstance(item, dict):
                yield item


def _apply_address(person: Person, address: Any) -> None:
    for addr in _as_list(address):
        if not isinstance(addr, dict):
            continue
        person.address = _squash(addr.get("streetAddress"))
        person.city = _squash(addr.get("addressLocality"))
        person.state = _squash(addr.get("addressRegion"))
        person.zip_code = _squash(addr.get("postalCode"))
        if person.address or person.city:
            return


def _person_from_jsonld(item: Dict[str, Any]) -> Person:
    person = Person(
        name=_squash(item.get("name")),
        first_name=_squash(item.get("givenName")),
        middle_name=" ".join(_unique(_as_list(item.get("additionalName")))),
        last_name=_squash(item.get("familyName")),
        url=absolute_url(item.get("url") or item.get("@id") or ""),
    )
    _apply_address(person, item.get("address"))
    phones = [format_phone(p) for p in _as_list(item.get("telephone"))]
    for cp in _as_list(item.get("contactPoint")):
        if isinstance(cp, dict):
            phones.append(format_phone(cp.get("telephone", "")))
    person.phones = _unique(p for p in phones if p)
    person.aliases = [a for a in _unique(_as_list(item.get("alternateName"))) if a != person.name]
    person.relatives = _names(item.get("relatedTo"))
    person.associates = _names(item.get("knows"))
    for prop in _as_list(item.get("additionalProperty")):
        if not isinstance(prop, dict):
            continue
        key, value = _squash(prop.get("name")).lower(), _squash(prop.get("value"))
        if key == "age range" and AGE_RANGE_RE.match(value):
            person.age_range = value
        elif key == "neighborhood":
            person.neighborhood = value
        elif key == "previous location" and value:
            person.previous_locations.append(value)
    person.previous_locations = _unique(person.previous_locations)
    if not person.age_range:
        match = AGE_TEXT_RE.search(_squash(item.get("description")))
        if match:
            person.age_range = match.group(1)
    return person


# --------------------------------------------------------------------------- pages


def parse_search_results(html: str) -> List[Person]:
    """People on a name search page, from its ``ItemList`` JSON-LD (up to 25)."""
    soup = BeautifulSoup(html, "html.parser")
    people: List[Person] = []
    for block in iter_jsonld(soup):
        if block.get("@type") != "ItemList":
            continue
        for element in _as_list(block.get("itemListElement")):
            item = element.get("item") if isinstance(element, dict) else None
            if isinstance(item, dict) and item.get("@type") == "Person":
                people.append(_person_from_jsonld(item))
    # Ages missing from the JSON-LD are often on the visible card
    cards = {}
    for card in soup.select(".serp-card"):
        link = card.select_one("a.name-link-text, [data-qa-selector=organic-card-person-name]")
        age = card.select_one(".person-age")
        if link and link.get("href") and age:
            cards[absolute_url(link["href"])] = _squash(age.get_text())
    for person in people:
        if not person.age_range and AGE_RANGE_RE.match(cards.get(person.url, "")):
            person.age_range = cards[person.url]
    return people


def parse_profile(html: str, url: str = "") -> Person:
    """A person page: JSON-LD ``Person`` plus the address and age from the HTML."""
    soup = BeautifulSoup(html, "html.parser")
    item = next((b for b in iter_jsonld(soup) if b.get("@type") == "Person"), None)
    if item is None:
        raise ValueError("No Person JSON-LD on this page; it is not a Whitepages person page")
    person = _person_from_jsonld(item)
    if url:
        person.url = absolute_url(url)
    if not person.address:
        line1 = soup.select_one(".address-line1")
        line2 = soup.select_one(".address-line2")
        if line1:
            person.address = _squash(line1.get_text(" "))
        if line2:
            match = CITY_LINE_RE.match(_squash(line2.get_text(" ")))
            if match:
                person.city, person.state, person.zip_code = match.group(1), match.group(2), match.group(3) or ""
    if not person.age_range:
        for el in soup.select("[data-qa-selector=person-age-mobile], .person-age"):
            match = re.search(r"\d{2}(?:s|\+)", el.get_text(" "))
            if match:
                person.age_range = match.group(0)
                break
    html_phones = [format_phone(a.get_text()) for a in soup.select("[data-qa-selector=phone-number-link]")]
    person.phones = _unique(person.phones + [p for p in html_phones if p])
    return person


def is_profile_url(url: str) -> bool:
    return bool(PROFILE_RE.match(_squash(url)))
