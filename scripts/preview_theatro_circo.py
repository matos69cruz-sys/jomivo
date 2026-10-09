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
    """Lê cada cartão pela sequência título/data/categoria, nunca pelo cartão anterior."""
    today = today or date.today()
    cutoff = today + timedelta(days=30)
    parser = Links()
    parser.feed(html)
    found = {}
    # A âncora da imagem precede o título e data do respetivo evento.
    # Há também links de bilheteira; só usar a primeira ligação de cada cartão.
    for pos, (index, label, href) in enumerate(parser.links):
        next_index = parser.links[pos + 1][0] if pos + 1 < len(parser.links) else len(parser.parts)
        card = parser.parts[index:next_index]
        ui = {"bilhetes", "acessibilidade", "infantojuvenil", "saber mais",
              "comprar bilhetes", "esgotado", "→", "programação"}
        # A primeira data tem de estar dentro do próprio cartão.
        dated = [(i, DATE_RE.search(part)) for i, part in enumerate(card)]
        dated = [(i, m) for i, m in dated if m]
        if not dated:
            continue
        date_index, match = dated[0]
        before = [p.strip() for p in card[:date_index] if p.strip()]
        before = [p for p in before if p.casefold() not in ui]
        title = " ".join(label.split()) or (before[0] if before else "")
        if not title or title.casefold() in ui or len(title) > 180:
            continue
        if any(term in title.casefold() for term in EXCLUDED):
            continue
        day, month = int(match.group(1)), MONTHS[match.group(2).lower()]
        year = today.year
        if month < today.month and today.month >= 11:
            year += 1
        try:
            when = date(year, month, day)
        except ValueError:
            continue
        if not today <= when <= cutoff:
            continue
        after = card[date_index + 1:date_index + 8]
        category = ""
        for i, part in enumerate(after):
            if part.strip() == "→" and i + 1 < len(after):
                category = after[i + 1].casefold()
                break
        if not category or any(term in category for term in EXCLUDED):
            continue
        if not any(term in category for term in ALLOWED):
            continue
        url = urljoin(URL, href)
        parsed = urlparse(url)
        if parsed.hostname not in ("theatrocirco.com", "www.theatrocirco.com"):
            continue
        if not parsed.path.startswith("/event/"):
            continue
        # Evita associar datas de outubro a páginas explicitamente datadas de dezembro.
        slug = parsed.path.casefold()
        month_slugs = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5,
                       "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10,
                       "nov": 11, "dez": 12}
        slug_date = re.search(r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)20\d{2}", slug)
        if slug_date and month_slugs[slug_date.group(1)] != when.month:
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
    for pos, (index, label, href) in enumerate(parser.links[:18]):
        next_index = parser.links[pos + 1][0] if pos + 1 < len(parser.links) else len(parser.parts)
        print("JOMIVO CARTÃO:", href, repr(" | ".join(parser.parts[index:next_index])[:350]))
    events = preview_html(html)
    print("JOMIVO THEATRO CIRCO (pré-visualização, não publica):", len(events))
    for event in events:
        print(event["start"], "|", event["name"], "|", event["url"])


if __name__ == "__main__":
    main()
