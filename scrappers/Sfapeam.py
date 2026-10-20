# -*- coding: utf-8 -*-
"""
Scraper dos Editais VIGENTES — FAPEAM
https://www.fapeam.am.gov.br/editais/?aba=vigentes

A listagem é montada por JavaScript, então o requests vê a página vazia.
Por isso: tenta primeiro com requests (rápido); se vier 0 cards, RENDERIZA
com Playwright e lê os cards já montados.

Saída padronizada (dados/fapeam/): site, titulo, prazo, link, resumo,
coletado_em + extras (vigencia_inicio, vigencia_fim, primeiro_paragrafo).

Instalação:
    pip install requests beautifulsoup4 lxml playwright
    playwright install chromium

Uso:
    python fapeam.py
    python fapeam.py --show          # abre o navegador na renderização
    python fapeam.py --todos         # não filtra por vigência
    python fapeam.py --sem-render    # força só requests
    python fapeam.py --debug
    python fapeam.py --out /caminho/pasta
"""

import argparse
import json
import os
import re
import time
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo
except ImportError:  # execução direta: python scrappers/Sfapeam.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo

SITE = "FAPEAM"
LISTA_URL = "https://www.fapeam.am.gov.br/editais/?aba=vigentes"
BASE = "https://www.fapeam.am.gov.br/"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

RX_VIG = re.compile(
    r"vig[\u00eae]ncia:?\s*(\d{1,2}/\d{1,2}/\d{2,4})"
    r"\s*(?:at[\u00e9e]|a|-|\u2013|\u2014)\s*(\d{1,2}/\d{1,2}/\d{2,4})",
    re.I)
RX_VIG1 = re.compile(r"vig[\u00eae]ncia:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", re.I)


def limpar(t):
    return re.sub(r"[ \t\r\n]+", " ", (t or "")).strip()


def parse_data(d):
    try:
        dd, mm, aa = [int(x) for x in d.split("/")]
        if aa < 100:
            aa += 2000
        return date(aa, mm, dd)
    except Exception:
        return None


def default_out_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(script_dir), "dados", "fapeam")


# --------------------------------------------------------------------------- #
# Baixar HTML da listagem
# --------------------------------------------------------------------------- #
def baixar_requests(url, sessao):
    r = sessao.get(url, headers=HEADERS, timeout=30)
    return r.text, r.status_code


def baixar_render(url, headless=True, debug=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright não instalado. Rode:\n"
                           "    pip install playwright\n"
                           "    playwright install chromium")
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        pagina = navegador.new_page(user_agent=HEADERS["User-Agent"])
        pagina.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            aba = pagina.get_by_text("Vigentes", exact=False).first
            if aba and aba.is_visible():
                aba.click()
                pagina.wait_for_timeout(1500)
        except Exception:
            pass
        try:
            pagina.wait_for_selector("text=/Vig[eê]ncia/i", timeout=15000)
        except Exception:
            pass
        html = pagina.content()
        navegador.close()
    if debug:
        print(f"[render] HTML final tem {len(html)} chars")
    return html


# --------------------------------------------------------------------------- #
# Parsing da listagem
# --------------------------------------------------------------------------- #
def eh_link_edital(href):
    p = urlparse(href).path.rstrip("/")
    return p.startswith("/editais/") and len(p) > len("/editais")


def achar_vigencia_no_card(a_tag):
    no = a_tag
    for _ in range(6):
        if no is None:
            break
        txt = no.get_text(" ") if hasattr(no, "get_text") else ""
        m = RX_VIG.search(txt)
        if m:
            return m.group(1), m.group(2)
        no = no.parent
    no = a_tag
    for _ in range(6):
        if no is None:
            break
        txt = no.get_text(" ") if hasattr(no, "get_text") else ""
        m = RX_VIG1.search(txt)
        if m:
            return m.group(1), ""
        no = no.parent
    return "", ""


def parse_cards(html, hoje, filtrar=True):
    sopa = BeautifulSoup(html, "html.parser")
    vistos = set()
    cards = []
    for a in sopa.find_all("a", href=True):
        href = urljoin(BASE, a["href"].strip())
        if not eh_link_edital(href) or href in vistos:
            continue
        titulo = limpar(a.get_text())
        if len(titulo) < 8:
            continue
        vig_ini, vig_fim = achar_vigencia_no_card(a)
        if filtrar:
            dfim = parse_data(vig_fim)
            if dfim and dfim < hoje:
                continue
        vistos.add(href)
        cards.append({"titulo_lista": titulo, "link": href,
                      "vig_ini": vig_ini, "vig_fim": vig_fim})
    return cards


def coletar_cards(sessao, hoje, filtrar=True, usar_render=True,
                  headless=True, debug=False):
    html, status = baixar_requests(LISTA_URL, sessao)
    cards = parse_cards(html, hoje, filtrar)
    if debug:
        print(f"[requests] status={status} len={len(html)} cards={len(cards)}")
    if cards or not usar_render:
        return cards, html, "requests"
    if debug:
        print("[requests] 0 cards -> renderizando com navegador...")
    html = baixar_render(LISTA_URL, headless=headless, debug=debug)
    cards = parse_cards(html, hoje, filtrar)
    if debug:
        print(f"[render] cards={len(cards)}")
    return cards, html, "render"


# --------------------------------------------------------------------------- #
# Parsing do detalhe
# --------------------------------------------------------------------------- #
def primeiro_p_apos(sopa, termos, min_len=40):
    tags = sopa.find_all(["h1", "h2", "h3", "h4", "h5", "h6",
                          "strong", "b", "p", "li", "span"])
    idx = -1
    casou = ""
    for termo in termos:
        rx = re.compile(termo, re.I)
        for i, t in enumerate(tags):
            if rx.search(limpar(t.get_text(" "))):
                idx = i
                casou = termo
                break
        if idx >= 0:
            break
    if idx < 0:
        return "", ""
    for t in tags[idx + 1:]:
        if t.name == "p":
            txt = limpar(t.get_text(" "))
            if len(txt) >= min_len:
                return txt, casou
    return "", casou


def extrair_detalhe(url, sessao, vig_ini="", vig_fim="",
                    usar_render=True, headless=True, debug=False):
    r = sessao.get(url, headers=HEADERS, timeout=30)
    sopa = BeautifulSoup(r.text, "html.parser")

    h1 = sopa.select_one("h1.page-title") or sopa.find("h1")
    titulo = limpar(h1.get_text(" ")) if h1 else ""

    if not titulo and usar_render:
        if debug:
            print("   [detalhe] sem h1 no requests -> renderizando...")
        html = baixar_render(url, headless=headless, debug=debug)
        sopa = BeautifulSoup(html, "html.parser")
        h1 = sopa.select_one("h1.page-title") or sopa.find("h1")
        titulo = limpar(h1.get_text(" ")) if h1 else ""

    if not titulo:
        og = sopa.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            titulo = limpar(og["content"])

    objetivo, _ = primeiro_p_apos(
        sopa, [r"objetivo\s+geral", r"objetivo", r"\bgeral\b"])

    primeiro = ""
    for p in sopa.find_all("p"):
        t = limpar(p.get_text(" "))
        if len(t) >= 40:
            primeiro = t
            break

    if debug:
        print("=" * 66)
        print("URL:", url)
        print(">> TITULO   :", repr(titulo[:110]))
        print(">> OBJETIVO :", repr(objetivo[:200]))
        print(">> 1o PARAGRAFO:", repr(primeiro[:160]))
        print(">> VIGENCIA :", vig_ini, "ate", vig_fim)
        print("=" * 66)

    return {
        "titulo": titulo,
        "vigencia_inicio": vig_ini,
        "vigencia_fim": vig_fim,
        "objetivo": objetivo,
        "primeiro_paragrafo": primeiro,
        "conteudo": limpar(sopa.get_text(" "))[:30000],
        "link": url,
    }


# --------------------------------------------------------------------------- #
def scrape(out_dir, filtrar=True, usar_render=True, headless=True,
           delay=0.8, debug=False, progresso=None):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "editais.json")
    cache_anterior = cache_do_arquivo(json_path)
    reutilizados = 0
    sessao = requests.Session()
    hoje = date.today()

    print("Lendo a listagem de editais vigentes...")
    cards, html, via = coletar_cards(sessao, hoje, filtrar=filtrar,
                                     usar_render=usar_render,
                                     headless=headless, debug=debug)
    print(f"[via {via}] Encontrados {len(cards)} editais "
          f"{'vigentes' if filtrar else '(todos)'}.\n")

    resultados = []
    for i, c in enumerate(cards, 1):
        anterior = cache_anterior.buscar(c["link"], c["titulo_lista"])
        if anterior and tem_conteudo(anterior, "objetivo", "resumo", "conteudo", "primeiro_paragrafo"):
            d = {
                "titulo": anterior.get("titulo") or c["titulo_lista"],
                "vigencia_inicio": c["vig_ini"],
                "vigencia_fim": c["vig_fim"],
                "objetivo": anterior.get("resumo") or anterior.get("objetivo", ""),
                "primeiro_paragrafo": anterior.get("primeiro_paragrafo", ""),
                "conteudo": anterior.get("conteudo", ""),
                "link": c["link"],
            }
            reutilizados += 1
            print(f"  [{i}] [PULADO] Detalhe já coletado; usando cache local.")
        else:
            try:
                d = extrair_detalhe(c["link"], sessao, vig_ini=c["vig_ini"],
                                    vig_fim=c["vig_fim"], usar_render=usar_render,
                                    headless=headless, debug=debug)
            except Exception as e:
                print(f"  [{i}] ERRO em {c['titulo_lista'][:50]}: {e}")
                d = {"titulo": c["titulo_lista"], "vigencia_inicio": c["vig_ini"],
                     "vigencia_fim": c["vig_fim"], "objetivo": "",
                     "primeiro_paragrafo": "", "conteudo": "", "link": c["link"]}
            print(f"  [{i}] ERRO em {c['titulo_lista'][:50]}: {e}")
            d = {"titulo": c["titulo_lista"], "vigencia_inicio": c["vig_ini"],
                 "vigencia_fim": c["vig_fim"], "objetivo": "",
                 "primeiro_paragrafo": "", "conteudo": "", "link": c["link"]}
        if not d["titulo"]:
            d["titulo"] = c["titulo_lista"]

        # prazo = fim da vigência (ou intervalo, se só houver início)
        prazo = d["vigencia_fim"] or d["vigencia_inicio"] or "não informado"

        resultados.append({
            "site": SITE,
            "titulo": d["titulo"],
            "prazo": prazo,
            "link": d["link"],
            "resumo": d["objetivo"],
            "vigencia_inicio": d["vigencia_inicio"],
            "vigencia_fim": d["vigencia_fim"],
            "primeiro_paragrafo": d["primeiro_paragrafo"],
            "conteudo": d.get("conteudo", ""),
            "coletado_em": data_coleta_antiga(anterior)
                or datetime.now().isoformat(timespec="seconds"),
        })
        print(f"  [{i}/{len(cards)}] {d['titulo'][:55]} | "
              f"vig: {d['vigencia_inicio']}-{d['vigencia_fim']}")
        if progresso:
            progresso(
                processados=i,
                total=len(cards),
                coletados=len(resultados),
                erros=0,
                item=d.get("titulo", ""),
                etapa="detalhes",
            )
        time.sleep(delay)

    campos = ["site", "titulo", "prazo", "link", "resumo",
              "vigencia_inicio", "vigencia_fim", "primeiro_paragrafo",
              "coletado_em"]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 60 + "\nRESUMO\n" + "=" * 60)
    print(f"Editais coletados: {len(resultados)}")
    print(f"Detalhes reaproveitados do cache: {reutilizados}")
    print(f"JSON: {os.path.abspath(json_path)}")
    return resultados


def main():
    ap = argparse.ArgumentParser(description="Scraper editais vigentes FAPEAM")
    ap.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    ap.add_argument("--show", action="store_true", help="abre o navegador")
    ap.add_argument("--todos", action="store_true", help="não filtra por vigência")
    ap.add_argument("--sem-render", action="store_true",
                    help="não usa navegador (só requests)")
    ap.add_argument("--delay", type=float, default=0.8, help="pausa (s)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    scrape(args.out, filtrar=not args.todos, usar_render=not args.sem_render,
           headless=not args.show, delay=args.delay, debug=args.debug)


if __name__ == "__main__":
    main()
