# -*- coding: utf-8 -*-
"""
Scraper dos Editais — Rota do Fomento (filtro: Editais de fomento)
https://rotadofomento.org/editais/?c=editais-de-fomento

WordPress renderizado no servidor (dá pra usar requests). Fluxo:
  1) percorre TODAS as páginas da listagem (paginação /page/N/)
  2) de cada card pega: titulo, fonte, "Inscrições até:" e "Vigência"
     -> IGNORA os "Encerrado", fica só com os "Aberto"
  3) entra em cada edital aberto e pega os objetivos (o <p> após "Objetivos:")

Saída padronizada (dados/rota_fomento/): site, titulo, prazo, link, resumo,
coletado_em + extras (fonte, vigencia).

Instalação:
    pip install requests beautifulsoup4 lxml

Uso:
    python rotas_fomento.py
    python rotas_fomento.py --todos     # não filtra por vigência
    python rotas_fomento.py --debug
    python rotas_fomento.py --out /caminho/pasta
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag, NavigableString

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo
except ImportError:  # execução direta: python scrappers/Srotas_fomento.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo

SITE = "Rota do Fomento"
BASE = "https://rotadofomento.org/"
CATEGORIA_QS = "c=editais-de-fomento"
MAX_PAGINAS = 15

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

RX_VIG = re.compile(r"vig[êe]ncia\s*:?\s*(aberto|encerrado)", re.I)
RX_INSCR = re.compile(
    r"inscri[çc][õo]es\s+at[ée]\s*:?\s*"
    r"(\d{1,2}/\d{1,2}/\d{2,4}(?:\s+\d{1,2}:\d{2})?)", re.I)
RX_FONTE = re.compile(r"^(.*?)\s*(?:[ÁA]reas\s*:|Categorias\s*:|Vig[êe]ncia\s*:)",
                      re.I | re.S)


def limpar(t):
    t = (t or "").replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"[ \t\r\n]+", " ", t).strip()


def default_out_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(script_dir), "dados", "rota_fomento")


def eh_link_edital(href):
    p = urlparse(href).path.rstrip("/")
    return p.startswith("/editais/") and len(p) > len("/editais") \
        and "/page/" not in p


# --------------------------------------------------------------------------- #
# LISTAGEM
# --------------------------------------------------------------------------- #
def titulos_da_pagina(sopa):
    heads = []
    for h in sopa.find_all(["h1", "h2", "h3"]):
        a = h.find("a", href=True)
        if a and eh_link_edital(a["href"]):
            heads.append((h, a))
    return heads


def texto_ate_proximo(heading, boundary):
    partes = []
    for node in heading.next_elements:
        if node is boundary:
            break
        if heading in node.parents:
            continue
        if isinstance(node, NavigableString):
            partes.append(str(node))
    return limpar(" ".join(partes))


def parse_listagem(html, filtrar=True):
    sopa = BeautifulSoup(html, "html.parser")
    heads = titulos_da_pagina(sopa)
    cards = []
    for i, (h, a) in enumerate(heads):
        boundary = heads[i + 1][0] if i + 1 < len(heads) else None
        titulo = limpar(h.get_text(" "))
        link = urljoin(BASE, a["href"].strip())
        bloco = texto_ate_proximo(h, boundary)

        mv = RX_VIG.search(bloco)
        vigencia = mv.group(1).capitalize() if mv else ""
        mi = RX_INSCR.search(bloco)
        data_inscricao = limpar(mi.group(1)) if mi else ""
        mf = RX_FONTE.match(bloco)
        fonte = limpar(mf.group(1)) if mf else ""
        if len(fonte) > 60:
            fonte = ""

        if filtrar and vigencia.lower().startswith("encerrad"):
            continue
        if filtrar and not vigencia.lower().startswith("abert"):
            continue

        cards.append({"titulo": titulo, "fonte": fonte,
                      "data_inscricao": data_inscricao,
                      "vigencia": vigencia or "?", "link": link})
    return cards


def achar_proxima_pagina(sopa, url_atual):
    a = sopa.find("a", rel=lambda v: v and "next" in v)
    if a and a.get("href"):
        return urljoin(url_atual, a["href"])
    for a in sopa.find_all("a", href=True):
        t = limpar(a.get_text()).lower()
        if t in ("next →", "next", "próxima", "proxima", "»", "próximo"):
            return urljoin(url_atual, a["href"])
    return None


def coletar_listagem(sessao, filtrar=True, delay=0.6, debug=False):
    vistos = set()
    todos = []
    for n in range(1, MAX_PAGINAS + 1):
        if n == 1:
            url = urljoin(BASE, f"editais/?{CATEGORIA_QS}")
        else:
            url = urljoin(BASE, f"editais/page/{n}/?{CATEGORIA_QS}")
        r = sessao.get(url, headers=HEADERS, timeout=30)
        sopa = BeautifulSoup(r.text, "html.parser")
        cards = parse_listagem(r.text, filtrar=filtrar)
        novos = 0
        for c in cards:
            if c["link"] in vistos:
                continue
            vistos.add(c["link"])
            todos.append(c)
            novos += 1
        if debug:
            print(f"[pagina {n}] {url}  cards_aceitos={len(cards)} novos={novos}")
        if not titulos_da_pagina(sopa):
            break
        if not achar_proxima_pagina(sopa, url):
            break
        time.sleep(delay)
    return todos


# --------------------------------------------------------------------------- #
# DETALHE
# --------------------------------------------------------------------------- #
def extrair_objetivos(sopa):
    rotulo = None
    for t in sopa.find_all(["p", "h1", "h2", "h3", "h4", "h5", "strong", "b"]):
        txt = limpar(t.get_text(" "))
        if re.match(r"^objetivos?\b\s*:?\s*$", txt, re.I):
            rotulo = t
            break
        m = re.match(r"^objetivos?\s*:\s*(.+)$", txt, re.I)
        if m and len(m.group(1)) >= 40:
            return limpar(m.group(1))
    if rotulo is not None:
        for node in rotulo.next_elements:
            if isinstance(node, Tag) and node.name == "p":
                txt = limpar(node.get_text(" "))
                if len(txt) >= 40:
                    return txt
    for p in sopa.find_all("p"):
        txt = limpar(p.get_text(" "))
        if len(txt) >= 60 and (txt[:1] in "“\"'" or "edital" in txt.lower()):
            return txt
    return ""


def extrair_detalhe(url, sessao, debug=False):
    r = sessao.get(url, headers=HEADERS, timeout=30)
    sopa = BeautifulSoup(r.text, "html.parser")
    objetivos = extrair_objetivos(sopa)
    conteudo = limpar(sopa.get_text(" "))[:30000]
    if debug:
        print("-" * 66)
        print("link     :", url)
        print("objetivos:", objetivos[:160])
    return {"resumo": objetivos, "conteudo": conteudo}


# --------------------------------------------------------------------------- #
def scrape(out_dir, filtrar=True, delay=0.6, debug=False, progresso=None):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "editais.json")
    cache_anterior = cache_do_arquivo(json_path)
    reutilizados = 0
    sessao = requests.Session()
    print("Lendo a listagem (todas as páginas)...")
    cards = coletar_listagem(sessao, filtrar=filtrar, delay=delay, debug=debug)
    print(f"\n{len(cards)} editais {'em aberto' if filtrar else '(todos)'}.\n")

    resultados = []
    for i, c in enumerate(cards, 1):
        anterior = cache_anterior.buscar(c["link"], c["titulo"])
        if anterior and tem_conteudo(anterior, "resumo", "conteudo"):
            detalhe = {
                "resumo": anterior.get("resumo", ""),
                "conteudo": anterior.get("conteudo", ""),
            }
            reutilizados += 1
            print(f"  [{i}] [PULADO] Detalhe já coletado; usando cache local.")
        else:
            try:
                detalhe = extrair_detalhe(c["link"], sessao, debug=debug)
            except Exception as e:
                print(f"  [{i}] ERRO em {c['titulo'][:45]}: {e}")
                detalhe = {"resumo": "", "conteudo": ""}
        resultados.append({
            "site": SITE,
            "titulo": c["titulo"],
            "prazo": c["data_inscricao"] or "não informado",
            "link": c["link"],
            "resumo": detalhe.get("resumo", ""),
            "conteudo": detalhe.get("conteudo", ""),
            "fonte": c["fonte"],
            "vigencia": c["vigencia"],
            "coletado_em": data_coleta_antiga(anterior)
                or datetime.now().isoformat(timespec="seconds"),
        })
        print(f"  [{i}/{len(cards)}] {c['titulo'][:50]} | "
              f"insc: {c['data_inscricao'] or '?'}")
        if progresso:
            progresso(
                processados=i,
                total=len(cards),
                coletados=len(resultados),
                erros=0,
                item=c.get("titulo", ""),
                etapa="detalhes",
            )
        time.sleep(delay)

    campos = ["site", "titulo", "prazo", "link", "resumo",
              "fonte", "vigencia", "coletado_em"]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 60 + "\nRESUMO\n" + "=" * 60)
    print(f"Editais coletados: {len(resultados)}")
    print(f"Detalhes reaproveitados do cache: {reutilizados}")
    print(f"JSON: {os.path.abspath(json_path)}")
    return resultados


def main():
    ap = argparse.ArgumentParser(description="Scraper editais Rota do Fomento")
    ap.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    ap.add_argument("--todos", action="store_true", help="não filtra por vigência")
    ap.add_argument("--delay", type=float, default=0.6, help="pausa (s)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    scrape(args.out, filtrar=not args.todos, delay=args.delay, debug=args.debug)


if __name__ == "__main__":
    main()
