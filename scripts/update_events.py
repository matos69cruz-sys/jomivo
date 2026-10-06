#!/usr/bin/env python3

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SOURCES = [
    ("Porto", "Porto", "https://www.agenda-porto.pt/"),
    ("Aveiro", "Aveiro", "https://www.cm-aveiro.pt/visitantes/agenda-aveiro"),
    (
        "Braga",
        "Braga",
        "https://www.cm-braga.pt/pt/0502/viver/cultura-e-patrimonio/"
        "dinamizacao-cultural/agenda-cultural-de-braga",
    ),
]

OUT = Path("events.json")
UA = "Mozilla/5.0 (compatible; JOMIVO-events/1.0)"


def fetch(url):
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "pt-PT,pt;q=0.9",
        },
    )
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def iso(value):
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value))
    return match.group(1) if match else None


def date_label(start, end):
    first = datetime.strptime(start, "%Y-%m-%d")
    last = datetime.strptime(end or start, "%Y-%m-%d")

    months = [
        "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
        "Jul", "Ago", "Set", "Out", "Nov", "Dez",
    ]

    if first.date() == last.date():
        return f"{first.day} {months[first.month - 1]}"

    return f"{first.day}–{last.day} {months[last.month - 1]}"


def clean(value, limit=180):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip()


def parse_events(area, city, source_url, html):
    events = []

    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>'
        r'(.*?)</script>',
        html,
        re.I | re.S,
    )

    for raw in blocks:
        try:
            data = json.loads(raw.strip())
        except Exception:
            continue

        for item in walk(data):
            event_type = item.get("@type")
            types = event_type if isinstance(event_type, list) else [event_type]

            if "Event" not in types:
                continue

            start = iso(item.get("startDate"))
            end = iso(item.get("endDate"))
            name = clean(item.get("name"), 100)

            if not start or not name:
                continue

            end = end or start

            location = item.get("location") or {}
            venue = (
                clean(location.get("name"), 80)
                if isinstance(location, dict)
                else ""
            )

            description = clean(item.get("description"), 180)
            event_url = item.get("url") or source_url

            events.append(
                {
                    "name": name,
                    "area": area,
                    "city": city,
                    "venue": venue,
                    "type": "Evento",
                    "start": start,
                    "end": end,
                    "date": date_label(start, end),
                    "desc": description,
                    "url": urljoin(source_url, str(event_url)),
                    "source": source_url,
                }
            )

    return events


def main():
    today = date.today().isoformat()
    all_events = []
    working_sources = []

    for area, city, source_url in SOURCES:
        try:
            events = parse_events(
                area,
                city,
                source_url,
                fetch(source_url),
            )

            if events:
                working_sources.append(area)
                all_events.extend(events)
            else:
                print(
                    f"AVISO: {area} não forneceu eventos estruturados.",
                    file=sys.stderr,
                )

        except Exception as error:
            print(
                f"AVISO: erro ao consultar {area}: {error}",
                file=sys.stderr,
            )

    # Segurança:
    # nunca substitui uma agenda saudável por uma recolha vazia.
    if len(all_events) < 3:
        print(
            "Recolha insuficiente. events.json foi preservado.",
            file=sys.stderr,
        )
        return 0

    unique = {}

    for event in all_events:
        if event["end"] >= today:
            key = (
                event["name"].casefold(),
                event["start"],
                event["area"],
            )
            unique[key] = event

    events = sorted(
        unique.values(),
        key=lambda event: (
            event["start"],
            event["area"],
            event["name"],
        ),
    )

    if len(events) < 3:
        print(
            "Poucos eventos futuros. events.json foi preservado.",
            file=sys.stderr,
        )
        return 0

    payload = {
        "updated": today,
        "events": events,
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(
        f"{len(events)} eventos encontrados. "
        f"Fontes: {', '.join(working_sources)}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
