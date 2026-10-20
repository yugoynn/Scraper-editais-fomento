#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scraper do Radar de Oportunidades do Observatório Sebrae Startups.

Este scraper salva SOMENTE JSON em dados/sebrae/oportunidades.json.
Ele não gera CSV nem Excel. A planilha consolidada é criada apenas pela
função de exportação do sistema.
"""

import argparse
import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse, urljoin

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga
except ImportError:  # execução direta: python scrappers/Ssebrae.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga

SITE = "Sebrae Startups"
URL = "https://observatorio.sebraestartups.com.br/pt-br/oportunidades"
FINEP_DOMAIN = "finep.gov.br"
FINEP_TITLE = re.compile(r"\bfinep\b", re.I)


def default_out_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, "dados", "sebrae")


EXTRACT_JS = r"""
() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const anchors = Array.from(document.querySelectorAll('a'))
    .filter(a => norm(a.textContent).toLowerCase() === 'ler mais');

  const cards = [];
  for (const a of anchors) {
    let card = a, hops = 0;
    while (card && hops < 8) {
      if (card.querySelector && card.querySelector('h2, h3')) break;
      card = card.parentElement;
      hops++;
    }
    if (!card) continue;

    const h = card.querySelector('h2, h3');
    const titulo = norm(h ? h.textContent : '');
    const href = a.getAttribute('href') || '';

    let body = norm(card.textContent);
    if (titulo && body.startsWith(titulo)) {
      body = body.slice(titulo.length).trim();
    }

    let prazo = '';
    const pm = body.match(/Prazo de inscri[cç][aã]o:\s*(.*?)\s*Ler mais/i);
    if (pm) prazo = pm[1].trim();

    let resumo = body;
    const idx = body.search(/Prazo de inscri[cç][aã]o:/i);
    if (idx >= 0) resumo = body.slice(0, idx).trim();
    resumo = resumo.replace(/\s*Ler mais\s*$/i, '').trim();

    cards.push({ titulo, resumo, prazo, link: href });
  }
  return cards;
}
"""



def normalizar_link(link):
    valor = (link or "").strip()
    if not valor:
        return ""

    match_http = re.search(r"https?://[^\\\s]+", valor, re.I)
    if match_http:
        return match_http.group(0)

    match_www = re.search(r"www\.[^\\\s]+", valor, re.I)
    if match_www:
        return "https://" + match_www.group(0)

    if valor.startswith("/"):
        return urljoin(URL, valor)

    return valor

def is_finep(card):
    host = urlparse(card.get("link", "")).netloc.lower()
    return FINEP_DOMAIN in host or bool(FINEP_TITLE.search(card.get("titulo", "")))


def read_page_indicator(page):
    try:
        txt = page.locator("text=/\\d+\\s+de\\s+\\d+/").first.inner_text(timeout=3000)
        match = re.search(r"(\d+)\s+de\s+(\d+)", txt)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return None, None


def dismiss_popups(page):
    for label in ["Dispensar", "Aceitar", "Aceito", "Fechar", "OK"]:
        try:
            btn = page.get_by_text(label, exact=True)
            if btn.count() > 0:
                btn.first.click(timeout=1500)
                page.wait_for_timeout(300)
        except Exception:
            pass


def go_next_page(page):
    for name in ["Ir para próxima página", "Próxima página", "Next"]:
        try:
            btn = page.get_by_role("button", name=name)
            if btn.count() == 0:
                btn = page.get_by_text(name, exact=True)
            if btn.count() > 0:
                target = btn.first
                if target.is_disabled():
                    return False
                target.click(timeout=3000)
                return True
        except Exception:
            continue

    try:
        el = page.locator("[aria-label*='próxima' i], [aria-label*='next' i]").first
        if el.count() > 0 and not el.is_disabled():
            el.click(timeout=3000)
            return True
    except Exception:
        pass

    return False


def scrape(out_dir=None, headless=True, max_pages=50, delay=1.0, progresso=None):
    """Coleta as oportunidades e grava somente oportunidades.json."""
    if out_dir is None:
        out_dir = default_out_dir()

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError as erro:
        raise RuntimeError(
            "Playwright não está instalado. Execute: pip install playwright && playwright install chromium"
        ) from erro

    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "oportunidades.json")
    cache_anterior = cache_do_arquivo(json_path)
    reutilizados = 0

    todos = []
    vistos = set()
    finep_descartados = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        print(f"Abrindo {URL}")
        page.goto(URL, wait_until="networkidle", timeout=60000)
        dismiss_popups(page)

        try:
            page.wait_for_selector("text=Ler mais", timeout=15000)
        except PWTimeout:
            browser.close()
            raise RuntimeError("Não encontrei cards de oportunidades no site do Sebrae.")

        _, total = read_page_indicator(page)
        total = total or max_pages
        print(f"Total de páginas detectado: {total}")

        pagina = 1
        while pagina <= max_pages:
            page.wait_for_timeout(int(delay * 1000))
            cards = page.evaluate(EXTRACT_JS)
            novos = 0

            for card in cards:
                chave = (card.get("titulo", ""), card.get("link", ""))
                if chave in vistos:
                    continue

                vistos.add(chave)

                card["link"] = normalizar_link(card.get("link", ""))

                if is_finep(card):
                    finep_descartados += 1
                    continue

                card["site"] = SITE
                anterior = cache_anterior.buscar(card.get("link", ""), card.get("titulo", ""))
                if anterior:
                    card["coletado_em"] = data_coleta_antiga(anterior) \
                        or datetime.now().isoformat(timespec="seconds")
                    reutilizados += 1
                else:
                    card["coletado_em"] = datetime.now().isoformat(timespec="seconds")
                todos.append(card)
                novos += 1

                if progresso:
                    progresso(
                        processados=len(todos),
                        total=None,
                        coletados=len(todos),
                        erros=0,
                        item=card.get("titulo", ""),
                        etapa=f"pagina_{pagina}",
                    )

            atual, total_now = read_page_indicator(page)
            total = total_now or total

            print(
                f"[página {atual or pagina}/{total}] "
                f"{len(cards)} cards | {novos} novos não-FINEP"
            )

            if atual is not None and total is not None and atual >= total:
                break

            primeiro_titulo = cards[0].get("titulo", "") if cards else ""
            if not go_next_page(page):
                print("Não há botão de próxima página; encerrando.")
                break

            try:
                page.wait_for_function(
                    """(prev) => {
                        const a = Array.from(document.querySelectorAll('a'))
                          .find(x => x.textContent.trim().toLowerCase() === 'ler mais');
                        if (!a) return false;
                        let card = a, hops = 0;
                        while (card && hops < 8) {
                          if (card.querySelector && card.querySelector('h2,h3')) break;
                          card = card.parentElement; hops++;
                        }
                        const h = card && card.querySelector('h2,h3');
                        return h && h.textContent.trim() !== prev;
                    }""",
                    arg=primeiro_titulo,
                    timeout=10000,
                )
            except PWTimeout:
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

            pagina += 1

        browser.close()

    with open(json_path, "w", encoding="utf-8") as arquivo:
        json.dump(todos, arquivo, ensure_ascii=False, indent=2)

    if progresso:
        progresso(
            processados=len(todos),
            total=len(todos),
            coletados=len(todos),
            erros=0,
            etapa="finalizado",
        )

    # Formato compatível com a tabela do Coletor.
    editais = []
    for item in todos:
        editais.append({
            "site": item.get("site", SITE),
            "titulo": item.get("titulo", ""),
            "resumo": item.get("resumo", ""),
            "prazo": item.get("prazo", ""),
            "link": item.get("link", ""),
            "pagina_edital": item.get("link", ""),
            "arquivo": "oportunidades.json",
            "coletado_em": item.get("coletado_em", ""),
        })

    print("\n" + "=" * 60)
    print("RESUMO SEBRAE")
    print("=" * 60)
    print(f"Oportunidades coletadas (não-FINEP): {len(todos)}")
    print(f"Registros já conhecidos reaproveitados: {reutilizados}")
    print(f"Cards da FINEP descartados         : {finep_descartados}")
    print(f"JSON: {os.path.abspath(json_path)}")
    print("CSV/Excel: não gerado pelo scraper")

    return {
        "sucesso": True,
        "encontrados": len(todos),
        "baixados": len(todos),
        "coletados": len(todos),
        "reutilizados": reutilizados,
        "novos": max(0, len(todos) - reutilizados),
        "erros": 0,
        "editais": editais,
        "finep_descartados": finep_descartados,
        "json": os.path.abspath(json_path),
    }


def coletar_oportunidades(out=None, delay=1.0, headless=True, max_pages=50, progresso=None):
    return scrape(
        out_dir=out,
        headless=headless,
        max_pages=max_pages,
        delay=delay,
        progresso=progresso,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Scraper de oportunidades do Observatório Sebrae Startups"
    )
    parser.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    parser.add_argument("--show", action="store_true", help="abre o navegador")
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    scrape(
        out_dir=args.out,
        headless=not args.show,
        max_pages=args.max_pages,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
