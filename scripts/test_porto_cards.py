import re
from collections import defaultdict
from html import unescape
from urllib.request import Request, urlopen

url = "https://www.agenda-porto.pt/pesquisa/"
req = Request(url, headers={"User-Agent": "Mozilla/5.0"})

with urlopen(req, timeout=30) as response:
    html = response.read().decode("utf-8", "replace")

cards = defaultdict(list)

for match in re.finditer(
    r'<[^>]+data-content-id="([^"]+)"[^>]*>[^<]*',
    html
):
    cid = match.group(1)
    fragment = match.group(0)

    link = re.search(r'href="([^"]*/evento/[^"]+)"', fragment)
    if link:
        cards[cid].append(("LINK", link.group(1)))

    value = re.sub(r"<[^>]+>", " ", fragment)
    value = unescape(value).strip()

    if value:
        cards[cid].append(("TEXTO", value[:120]))

found = 0

for cid, items in cards.items():
    links = [v for kind, v in items if kind == "LINK"]
    if not links:
        continue

    print("\nCARTÃO:", cid)
    for kind, value in items[:15]:
        print(kind + ":", value)

    found += 1
    if found == 5:
        break

print("\nCARTÕES COM LINK:", sum(
    any(kind == "LINK" for kind, _ in items)
    for items in cards.values()
))
