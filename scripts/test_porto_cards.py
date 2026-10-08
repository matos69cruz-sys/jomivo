
import re
from html import unescape
from urllib.request import Request, urlopen

URL = "https://www.agenda-porto.pt/pesquisa/"
req = Request(URL, headers={"User-Agent": "Mozilla/5.0"})

with urlopen(req, timeout=30) as response:
    html = response.read().decode("utf-8", "replace")

print("HTML recebido:", len(html), "caracteres")

for slug in ("heat", "moonspell-nov26"):
    pattern = (
        r'<a\b[^>]*href=["\']'
        r'(?:https?://[^"\']+)?/?evento/'
        + re.escape(slug)
        + r'/["\'][^>]*>'
    )

    match = re.search(pattern, html, re.I)

    print("\n" + "=" * 50)
    print("EVENTO:", slug)

    if not match:
        print("Link não encontrado")
        continue

    tag = match.group(0)
    cid_match = re.search(
        r'data-content-id=["\']([^"\']+)',
        tag
    )

    print("TAG DO LINK:", tag[:1200])

    if cid_match:
        cid = cid_match.group(1)
        print("CONTENT ID:", cid)

        occurrences = list(re.finditer(
            re.escape(cid), html
        ))

        print("OCORRÊNCIAS DO ID:", len(occurrences))

        for i, occurrence in enumerate(occurrences[:5], 1):
            start = max(0, occurrence.start() - 350)
            end = min(len(html), occurrence.end() + 350)
            fragment = html[start:end]

            print("\nELEMENTO", i)
            print(fragment[:800])

    start = max(0, match.start() - 1800)
    end = min(len(html), match.end() + 500)

    fragment = html[start:end]
    plain = unescape(re.sub(r"<[^>]+>", " ", fragment))
    plain = re.sub(r"\s+", " ", plain).strip()

    print("\nTEXTO PRÓXIMO:", plain[:1000])

print("\nDIAGNÓSTICO CONCLUÍDO")
