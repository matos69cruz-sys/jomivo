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


def main():
    events = preview(fetch_html())
    print("JOMIVO TEATRO AVEIRENSE (pré-visualização, não publica):", len(events))
    for event in events:
        print(event["start"], "|", event["name"], "|", event["url"])
    if not events:
        print("AVISO: sem eventos JSON-LD válidos; é necessário um extrator HTML específico.")
    # Sem escrita em events.json.


if __name__ == "__main__":
    main()
