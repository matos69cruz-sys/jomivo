"""Pré-visualização conservadora da seleção JOMIVO.

Não modifica events.json nem altera o site. Só apresenta contagens e exemplos.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "events.json"
KEEP = {"PREMIUM", "RECOMENDADO", "INTERESSANTE"}
REVIEW = {"POR AVALIAR"}
EXCLUDE = {"ROTINA"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA, help="Ficheiro JSON para analisar")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    porto = [e for e in events if e.get("area") == "Porto"]
    levels = Counter(e.get("quality_level", "SEM CLASSIFICAÇÃO") for e in porto)
    selected = [e for e in porto if e.get("quality_level") in KEEP]
    review = [e for e in porto if e.get("quality_level") in REVIEW]
    excluded = [e for e in porto if e.get("quality_level") in EXCLUDE]
    unknown = [e for e in porto if e.get("quality_level") not in KEEP | REVIEW | EXCLUDE]

    print("JOMIVO PRÉ-VISUALIZAÇÃO (sem exclusões reais)")
    print(f"Total geral: {len(events)} | Porto: {len(porto)}")
    print("Classificações:", dict(sorted(levels.items())))
    print(f"Potencial seleção: {len(selected)}")
    print(f"Revisão humana: {len(review)}")
    print(f"Potencial rotina: {len(excluded)}")
    print(f"Sem classificação reconhecida: {len(unknown)}")
    # Comparar cenários sem eliminar concertos nem impor um limite artificial.
    core = [e for e in porto if e.get("quality_level") in {"PREMIUM", "RECOMENDADO"}]
    expanded = selected
    print(f"Cenário essencial (Premium + Recomendado): {len(core)}")
    print(f"Cenário alargado (+ Interessante): {len(expanded)}")
    print("Distribuição por tipo no cenário essencial:")
    for category, count in sorted(Counter(e.get("type", "Outros") for e in core).items()):
        print(f"  {category}: {count}")
    print("Eventos interessantes fora do cenário essencial (até 30):")
    for event in [e for e in porto if e.get("quality_level") == "INTERESSANTE"][:30]:
        print(f"  {event.get('start', '?')} | {event.get('type', '?')} | {event.get('name', '?')}")
    # Sinalizar experiências potencialmente valiosas que a pontuação não destacou.
    experience_terms = (
        "vinho", "vinhos", "degustação", "prova de", "gastronomia",
        "jantar", "chef", "visita guiada", "visitas guiadas",
        "percurso guiado", "rota das", "rota dos", "património",
        "experiência imersiva", "experiencia imersiva",
    )
    overlooked = [
        e for e in porto
        if e.get("quality_level") not in {"PREMIUM", "RECOMENDADO"}
        and e.get("quality_level") != "ROTINA"
        and any(
            term in (e.get("name", "") + " " + e.get("desc", "")).casefold()
            for term in experience_terms
        )
    ]
    print(f"Experiências a rever fora da seleção essencial: {len(overlooked)}")
    for event in overlooked[:30]:
        print(
            f"  {event.get('quality_level', '?')} | "
            f"{event.get('start', '?')} | {event.get('type', '?')} | "
            f"{event.get('name', '?')}"
        )
    # Diagnóstico de fontes: identificar lacunas regionais e dependência
    # excessiva de uma só agenda, sem alterar a recolha/publicação.
    from urllib.parse import urlparse
    by_area = {}
    for event in events:
        area = event.get("area", "Desconhecida")
        domain = urlparse(event.get("url", "")).netloc.lower() or "sem domínio"
        by_area.setdefault(area, Counter())[domain] += 1
    # Fontes oficiais já integradas na recolha de testes (PR), não publicadas.
    candidate_sources = {
        "Aveiro": ("Teatro Aveirense", "https://www.teatroaveirense.pt/pt/programacao/"),
        "Braga": ("Theatro Circo", "https://theatrocirco.com/"),
    }
    print("JOMIVO FONTES OFICIAIS NA RECOLHA DE TESTES:")
    for area, (venue, url) in candidate_sources.items():
        print(f"  {area}: {venue} | {url}")
    # Auditoria editorial por cidade: identificar variedade e fontes diretas.
    for area in sorted({e.get("area", "") for e in events}):
        local = [e for e in events if e.get("area") == area]
        classes = Counter(e.get("quality_level", "SEM CLASSIFICAÇÃO") for e in local)
        types = Counter(e.get("type", "Outros") for e in local)
        missing_links = sum(not e.get("url") or e.get("url") == e.get("source") for e in local)
        print(f"JOMIVO QUALIDADE {area}: {len(local)} eventos | níveis {dict(classes)}")
        print(f"JOMIVO TIPOS {area}: {dict(types.most_common(12))}")
        print(f"JOMIVO LINKS GENÉRICOS {area}: {missing_links}")
        if area == "Braga":
            circo = [e for e in local if e.get("venue") == "Theatro Circo"]
            print(f"JOMIVO BRAGA THEATRO CIRCO: {len(circo)} espetáculos com link direto")
    # Lista de revisão editorial por cidade, sem exclusão automática.
    priority_terms = (
        "vinho", "vinhos", "degustação", "prova", "jantar", "gastronomia",
        "visita guiada", "visitas guiadas", "património", "festival",
        "concerto", "espetáculo", "ópera", "teatro", "exposição",
    )
    for area in sorted({e.get("area", "") for e in events}):
        candidates = [
            e for e in events
            if e.get("area") == area and e.get("quality_level") == "POR AVALIAR"
        ]
        candidates.sort(key=lambda e: (
            -sum(term in (e.get("name", "") + " " + e.get("desc", "")).casefold()
                 for term in priority_terms),
            e.get("start", ""),
            e.get("name", "").casefold(),
        ))
        print(f"JOMIVO REVISÃO PRIORITÁRIA {area}: {len(candidates)} por avaliar")
        for e in candidates[:20]:
            print(
                f"  {e.get('start', '?')} | {e.get('type', '?')} | "
                f"{e.get('name', '?')} | {e.get('url', '')}"
            )
    print("JOMIVO COBERTURA DE FONTES:")
    for area, domains in sorted(by_area.items()):
        total = sum(domains.values())
        print(f"  {area}: {total} eventos | {len(domains)} domínio(s)")
        for domain, count in domains.most_common(8):
            print(f"    {domain}: {count}")
        if total < 15:
            print(f"  JOMIVO ALERTA COBERTURA: {area} tem menos de 15 eventos")
        if total and domains.most_common(1)[0][1] / total >= 0.9:
            print(f"  JOMIVO ALERTA CONCENTRAÇÃO: {area} depende >=90% de uma fonte")
    print("Atenção: cenário essencial é apenas diagnóstico, NÃO um filtro.")
    print("Nota: estas contagens NÃO alteram a agenda pública.")
    for title, group in (("REVER", review), ("ROTINA", excluded)):
        print(f"--- {title}: exemplos (máximo 20) ---")
        for event in group[:20]:
            print(f"  {event.get('start', '?')} | {event.get('type', '?')} | {event.get('name', '?')}")


if __name__ == "__main__":
    main()
