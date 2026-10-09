#!/usr/bin/env python3
"""Recolha experimental de eventos do Teatro Aveirense (sem publicar)."""
import json
import re
from datetime import date, timedelta
from html import unescape
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse

URL = "https://www.teatroaveirense.pt/pt/programacao/"
BASE = "https://www.teatroaveirense.pt"
ALLOWED = {"MusicEvent", "TheaterEvent", "DanceEvent", "Festival", "ExhibitionEvent", "Event"}
REJECT = ("oficina", "workshop", "cinema", "conversa", "curso", "formação", "seminário")


def fetch_html(url=URL):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (JOMIVO preview)"})
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def extract_jsonld(html):
    results = []
    for raw in re.findall(r'<script[^>]*type=["\x27]application/ld[+]json["\x27][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            value = json.loads(unescape(raw.strip()))
        except (ValueError, TypeError):
            continue
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                stack.extend(item.get("@graph", []))
                kind = item.get("@type", "")
                kinds = {kind} if isinstance(kind, str) else set(kind)
                if kinds & ALLOWED:
                    results.append(item)
    return results


def preview(html, today=None):
    today = today or date.today()
    cutoff = today + timedelta(days=30)
    found = {}
    for item in extract_jsonld(html):
        title = re.sub(r"\s+", " ", str(item.get("name", ""))).strip()
        start = str(item.get("startDate", ""))[:10]
        url = urljoin(BASE, str(item.get("url", "")))
        if not title or any(term in title.casefold() for term in REJECT):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start):
            continue
        try:
            when = date.fromisoformat(start)
        except ValueError:
            continue
        parsed = urlparse(url)
        if not (today <= when <= cutoff and parsed.hostname in {"www.teatroaveirense.pt", "teatroaveirense.pt"}):
            continue
        if not (parsed.path.startswith("/pt/programacao/") or parsed.path.startswith("/index.php/evento/")):
            continue
        found[(start, url)] = {"name": title, "start": start, "url": url, "area": "Aveiro", "source": URL}
    return list(found.values())


from html.parser import HTMLParser

MONTHS = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
          "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
          "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
CATEGORIES = {"Música", "Teatro", "Dança", "Ópera", "Exposição",
              "Festival", "Teatro de Marionetas"}
MONTH_PATTERN = "|".join(MONTHS)


class ProgrammeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.parts = []
        self.link = None
        self.link_parts = []
        self.in_main = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            href = attrs.get("href", "")
            if "/pt/evento/" in href:
                self.link = href
                self.link_parts = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.parts.append(value)
            if self.link is not None:
                self.link_parts.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.link is not None:
            self.items.append((len(self.parts), " ".join(self.link_parts), self.link))
            self.link = None


def preview_html(html, today=None):
    today = today or date.today()
    cutoff = today + timedelta(days=30)
    parser = ProgrammeParser()
    parser.feed(html)
    found = {}
    for index, title, href in parser.items:
        context = parser.parts[max(0, index - 12):index]
        context_text = " | ".join(context).casefold()
        dates = list(re.finditer(
            rf"(\\d{{1,2}})(?:\\s*[-–+]\\s*\\d{{1,2}})?\\s+({MONTH_PATTERN})",
            context_text,
        ))
        if not dates:
            continue
        day = int(dates[-1].group(1))
        month = MONTHS[dates[-1].group(2)]
        year = today.year
        try:
            when = date(year, month, day)
            if when < today and today.month == 12 and month == 1:
                when = date(year + 1, month, day)
        except ValueError:
            continue
        category_match = re.findall(
            r"categoria\\s*\\|?\\s*(música|teatro de marionetas|teatro|dança|ópera|exposição|festival)",
            context_text,
        )
        category = category_match[-1].title() if category_match else ""
        if category not in CATEGORIES or not (today <= when <= cutoff):
            continue
        if not title or any(term in title.casefold() for term in REJECT):
            continue
        url = urljoin(BASE, href)
        if urlparse(url).hostname not in {"www.teatroaveirense.pt", "teatroaveirense.pt"}:
            continue
        found[(when.isoformat(), url)] = {
            "name": title, "start": when.isoformat(), "url": url,
            "area": "Aveiro", "type": category, "source": URL,
        }
    return list(found.values())


def main():
    html = fetch_html()
    events = preview(html)
    if not events:
        events = preview_html(html)
    print("JOMIVO TEATRO AVEIRENSE (pré-visualização, não publica):", len(events))
    for event in events:
        print(event["start"], "|", event["name"], "|", event["url"])
    if not events:
        print("AVISO: sem eventos JSON-LD válidos; é necessário um extrator HTML específico.")
    # Sem escrita em events.json.


if __name__ == "__main__":
    main()
