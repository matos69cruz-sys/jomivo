#!/usr/bin/env python3
"""Pré-visualização da programação oficial do Theatro Circo (não publica)."""
import re
import json
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
    """A página coloca data/categoria ANTES do título e link do evento seguinte."""
    today = today or date.today()
    cutoff = today + timedelta(days=30)
    parser = Links()
    parser.feed(html)
    found = {}
    ui = {"bilhetes", "acessibilidade", "infantojuvenil", "saber mais",
          "comprar bilhetes", "esgotado", "→", "programação"}
    # Cada âncora aponta para o cartão cuja data/categoria surgem no início
    # do segmento; o título surge depois da categoria, antes da âncora seguinte.
    for pos, (index, label, href) in enumerate(parser.links):
        next_index = parser.links[pos + 1][0] if pos + 1 < len(parser.links) else len(parser.parts)
        segment = [p.strip() for p in parser.parts[index:next_index] if p.strip()]
        # Identificar data seguida da seta e da categoria.
        matches = [(i, DATE_RE.search(part)) for i, part in enumerate(segment)]
        matches = [(i, match) for i, match in matches if match]
        if not matches:
            continue
        date_index, match = matches[0]
        arrow = next((i for i in range(date_index + 1, min(date_index + 4, len(segment)))
                      if segment[i] == "→"), None)
        if arrow is None or arrow + 1 >= len(segment):
            continue
        category = segment[arrow + 1].casefold()
        if any(term in category for term in EXCLUDED):
            continue
        if not any(term in category for term in ALLOWED):
            continue
        # Título imediatamente depois da categoria, até à data seguinte.
        following = segment[arrow + 2:]
        title_candidates = []
        for part in following:
            if DATE_RE.search(part):
                break
            if part.casefold() not in ui and part != "→":
                title_candidates.append(part)
        title = " ".join(label.split()) or (title_candidates[0] if title_candidates else "")
        if not title or title.casefold() in ui or len(title) > 180:
            continue
        if any(term in title.casefold() for term in EXCLUDED):
            continue
        day, month = int(match.group(1)), MONTHS[match.group(2).lower()]
        year = today.year + (1 if month < today.month and today.month >= 11 else 0)
        try:
            when = date(year, month, day)
        except ValueError:
            continue
        if not today <= when <= cutoff:
            continue
        url = urljoin(URL, href)
        parsed = urlparse(url)
        if parsed.hostname not in ("theatrocirco.com", "www.theatrocirco.com"):
            continue
        if not parsed.path.startswith("/event/"):
            continue
        # A data da página pode contradizer a listagem: excluir se explícita.
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



def verified_events(today=None):
    """Devolve apenas eventos cuja data é confirmada pela página oficial."""
    today = today or date.today()
    cutoff = today + timedelta(days=30)
    candidates = preview_html(fetch_html(), today=today)
    approved = []
    pattern = re.compile(
        r"\b(\d{1,2})(?:\s*(?:a|até|[-–])\s*\d{1,2})?\s+("
        + "|".join(MONTHS) + r")(?:\s*\([^)]*\))?\s+(20\d{2})\b", re.I)
    class Visible(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.skip = 0
        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip += 1
        def handle_endtag(self, tag):
            if tag in ("script", "style") and self.skip:
                self.skip -= 1
        def handle_data(self, value):
            if not self.skip and value.strip():
                self.parts.append(" ".join(value.split()))
    for event in candidates:
        try:
            req = Request(event["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=12) as response:
                detail = response.read().decode("utf-8", "replace")
            visible = Visible()
            visible.feed(detail)
            dates = []
            for part in visible.parts:
                for match in pattern.finditer(part):
                    try:
                        dates.append(date(int(match.group(3)),
                                          MONTHS[match.group(2).lower()],
                                          int(match.group(1))))
                    except ValueError:
                        continue
            dates = list(dict.fromkeys(dates))
            if len(dates) != 1:
                print("JOMIVO THEATRO CIRCO BLOQUEADO (data ambígua):", event["name"], dates)
                continue
            official = dates[0]
            if not today <= official <= cutoff:
                print("JOMIVO THEATRO CIRCO BLOQUEADO (fora do prazo):", event["name"], official)
                continue
            approved.append({**event, "start": official.isoformat()})
        except Exception as error:
            print("JOMIVO THEATRO CIRCO BLOQUEADO (erro):", event["name"], error)
    return approved


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
    # Auditoria independente das datas em páginas individuais (não publica).
    for event in events:
        try:
            req = Request(event["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=12) as response:
                detail = response.read().decode("utf-8", "replace")
            blocks = re.findall(
                r'<script[^>]*type=["\x27]application/ld\+json["\x27][^>]*>(.*?)</script>',
                detail, flags=re.I | re.S)
            dates = []
            for block in blocks:
                try:
                    payload = json.loads(block)
                except (ValueError, TypeError):
                    continue
                nodes = payload if isinstance(payload, list) else [payload]
                for node in nodes:
                    if isinstance(node, dict):
                        if isinstance(node.get("@graph"), list):
                            nodes.extend(node["@graph"])
                        if node.get("startDate"):
                            dates.append(str(node["startDate"]))
            # Datas visíveis: a página oficial não disponibiliza startDate JSON-LD.
            class VisibleText(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.parts = []
                    self.skip = 0
                def handle_starttag(self, tag, attrs):
                    if tag in ("script", "style"):
                        self.skip += 1
                def handle_endtag(self, tag):
                    if tag in ("script", "style") and self.skip:
                        self.skip -= 1
                def handle_data(self, value):
                    if not self.skip and value.strip():
                        self.parts.append(" ".join(value.split()))
            visible = VisibleText()
            visible.feed(detail)
            official_dates = []
            pattern = re.compile(r"\b(\d{1,2})(?:\s*(?:a|até|[-–])\s*\d{1,2})?\s+(" + "|".join(MONTHS) + r")(?:\s*\([^)]*\))?\s+(20\d{2})\b", re.I)
            for part in visible.parts:
                for match in pattern.finditer(part):
                    try:
                        official_dates.append(date(int(match.group(3)),
                                                   MONTHS[match.group(2).lower()],
                                                   int(match.group(1))).isoformat())
                    except ValueError:
                        pass
            official_dates = list(dict.fromkeys(official_dates))
            status = ("CONFIRMADA" if event["start"] in official_dates
                      else "DIVERGENTE" if official_dates else "NÃO VERIFICÁVEL")
            if official_dates:
                verified = official_dates[0]
                if verified != event["start"]:
                    print("JOMIVO CORREÇÃO DATA:", event["name"],
                          event["start"], "->", verified)
                if not date.today().isoformat() <= verified <= (date.today() + timedelta(days=30)).isoformat():
                    print("JOMIVO EXCLUÍDO FORA DA JANELA:", event["name"], verified)
                else:
                    print("JOMIVO APTO PARA REVISÃO:", event["name"], verified)
            else:
                print("JOMIVO BLOQUEADO SEM DATA OFICIAL:", event["name"])
            print("JOMIVO DATA VISÍVEL:", status, event["name"],
                  "listagem:", event["start"], "página:", official_dates[:5])
            print("JOMIVO DATA DETALHE:", event["name"], event["start"],
                  "JSON-LD:", dates[:3] or "sem data estruturada")
        except Exception as error:
            print("JOMIVO DATA DETALHE ERRO:", event["url"], str(error)[:120])


if __name__ == "__main__":
    main()
