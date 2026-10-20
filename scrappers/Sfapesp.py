#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scraper de Chamadas Abertas da FAPESP.

A saída deste scraper é SOMENTE JSON em:
    dados/fapesp/chamadas_fapesp.json

Ele não gera CSV nem Excel. A planilha consolidada continua sendo criada
somente pela função de exportação do aplicativo.

V18:
- cada card da listagem é isolado até o próximo H3;
- o texto de uma chamada não "vaza" para as chamadas seguintes;
- tenta a página curta e URLs canônicas derivadas do título;
- rejeita páginas de detalhe que, por redirecionamento, voltarem à listagem;
- mantém o texto curto do card junto ao detalhe, ajudando a IA a encontrar prazo.
"""

import argparse
import json
import os
import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga
except ImportError:  # execução direta: python scrappers/Sfapesp.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga


SITE = "FAPESP"
BASE = "https://fapesp.br"
LIST_URL = f"{BASE}/chamadas/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
}

RE_PRAZO_LINHA = re.compile(
    r"(?:data\s*[- ]?limite|prazo|submiss(?:ão|ao)|inscri(?:ção|cao)|recebimento)[^\n]{0,180}",
    re.I,
)

MARCADORES_FIM_SECAO = (
    "chamadas próprias",
    "chamadas proprias",
    "colaboração internacional",
    "colaboracao internacional",
    "colaboração nacional",
    "colaboracao nacional",
    "chamadas previstas",
)


def default_out_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, "dados", "fapesp")


def _texto_limpo(elemento):
    if elemento is None:
        return ""
    return " ".join(elemento.get_text(" ", strip=True).split()).strip()


def _get_soup(session, url, timeout=35):
    resposta = session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    resposta.raise_for_status()
    resposta.encoding = resposta.apparent_encoding or resposta.encoding
    return BeautifulSoup(resposta.text, "html.parser"), resposta.url


def _encontrar_secao_abertas(soup):
    for tag in soup.find_all(True):
        texto = _texto_limpo(tag).lower()
        if texto == "chamadas abertas (todas)":
            return tag

    for tag in soup.find_all(["h1", "h2", "h3", "h4", "div", "span", "p"]):
        texto = _texto_limpo(tag).lower()
        if "chamadas abertas" in texto and "todas" in texto and len(texto) < 80:
            return tag
    return None


def _texto_ate_proximo_h3(h3):
    """Extrai somente o texto visual pertencente a um card da listagem.

    A versão anterior usava find_next_sibling(), mas os H3 da FAPESP podem
    estar em wrappers diferentes. O sibling seguinte podia ser um container
    com TODOS os cards restantes. Aqui percorremos a ordem real do documento
    e paramos assim que aparece o próximo H3.
    """
    linhas = []

    for elemento in h3.next_elements:
        if elemento is h3:
            continue

        if isinstance(elemento, Tag) and elemento.name == "h3":
            break

        if not isinstance(elemento, NavigableString):
            continue

        pai = elemento.parent
        if pai is None:
            continue

        # Não repete o próprio título do H3.
        if pai.name == "h3" or pai.find_parent("h3") is not None:
            continue

        texto = " ".join(str(elemento).split()).strip()
        if not texto:
            continue

        normal = texto.lower()
        if any(marcador in normal for marcador in MARCADORES_FIM_SECAO):
            break

        if not linhas or linhas[-1] != texto:
            linhas.append(texto)

    return "\n".join(linhas).strip()


def _extrair_cards_abertos(soup):
    """Retorna os H3 somente da primeira seção 'Chamadas Abertas (Todas)'."""
    inicio = _encontrar_secao_abertas(soup)
    cards = []
    vistos = set()

    if inicio is None:
        candidatos = soup.find_all("h3")
    else:
        candidatos = []
        for elemento in inicio.find_all_next():
            if elemento is inicio:
                continue

            texto = _texto_limpo(elemento).lower()
            if any(m in texto for m in MARCADORES_FIM_SECAO) and len(texto) < 160:
                break

            if elemento.name == "h3":
                candidatos.append(elemento)

    for h3 in candidatos:
        a = h3.find("a", href=True)
        if not a:
            continue

        href = urljoin(BASE, a.get("href", "").strip())
        titulo = _texto_limpo(a) or _texto_limpo(h3)

        if not titulo or "fapesp.br" not in href.lower():
            continue
        if href in vistos:
            continue

        card_texto = _texto_ate_proximo_h3(h3)

        vistos.add(href)
        cards.append({
            "titulo": titulo,
            "link": href,
            "texto_listagem": card_texto,
        })

    return cards


def _extrair_data_limite(texto):
    texto = str(texto or "").strip()
    if not texto:
        return ""

    linhas = [" ".join(linha.split()) for linha in texto.splitlines() if linha.strip()]
    for linha in linhas:
        n = linha.lower()
        if any(chave in n for chave in (
            "data-limite", "data limite", "prazo", "submissão", "submissao",
            "inscrição", "inscricao", "recebimento",
        )):
            if ":" in linha:
                valor = linha.split(":", 1)[1].strip()
                if valor:
                    return valor[:250]
            return linha[:250]

    achado = RE_PRAZO_LINHA.search(texto)
    return achado.group(0).strip()[:250] if achado else ""


def _slug(texto):
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", "-", texto).strip("-")
    return texto[:180]


def _urls_detalhe_candidatas(link, titulo):
    """Gera alternativas para os links curtos /18203 usados na listagem."""
    urls = []

    def adicionar(url):
        if url and url not in urls:
            urls.append(url)

    adicionar(link)

    parsed = urlparse(link)
    achado = re.search(r"/(\d{4,})(?:/|$)", parsed.path or "")
    if achado:
        codigo = achado.group(1)
        slug = _slug(titulo)
        if slug:
            adicionar(f"{BASE}/{codigo}/{slug}")
            adicionar(f"{BASE}/index.php/{codigo}/{slug}")

    return urls


def _parece_listagem_contaminada(texto, titulo_esperado=""):
    normal = " ".join(str(texto or "").lower().split())
    if not normal:
        return True

    if "chamadas abertas (todas)" in normal:
        return True

    # Uma página individual pode citar outra chamada, mas não deve conter uma
    # sequência inteira de cards com dezenas de Modalidade/Área/Prazo.
    cont_modalidade = len(re.findall(r"\bmodalidade(?:s)?\s*:", normal))
    cont_chamadas = normal.count("chamada de propostas") + normal.count("chamada conjunta")
    cont_prazos = len(re.findall(r"\b(?:data[- ]?limite|prazo(?: final)?|submiss[aã]o de propostas)\b", normal))

    if cont_modalidade >= 7 and cont_chamadas >= 5:
        return True
    if cont_chamadas >= 8 and cont_prazos >= 8:
        return True

    # Se o conteúdo é razoavelmente grande, o título esperado deve aparecer.
    titulo_norm = " ".join(str(titulo_esperado or "").lower().split())
    palavras_titulo = [p for p in re.findall(r"[a-zà-ÿ0-9]+", titulo_norm) if len(p) >= 5]
    if len(normal) > 1500 and palavras_titulo:
        acertos = sum(1 for p in palavras_titulo[:12] if p in normal)
        if acertos < max(2, min(4, len(palavras_titulo) // 3)):
            return True

    return False


def _extrair_texto_detalhe(soup, titulo_esperado=""):
    """Extrai o conteúdo útil da página individual, nunca a listagem inteira."""
    for seletor in ["script", "style", "noscript", "nav", "footer", "header", "aside"]:
        for tag in soup.select(seletor):
            tag.decompose()

    candidatos = []
    for seletor in [
        "article",
        "main article",
        ".entry-content",
        ".post-content",
        ".page-content",
        ".conteudo",
        "#content",
        "main",
    ]:
        for tag in soup.select(seletor):
            if tag not in candidatos:
                candidatos.append(tag)

    if soup.body is not None:
        candidatos.append(soup.body)

    melhor = ""
    melhor_pontuacao = -10**9
    titulo_norm = " ".join(str(titulo_esperado or "").lower().split())
    palavras_titulo = [p for p in re.findall(r"[a-zà-ÿ0-9]+", titulo_norm) if len(p) >= 5]

    for principal in candidatos:
        linhas = []
        for linha in principal.get_text("\n", strip=True).splitlines():
            limpa = " ".join(linha.split()).strip()
            if limpa and (not linhas or limpa != linhas[-1]):
                linhas.append(limpa)

        texto = "\n".join(linhas).strip()
        if len(texto) < 120:
            continue
        if _parece_listagem_contaminada(texto, titulo_esperado):
            continue

        normal = texto.lower()
        pontuacao = min(len(texto), 30000) / 1000.0
        pontuacao += sum(3 for p in palavras_titulo[:12] if p in normal)
        pontuacao += 4 if "elegibilidade" in normal else 0
        pontuacao += 3 if "submiss" in normal else 0
        pontuacao += 2 if "objetivo" in normal else 0

        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = texto

    if len(melhor) > 50000:
        melhor = melhor[:50000].rstrip() + " […]"

    return melhor


def _buscar_texto_detalhe(session, link, titulo):
    erros = []

    for url in _urls_detalhe_candidatas(link, titulo):
        try:
            soup, url_final = _get_soup(session, url)
            texto = _extrair_texto_detalhe(soup, titulo)
            if texto:
                return texto, url_final, ""
            erros.append(f"{url}: conteúdo vazio/listagem rejeitada")
        except Exception as exc:
            erros.append(f"{url}: {type(exc).__name__}: {exc}")

    return "", link, " | ".join(erros[-3:])


def scrape(out_dir=None, delay=0.8, progresso=None):
    if out_dir is None:
        out_dir = default_out_dir()

    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "chamadas_fapesp.json")
    cache_anterior = cache_do_arquivo(json_path)
    reutilizados = 0

    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"Abrindo {LIST_URL}")
    soup, _ = _get_soup(session, LIST_URL)
    cards = _extrair_cards_abertos(soup)

    print(f"Chamadas abertas encontradas: {len(cards)}")

    if progresso:
        progresso(
            processados=0,
            total=len(cards),
            coletados=0,
            erros=0,
            etapa="detalhes",
        )

    resultados = []
    erros = 0

    for indice, card in enumerate(cards, start=1):
        titulo = card.get("titulo", "")
        link = card.get("link", "")
        texto_listagem = card.get("texto_listagem", "")

        print(f"[{indice}/{len(cards)}] {titulo[:90]}")

        anterior = cache_anterior.buscar(link, titulo)
        texto_detalhe = ""
        link_final = link
        erro = ""
        if anterior and "CONTEÚDO DA CHAMADA:" in str(anterior.get("paragrafo", "")):
            texto_detalhe = str(anterior.get("paragrafo", "")).split(
                "CONTEÚDO DA CHAMADA:", 1
            )[1].strip()
            link_final = anterior.get("link") or link
            reutilizados += 1
            print("  [PULADO] Detalhe já coletado; usando cache local.")
        else:
            texto_detalhe, link_final, erro = _buscar_texto_detalhe(session, link, titulo)
            if erro and not texto_detalhe:
                erros += 1
                print(f"  [AVISO DETALHE] usando somente o card da listagem: {erro[:220]}")

        # O card é sempre preservado porque contém o prazo/modalidade corretos.
        # O detalhe é anexado somente se passou na validação anticontaminação.
        partes = []
        if texto_listagem:
            partes.append("DADOS DA LISTAGEM:\n" + texto_listagem)
        if texto_detalhe:
            partes.append("CONTEÚDO DA CHAMADA:\n" + texto_detalhe)
        paragrafo = "\n\n".join(partes).strip()

        registro = {
            "site": SITE,
            "titulo": titulo,
            "data_limite": _extrair_data_limite(texto_listagem),
            "paragrafo": paragrafo,
            "link": link_final or link,
            "coletado_em": data_coleta_antiga(anterior)
                or datetime.now().isoformat(timespec="seconds"),
        }
        if erro and not texto_detalhe:
            registro["aviso_detalhe"] = erro

        resultados.append(registro)
        if progresso:
            progresso(
                processados=indice,
                total=len(cards),
                coletados=len(resultados),
                erros=erros,
                item=titulo,
                etapa="detalhes",
            )
        time.sleep(max(0.0, float(delay)))

    with open(json_path, "w", encoding="utf-8") as arquivo:
        json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    editais = []
    for item in resultados:
        editais.append({
            "site": item.get("site", SITE),
            "titulo": item.get("titulo", ""),
            "resumo": item.get("paragrafo", "")[:500],
            "prazo": item.get("data_limite", ""),
            "link": item.get("link", ""),
            "pagina_edital": item.get("link", ""),
            "arquivo": "chamadas_fapesp.json",
            "coletado_em": item.get("coletado_em", ""),
        })

    print("\n" + "=" * 60)
    print("RESUMO FAPESP")
    print("=" * 60)
    print(f"Registros salvos: {len(resultados)}")
    print(f"Detalhes reaproveitados do cache: {reutilizados}")
    print(f"Detalhes indisponíveis/rejeitados: {erros}")
    print(f"JSON: {os.path.abspath(json_path)}")
    print("CSV/Excel: não gerado pelo scraper")

    return {
        "sucesso": True,
        "encontrados": len(resultados),
        "baixados": len(resultados),
        "coletados": len(resultados),
        "reutilizados": reutilizados,
        "novos": max(0, len(resultados) - reutilizados),
        "erros": erros,
        "editais": editais,
        "json": os.path.abspath(json_path),
    }


def coletar_oportunidades(out=None, delay=0.8, progresso=None):
    return scrape(out_dir=out or default_out_dir(), delay=delay, progresso=progresso)


def main():
    parser = argparse.ArgumentParser(description="Scraper de chamadas abertas da FAPESP")
    parser.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    parser.add_argument("--delay", type=float, default=0.8, help="pausa entre páginas")
    args = parser.parse_args()
    scrape(out_dir=args.out, delay=args.delay)


if __name__ == "__main__":
    main()
