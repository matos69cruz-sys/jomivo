#!/usr/bin/env python3
"""Pré-visualização da programação oficial do Theatro Circo (não publica)."""
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

URL = "https://theatrocirco.com/programa/"
MONTHS = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5,
          "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
          "novembro": 11, "dezembro": 12}
ALLOWED = ("música", "teatro", "dança", "ópera", "multidisciplinar", "exposição")
EXCLUDED = ("cinema", "mediação", "oficina", "workshop", "open call",
            "convocatória", "cancelado", "formação", "curso", "seminário")
DATE_RE = re.compile(
    r"(\d{1,2})(?:\s*(?:a|e|até|[-–])\s*\d{1,2})?\s+("
    + "|".join(MONTHS) + r")\b", re.I
)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.active = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if "/event/" in href:
                self.active = href
                self.text = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.parts.append(value)
            if self.active is not None:
                self.text.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.active is not None:
            self.links.append((len(self.parts), " ".join(self.text), self.active))
            self.active = None


def fetch_html():
    req = Request(URL, headers={"User-Agent": "Mozilla/5.0 (JOMIVO preview)"})
    with urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def preview_html(html, today=None):
    today = today or date.today()
    cutoff = today + timedelta(days=30)
    parser = Links()
    parser.feed(html)
    found = {}
    for index, label, href in parser.links:
        context = " | ".join(parser.parts[max(0, index - 16):index + 1])
        match = DATE_RE.search(context)
        if not match:
            continue
        day, month = int(match.group(1)), MONTHS[match.group(2).lower()]
        try:
            when = date(today.year + (today.month == 12 and month == 1), month, day)
        except ValueError:
            continue
        if not today <= when <= cutoff:
            continue
        low = context.casefold()
        if any(term in low for term in ("cancelado", "espetáculo cancelado")):
            continue
        # O tipo é obtido da última indicação editorial junto à data.
        categories = re.findall(
            r"→\s*([^|]{1,70})", context, re.I
        )
        category_text = categories[-1].casefold() if categories else ""
        if not any(term in category_text for term in ALLOWED):
            continue
        if any(term in category_text for term in EXCLUDED):
            continue
        title = " ".join(label.split())
        if not title or any(term in title.casefold() for term in EXCLUDED):
            continue
        url = urljoin(URL, href)
        parsed = urlparse(url)
        if parsed.hostname not in ("theatrocirco.com", "www.theatrocirco.com"):
            continue
        if not parsed.path.startswith("/event/"):
            continue
        found[(when.isoformat(), url)] = {
            "area": "Braga", "name": title, "start": when.isoformat(),
            "url": url, "source": URL, "type": "Música" if "música" in category_text
            else "Teatro" if "teatro" in category_text else "Dança" if "dança" in category_text
            else "Ópera" if "ópera" in category_text else "Evento",
        }
    return list(found.values())


def main():
    events = preview_html(fetch_html())
    print("JOMIVO THEATRO CIRCO (pré-visualização, não publica):", len(events))
    for event in events:
        print(event["start"], "|", event["name"], "|", event["url"])


if __name__ == "__main__":
    main()
