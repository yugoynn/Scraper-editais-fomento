# -*- coding: utf-8 -*-
"""
Scraper das Chamadas e Editais abertos — BNDES Conexões
https://conexoes.bndes.gov.br/chamadas-e-editais

Página única, renderizada no servidor. Cada card:
    <h3>TÍTULO</h3>
    <p>Perfil</p>
    <p>RESUMO ... Inscrições até DD/MM/AAAA ...</p>
    <a ...>Inscreva-se</a>   -> link do edital

Saída padronizada (dados/bndes/): site, titulo, prazo, link, resumo,
coletado_em + extra (perfil).

Instalação:
    pip install requests beautifulsoup4 lxml

Uso:
    python bndes.py
    python bndes.py --debug
    python bndes.py --out /caminho/pasta
"""

import argparse
import json
import os
import re
import unicodedata
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga
except ImportError:  # execução direta: python scrappers/Sbndes.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga

SITE = "BNDES"
URL = "https://conexoes.bndes.gov.br/chamadas-e-editais"
BASE = "https://conexoes.bndes.gov.br/"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0 Safari/537.36"),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

RX_DATA = re.compile(
    r"inscri[\u00e7c][\u00f5o]es[^.]*?at[\u00e9e]\s*(\d{1,2}/\d{1,2}/\d{2,4})",
    re.I)
RX_DATA2 = re.compile(r"at[\u00e9e]\s*(\d{1,2}/\d{1,2}/\d{2,4})", re.I)


def limpar(t):
    t = (t or "").replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"[ \t\r\n]+", " ", t).strip()


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


def default_out_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(script_dir), "dados", "bndes")


def tags_do_bloco(heading, boundary):
    saida = []
    for node in heading.next_elements:
        if node is boundary:
            break
        if isinstance(node, Tag):
            saida.append(node)
    return saida


def extrair_link_inscreva(tags):
    for t in tags:
        if t.name == "a" and t.get("href"):
            if "inscrev" in sem_acento(t.get_text(" ")):
                return urljoin(BASE, t["href"].strip())
    return ""


def extrair_resumo_e_perfil(tags):
    paras = []
    for t in tags:
        if t.name == "p":
            txt = limpar(t.get_text(" "))
            if txt:
                paras.append(txt)
    resumo = ""
    for p in paras:
        if re.search(r"inscri", p, re.I) and len(p) >= 60:
            resumo = p
            break
    if not resumo and paras:
        resumo = max(paras, key=len)
    perfil = ""
    for p in paras:
        if p != resumo and len(p) <= 60:
            perfil = p
            break
    return resumo, perfil


def extrair_data(resumo):
    m = RX_DATA.search(resumo) or RX_DATA2.search(resumo)
    return m.group(1) if m else ""


def coletar(html, debug=False):
    sopa = BeautifulSoup(html, "html.parser")
    heads = sopa.find_all(["h2", "h3"])
    boundaries = heads
    resultados = []
    for i, h in enumerate(heads):
        if h.name != "h3":
            continue
        titulo = limpar(h.get_text(" "))
        if len(titulo) < 5:
            continue
        boundary = boundaries[i + 1] if i + 1 < len(boundaries) else None
        tags = tags_do_bloco(h, boundary)

        link = extrair_link_inscreva(tags)
        resumo, perfil = extrair_resumo_e_perfil(tags)
        data = extrair_data(resumo)

        if not (link or resumo):
            continue

        item = {
            "site": SITE,
            "titulo": titulo,
            "prazo": data or "não informado",
            "link": link,
            "resumo": resumo,
            "perfil": perfil,
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
        }
        resultados.append(item)
        if debug:
            print("-" * 66)
            print("titulo:", titulo[:70])
            print("data  :", data, "| perfil:", perfil[:40])
            print("link  :", link[:80])
            print("resumo:", resumo[:120])
    return resultados


def scrape(out_dir, debug=False, progresso=None):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "editais.json")
    cache_anterior = cache_do_arquivo(json_path)
    reutilizados = 0
    print("Baixando a página de chamadas e editais...")
    r = requests.get(URL, headers=HEADERS, timeout=30)
    resultados = coletar(r.text, debug=debug)
    for item in resultados:
        anterior = cache_anterior.buscar(item.get("link", ""), item.get("titulo", ""))
        if anterior:
            item["coletado_em"] = data_coleta_antiga(anterior) or item.get("coletado_em", "")
            reutilizados += 1
    print(f"\nEncontrados {len(resultados)} editais.\n")
    for i, d in enumerate(resultados, 1):
        print(f"  [{i}] {d['titulo'][:55]} | {d['prazo']}")
        if progresso:
            progresso(
                processados=i,
                total=len(resultados),
                coletados=i,
                erros=0,
                item=d.get("titulo", ""),
                etapa="coleta",
            )

    campos = ["site", "titulo", "prazo", "link", "resumo", "perfil", "coletado_em"]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 60 + "\nRESUMO\n" + "=" * 60)
    print(f"Editais coletados: {len(resultados)}")
    print(f"Registros já conhecidos reaproveitados: {reutilizados}")
    print(f"JSON: {os.path.abspath(json_path)}")
    return resultados


def main():
    ap = argparse.ArgumentParser(description="Scraper BNDES Conexões")
    ap.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    scrape(args.out, debug=args.debug)


if __name__ == "__main__":
    main()
