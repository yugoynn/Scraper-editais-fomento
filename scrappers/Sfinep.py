#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper de Oportunidades — FINEP
================================

Página: https://www.finep.gov.br/oportunidades

Fluxo (conforme solicitado):
  1. Abre a página num navegador real (os filtros são via JavaScript).
  2. Aplica os filtros: "Fomento", "Empresas e ICTs", "Abertas" e "Sul".
  3. Coleta de cada card: título e prazo (ou "não informado").
  4. Entra em cada card e pega o link da página de detalhe.
     - Links que voltam para a própria página de pesquisa são ignorados.
  5. Existem DOIS tipos de página de destino:
     (A) .../e/chamada-publica/<id>/<id>         -> pega o RESUMO
     (B) .../financiamento-via-credito#<ancora>  -> pega Perfil, Objetivo,
         Valor do financiamento e Modelo de Operação
  6. Salva tudo em dados/finep/oportunidades.json.

IMPORTANTE — robots.txt:
  O site da FINEP sinaliza no robots.txt que não deseja acesso automatizado.
  Este script usa pausa entre requisições e um User-Agent de navegador real.
  Rode com moderação. A responsabilidade pelo uso é de quem executa.

Instalação (uma vez):
    pip install playwright
    playwright install chromium

Uso:
    python finep.py             # headless
    python finep.py --show      # abre o navegador para acompanhar/depurar
    python finep.py --out /caminho/pasta
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo
except ImportError:  # execução direta: python scrappers/Sfinep.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sync_playwright = None

    class PWTimeout(Exception):
        pass

SITE = "FINEP"
BASE = "https://www.finep.gov.br"
URL = f"{BASE}/oportunidades"

# ---------------------------------------------------------------------------
# FILTROS a aplicar. Cada item é uma LISTA de variações de rótulo — o script
# tenta cada variação até uma funcionar. Ajuste conforme o texto do site
# (use --show para ver na tela e o terminal indica qual foi aplicada).
# ---------------------------------------------------------------------------
FILTROS = [
    ["Fomento"],                                   # tipo/instrumento
    ["Empresas e ICTs", "Empresas e ICT",
     "Empresa e ICT", "Empresas e Icts"],          # público-alvo
    ["Abertas", "Aberta", "Aberto", "Abertos",
     "Em andamento", "Vigente", "Vigentes"],       # situação
    ["Sul", "Região Sul"],                         # região
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)


def default_out_dir():
    """dados/finep/ relativo à posição do script (…/scrapers/finep.py)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, "dados", "finep")


# ---------------------------------------------------------------------------
# Extração dos cards da página de listagem (rodando dentro do DOM real).
# Para cada card pega: título, prazo e o link de detalhe.
# ---------------------------------------------------------------------------
EXTRACT_CARDS_JS = r"""
() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();

  // Consideramos "card" qualquer elemento que contenha um link e um título.
  // Estratégia: pega todos os links de detalhe plausíveis e sobe até o card.
  const anchors = Array.from(document.querySelectorAll('a[href]'))
    .filter(a => {
      const h = a.getAttribute('href') || '';
      return /\/e\/chamada-publica\//i.test(h)
          || /\/chamadas?-publicas?\//i.test(h)
          || /\/chamadapublica\//i.test(h)
          || /financiamento-via-credito/i.test(h);
    });

  const seen = new Set();
  const cards = [];
  for (const a of anchors) {
    const href = a.getAttribute('href') || '';
    // sobe até um container que tenha um título (h1..h4 ou algo com texto forte)
    let card = a, hops = 0, titleEl = null;
    while (card && hops < 8) {
      titleEl = card.querySelector && card.querySelector('h1,h2,h3,h4,h5,.titulo,.title,.card-title,strong');
      if (titleEl && norm(titleEl.textContent)) break;
      card = card.parentElement; hops++;
    }
    const containerText = norm(card ? card.textContent : a.textContent);

    // título: do elemento de título, senão o próprio texto do link
    let titulo = titleEl ? norm(titleEl.textContent) : norm(a.textContent);
    if (!titulo) titulo = norm(a.textContent);

    // prazo: procura "Prazo" / "Data limite" / "Encerramento" no texto do card
    let prazo = '';
    const pm = containerText.match(
      /(?:Prazo(?:\s+de\s+inscri[cç][aã]o)?|Data\s+limite|Encerramento|Submiss[aã]o\s+at[ée])\s*:?\s*([0-3]?\d\/[01]?\d\/\d{2,4}|Fluxo\s+cont[ií]nuo|[^\.]{0,40}?\d{2,4})/i
    );
    if (pm) prazo = norm(pm[1]);

    const key = titulo + '||' + href;
    if (seen.has(key)) continue;
    seen.add(key);
    cards.push({ titulo, prazo, link: href, _cardText: containerText.slice(0, 400) });
  }
  return cards;
}
"""


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def classify_url(url):
    """Retorna 'chamada', 'credito' ou 'ignorar'."""
    u = url.lower()
    if "/oportunidades" in u:
        return "ignorar"  # volta para a pesquisa
    if "financiamento-via-credito" in u:
        return "credito"
    if ("/chamada-publica/" in u or "/chamadapublica/" in u
            or "/chamadas-publicas/" in u or "/e/chamada" in u):
        return "chamada"
    return "outro"


def extract_labeled_fields(text, labels):
    """
    Dado um texto corrido e uma lista de rótulos (ex.: 'Perfil', 'Objetivo'),
    devolve um dict {rotulo: conteúdo até o próximo rótulo conhecido}.
    """
    result = {lab: "" for lab in labels}
    # monta um padrão que localiza qualquer um dos rótulos
    alt = "|".join(re.escape(l) for l in labels)
    # encontra todas as ocorrências "Rótulo:" e as posições
    matches = list(re.finditer(rf"({alt})\s*:", text, re.I))
    for i, m in enumerate(matches):
        label_found = None
        for lab in labels:
            if m.group(1).lower() == lab.lower():
                label_found = lab
                break
        if label_found is None:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        result[label_found] = norm(text[start:end])
    return result


def extract_credito(page, hash_frag):
    """
    Página tipo B (/financiamento-via-credito).
    Extrai Perfil, Objetivo, Valor do financiamento e Modelo de Operação
    da seção indicada pela âncora (hash), se houver.
    """
    labels = ["Perfil", "Objetivo", "Valor do financiamento", "Modelo de Operação"]

    section_text = None
    if hash_frag:
        # tenta isolar a seção pela âncora (id igual ao hash)
        try:
            section_text = page.evaluate(
                """(id) => {
                    const el = document.getElementById(id) ||
                               document.querySelector('[name=\"'+id+'\"]') ||
                               document.querySelector('a[href$=\"#'+id+'\"]');
                    if (!el) return null;
                    // pega o container da seção: sobe alguns níveis
                    let sec = el;
                    for (let i=0;i<4 && sec.parentElement;i++){
                        if (sec.textContent && sec.textContent.length > 200) break;
                        sec = sec.parentElement;
                    }
                    return sec ? sec.innerText : null;
                }""",
                hash_frag,
            )
        except Exception:
            section_text = None

    full_text = page.evaluate("() => document.body.innerText")
    text = section_text or full_text
    fields = extract_labeled_fields(text, labels)

    # se a seção não trouxe os campos, tenta no texto inteiro
    if not any(fields.values()):
        fields = extract_labeled_fields(full_text, labels)

    return {
        "tipo_pagina": "credito",
        "perfil": fields.get("Perfil", ""),
        "objetivo": fields.get("Objetivo", ""),
        "valor_financiamento": fields.get("Valor do financiamento", ""),
        "modelo_operacao": fields.get("Modelo de Operação", ""),
    }


def extract_chamada(page):
    """
    Página tipo A (/e/chamada-publica/...). Extrai o RESUMO/objetivo.
    """
    # tenta campos rotulados primeiro
    full_text = page.evaluate("() => document.body.innerText")
    fields = extract_labeled_fields(full_text, ["Resumo", "Objetivo", "Descrição"])
    resumo = (fields.get("Resumo") or fields.get("Objetivo")
              or fields.get("Descrição") or "")

    # fallback: maior bloco de texto do conteúdo principal
    if not resumo:
        try:
            resumo = page.evaluate(
                """() => {
                    const cands = Array.from(document.querySelectorAll(
                      'main, article, .conteudo, .content, .descricao, #content, .texto'));
                    let best = '';
                    for (const c of cands) {
                        const t = (c.innerText || '').trim();
                        if (t.length > best.length) best = t;
                    }
                    if (!best) best = document.body.innerText || '';
                    return best;
                }"""
            )
        except Exception:
            resumo = ""
    # limita o tamanho para a classificação da IA depois
    resumo = norm(resumo)
    if len(resumo) > 4000:
        resumo = resumo[:4000] + " […]"
    return {"tipo_pagina": "chamada", "resumo": resumo}


def _try_click_value(page, valor):
    """Tenta clicar num controle de filtro com o texto `valor`. True se clicou."""
    estrategias = [
        lambda: page.get_by_role("button", name=valor, exact=False),
        lambda: page.get_by_role("checkbox", name=valor, exact=False),
        lambda: page.get_by_role("radio", name=valor, exact=False),
        lambda: page.get_by_role("option", name=valor, exact=False),
        lambda: page.get_by_role("link", name=valor, exact=False),
        lambda: page.get_by_label(valor, exact=False),
        lambda: page.get_by_text(valor, exact=True),
    ]
    for get in estrategias:
        try:
            loc = get()
            if loc.count() > 0:
                loc.first.scroll_into_view_if_needed(timeout=1500)
                loc.first.click(timeout=2500)
                page.wait_for_timeout(700)
                return True
        except Exception:
            continue
    # tenta como opção de um <select>
    try:
        selects = page.locator("select")
        for i in range(selects.count()):
            try:
                selects.nth(i).select_option(label=valor, timeout=1000)
                page.wait_for_timeout(700)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def apply_filters(page, filtros, verbose=True):
    """
    Aplica cada filtro. Cada filtro é uma lista de variações de rótulo;
    tenta cada variação até uma funcionar.
    """
    for variantes in filtros:
        aplicado = None
        for valor in variantes:
            if _try_click_value(page, valor):
                aplicado = valor
                break
        if verbose:
            alvo = variantes[0]
            if aplicado:
                extra = "" if aplicado == alvo else f" (via '{aplicado}')"
                print(f"  filtro '{alvo}': aplicado{extra}")
            else:
                print(f"  filtro '{alvo}': NÃO encontrado "
                      f"(tentei: {', '.join(variantes)})")
    # dá um tempo para a lista recarregar após os filtros
    try:
        page.wait_for_load_state("load", timeout=6000)
    except PWTimeout:
        pass
    page.wait_for_timeout(1500)


def go_to_next_listing_page(page, current_page):
    """
    Avança para a próxima página da listagem.
    Trata paginação NUMERADA (1 2 3 4…) e, como reserva, botão de seta.
    Retorna True se conseguiu avançar.
    """
    proximo = str(current_page + 1)

    # 1) paginação numerada: procura um link/botão cujo texto seja o número
    numeric_getters = [
        lambda: page.get_by_role("link", name=proximo, exact=True),
        lambda: page.get_by_role("button", name=proximo, exact=True),
        lambda: page.get_by_role("link", name=f"Página {proximo}", exact=False),
        lambda: page.get_by_role("link", name=f"Ir para página {proximo}", exact=False),
        # link/botão dentro de um container de paginação cujo texto exato é o número
        lambda: page.locator(
            "nav a, nav button, .pagination a, .pagination button, "
            "ul.pagination a, [class*=pagina] a, [class*=pagina] button"
        ).filter(has_text=re.compile(rf"^\s*{proximo}\s*$")),
    ]
    for get in numeric_getters:
        try:
            loc = get()
            if loc.count() > 0:
                loc.first.scroll_into_view_if_needed(timeout=1500)
                loc.first.click(timeout=2500)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue

    # 2) botão/seta de "próxima"
    for name in ["Próxima", "Próximo", "próxima página", "Next",
                 "Carregar mais", "Ver mais", "Mostrar mais"]:
        try:
            btn = page.get_by_role("button", name=name, exact=False)
            if btn.count() == 0:
                btn = page.get_by_role("link", name=name, exact=False)
            if btn.count() == 0:
                btn = page.get_by_text(name, exact=False)
            if btn.count() > 0 and not btn.first.is_disabled():
                btn.first.scroll_into_view_if_needed(timeout=1500)
                btn.first.click(timeout=2500)
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue

    # 3) seta por aria-label ou símbolo (› » >)
    try:
        el = page.locator(
            "[aria-label*='próxima' i], [aria-label*='proxima' i], "
            "[aria-label*='next' i], a[rel='next']"
        ).first
        if el.count() > 0 and not el.is_disabled():
            el.scroll_into_view_if_needed(timeout=1500)
            el.click(timeout=2500)
            page.wait_for_timeout(1500)
            return True
    except Exception:
        pass

    return False


def scrape(out_dir, headless=True, delay=1.5, max_pages=30, progresso=None):
    if sync_playwright is None:
        raise RuntimeError(
            "Playwright não está instalado. Execute: pip install playwright && playwright install chromium"
        )

    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "oportunidades.json")
    cache_anterior = cache_do_arquivo(json_path)
    resultados = []
    vistos_cards = set()
    reutilizados = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(user_agent=USER_AGENT, locale="pt-BR")
        page = ctx.new_page()

        print(f"Abrindo {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        # espera algum conteúdo aparecer, sem depender de rede ociosa
        try:
            page.wait_for_load_state("load", timeout=15000)
        except PWTimeout:
            pass
        page.wait_for_timeout(2500)

        print("Aplicando filtros...")
        apply_filters(page, FILTROS)

        # ---- coleta os cards (com paginação, se houver) ----
        cards = []
        pagina = 1
        while pagina <= max_pages:
            page.wait_for_timeout(int(delay * 1000))
            atuais = page.evaluate(EXTRACT_CARDS_JS)
            novos = 0
            for c in atuais:
                key = (c["titulo"], c["link"])
                if key in vistos_cards:
                    continue
                vistos_cards.add(key)
                cards.append(c)
                novos += 1
            print(f"[listagem pág {pagina}] {len(atuais)} cards | {novos} novos")
            if novos == 0:
                break
            if not go_to_next_listing_page(page, pagina):
                print("  não há próxima página; encerrando a listagem")
                break
            pagina += 1

        print(f"\nTotal de cards coletados: {len(cards)}")
        print("Visitando páginas de detalhe...\n")

        if progresso:
            progresso(
                processados=0,
                total=len(cards),
                coletados=0,
                erros=0,
                etapa="detalhes",
            )

        # ---- visita cada card e extrai o detalhe ----
        for i, c in enumerate(cards, 1):
            link_abs = urljoin(BASE, c["link"])
            tipo = classify_url(link_abs)
            titulo = c["titulo"]
            prazo = c["prazo"] or "não informado"

            print(f"[{i}/{len(cards)}] ({tipo}) {titulo[:60]}")

            if tipo == "ignorar":
                print("    link volta para a pesquisa; ignorado")
                if progresso:
                    progresso(
                        processados=i,
                        total=len(cards),
                        coletados=len(resultados),
                        erros=sum(1 for x in resultados if x.get("erro")),
                        item=titulo,
                        etapa="detalhes",
                    )
                continue

            registro = {
                "site": SITE,
                "titulo": titulo,
                "prazo": prazo,
                "link": link_abs,
                "coletado_em": datetime.now().isoformat(timespec="seconds"),
            }

            anterior = cache_anterior.buscar(link_abs, titulo)
            cache_valido = (
                anterior
                and not anterior.get("erro")
                and tem_conteudo(anterior, "resumo", "perfil", "objetivo", "modelo_operacao")
            )
            if cache_valido:
                registro = dict(anterior)
                registro.update({
                    "site": SITE,
                    "titulo": titulo,
                    "prazo": prazo,
                    "link": link_abs,
                    "coletado_em": data_coleta_antiga(anterior)
                        or datetime.now().isoformat(timespec="seconds"),
                })
                resultados.append(registro)
                reutilizados += 1
                print("    [PULADO] Detalhe já coletado; usando cache local.")
                if progresso:
                    progresso(
                        processados=i,
                        total=len(cards),
                        coletados=len(resultados),
                        erros=sum(1 for x in resultados if x.get("erro")),
                        item=titulo,
                        etapa="detalhes",
                    )
                continue

            try:
                page.goto(link_abs, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(int(delay * 1000))
            except Exception as e:
                print(f"    [erro] não abriu: {e}")
                registro["erro"] = str(e)
                resultados.append(registro)
                if progresso:
                    progresso(
                        processados=i,
                        total=len(cards),
                        coletados=len(resultados),
                        erros=sum(1 for x in resultados if x.get("erro")),
                        item=titulo,
                        etapa="detalhes",
                    )
                continue

            if tipo == "credito":
                frag = urlparse(link_abs).fragment  # ex.: finep-mais-inovacao
                registro.update(extract_credito(page, frag))
            elif tipo == "chamada":
                registro.update(extract_chamada(page))
            else:
                # tipo desconhecido: guarda um resumo genérico
                registro.update(extract_chamada(page))
                registro["tipo_pagina"] = "outro"

            resultados.append(registro)
            if progresso:
                progresso(
                    processados=i,
                    total=len(cards),
                    coletados=len(resultados),
                    erros=sum(1 for x in resultados if x.get("erro")),
                    item=titulo,
                    etapa="detalhes",
                )
            time.sleep(delay)

        ctx.close()
        browser.close()

    # ---- salva somente JSON; Excel é gerado apenas na exportação consolidada ----
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    editais = []
    erros = 0
    for item in resultados:
        if item.get("erro"):
            erros += 1
        editais.append({
            "site": item.get("site", SITE),
            "titulo": item.get("titulo", ""),
            "resumo": item.get("resumo", ""),
            "prazo": item.get("prazo", ""),
            "link": item.get("link", ""),
            "pagina_edital": item.get("link", ""),
            "tipo_pagina": item.get("tipo_pagina", ""),
            "arquivo": "oportunidades.json",
            "coletado_em": item.get("coletado_em", ""),
        })

    print("\n" + "=" * 60)
    print("RESUMO FINEP")
    print("=" * 60)
    print(f"Registros salvos: {len(resultados)}")
    print(f"Detalhes reaproveitados do cache: {reutilizados}")
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


def coletar_oportunidades(out=None, delay=1.5, headless=True, max_pages=30, progresso=None):
    return scrape(
        out_dir=out or default_out_dir(),
        headless=headless,
        delay=delay,
        max_pages=max_pages,
        progresso=progresso,
    )


def main():
    ap = argparse.ArgumentParser(description="Scraper de oportunidades da FINEP")
    ap.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    ap.add_argument("--show", action="store_true", help="abre o navegador (debug)")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="pausa (s) entre ações/requisições")
    ap.add_argument("--max-pages", type=int, default=30,
                    help="limite de páginas da listagem")
    args = ap.parse_args()

    scrape(args.out, headless=not args.show,
           delay=args.delay, max_pages=args.max_pages)


if __name__ == "__main__":
    main()