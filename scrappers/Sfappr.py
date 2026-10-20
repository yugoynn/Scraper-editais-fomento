# -*- coding: utf-8 -*-
"""
Scraper dos Programas Abertos — Fundação Araucária (FAPPR)
https://www.fappr.pr.gov.br/Programas-Abertos

Página única, renderizada no servidor (Drupal). Cada edital é um bloco.
Alguns editais ficam dentro de um ACORDEÃO: o cabeçalho fica num <div> e o
conteúdo (descrição, links, data) fica em OUTRO <div> — por isso o bloco é
lido em ORDEM DE DOCUMENTO, delimitado pelo próximo edital/seção.

Saída padronizada (dados/fappr/): site, titulo, prazo, link, resumo,
coletado_em + extras (codigo, programa, categoria).

Instalação:
    pip install requests beautifulsoup4 lxml

Uso:
    python fappr.py
    python fappr.py --debug
    python fappr.py --out /caminho/pasta
"""

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga
except ImportError:  # execução direta: python scrappers/Sfappr.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga

SITE = "FAPPR"
URL = "https://www.fappr.pr.gov.br/Programas-Abertos"
BASE = "https://www.fappr.pr.gov.br/"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

RX_CODIGO = re.compile(r"^\s*(CP|PI|PA|PMI)\b", re.I)
RX_COD_CURTO = re.compile(r"^\s*((?:CP|PI|PA|PMI)[^:]*?):", re.I)
RX_ATE = re.compile(r"at[ée]\s*(\d{1,2}/\d{1,2}/\d{2,4})", re.I)
RX_ROTULO_DATA = re.compile(
    r"(?:submiss[ãa]o[^:\n]*sparkx|submiss[ãa]o|inscri[çc][õoã][eo]?s?|"
    r"inscri[çc][ãa]o|prazo)[^:\n]{0,25}:?\s*(?:at[ée]\s*)?(\d{1,2}/\d{1,2}/\d{2,4})",
    re.I)
RX_FLUXO = re.compile(r"fluxo\s+cont[ií]nuo", re.I)

SECOES = ("chamadas p", "processos de inexig", "parcerias da arau",
          "processos de manifest")
META_INI = re.compile(r"^(resp\.?|setor|dota[çc]|submiss|inscri|prazo|"
                      r"para mais|docs?)\b", re.I)


def limpar(t):
    t = (t or "").replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"[ \t\r\n]+", " ", t).strip()


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


def eh_secao(txt):
    n = sem_acento(txt)
    return any(n.startswith(s) for s in SECOES)


def default_out_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(script_dir), "dados", "fappr")


# --------------------------------------------------------------------------- #
def limites_e_editais(sopa):
    heads = sopa.find_all(["h2", "h3", "h4", "hr"])
    boundaries = []
    for h in heads:
        if h.name == "hr":
            boundaries.append(h)
            continue
        txt = limpar(h.get_text(" "))
        if RX_CODIGO.match(txt) or eh_secao(txt):
            boundaries.append(h)

    editais = []
    categoria = ""
    for b in boundaries:
        if b.name == "hr":
            continue
        txt = limpar(b.get_text(" "))
        if RX_CODIGO.match(txt):
            editais.append((categoria, b))
        elif eh_secao(txt):
            categoria = txt
    return boundaries, editais


def tags_e_texto_do_bloco(heading, boundary):
    tags, textos = [], []
    for node in heading.next_elements:
        if node is boundary:
            break
        if isinstance(node, Tag):
            tags.append(node)
        elif isinstance(node, NavigableString):
            textos.append(str(node))
    return tags, limpar(" ".join(textos))


def extrair_descricao(tags):
    partes = []
    for t in tags:
        if t.name != "p":
            continue
        txt = limpar(t.get_text(""))
        if len(txt) >= 40 and not META_INI.match(txt):
            partes.append(txt)
    return " ".join(partes).strip()


def extrair_link_edital(tags):
    links = []
    for t in tags:
        if t.name == "a" and t.get("href"):
            links.append((limpar(t.get_text(" ")), urljoin(BASE, t["href"].strip())))

    def pdf(h):
        return h.lower().split("?")[0].endswith(".pdf")

    for txt, href in links:
        if "edital" in txt.lower() and pdf(href):
            return href
    for txt, href in links:
        if "diretriz" in txt.lower() and pdf(href):
            return href
    for txt, href in links:
        if pdf(href) and "fappr.pr.gov.br" in href:
            return href
    for txt, href in links:
        if pdf(href):
            return href
    return ""


def extrair_data(tags, texto_bloco):
    for t in tags:
        if t.name == "span":
            estilo = (t.get("style") or "") + " " + (t.get("data-color") or "")
            if "ce0b00" in estilo.lower():
                v = limpar(t.get_text(" "))
                if v:
                    return v
    m = RX_ATE.search(texto_bloco)
    if m:
        return "at\u00e9 " + m.group(1)
    m = RX_ROTULO_DATA.search(texto_bloco)
    if m:
        return "at\u00e9 " + m.group(1)
    if RX_FLUXO.search(texto_bloco):
        return "Fluxo Cont\u00ednuo"
    return ""


def extrair_um(categoria, heading, boundary, debug=False):
    titulo = limpar(heading.get_text(" "))
    strong = heading.find("strong")
    programa = limpar(strong.get_text(" ")) if strong else ""
    mcod = RX_COD_CURTO.match(titulo)
    codigo = limpar(mcod.group(1)) if mcod else ""

    tags, texto_bloco = tags_e_texto_do_bloco(heading, boundary)
    descricao = extrair_descricao(tags)
    link_edital = extrair_link_edital(tags)
    data = extrair_data(tags, texto_bloco)

    if debug:
        print("-" * 66)
        print("titulo   :", titulo)
        print("categoria:", categoria, "| codigo:", codigo, "| programa:", programa)
        print("data     :", repr(data))
        print("link     :", link_edital)
        print("descricao:", descricao[:120])

    return {
        "site": SITE,
        "titulo": titulo,
        "prazo": data or "não informado",
        "link": link_edital,
        "resumo": descricao,
        "codigo": codigo,
        "programa": programa,
        "categoria": categoria,
        "conteudo": texto_bloco[:30000],
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
    }


def coletar(html, debug=False):
    sopa = BeautifulSoup(html, "html.parser")
    boundaries, editais = limites_e_editais(sopa)
    idx = {id(b): i for i, b in enumerate(boundaries)}
    resultados = []
    for categoria, h in editais:
        i = idx[id(h)]
        boundary = boundaries[i + 1] if i + 1 < len(boundaries) else None
        resultados.append(extrair_um(categoria, h, boundary, debug=debug))
    return resultados


# --------------------------------------------------------------------------- #
def scrape(out_dir, debug=False, progresso=None):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "editais.json")
    cache_anterior = cache_do_arquivo(json_path)
    reutilizados = 0
    print("Baixando a página de Programas Abertos...")
    r = requests.get(URL, headers=HEADERS, timeout=30)
    resultados = coletar(r.text, debug=debug)
    for item in resultados:
        anterior = cache_anterior.buscar(item.get("link", ""), item.get("titulo", ""))
        if anterior:
            item["coletado_em"] = data_coleta_antiga(anterior) or item.get("coletado_em", "")
            reutilizados += 1
    print(f"\nEncontrados {len(resultados)} editais.\n")
    for i, d in enumerate(resultados, 1):
        print(f"  [{i}] {d['titulo'][:52]} | {d['prazo']} | "
              f"{'PDF ok' if d['link'] else 'SEM LINK'}")
        if progresso:
            progresso(
                processados=i,
                total=len(resultados),
                coletados=i,
                erros=0,
                item=d.get("titulo", ""),
                etapa="coleta",
            )

    campos = ["site", "titulo", "prazo", "link", "resumo",
              "codigo", "programa", "categoria", "coletado_em"]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 60 + "\nRESUMO\n" + "=" * 60)
    print(f"Editais coletados: {len(resultados)}")
    print(f"Registros já conhecidos reaproveitados: {reutilizados}")
    print(f"JSON: {os.path.abspath(json_path)}")
    return resultados


def main():
    ap = argparse.ArgumentParser(description="Scraper Programas Abertos FAPPR")
    ap.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    scrape(args.out, debug=args.debug)


if __name__ == "__main__":
    main()
