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
        "url": (
            "https://www.cm-braga.pt/pt/0502/viver/"
            "cultura-e-patrimonio/dinamizacao-cultural/"
            "agenda-cultural-de-braga"
        ),
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

    events = []

    # Primeiro aproveitamos qualquer Event em JSON-LD.
    events.extend(
        jsonld_events(
            area,
            city,
            source,
            html,
        )
    )

    # A Agenda Porto apresenta os eventos diretamente
    # na página principal. Cada cartão começa pelo local
    # e contém data, título, descrição e categoria.
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

    # Divide o texto usando datas do tipo "06 Out".
    pattern = re.compile(
        r"\b(0?[1-9]|[12]\d|3[01])\s+"
        r"(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez)\b",
        re.I,
    )

    matches = list(pattern.finditer(raw))

    print(
        f"Porto: {len(matches)} datas encontradas na agenda."
    )

    for index, match in enumerate(matches):
        day = int(match.group(1))
        month = months[match.group(2).lower()]

        year = today.year

        try:
            start_date = date(
                year,
                month,
                day,
            )
        except ValueError:
            continue

        # Se a data já ficou muito para trás,
        # assume que pertence ao ano seguinte.
        if start_date < today - timedelta(days=30):
            try:
                start_date = date(
                    year + 1,
                    month,
                    day,
                )
            except ValueError:
                continue

        end_pos = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else min(len(raw), match.end() + 700)
        )

        block = raw[
            match.end():end_pos
        ].strip()

                lines = [
            clean(line, 180)
            for line in block.splitlines()
            if clean(line, 180)
        ]

        if not lines:
            continue

        # Remove elementos de interface e etiquetas que
        # não fazem parte do nome do evento.
        ignored = {
            "gratuito",
            "pago",
            "evento",
            "hoje",
            "próximos eventos",
            "saber mais",
            "ver evento",
        }

        useful = [
            line
            for line in lines
            if line.casefold() not in ignored
        ]

        if not useful:
            continue

        # Categorias/tipos usados pela Agenda Porto.
        category_terms = (
            "música e clubbing",
            "cinema",
            "artes visuais",
            "palcos",
            "literatura",
            "famílias",
            "desporto",
            "conversas",
            "dança",
            "exposições",
            "concerto",
            "filme",
            "exposição",
            "performance",
            "teatro",
        )

        # Remove categoria/tipo do final do texto para
        # impedir que entre no título.
        cleaned_lines = []

        for line in useful:
            value = line.strip()

            for term in category_terms:
                value = re.sub(
                    r"\s+" + re.escape(term) + r"\s*$",
                    "",
                    value,
                    flags=re.I,
                ).strip()

            if value:
                cleaned_lines.append(value)

        if not cleaned_lines:
            continue

        title = cleaned_lines[0]

        if (
            len(title) < 3
            or len(title) > 160
        ):
            continue

        # Evita usar novamente o título como descrição.
        description = ""

        for candidate in cleaned_lines[1:]:
            if (
                candidate.casefold() != title.casefold()
                and len(candidate) >= 15
            ):
                description = candidate
                break

        # Determina a categoria usando primeiro as
        # etiquetas originais do cartão.
        category = "Evento"
        block_lower = block.casefold()

        category_map = [
            ("Cinema", ("cinema", "filme")),
            ("Teatro", ("palcos", "teatro", "performance")),
            ("Exposição", ("artes visuais", "exposição")),
            ("Dança", ("dança", "danca")),
            ("Literatura", ("literatura", "livro")),
            ("Família", ("famílias", "familia", "crianças")),
            ("Desporto", ("desporto", "movimento")),
            ("Conversas", ("conversas", "palestra")),
            ("Música", ("música", "musica", "clubbing", "concerto")),
        ]

        for category_name, words in category_map:
            if any(
                word.casefold() in block_lower
                for word in words
            ):
                category = category_name
                break

        events.append(
            make_event(
                name=title,
                area=area,
                city=city,
                venue="",
                event_type=category,
                start=start_date.isoformat(),
                end=start_date.isoformat(),
                desc=description,
                url=source,
                source=source,
            )
        )

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

        if "cm-braga.pt" not in host:
            continue

        if any(
            word in low
            for word in (
                "agenda",
                "evento",
                "cultura",
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
                extract_description(page),
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
