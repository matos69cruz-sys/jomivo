#!/usr/bin/env python3

import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

OUT = Path("events.json")
UA = "Mozilla/5.0 (compatible; JOMIVO-events/2.0)"

SOURCES = {
    "Porto": {
        "city": "Porto",
        "url": "https://www.agenda-porto.pt/",
    },
    "Aveiro": {
        "city": "Aveiro",
        "url": "https://www.cm-aveiro.pt/visitantes/agenda-aveiro",
    },
    "Braga": {
        "city": "Braga",
        "url": "https://visitbraga.travel/agenda-braga/",
    },
}

MONTHS = {
    "jan": 1, "janeiro": 1,
    "fev": 2, "fevereiro": 2,
    "mar": 3, "março": 3, "marco": 3,
    "abr": 4, "abril": 4,
    "mai": 5, "maio": 5,
    "jun": 6, "junho": 6,
    "jul": 7, "julho": 7,
    "ago": 8, "agosto": 8,
    "set": 9, "setembro": 9,
    "out": 10, "outubro": 10,
    "nov": 11, "novembro": 11,
    "dez": 12, "dezembro": 12,
}

MONTH_LABELS = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]


def fetch(url, timeout=25, attempts=2):
    last_error = None

    for attempt in range(attempts):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.5",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )

            with urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")

        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(2)

    raise last_error


def text(value):
    value = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        str(value or ""),
        flags=re.I | re.S,
    )
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def clean(value, limit=180):
    return text(value)[:limit].rstrip()

def porto_slug(value):
    value = unescape(str(value or "")).casefold()
    value = (
        value.replace("á", "a").replace("à", "a")
        .replace("ã", "a").replace("â", "a")
        .replace("é", "e").replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o").replace("õ", "o").replace("ô", "o")
        .replace("ú", "u").replace("ç", "c")
    )
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")

def porto_event_links(html, source):
    links = re.findall(
        r'href\s*=\s*["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )

    event_links = []

    for link in links:
        full_url = urljoin(source, unescape(link))

        if "/evento/" in full_url:
            event_links.append(full_url)

    return list(dict.fromkeys(event_links))

def porto_event_contexts(html, source):
    contexts = []

    for match in re.finditer(
        r'href\s*=\s*["\']([^"\']+)["\']',
        html,
        flags=re.I,
    ):
        link = urljoin(source, unescape(match.group(1)))

        if "/evento/" not in link:
            continue

        start = max(0, match.start() - 1200)
        end = min(len(html), match.end() + 1200)
        context = text(html[start:end])

        contexts.append((link, context))

    return contexts

def porto_link_for_title(html, title, source):
    title_text = clean(title, 180)

    if not title_text:
        return source

    for match in re.finditer(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        link = urljoin(source, unescape(match.group(1)))

        if "/evento/" not in link:
            continue

        link_text = clean(match.group(2), 500)

        if title_text.casefold() in link_text.casefold():
            return link

    return source

def iso(value):
    if not value:
        return None

    match = re.search(
        r"(\d{4})-(\d{2})-(\d{2})",
        str(value),
    )

    if not match:
        return None

    try:
        return date(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        ).isoformat()
    except ValueError:
        return None


def date_label(start, end):
    first = datetime.strptime(start, "%Y-%m-%d")
    last = datetime.strptime(end or start, "%Y-%m-%d")

    if first.date() == last.date():
        return f"{first.day} {MONTH_LABELS[first.month - 1]}"

    if first.month == last.month:
        return (
            f"{first.day}–{last.day} "
            f"{MONTH_LABELS[last.month - 1]}"
        )

    return (
        f"{first.day} {MONTH_LABELS[first.month - 1]} – "
        f"{last.day} {MONTH_LABELS[last.month - 1]}"
    )


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)

    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def jsonld_events(area, city, source_url, html):
    found = []

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
            types = (
                event_type
                if isinstance(event_type, list)
                else [event_type]
            )

            if "Event" not in types:
                continue

            start = iso(item.get("startDate"))
            end = iso(item.get("endDate")) or start
            name = clean(item.get("name"), 120)

            if not start or not name:
                continue

            location = item.get("location") or {}

            if isinstance(location, dict):
                venue = clean(location.get("name"), 100)
            else:
                venue = ""

            found.append(
                make_event(
                    name=name,
                    area=area,
                    city=city,
                    venue=venue,
                    event_type="Evento",
                    start=start,
                    end=end,
                    desc=clean(item.get("description"), 180),
                    url=urljoin(
                        source_url,
                        str(item.get("url") or source_url),
                    ),
                    source=source_url,
                )
            )

    return found


def make_event(
    name,
    area,
    city,
    venue,
    event_type,
    start,
    end,
    desc,
    url,
    source,
):
    return {
        "name": clean(name, 120),
        "area": area,
        "city": city,
        "venue": clean(venue, 100),
        "type": clean(event_type, 60) or "Evento",
        "start": start,
        "end": end or start,
        "date": date_label(start, end or start),
        "desc": clean(desc, 180),
        "url": url,
        "source": source,
    }


def links_from_html(html, base_url):
    links = []

    for href, label in re.findall(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        re.I | re.S,
    ):
        absolute = urljoin(base_url, unescape(href))
        label = clean(label, 160)

        if not label:
            continue

        if absolute not in [item[0] for item in links]:
            links.append((absolute, label))

    return links


def parse_porto():
    area = "Porto"
    city = "Porto"
    source = SOURCES[area]["url"]

    html = fetch(
        source,
        timeout=15,
        attempts=1,
    )
    event_links = porto_event_links(html, source)
    event_contexts = porto_event_contexts(html, source)
    print(f"Porto: {len(event_contexts)} contextos de eventos encontrados.")
    print(f"Porto: {len(event_links)} links individuais encontrados.")
   
    events = []

    # Mantém suporte a eventos estruturados.
    events.extend(
        jsonld_events(
            area,
            city,
            source,
            html,
        )
    )

    raw = text(html)

    months = {
        "jan": 1,
        "fev": 2,
        "mar": 3,
        "abr": 4,
        "mai": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "set": 9,
        "out": 10,
        "nov": 11,
        "dez": 12,
    }

    today = date.today()

    # Este é o formato que já provámos que a página
    # entrega corretamente ao coletor: "06 Out".
    date_pattern = re.compile(
        r"\b(0?[1-9]|[12]\d|3[01])\s+"
        r"(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez)"
        r"(?:\s+(20\d{2}))?\b",
        re.I,
    )

    matches = list(date_pattern.finditer(raw))

    print(
        f"Porto: {len(matches)} datas encontradas na agenda."
    )

    category_map = [
        ("Cinema", ("cinema", "filme")),
        ("Teatro", ("palcos", "teatro", "performance")),
        ("Exposição", ("artes visuais", "exposição")),
        ("Dança", ("dança", "danca")),
        ("Literatura", ("literatura",)),
        ("Família", ("famílias", "familia")),
        ("Desporto", ("desporto", "movimento")),
        ("Conversas", ("conversas", "palestra")),
        ("Música", ("música", "musica", "clubbing", "concerto")),
    ]

    category_terms = (
        "música e clubbing",
        "artes visuais",
        "desporto e movimento",
        "cinema",
        "palcos",
        "literatura",
        "famílias",
        "conversas",
        "concerto",
        "filme",
        "exposição",
        "performance",
        "teatro",
        "dança",
    )

    index = 0

    while index < len(matches):
        first = matches[index]

        day1 = int(first.group(1))
        month1 = months[first.group(2).lower()]
        year1_raw = first.group(3)

        year1 = (
            int(year1_raw)
            if year1_raw
            else today.year
        )

        try:
            start_date = date(
                year1,
                month1,
                day1,
            )
        except ValueError:
            index += 1
            continue

        if (
            not year1_raw
            and start_date < today - timedelta(days=30)
        ):
            try:
                start_date = date(
                    year1 + 1,
                    month1,
                    day1,
                )
            except ValueError:
                index += 1
                continue

        end_date = start_date
        body_start = first.end()
        consumed = 1

        # Se a data seguinte estiver imediatamente junto
        # da primeira, tratamo-la como a data FINAL do
        # mesmo cartão, e não como outro evento.
        if index + 1 < len(matches):
            second = matches[index + 1]

            between = clean(
             raw[first.end():second.start()],
             120,
            )

            if len(between) <= 8:
                day2 = int(second.group(1))
                month2 = months[
                    second.group(2).lower()
                ]
                year2_raw = second.group(3)

                year2 = (
                    int(year2_raw)
                    if year2_raw
                    else start_date.year
                )

                try:
                    possible_end = date(
                        year2,
                        month2,
                        day2,
                    )

                    gap = (
                        possible_end - start_date
                    ).days

                    if 0 <= gap <= 31:
                        end_date = possible_end
                        body_start = second.end()
                        consumed = 2
                except ValueError:
                    pass

        next_index = index + consumed

        if next_index < len(matches):
            body_end = matches[next_index].start()
        else:
            body_end = min(
                len(raw), 
                body_start + 900,
            )

        block = raw[
            body_start:body_end
        ].strip()

        # O text() transforma o cartão numa frase corrida.
        # Em vez de depender de quebras de linha, usamos
        # as etiquetas da Agenda Porto como separadores.
        value = clean(block, 900)

        if not value:
            index += consumed
            continue

        category = "Evento"
        event_kind = ""

        category_markers = [
            ("Cinema", ("Cinema",)),
            ("Teatro", ("Palcos",)),
            ("Exposição", ("Arte e exposições",)),
            ("Dança", ("Dança",)),
            ("Literatura", ("Literatura",)),
            ("Família", ("Famílias",)),
            ("Desporto", ("Desporto e movimento",)),
            ("Conversas", ("Conversas",)),
            ("Música", ("Música e clubbing",)),
        ]

        # Tipos que aparecem depois da categoria.
        kind_markers = (
            "Concerto",
            "Filme",
            "Exposição",
            "Oficina",
            "Aula",
            "Dança",
            "Teatro",
            "Performance",
            "Leitura",
            "Festa",
            "Palestra",
            "Conversa",
            "Provas",
            "Escuta",
            "Comédia",
            "Ar livre",
        )

        category_pos = None
        category_marker = ""

        for category_name, markers in category_markers:
            for marker in markers:
                match_category = re.search(
                    r"\b" + re.escape(marker) + r"\b",
                    value,
                    re.I,
                )

                if (
                    match_category
                    and (
                        category_pos is None
                        or match_category.start() < category_pos
                    )
                ):
                    category_pos = match_category.start()
                    category_marker = match_category.group(0)
                    category = category_name

        # Tudo antes da categoria contém título +
        # eventualmente uma pequena descrição.
        if category_pos is not None:
            before_category = value[:category_pos].strip()
            after_category = value[
                category_pos + len(category_marker):
            ].strip()
        else:
            before_category = value
            after_category = ""

        # O título é a primeira parte relevante.
        # A Agenda Porto usa frequentemente "..." quando
        # o título apresentado no cartão é truncado.
        title = before_category.strip()
        event_url = source

        # Remove etiquetas ocasionais do início/fim.
        title = re.sub(
            r"^(?:Gratuito|Pago)\s+",
            "",
            title,
            flags=re.I,
        ).strip()

        if (
            not title
            or len(title) < 3
            or len(title) > 180
        ):
            index += consumed
            continue

        # Depois da categoria procuramos o tipo.
        for kind in kind_markers:
            match_kind = re.search(
                r"\b" + re.escape(kind) + r"\b",
                after_category,
                re.I,
            )

            if match_kind:
                event_kind = match_kind.group(0)

                after_category = after_category[
                    match_kind.end():
                ].strip()

                break

        # Remove indicação de preço antes do local.
        after_category = re.sub(
            r"^(?:Gratuito|Pago)\s+",
            "",
            after_category,
            flags=re.I,
        ).strip()

        # O que sobra depois de categoria/tipo é,
        # normalmente, o local do evento.
        
        venue = clean(
            after_category,
            100,
                )

        # Evita locais claramente inválidos.
        if venue.casefold() in {
            "gratuito",
            "pago",
            "evento",
        }:
            venue = ""

        description = ""

        # Mantemos o tipo específico junto da categoria
        # quando ele acrescenta informação útil.
        if event_kind:
            description = event_kind

        
        events.append(
            make_event(
                name=title,
                area=area,
                city=city,
                venue=venue,
                event_type=category,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                desc=description,
                url=event_url,
                source=source,
            )
        )

        index += consumed

    matched_links = sum(1 for event in events if event.get("url") != source)
    print(f"Porto: {matched_links} eventos com link individual.")

    context_matches = 0

for event in events:
    event_slug = porto_slug(event.get("name", ""))

    if event_slug and any(
        event_slug in porto_slug(context)
        for _, context in event_contexts
    ):
        context_matches += 1

        print(f"Porto: {context_matches} títulos encontrados nos contextos.")
    
        events = dedupe(events)

        print(
        f"Porto: {len(events)} eventos extraídos da agenda."
        )

        return events


def parse_aveiro():
    area = "Aveiro"
    city = "Aveiro"
    base = SOURCES[area]["url"]

    today = date.today()

    month_urls = []

    for offset in range(0, 3):
        month = (
            today.replace(day=1)
            + timedelta(days=32 * offset)
        ).replace(day=1)

        month_urls.append(
            base
            + "?events_calendar_list_7_month="
            + month.strftime("%Y%m")
        )

    event_links = []
    events = []

    for month_url in month_urls:
        try:
            html = fetch(month_url)
        except Exception as error:
            print(
                f"AVISO Aveiro: {error}",
                file=sys.stderr,
            )
            continue

        events.extend(
            jsonld_events(
                area,
                city,
                base,
                html,
            )
        )

        for url, label in links_from_html(html, base):
            low = url.lower()

            if "/agenda-aveiro/evento/" in low:
                event_links.append((url, label))

    unique_links = {}
    for url, label in event_links:
        unique_links[url] = label

    for url, link_name in list(unique_links.items())[:100]:
        try:
            page = fetch(
                url,
                timeout=15,
                attempts=1,
            )
        except Exception:
            continue

        structured = jsonld_events(
            area,
            city,
            base,
            page,
        )

        if structured:
            events.extend(structured)
            continue

        plain = text(page)
        dates = extract_dates(plain)

        if not dates:
            continue

        start, end = dates

        title = extract_title(page) or link_name

        category = extract_aveiro_category(plain)
        venue = extract_aveiro_venue(page)
        description = extract_description(page)

        events.append(
            make_event(
                title,
                area,
                city,
                venue,
                category,
                start,
                end,
                description,
                url,
                base,
            )
        )

    return dedupe(events)


def parse_braga():
    area = "Braga"
    city = "Braga"
    source = SOURCES[area]["url"]

    try:
        html = fetch(
            source,
            timeout=45,
            attempts=3,
        )
    except Exception as error:
        print(
            f"AVISO Braga: {error}",
            file=sys.stderr,
        )
        return []

    events = jsonld_events(
        area,
        city,
        source,
        html,
    )

    event_links = []

    for url, label in links_from_html(html, source):
        host = urlparse(url).netloc.lower()
        low = url.lower()

        if "visitbraga.travel" not in host:
           continue

        if any(
            word in low
            for word in (
                "agenda",
                "evento",
                "cultura",
                "event/",
            )
        ):
            event_links.append((url, label))

    seen = set()

    for url, link_name in event_links[:60]:
        if url in seen or url == source:
            continue

        seen.add(url)

        try:
            page = fetch(
                url,
                timeout=20,
                attempts=1,
            )
        except Exception:
            continue

        structured = jsonld_events(
            area,
            city,
            source,
            page,
        )

        if structured:
            events.extend(structured)
            continue

        dates = extract_dates(text(page))

        if not dates:
            continue

        start, end = dates
        title = extract_title(page) or link_name

        if len(title) < 3:
            continue

        events.append(
            make_event(
                title,
                area,
                city,
                extract_meta(
                    page,
                    ("location", "venue", "local"),
                ),
                extract_meta(
                    page,
                    ("category", "categoria"),
                ) or "Evento",
                start,
                end,
                extract_braga_description(page),
                url,
                source,
            )
        )

    return dedupe(events)

def extract_title(html):
    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title',
        r"<h1[^>]*>(.*?)</h1>",
        r"<title[^>]*>(.*?)</title>",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            html,
            re.I | re.S,
        )

        if match:
            value = clean(match.group(1), 120)

            value = re.sub(
                r"\s*[|\-–]\s*(Agenda Porto|Câmara.*)$",
                "",
                value,
                flags=re.I,
            ).strip()

            if value:
                return value

    return ""

def extract_braga_description(html):
    # Primeiro tenta a descrição Open Graph,
    # que no Visit Braga tende a ser a mais limpa.
    match = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I | re.S,
    )

    if match:
        value = clean(match.group(1), 180)
        if value:
            return value

    # Se não existir, procura parágrafos e ignora
    # elementos típicos da navegação do Visit Braga.
    paragraphs = re.findall(
        r"<p[^>]*>(.*?)</p>",
        html,
        re.I | re.S,
    )

    ignore = (
        "o que visitar",
        "o que fazer",
        "o que comer",
        "visit braga",
        "meet braga",
        "monumentos",
        "espaços culturais",
        "arte urbana",
        "praias fluviais",
    )

    for paragraph in paragraphs:
        value = clean(paragraph, 180)
        value = re.sub(
            r"^Adicionar aos favoritos\s*",
            "",
            value,
            flags=re.I,
        ).strip()

        if len(value) < 35:
            continue

        low = value.casefold()

        if any(term in low for term in ignore):
            continue

        return value

    return ""

def extract_description(html):
    patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            html,
            re.I | re.S,
        )

        if match:
            value = clean(match.group(1), 180)
            if value:
                return value

    paragraphs = re.findall(
        r"<p[^>]*>(.*?)</p>",
        html,
        re.I | re.S,
    )

    for paragraph in paragraphs:
        value = clean(paragraph, 180)

        if len(value) >= 35:
            return value

    return ""


def extract_meta(html, names):
    for name in names:
        patterns = [
            rf'<meta[^>]+(?:name|property)=["\'][^"\']*{re.escape(name)}[^"\']*["\'][^>]+content=["\']([^"\']+)',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'][^"\']*{re.escape(name)}',
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                html,
                re.I | re.S,
            )

            if match:
                return clean(match.group(1), 100)

    return ""


def extract_dates(value):
    # Primeiro procura datas ISO.
    iso_dates = []

    for year, month, day in re.findall(
        r"\b(20\d{2})-(\d{2})-(\d{2})\b",
        value,
    ):
        try:
            parsed = date(
                int(year),
                int(month),
                int(day),
            )

            if parsed not in iso_dates:
                iso_dates.append(parsed)

        except ValueError:
            pass

    if iso_dates:
        iso_dates.sort()
        return (
            iso_dates[0].isoformat(),
            iso_dates[-1].isoformat(),
        )

    # Formato português:
    # 07 a 10 Out 2026
    range_match = re.search(
        r"\b(\d{1,2})\s*(?:a|–|-)\s*"
        r"(\d{1,2})\s+"
        r"([A-Za-zÀ-ÿ]+)\s+(20\d{2})",
        value,
        re.I,
    )

    if range_match:
        d1, d2, month_name, year = range_match.groups()
        month = MONTHS.get(
            month_name.lower().rstrip(".")
        )

        if month:
            try:
                first = date(
                    int(year),
                    month,
                    int(d1),
                )
                last = date(
                    int(year),
                    month,
                    int(d2),
                )
                return first.isoformat(), last.isoformat()
            except ValueError:
                pass

    single_match = re.search(
        r"\b(\d{1,2})\s+"
        r"([A-Za-zÀ-ÿ]+)\s+(20\d{2})",
        value,
        re.I,
    )

    if single_match:
        day, month_name, year = single_match.groups()
        month = MONTHS.get(
            month_name.lower().rstrip(".")
        )

        if month:
            try:
                parsed = date(
                    int(year),
                    month,
                    int(day),
                )
                return (
                    parsed.isoformat(),
                    parsed.isoformat(),
                )
            except ValueError:
                pass

    # Formato Visit Braga: "9 OUT. | 17h00"
    no_year_match = re.search(
        r"\b(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\.?",
        value,
        re.I,
    )

    if no_year_match:
        day, month_name = no_year_match.groups()
        month = MONTHS.get(
            month_name.lower().rstrip(".")
        )

        if month:
            try:
                today = date.today()
                parsed = date(
                    today.year,
                    month,
                    int(day),
                )

                # Se a data já passou claramente, assume o ano seguinte.
                if parsed < today:
                    parsed = date(
                        today.year + 1,
                        month,
                        int(day),
                    )

                return (
                    parsed.isoformat(),
                    parsed.isoformat(),
                )
            except ValueError:
                pass
    
    return None


def extract_aveiro_category(value):
    categories = [
        "Festivais",
        "Festas, Feiras e Mercados",
        "Exposições",
        "Música",
        "Teatro",
        "Cinema",
        "Desporto",
        "Visitas Guiadas",
        "Palestras e Conferências",
        "Infantojuvenil",
        "Livros e Leituras",
        "Ambiente",
        "Conversas",
        "Oficina",
        "Multidisciplinares",
    ]

    for category in categories:
        if category.casefold() in value.casefold():
            return category

    return "Evento"


def extract_aveiro_venue(html):
    plain = text(html)

    patterns = [
        r"(Teatro Aveirense[^|]{0,80})",
        r"(ATLAS Aveiro[^|]{0,80})",
        r"(Centro de Congressos[^|]{0,80})",
        r"(Museu Arte Nova[^|]{0,80})",
        r"(Cais da Fonte Nova[^|]{0,80})",
        r"(São Jacinto[^|]{0,80})",
        r"(Marinha da Noeirinha[^|]{0,80})",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            plain,
            re.I,
        )

        if match:
            return clean(match.group(1), 100)

    return ""

def curate_tourist_events(events):
    curated = []

    hard_exclude = (
        "aula",
        "aulas",
        "curso",
        "palestra",
        "conferência",
        "clube de leitura",
        "clube de poesia",
        "yoga",
        "tricot",
        "encadernação",
        "encadernacao",
        "oficina",
        "workshop",
        "visita orientada",
        "sessão de escuta",
        "sessao de escuta",
        "sessão de cinema",
        "sessao de cinema",
        "jam session",
        "agenda braga",
    )

    for event in events:
        name = str(event.get("name", "")).casefold()
        event_type = str(event.get("type", "")).casefold()
        desc = str(event.get("desc", "")).casefold()
        area = str(event.get("area", "")).casefold()
        is_braga = area == "braga"

        # Não usamos venue na seleção:
        # os locais recolhidos ainda não são suficientemente fiáveis.
        search_text = f"{name} {event_type} {desc}"

        if not is_braga and any(term in search_text for term in hard_exclude):
          continue

        score = 0

        # Braga: a agenda oficial usa categorias pouco específicas,
        # por isso damos prioridade a eventos reais com interesse turístico.
        if is_braga:
            if any(
                term in search_text
                for term in (
                    "música",
                    "musica",
                    "concerto",
                    "orquestra",
                    "festival",
                    "trilho",
                    "natureza",
                    "exposição",
                    "exposicao",
                    "teatro",
                    "performance",
                    "dança",
                    "danca",
                    "caminhada",
                    "percurso",
                    "pedestre",
                    "sobreposta",
                    "verde",
                )
            ):
                score += 3

        # Eventos com interesse turístico forte
        if any(
            term in name
            for term in (
                "festival",
                "fimp",
                "feira",
                "romaria",
                "são joão",
                "sao joao",
                "passagem de ano",
                "city race",
                "vinhos à prova",
                "vinhos a prova",
            )
        ):
            score += 4

        # Música ao vivo
        if event_type == "concerto" or desc == "concerto":
            score += 3

        if any(
            term in name
            for term in (
                "concerto",
                "fado",
                "orquestra",
                "rui veloso",
            )
        ):
            score += 3

        # Gastronomia e vinho
        if any(
            term in search_text
            for term in (
                "prova de vinhos",
                "vinhos à prova",
                "vinhos a prova",
                "degustação",
                "degustacao",
                "gastronomia",
            )
        ):
            score += 4

        # Desporto com potencial para visitante
        if any(
            term in search_text
            for term in (
                "city race",
                "maratona",
                "triatlo",
                "corrida",
            )
        ):
            score += 4

        # Exposições têm algum interesse,
        # mas não entram apenas por serem exposições.
        if "exposição" in search_text or "exposicao" in search_text:
            score += 1

        # Eventos muito locais/específicos perdem prioridade
        if any(
            term in search_text
            for term in (
                "coro",
                "microvolumes",
                "projeto musical",
                "projecto musical",
                "fotografia e tropicalidade",
            )
        ):
            score -= 2

        # Cinema normal não é prioridade turística.
        if "cinema" in search_text or "filme" in search_text:
            score -= 3

        # Evita encher a agenda com vários espetáculos
        # individuais do FIMP. Mantemos o festival principal.
        if (
            ("fimp'26" in name or "festival internacional de marionetas" in name)
            and not name.startswith("fimp")
        ):
            score -= 2
        
        if score < 3:
            continue

        # Classificação final
        if is_braga and any(
            term in search_text
            for term in (
                "música",
                "musica",
                "concerto",
                "orquestra",
            )
        ):
            event["type"] = "Música"

        elif is_braga and any(
            term in search_text
            for term in (
                "trilho",
                "caminhada",
                "percurso",
                "pedestre",
            )
        ):
            event["type"] = "Festas & Cultura"

        elif is_braga and any(
            term in search_text
            for term in (
                "exposição",
                "exposicao",
                "exposições",
                "exposicoes",
            )
        ):
            event["type"] = "Festas & Cultura"
        
        elif any(
            term in search_text
            for term in (
                "prova de vinhos",
                "vinhos à prova",
                "vinhos a prova",
                "degustação",
                "degustacao",
                "gastronomia",
            )
        ):
            event["type"] = "Gastronomia"

        elif any(
            term in search_text
            for term in (
                "city race",
                "maratona",
                "triatlo",
                "corrida",
            )
        ):
            event["type"] = "Desporto"

        elif (
            event_type == "concerto"
            or desc == "concerto"
            or any(
                term in name
                for term in (
                    "concerto",
                    "fado",
                    "orquestra",
                    "rui veloso",
                )
            )
        ):
            event["type"] = "Música"

        elif any(
            term in name
            for term in (
                "festival",
                "fimp",
                "feira",
                "romaria",
                "são joão",
                "sao joao",
                "passagem de ano",
            )
        ):
            event["type"] = "Festas & Cultura"

        else:
            event["type"] = "Outros"

        # Enquanto os locais não forem fiáveis,
        # é preferível não mostrar informação errada.
        event["venue"] = ""

        curated.append(event)

    return curated
    
def dedupe(events):
    grouped = {}

    for event in events:
        if (
            not event.get("name")
            or not event.get("start")
            or not event.get("end")
        ):
            continue

        # Normaliza o nome para conseguir reconhecer
        # o mesmo evento em dias diferentes.
        normalized_name = re.sub(
            r"\s+",
            " ",
            event["name"].casefold(),
        ).strip()

        normalized_venue = re.sub(
            r"\s+",
            " ",
            (event.get("venue") or "").casefold(),
        ).strip()

        key = (
            normalized_name,
            event.get("area", ""),
            normalized_venue,
        )

        old = grouped.get(key)

        if old is None:
            grouped[key] = event.copy()
            continue

        try:
            old_start = date.fromisoformat(old["start"])
            old_end = date.fromisoformat(old["end"])
            new_start = date.fromisoformat(event["start"])
            new_end = date.fromisoformat(event["end"])
        except (ValueError, TypeError):
            continue

        # Só juntamos ocorrências suficientemente próximas.
        # Isto evita unir, por exemplo, duas edições do mesmo
        # evento separadas por vários meses.
        earliest = min(old_start, new_start)
        latest = max(old_end, new_end)

        if (latest - earliest).days > 31:
            separate_key = (
                normalized_name,
                event.get("area", ""),
                normalized_venue,
                event["start"],
            )

            grouped[separate_key] = event.copy()
            continue

        old["start"] = earliest.isoformat()
        old["end"] = latest.isoformat()

        # Mantém o registo que tiver a informação mais útil.
        for field in (
            "venue",
            "type",
            "desc",
            "url",
            "source",
        ):
            if (
                not old.get(field)
                and event.get(field)
            ):
                old[field] = event[field]

        # Atualiza também a etiqueta de data.
        if earliest == latest:
            old["date"] = date_label(
                earliest.isoformat(),
                latest.isoformat(),
            )
        else:
            old["date"] = date_label(
                earliest.isoformat(),
                latest.isoformat(),
            )

    return list(grouped.values())


def load_existing():
    if not OUT.exists():
        return []

    try:
        data = json.loads(
            OUT.read_text(encoding="utf-8")
        )
        return data.get("events", [])
    except Exception:
        return []


def main():
    today = date.today()
    cutoff = today + timedelta(days=90)

    collectors = {
        "Porto": parse_porto,
        "Aveiro": parse_aveiro,
        "Braga": parse_braga,
    }

    collected = []
    successful_areas = []

    for area, collector in collectors.items():
        try:
            events = collector()

            future = []

            for event in events:
                try:
                    end = date.fromisoformat(event["end"])
                    start = date.fromisoformat(event["start"])
                except Exception:
                    continue

                if end < today:
                    continue

                if start > cutoff:
                    continue

                future.append(event)

            future = dedupe(future)
            future = curate_tourist_events(future)

            print(
                f"{area}: {len(future)} eventos futuros encontrados."
            )

            if future:
                successful_areas.append(area)
                collected.extend(future)

        except Exception as error:
            print(
                f"AVISO {area}: {error}",
                file=sys.stderr,
            )

    # Se uma cidade falhar, preservamos os eventos futuros
    # dessa cidade que já existiam no ficheiro.
    existing = load_existing()

    for event in existing:
        area = event.get("area")

        if area in successful_areas:
            continue

        try:
            if date.fromisoformat(event["end"]) >= today:
                collected.append(event)
        except Exception:
            continue

    collected = dedupe(collected)

    collected.sort(
        key=lambda event: (
            event["start"],
            event["area"],
            event["name"].casefold(),
        )
    )

    # Proteção final contra uma recolha defeituosa.
    if len(collected) < 3:
        print(
            "Recolha insuficiente. events.json foi preservado.",
            file=sys.stderr,
        )
        return 0

    payload = {
        "updated": today.isoformat(),
        "events": collected,
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"TOTAL: {len(collected)} eventos guardados."
    )

    if successful_areas:
        print(
            "Fontes atualizadas: "
            + ", ".join(successful_areas)
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
