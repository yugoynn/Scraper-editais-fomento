# -*- coding: utf-8 -*-
"""
Scraper das Chamadas e Editais ABERTOS — FAPEMIG
https://fapemig.br/oportunidades/chamadas-e-editais?status=aberta

Como o site funciona:
  - A LISTAGEM é um app Vue/Nuxt: os cards são montados por JavaScript, então
    o requests sozinho não os vê. Renderizamos a listagem com Playwright só
    para colher os links do "Saiba mais".
  - As PÁGINAS DE DETALHE são renderizadas no servidor (SSR): o requests lê
    título, prazo e descrição normalmente.

Saída padronizada (dados/fapemig/): site, titulo, prazo, link, resumo, coletado_em

Instalação:
    pip install requests beautifulsoup4 lxml playwright
    playwright install chromium

Uso:
    python fapemig.py
    python fapemig.py --show          # abre o navegador na renderização
    python fapemig.py --debug
    python fapemig.py --out /caminho/pasta
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo
except ImportError:  # execução direta: python scrappers/Sfapemig.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo

SITE = "FAPEMIG"
BASE = "https://fapemig.br/"
LISTA_URL = "https://fapemig.br/oportunidades/chamadas-e-editais?status=aberta"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

RX_PRAZO = re.compile(
    r"limite\s+para\s+submiss[\u00e3a]o\s*:?\s*"
    r"(fluxo\s+cont[\u00edi]nuo|\d{1,2}\s+de\s+[a-z\u00e7]+\.?\s+de\s+\d{4})",
    re.I)

PREFIXO_DETALHE = "/oportunidades/chamadas-e-editais/"


def limpar(t):
    t = (t or "").replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"[ \t\r\n]+", " ", t).strip()


def default_out_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(script_dir), "dados", "fapemig")


def eh_link_detalhe(href):
    p = urlparse(href).path
    if not p.startswith(PREFIXO_DETALHE):
        return False
    return bool(p[len(PREFIXO_DETALHE):].strip("/"))


# --------------------------------------------------------------------------- #
# LISTAGEM (render com Playwright)
# --------------------------------------------------------------------------- #
def render_listagem(headless=True, debug=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright não instalado. Rode:\n"
                           "    pip install playwright\n"
                           "    playwright install chromium")
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=headless)
        pag = nav.new_page(user_agent=HEADERS["User-Agent"])
        pag.goto(LISTA_URL, wait_until="domcontentloaded", timeout=45000)
        try:
            pag.wait_for_selector(
                "a[href*='/oportunidades/chamadas-e-editais/']", timeout=15000)
        except Exception:
            pass
        html = pag.content()
        nav.close()
    if debug:
        print(f"[render] HTML final: {len(html)} chars")
    return html


def links_da_listagem(html):
    sopa = BeautifulSoup(html, "html.parser")
    vistos = []
    for a in sopa.find_all("a", href=True):
        href = urljoin(BASE, a["href"].strip())
        if eh_link_detalhe(href) and href not in vistos:
            vistos.append(href)
    return vistos


# --------------------------------------------------------------------------- #
# DETALHE (SSR, requests)
# --------------------------------------------------------------------------- #
def extrair_descricao(sopa):
    el = sopa.select_one(".call-details__text")
    if el:
        t = limpar(el.get_text(" "))
        if t:
            return t
    for h in sopa.find_all(["h2", "h3", "h4"]):
        if re.search(r"descri[\u00e7c][\u00e3a]o\s+da\s+chamada",
                     limpar(h.get_text()), re.I):
            for nxt in h.find_all_next(["p", "div"]):
                t = limpar(nxt.get_text(" "))
                if len(t) >= 40:
                    return t
    el = sopa.select_one(".wordpress-content")
    return limpar(el.get_text(" ")) if el else ""


def extrair_prazo(sopa):
    m = RX_PRAZO.search(sopa.get_text("\n"))
    if m:
        return limpar(m.group(1))
    for sp in sopa.find_all(["span", "div", "p", "li"]):
        t = limpar(sp.get_text(" "))
        if re.search(r"limite\s+para\s+submiss", t, re.I):
            return re.sub(r".*?limite\s+para\s+submiss[\u00e3a]o\s*:?\s*", "",
                          t, flags=re.I).strip()
    return ""


def extrair_detalhe(url, sessao, debug=False):
    r = sessao.get(url, headers=HEADERS, timeout=30)
    sopa = BeautifulSoup(r.text, "html.parser")

    h1 = sopa.find("h1")
    titulo = limpar(h1.get_text(" ")) if h1 else ""
    if not titulo:
        og = sopa.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            titulo = limpar(og["content"])

    prazo = extrair_prazo(sopa)
    descricao = extrair_descricao(sopa)

    if debug:
        print("-" * 66)
        print("titulo   :", titulo[:80])
        print("prazo    :", repr(prazo))
        print("descricao:", descricao[:160])

    return {"titulo": titulo, "prazo": prazo or "não informado",
            "resumo": descricao, "conteudo": limpar(sopa.get_text(" "))[:30000],
            "link": r.url}


# --------------------------------------------------------------------------- #
def scrape(out_dir, headless=True, delay=0.6, debug=False, progresso=None):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "editais.json")
    cache_anterior = cache_do_arquivo(json_path)
    reutilizados = 0
    print("Renderizando a listagem (status=aberta)...")
    html = render_listagem(headless=headless, debug=debug)
    links = links_da_listagem(html)
    print(f"{len(links)} chamadas abertas encontradas.\n")

    sessao = requests.Session()
    resultados = []
    for i, link in enumerate(links, 1):
        anterior = cache_anterior.buscar(link, "")
        if anterior and tem_conteudo(anterior, "resumo", "conteudo"):
            d = {
                "titulo": anterior.get("titulo", ""),
                "prazo": anterior.get("prazo", "não informado"),
                "resumo": anterior.get("resumo", ""),
                "conteudo": anterior.get("conteudo", ""),
                "link": link,
            }
            reutilizados += 1
            print(f"  [{i}] [PULADO] Detalhe já coletado; usando cache local.")
        else:
            try:
                d = extrair_detalhe(link, sessao, debug=debug)
            except Exception as e:
                print(f"  [{i}] ERRO em {link}: {e}")
                d = {"titulo": "", "prazo": "não informado", "resumo": "", "conteudo": "", "link": link}
        resultados.append({
            "site": SITE,
            "titulo": d["titulo"],
            "prazo": d["prazo"],
            "link": d["link"],
            "resumo": d["resumo"],
            "conteudo": d.get("conteudo", ""),
            "coletado_em": data_coleta_antiga(anterior)
                or datetime.now().isoformat(timespec="seconds"),
        })
        print(f"  [{i}/{len(links)}] {d['titulo'][:55]} | {d['prazo']}")
        if progresso:
            progresso(
                processados=i,
                total=len(links),
                coletados=len(resultados),
                erros=0,
                item=d.get("titulo", ""),
                etapa="detalhes",
            )
        time.sleep(delay)

    salvar(out_dir, resultados)
    print(f"Detalhes reaproveitados do cache: {reutilizados}")
    return resultados


def salvar(out_dir, resultados):
    campos = ["site", "titulo", "prazo", "link", "resumo", "coletado_em"]
    json_path = os.path.join(out_dir, "editais.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 60 + "\nRESUMO\n" + "=" * 60)
    print(f"Editais coletados: {len(resultados)}")
    print(f"JSON: {os.path.abspath(json_path)}")


def main():
    ap = argparse.ArgumentParser(description="Scraper FAPEMIG (chamadas abertas)")
    ap.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    ap.add_argument("--show", action="store_true", help="abre o navegador")
    ap.add_argument("--delay", type=float, default=0.6, help="pausa (s) entre editais")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    scrape(args.out, headless=not args.show, delay=args.delay, debug=args.debug)


if __name__ == "__main__":
    main()
