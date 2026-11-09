import csv
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from whitepages_scraper import (  # noqa: E402
    CSV_FIELDS,
    ScrapeError,
    WhitepagesScraper,
    format_phone,
    is_profile_url,
    name_search_url,
    parse_profile,
    parse_search_results,
)
from whitepages_scraper import cli  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
SEARCH = (FIX / "search_jane_doe.html").read_text(encoding="utf-8")
PROFILE = (FIX / "profile_jane_doe.html").read_text(encoding="utf-8")
CHALLENGE = (FIX / "challenge.html").read_text(encoding="utf-8")
PURL = "https://www.whitepages.com/name/Jane-Doe/Seattle-WA/PExample001"


class R:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        return self.responses.pop(0)


class ParserTests(unittest.TestCase):
    def test_search_url(self):
        self.assertEqual(name_search_url("John Smith"), "https://www.whitepages.com/name/John-Smith")
        self.assertEqual(name_search_url("John Smith", state="wa"), "https://www.whitepages.com/name/John-Smith/WA")
        self.assertEqual(name_search_url("John  Smith", "Seattle", "WA", 2), "https://www.whitepages.com/name/John-Smith/Seattle-WA?page=2")
        self.assertEqual(name_search_url("Mary O'Neil", "San Jose", "CA"), "https://www.whitepages.com/name/Mary-ONeil/San-Jose-CA")

    def test_search_url_errors(self):
        for args in (("",), ("123",), ("John", "", "Texas"), ("John", "Seattle", "")):
            with self.assertRaises(ValueError):
                name_search_url(*args)

    def test_format_phone(self):
        self.assertEqual(format_phone("+1-206-555-0103"), "(206) 555-0103")
        self.assertEqual(format_phone("(206) 555-0101"), "(206) 555-0101")
        self.assertEqual(format_phone("(206) *** ****"), "")
        self.assertEqual(format_phone(""), "")

    def test_parse_search(self):
        people = parse_search_results(SEARCH)
        self.assertEqual(len(people), 3)
        jane = people[0]
        self.assertEqual((jane.name, jane.first_name, jane.middle_name, jane.last_name), ("Jane Doe", "Jane", "Q", "Doe"))
        self.assertEqual((jane.address, jane.city, jane.state, jane.zip_code), ("100 Example St Apt 1", "Seattle", "WA", "98101"))
        self.assertEqual(jane.phones, ["(206) 555-0101"])
        self.assertEqual(jane.age_range, "40s")
        self.assertEqual(jane.neighborhood, "Capitol Hill")
        self.assertEqual(jane.previous_locations, ["Tacoma, WA"])
        self.assertEqual(jane.relatives, ["John Doe", "Mary Doe"])
        self.assertEqual(jane.aliases, ["Jane Q Doe"])
        self.assertEqual(jane.url, PURL)
        self.assertEqual(jane.profile_id, "PExample001")

    def test_search_age_falls_back_to_card(self):
        people = parse_search_results(SEARCH)
        self.assertEqual(people[1].age_range, "50s")  # not in JSON-LD, read from the card
        self.assertEqual(people[1].phones, [])
        self.assertEqual(people[2].phones, ["(206) 555-0103"])
        self.assertEqual(people[2].age_range, "80+")

    def test_parse_search_empty(self):
        self.assertEqual(parse_search_results("<html></html>"), [])

    def test_parse_profile(self):
        p = parse_profile(PROFILE)
        self.assertEqual(p.name, "Jane Doe")
        self.assertEqual(p.age_range, "40s")
        self.assertEqual((p.address, p.city, p.state, p.zip_code), ("100 Example St Apt 1", "Seattle", "WA", "98101"))
        self.assertEqual(p.phones, ["(206) 555-0101", "(206) 555-0199"])
        self.assertEqual(p.relatives, ["John Doe"])
        self.assertEqual(p.associates, ["Alex Roe"])
        self.assertEqual(p.aliases, ["Jane Q Doe"])

    def test_parse_profile_rejects_other_pages(self):
        with self.assertRaises(ValueError):
            parse_profile(SEARCH)

    def test_profile_url(self):
        self.assertTrue(is_profile_url(PURL))
        self.assertTrue(is_profile_url("/name/Jane-Doe/Seattle-WA/PExample001"))
        self.assertFalse(is_profile_url("https://www.whitepages.com/name/Jane-Doe/Seattle-WA"))
        self.assertFalse(is_profile_url("https://example.com/name/a/b/PExample001"))

    def test_rows(self):
        row = parse_search_results(SEARCH)[0].to_row()
        self.assertEqual(list(row), CSV_FIELDS)
        self.assertEqual(row["relatives"], "John Doe | Mary Doe")


class ClientTests(unittest.TestCase):
    def test_needs_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                WhitepagesScraper()

    def test_search_params_and_pagination(self):
        s = Session([R(200, SEARCH)])
        wp = WhitepagesScraper(token="T", session=s)
        people = wp.search("Jane Doe", "Seattle", "WA", pages=3)
        self.assertEqual(len(people), 3)
        self.assertEqual(len(s.calls), 1)  # fewer than 25, so no page 2
        self.assertEqual(s.calls[0]["url"], "https://www.whitepages.com/name/Jane-Doe/Seattle-WA")
        self.assertEqual((s.calls[0]["super"], s.calls[0]["geoCode"]), ("true", "us"))
        self.assertEqual(wp.credits_used, 10)

    def test_challenge_retried(self):
        s = Session([R(200, CHALLENGE), R(200, PROFILE)])
        with mock.patch("whitepages_scraper.client.time.sleep"):
            p = WhitepagesScraper(token="T", session=s, retries=1).get_profile(PURL)
        self.assertEqual(p.name, "Jane Doe")
        self.assertEqual(len(s.calls), 2)

    def test_client_error_not_retried(self):
        s = Session([R(401), R(200, PROFILE)])
        with self.assertRaises(ScrapeError) as ctx:
            WhitepagesScraper(token="T", session=s, retries=2).get_profile(PURL)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(len(s.calls), 1)

    def test_rejects_non_profile(self):
        with self.assertRaises(ValueError):
            WhitepagesScraper(token="T", session=Session([])).get_profile("https://example.com/x")


class CliTests(unittest.TestCase):
    def test_search_csv(self):
        out = io.StringIO()
        with mock.patch("whitepages_scraper.client.requests.Session", return_value=Session([R(200, SEARCH)])), \
                mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", io.StringIO()):
            code = cli.main(["-n", "Jane Doe", "--city", "Seattle", "-s", "WA", "-t", "T", "-f", "csv"])
        self.assertEqual(code, 0)
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        self.assertEqual([r["age_range"] for r in rows], ["40s", "50s", "80+"])

    def test_nothing_to_do(self):
        with mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(cli.main(["-t", "T"]), 2)


if __name__ == "__main__":
    unittest.main()
