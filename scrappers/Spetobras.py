#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper de Desafios — Petrobras "Conexões para Inovação"
========================================================

Página: https://conexoes-inovacao.petrobras.com.br/s/?language=pt_BR

O site é um portal Salesforce Experience Cloud (Lightning/Aura): a lista de
desafios é carregada por JavaScript. Cada desafio tem uma URL real
(/s/desafio/{id}/{slug}), então:
  1) coletamos título + link de todos os desafios na LISTA (com scroll);
  2) entramos em cada desafio pela URL e lemos resumo + prazo no DETALHE.

Saída padronizada (igual aos outros scrapers), em dados/petrobras/:
  - site         -> "Petrobras"
  - titulo       -> texto do a[data-refid="recordId"]
  - prazo        -> data limite lida no detalhe (ou "não informado")
  - link         -> URL absoluta do desafio
  - resumo       -> texto da aba "Descrição" no detalhe
  - coletado_em  -> data/hora da coleta

Instalação:
    pip install playwright
    playwright install chromium

Uso:
    python petrobras.py            # headless
    python petrobras.py --show     # abre o navegador (1a vez / debug)
    python petrobras.py --debug    # imprime os campos do 1o desafio
    python petrobras.py --limit 5  # lê apenas os 5 primeiros
    python petrobras.py --out /caminho/pasta
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

try:
    from scrappers.cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo
except ImportError:  # execução direta: python scrappers/Spetobras.py
    from cache_utils import cache_do_arquivo, data_coleta_antiga, tem_conteudo

SITE = "Petrobras"
LISTA_URL = "https://conexoes-inovacao.petrobras.com.br/s/?language=pt_BR"
ORIGEM = "https://conexoes-inovacao.petrobras.com.br"

MAX_SCROLLS = 40   # trava de segurança para o scroll/paginação

# rótulos que provavelmente identificam a data limite no detalhe
ROTULO_DATA_RE = re.compile(r"(data\s*limite|prazo|encerr|data\s*fim|"
                            r"submiss|inscri)", re.I)
DATA_VAL_RE = re.compile(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")


def limpar(t):
    return re.sub(r"\s+", " ", (t or "")).strip()


def default_out_dir():
    """dados/petrobras/ relativo à posição do script (…/scrapers/petrobras.py)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, "dados", "petrobras")


# --------------------------------------------------------------------------- #
# 1) Coleta a lista de desafios (título + link)
# --------------------------------------------------------------------------- #
def coletar_links(page):
    """Retorna dict {href: titulo} de todos os a[data-refid=recordId] atuais."""
    itens = page.evaluate(
        """() => {
            const out = [];
            const as = document.querySelectorAll('a[data-refid="recordId"]');
            for (const a of as) {
                const href = a.getAttribute('href') || '';
                const nome = (a.getAttribute('title') || a.textContent || '')
                    .replace(/\\s+/g, ' ').trim();
                if (href.includes('/desafio/')) out.push({href, nome});
            }
            return out;
        }"""
    )
    return {it["href"]: it["nome"] for it in itens}


def carregar_todos_os_desafios(page):
    """Faz scroll (e tenta botões de 'mais/próximo') até a lista parar de crescer."""
    print("Aguardando a lista carregar...")
    page.wait_for_selector('a[data-refid="recordId"]', timeout=45000)

    desafios = {}
    estavel = 0
    for i in range(MAX_SCROLLS):
        desafios.update(coletar_links(page))
        antes = len(desafios)

        # tenta clicar em botão de carregar mais / próxima página
        page.evaluate(
            """() => {
                const cand = Array.from(document.querySelectorAll('button, a, span'))
                  .filter(e => /(carregar mais|ver mais|mostrar mais|pr[oó]ximo|next|more)/i
                                .test((e.textContent||'').trim()));
                for (const el of cand) {
                    const dis = el.disabled ||
                                el.getAttribute('aria-disabled') === 'true';
                    if (!dis) { try { el.click(); } catch(e){} }
                }
            }"""
        )

        # rola até o fim para disparar carregamento sob demanda
        page.mouse.wheel(0, 20000)
        page.wait_for_timeout(1500)

        desafios.update(coletar_links(page))
        depois = len(desafios)
        print(f"  scroll {i+1}: {depois} desafios")

        if depois == antes:
            estavel += 1
            if estavel >= 3:   # 3 rodadas sem novidade -> parou
                break
        else:
            estavel = 0

    return desafios


# --------------------------------------------------------------------------- #
# 2) Lê o detalhe de cada desafio
# --------------------------------------------------------------------------- #
def ler_detalhe(page, url, debug=False):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # 1) espera o app Aura montar algo
    try:
        page.wait_for_selector(".forceCommunityRecordDetail, .slds-page-header, "
                               "h1, h2, span.uiOutputTextArea",
                               state="attached", timeout=20000)
    except PWTimeout:
        pass

    # 2) fecha o modal de cookies com clique real
    for nome_btn in ["Rejeitar", "Recusar", "Rejeitar todos", "Aceitar todos",
                     "Aceitar", "Fechar", "Entendi", "OK"]:
        try:
            page.get_by_role("button", name=re.compile(nome_btn, re.I)).first.click(
                timeout=1500)
            page.wait_for_timeout(300)
            break
        except Exception:
            continue

    # 3) clica na aba "Descrição" (o Aura só reage a eventos confiáveis; o
    #    resumo só renderiza ao abrir essa aba)
    for tentativa in (
        lambda: page.get_by_role("tab", name=re.compile(r"^\s*Descri", re.I)),
        lambda: page.get_by_text(re.compile(r"^Descri[cç][aã]o$", re.I)),
        lambda: page.locator("li", has_text=re.compile(r"^Descri", re.I)),
    ):
        try:
            tentativa().first.click(timeout=3000)
            break
        except Exception:
            continue
    page.wait_for_timeout(1200)
    try:
        page.wait_for_function(
            r"""() => {
                const deep = (sel, root=document, out=[]) => {
                    if (root.querySelectorAll)
                        root.querySelectorAll(sel).forEach(e => out.push(e));
                    const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                    all.forEach(e => { if (e.shadowRoot) deep(sel, e.shadowRoot, out); });
                    return out;
                };
                const els = deep('.slds-tabs_default__content.slds-show, .js-tab.slds-show');
                for (const e of els)
                    if ((e.textContent || '').trim().length > 100) return true;
                return false;
            }""",
            timeout=15000,
        )
    except PWTimeout:
        pass
    page.wait_for_timeout(400)

    dados = page.evaluate(
        r"""(rotuloReStr) => {
            const rotuloRe = new RegExp(rotuloReStr, 'i');
            const dataValRe = /\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}/;
            const norm = (s) => (s||'').replace(/\s+/g,' ').trim();

            // busca que ATRAVESSA shadow DOM (Salesforce renderiza em shadow roots)
            const deep = (sel, root=document, out=[]) => {
                if (root.querySelectorAll)
                    root.querySelectorAll(sel).forEach(e => out.push(e));
                const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                all.forEach(e => { if (e.shadowRoot) deep(sel, e.shadowRoot, out); });
                return out;
            };

            // ---- resumo: texto do painel da aba "Descrição" (visível) ----
            const paineis = deep('.slds-tabs_default__content.slds-show, .js-tab.slds-show');
            let painel = null, melhor = -1;
            for (const p of paineis) {
                const t = norm(p.textContent);
                if (t.length > melhor) { melhor = t.length; painel = p; }
            }
            let resumo = '';
            if (painel) {
                const cands = [];
                painel.querySelectorAll('*').forEach(el => {
                    const t = norm(el.textContent);
                    const nc = el.children ? el.children.length : 0;
                    if (t.length >= 60 && nc <= 2) cands.push(t);
                });
                cands.sort((a, b) => b.length - a.length);
                resumo = cands.length ? cands[0] : norm(painel.textContent);
            }
            if (!resumo) {
                const alt = deep('span.uiOutputTextArea, [data-aura-class="uiOutputTextArea"], .uiOutputRichText')
                    .map(e => norm(e.textContent)).filter(Boolean);
                alt.sort((a, b) => b.length - a.length);
                resumo = alt.length ? alt[0] : '';
            }

            // ---- data limite: procura rótulo -> data próxima ----
            let dataLimite = '';
            const candidatosData = [];
            const todos = deep('*');
            for (const el of todos) {
                const txt = norm(el.textContent);
                if (!txt || txt.length > 40) continue;
                if (rotuloRe.test(txt)) {
                    const escopos = [];
                    if (el.parentElement) escopos.push(el.parentElement);
                    if (el.parentElement && el.parentElement.parentElement)
                        escopos.push(el.parentElement.parentElement);
                    if (el.nextElementSibling) escopos.push(el.nextElementSibling);
                    for (const s of escopos) {
                        const m = norm(s.textContent).match(dataValRe);
                        if (m) { candidatosData.push({rotulo: txt, valor: m[0]}); break; }
                    }
                }
            }
            if (candidatosData.length) dataLimite = candidatosData[0].valor;
            if (!dataLimite) {
                const m = norm(document.body.innerText).match(dataValRe);
                if (m) dataLimite = m[0];
            }

            // ---- diagnóstico (usado só com --debug) ----
            const candidatosTexto = [];
            for (const el of todos) {
                const t = norm(el.textContent);
                if (t.length < 60) continue;
                const nFilhos = el.children ? el.children.length : 0;
                if (nFilhos > 3) continue;
                if (el.tagName === 'STYLE' || el.tagName === 'SCRIPT') continue;
                candidatosTexto.push({
                    tag: el.tagName,
                    cls: (el.getAttribute && (el.getAttribute('class')||'')).slice(0,80),
                    len: t.length, txt: t.slice(0, 90),
                });
            }
            candidatosTexto.sort((a,b) => b.len - a.len);
            const diag = candidatosTexto.slice(0, 15);
            const bodyText = norm(document.body.innerText);

            return {resumo, dataLimite, candidatosData, diag,
                    bodyLen: bodyText.length, bodySample: bodyText.slice(0, 1200),
                    conteudo: bodyText.slice(0, 30000)};
        }""",
        ROTULO_DATA_RE.pattern,
    )

    if debug:
        print("\n--- DEBUG do detalhe ---")
        print("Candidatos rótulo->data:")
        for c in dados.get("candidatosData", [])[:15]:
            print(f"   [{c['rotulo']}] = {c['valor']}")
        print(f"Amostra do resumo: {limpar(dados.get('resumo',''))[:150]!r}")
        print(f"Tamanho total do texto da página: {dados.get('bodyLen')} chars")
        print(">>> MAIORES BLOCOS DE TEXTO (folha):")
        for c in dados.get("diag", []):
            print(f"   <{c['tag'].lower()} class='{c['cls']}' len={c['len']}>")
            print(f"       {c['txt']!r}")
        print(">>> AMOSTRA DO TEXTO DA PÁGINA:")
        print(dados.get("bodySample", ""))
        print("--- fim do DEBUG ---\n")

    return {
        "resumo": limpar(dados.get("resumo", "")),
        "prazo": dados.get("dataLimite", "") or "não informado",
        "conteudo": limpar(dados.get("conteudo", ""))[:30000],
    }


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #
def scrape(out_dir, headless=True, delay=1.0, limit=0, debug=False, progresso=None):
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "desafios.json")
    cache_anterior = cache_do_arquivo(json_path)
    reutilizados = 0
    resultados = []

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        page = navegador.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0 Safari/537.36"
            )
        )
        page.set_default_timeout(30000)

        page.goto(LISTA_URL, wait_until="domcontentloaded", timeout=60000)
        desafios = carregar_todos_os_desafios(page)
        print(f"\nTotal de desafios encontrados na lista: {len(desafios)}\n")

        itens = list(desafios.items())
        if limit:
            itens = itens[:limit]
            print(f">>> Lendo apenas os {len(itens)} primeiros desafios\n")

        for i, (href, nome) in enumerate(itens, 1):
            url = urljoin(ORIGEM, href)
            anterior = cache_anterior.buscar(url, nome)
            if anterior and tem_conteudo(anterior, "resumo", "conteudo"):
                det = {
                    "resumo": anterior.get("resumo", ""),
                    "prazo": anterior.get("prazo", "não informado"),
                    "conteudo": anterior.get("conteudo", ""),
                }
                reutilizados += 1
                print(f"  [{i}] [PULADO] Detalhe já coletado; usando cache local.")
            else:
                try:
                    det = ler_detalhe(page, url, debug=(debug and i == 1))
                except Exception as e:
                    print(f"  [{i}] ERRO em {nome[:40]}: {e}")
                    det = {"resumo": "", "prazo": "não informado", "conteudo": ""}

            resultados.append({
                "site": SITE,
                "titulo": nome,
                "prazo": det["prazo"],
                "link": url,
                "resumo": det["resumo"],
                "conteudo": det.get("conteudo", ""),
                "coletado_em": data_coleta_antiga(anterior)
                    or datetime.now().isoformat(timespec="seconds"),
            })
            print(f"  [{i}/{len(itens)}] {nome[:50]} | prazo: {det['prazo']}")
            if progresso:
                progresso(
                    processados=i,
                    total=len(itens),
                    coletados=len(resultados),
                    erros=0,
                    item=nome,
                    etapa="detalhes",
                )
            time.sleep(delay)

        navegador.close()

    # ---- salva (somente JSON, no mesmo padrão dos outros) ----
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    campos = ["site", "titulo", "prazo", "link", "resumo", "coletado_em"]
    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"Desafios coletados: {len(resultados)}")
    print(f"Detalhes reaproveitados do cache: {reutilizados}")
    print(f"JSON: {os.path.abspath(json_path)}")
    return resultados


def main():
    ap = argparse.ArgumentParser(
        description="Scraper de desafios da Petrobras Conexões para Inovação"
    )
    ap.add_argument("--out", default=default_out_dir(), help="pasta de saída")
    ap.add_argument("--show", action="store_true",
                    help="abre o navegador (desativa headless)")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="pausa (s) entre desafios")
    ap.add_argument("--limit", type=int, default=0,
                    help="lê apenas os N primeiros desafios (0 = todos)")
    ap.add_argument("--debug", action="store_true",
                    help="imprime os campos do 1º desafio (diagnóstico)")
    args = ap.parse_args()

    scrape(args.out, headless=not args.show, delay=args.delay,
           limit=args.limit, debug=args.debug)


if __name__ == "__main__":
    main()
