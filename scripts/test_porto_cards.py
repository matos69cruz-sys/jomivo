
#!/usr/bin/env python3
"""Diagnóstico dos cartões da Agenda Porto. Não altera events.json."""

from collections import defaultdict
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import re

BASE = "https://www.agenda-porto.pt/"
URL = urljoin(BASE, "pesquisa/")


class Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.cards = defaultdict(
            lambda: {"fields": defaultdict(list), "url": ""}
        )

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        parent = self.stack[-1]["cid"] if self.stack else None
        cid = a.get("data-content-id") or parent
        name = a.get("data-bl-name", "")
        href = a.get("href", "")

        self.stack.append({
            "cid": cid,
            "name": name,
            "text": []
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
            fields = self.cards[node["cid"]]["fields"][node["name"]]
            if value not in fields:
                fields.append(value)

        if self.stack:
            self.stack[-1]["text"].append(value + " ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


request = Request(
    URL,
    headers={"User-Agent": "Mozilla/5.0"}
)

with urlopen(request, timeout=30) as response:
    html = response.read().decode("utf-8", "replace")

parser = Cards()
parser.feed(html)

linked = [
    (cid, card)
    for cid, card in parser.cards.items()
    if card["url"]
]

print("CARTOES COM LINK:", len(linked))

for cid, card in linked:
    if not any(
        slug in card["url"]
        for slug in ("moonspell-nov26", "heat")
    ):
        continue

    print("\nEVENTO:", card["url"])
    print("ID:", cid)

    for name, values in card["fields"].items():
        if name in (
            "Text", "Date", "Title", "Heading",
            "Local", "Card. Card Event",
            "Top row", "Row"
        ):
            print(
                name, ":", repr(values[:5])[:500]
            )

print("\nAMOSTRA DOS PRIMEIROS 3 CARTOES")

for cid, card in linked[:3]:
    print("URL:", card["url"])

    for name, values in card["fields"].items():
        if name in (
            "Text", "Date", "Title",
            "Heading", "Local"
        ):
            print(
                " ", name, ":", repr(values[:3])[:200]
            )

print("\nDIAGNOSTICO CONCLUIDO")
