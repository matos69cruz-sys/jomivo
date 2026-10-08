
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE = "https://www.agenda-porto.pt"
URL = BASE + "/pesquisa/"


class EventParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.events = []
        self.seen = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cid = attrs.get("data-content-id")

        inherited = self.stack[-1] if self.stack else None
        current = cid or inherited
        self.stack.append(current)

        href = attrs.get("href", "")
        if "/evento/" in href:
            link = urljoin(BASE, href)

            if link not in self.seen:
                self.seen.add(link)
                self.events.append({
                    "id": current,
                    "url": link
                })

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.stack:
            self.stack.pop()


req = Request(
    URL,
    headers={"User-Agent": "Mozilla/5.0"}
)

with urlopen(req, timeout=30) as response:
    html = response.read().decode(
        "utf-8", "replace"
    )

parser = EventParser()
parser.feed(html)

print("TOTAL DE LINKS:", len(parser.events))

with_id = sum(
    bool(event["id"])
    for event in parser.events
)

print("LINKS COM ID:", with_id)

for event in parser.events[:10]:
    print("\nID:", event["id"])
    print("LINK:", event["url"])
