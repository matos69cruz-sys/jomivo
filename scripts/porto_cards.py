
"""Recolha estruturada dos eventos da Agenda Porto."""

from collections import defaultdict
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import re

BASE = "https://www.agenda-porto.pt/"
SEARCH = urljoin(BASE, "pesquisa/")

MONTHS = {
    "jan": 1, "fev": 2, "mar": 3,
    "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9,
    "out": 10, "nov": 11, "dez": 12,
}


class PortoCardParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.cards = defaultdict(
            lambda: {"fields": defaultdict(list), "url": ""}
        )

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        parent = (
            self.stack[-1]["cid"]
            if self.stack else None
        )

        cid = attrs.get("data-content-id") or parent
        name = attrs.get("data-bl-name", "")
        href = attrs.get("href", "")

        self.stack.append({
            "cid": cid,
            "name": name,
            "text": [],
        })

        if cid and "evento/" in href:
            self.cards[cid]["url"] = urljoin(BASE, href)

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"].append(data)

    def handle_endtag(self, tag):
        if not self.stack:
            return

        node = self.stack.pop()
        value = re.sub(
            r"\s+", " ", "".join(node["text"])
        ).strip()

        if node["cid"] and node["name"] and value:
            values = self.cards[node["cid"]]["fields"][
                node["name"]
            ]
            if value not in values:
                values.append(value)

        if self.stack:
            self.stack[-1]["text"].append(value + " ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


def first(fields, key):
    values = fields.get(key, [])
    return values[0] if values else ""


def parse_event_date(value, today):
    match = re.search(
        r"\b([0-3]?\d)\s+"
        r"(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez)"
        r"(?:\s+(20\d{2}))?\b",
        value,
        re.I,
    )

    if not match:
        return None

    day = int(match.group(1))
    month = MONTHS[match.group(2).lower()]
    year = (
        int(match.group(3))
        if match.group(3)
        else today.year
    )

    try:
        result = date(year, month, day)
    except ValueError:
        return None

    if not match.group(3) and result < today - timedelta(days=30):
        try:
            result = date(year + 1, month, day)
        except ValueError:
            return None

    return result

def parse_date_range(value, today):
    pattern = (
        r"\b([0-3]?\d)\s+"
        r"(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez)\b"
    )
    matches = list(re.finditer(pattern, value, re.I))

    if not matches:
        return None, None

    years = re.findall(r"\b20\d{2}\b", value)
    year = int(years[-1]) if years else today.year

    try:
        dates = [
            date(year, MONTHS[m.group(2).lower()], int(m.group(1)))
            for m in matches[:2]
        ]
    except ValueError:
        return None, None

    start = dates[0]
    end = dates[-1]

    if len(dates) > 1 and end < start:
        end = date(year + 1, end.month, end.day)

    if not years and end < today - timedelta(days=30):
        start = date(start.year + 1, start.month, start.day)
        end = date(end.year + 1, end.month, end.day)

    return start, end

def fetch_porto_cards(today=None, days=90):
    """Devolve eventos futuros com os campos associados."""

    today = today or date.today()
    cutoff = today + timedelta(days=days)

    request = Request(
        SEARCH,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "pt-PT,pt;q=0.9",
        },
    )

    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", "replace")

    parser = PortoCardParser()
    parser.feed(html)

    events = []
    seen = set()

    for card in parser.cards.values():
        url = card["url"]

        if not url or url in seen:
            continue

        fields = card["fields"]
        title = first(fields, "Title").strip()
        venue = first(fields, "Local").strip()
        date_text = first(fields, "Date")

        if any(word in title.casefold() for word in ("exposição", "museu", "festival")):
            print(
                "DIAGNOSTICO DATAS:",
                repr(title),
                repr(fields.get("Date", [])),
                repr(fields.get("Row", [])),
            )
        
        start, end = parse_date_range(date_text, today)

        if not title or not start or not end:
            continue

        if end < today or start > cutoff:
            continue
        
        # Evitar títulos visivelmente truncados.
        if title.endswith(("...", "…")):
            continue

        category = "Evento"

        text_fields = fields.get("Text", [])

        for value in text_fields:
            normalized = value.casefold()

            if "música e clubbing" in normalized:
                category = "Música"
            elif normalized == "cinema":
                category = "Cinema"
            elif normalized == "palcos":
                category = "Teatro"
            elif normalized in ("artes visuais", "arte e exposições"):
                category = "Exposição"
            elif normalized == "literatura":
                category = "Literatura"
            elif normalized == "famílias":
                category = "Família"
            elif normalized == "dança":
                category = "Dança"
            elif normalized.startswith("desporto"):
                category = "Desporto"

        events.append({
            "name": title,
            "area": "Porto",
            "city": "Porto",
            "venue": venue,
            "type": category,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "desc": "",
            "url": url,
            "source": BASE,
        })

        seen.add(url)

    events.sort(key=lambda event: (
        event["start"],
        event["name"].casefold(),
    ))

    print(
        f"Agenda Porto: {len(parser.cards)} cartões analisados, "
        f"{len(events)} eventos futuros válidos."
    )

    return events


if __name__ == "__main__":
    for event in fetch_porto_cards():
        print(
            event["start"],
            event["name"],
            event["url"],
        )
