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
    # Theatro Circo: o link da imagem vem antes do título e da data.
    # A próxima ligação inicia um novo cartão de evento.
    for pos, (index, label, href) in enumerate(parser.links):
        next_index = parser.links[pos + 1][0] if pos + 1 < len(parser.links) else len(parser.parts)
        card = parser.parts[index:next_index]
        # Ignorar menus, scripts e ligações que não tenham um cartão completo.
        matches = [(i, DATE_RE.search(part)) for i, part in enumerate(card)]
        matches = [(i, match) for i, match in matches if match]
        if not matches:
            continue
        date_index, match = matches[0]
        day, month = int(match.group(1)), MONTHS[match.group(2).lower()]
        try:
            when = date(today.year + (today.month == 12 and month == 1), month, day)
        except ValueError:
            continue
        if not today <= when <= cutoff:
            continue
        # O título surge antes da data; o subtítulo pode estar entre ambos.
        before = [part for part in card[:date_index] if part.strip()]
        ui_labels = {"bilhetes", "acessibilidade", "infantojuvenil", "saber mais",
                     "comprar bilhetes", "esgotado", "→", "programação"}
        candidates = [part for part in before if part.casefold().strip() not in ui_labels
                      and not DATE_RE.search(part)]
        title = " ".join(label.split())
        if title.casefold().strip() in ui_labels:
            title = ""
        if not title:
            title = candidates[0] if candidates else ""
        if title.casefold().strip() in ui_labels:
            continue
        if not title or len(title) > 180:
            continue
        if any(term in title.casefold() for term in EXCLUDED):
            continue
        # A seta e a categoria surgem após a data, normalmente em nós separados.
        after = card[date_index + 1:date_index + 8]
        category = ""
        for i, part in enumerate(after):
            if part.strip() == "→" and i + 1 < len(after):
                category = after[i + 1].casefold()
                break
        if not category:
            category = " ".join(after[:3]).casefold()
        if any(term in category for term in EXCLUDED):
            continue
        if not any(term in category for term in ALLOWED):
            continue
        url = urljoin(URL, href)
        parsed = urlparse(url)
        if parsed.hostname not in ("theatrocirco.com", "www.theatrocirco.com"):
            continue
        if not parsed.path.startswith("/event/"):
            continue
        event_type = ("Música" if "música" in category else "Teatro" if "teatro" in category
                      else "Dança" if "dança" in category else "Ópera" if "ópera" in category
                      else "Exposição" if "exposição" in category else "Evento")
        found[(when.isoformat(), url)] = {
            "area": "Braga", "name": title, "start": when.isoformat(),
            "url": url, "source": URL, "type": event_type,
        }
    return list(found.values())


def main():
    html = fetch_html()
    parser = Links()
    parser.feed(html)
    print("JOMIVO THEATRO CIRCO DIAGNÓSTICO: links /event/ =", len(parser.links))
    for index, title, href in parser.links[:8]:
        print("JOMIVO LINK AMOSTRA:", repr(title[:100]), href, repr(" | ".join(parser.parts[max(0, index - 12):index])[:250]))
    events = preview_html(html)
    print("JOMIVO THEATRO CIRCO (pré-visualização, não publica):", len(events))
    for event in events:
        print(event["start"], "|", event["name"], "|", event["url"])


if __name__ == "__main__":
    main()
