import argparse
import json
import os
import re
import time

from datetime import datetime
from urllib.parse import urljoin, urlparse, unquote

from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from scrappers.cache_utils import cache_do_arquivo
except ImportError:  # execução direta: python scrappers/Sfapesc.py
    from cache_utils import cache_do_arquivo


# ============================================================
# CONFIGURAÇÕES
# ============================================================

SITE = "FAPESC"

BASE = "https://fapesc.sc.gov.br"

CATEGORY_URL = f"{BASE}/category/chamadas-abertas/"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}


LINK_TEXTS = [
    "acesse o edital completo",
    "edital completo",
    "acesse o edital"
]


# ============================================================
# ACESSAR PÁGINA
# ============================================================

def get_soup(session, url):

    try:

        resp = session.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if resp.status_code == 404:
            return "__FIM_PAGINACAO__"

        resp.raise_for_status()

        return BeautifulSoup(
            resp.text,
            "html.parser"
        )

    except requests.RequestException as erro:

        print(
            f"[ERRO] Falha ao acessar {url}: {erro}"
        )

        return None


# ============================================================
# COLETAR LINKS DOS EDITAIS
# ============================================================

def collect_edital_links(session, max_pages=50):

    edital_links = []

    seen = set()

    page = 1


    while page <= max_pages:

        if page == 1:

            url = CATEGORY_URL

        else:

            url = (
                f"{CATEGORY_URL}"
                f"page/{page}/"
            )


        print()
        print(
            f"[PÁGINA {page}] {url}"
        )


        soup = get_soup(
            session,
            url
        )


        if soup == "__FIM_PAGINACAO__":
            print("[FIM] Página não existe. Última página alcançada.")
            break

        if soup is None:

            print(
                "Página não acessível. "
                "Encerrando paginação."
            )

            break


        found_on_page = 0


        for h in soup.find_all(
            ["h1", "h2", "h3"]
        ):

            a = h.find(
                "a",
                href=True
            )


            if not a:
                continue


            href = urljoin(
                BASE,
                a["href"]
            )


            texto = a.get_text(
                " ",
                strip=True
            )


            titulo_ok = re.search(
                r"edital|chamada|pr[êe]mio|bolsa|programa",
                texto,
                re.I
            )


            url_ruim = re.search(
                r"/category/|/page/|/tag/|#",
                href,
                re.I
            )


            mesmo_dominio = (
                urlparse(href)
                .netloc
                .endswith(
                    "fapesc.sc.gov.br"
                )
            )


            if (
                mesmo_dominio
                and titulo_ok
                and not url_ruim
            ):

                if href not in seen:

                    seen.add(href)

                    edital_links.append(
                        (
                            texto,
                            href
                        )
                    )

                    found_on_page += 1


        print(
            f"{found_on_page} editais encontrados "
            f"nesta página."
        )


        if found_on_page == 0:
            break


        page += 1

        time.sleep(0.5)


    return edital_links


# ============================================================
# ENCONTRAR PDF
# ============================================================

def find_pdf_url(
    soup,
    page_url
):

    # --------------------------------------------------------
    # Primeiro tenta localizar pelo texto do botão/link
    # --------------------------------------------------------

    for a in soup.find_all(
        "a",
        href=True
    ):

        texto = (
            a.get_text(
                " ",
                strip=True
            )
            .lower()
        )


        if any(
            texto_link in texto
            for texto_link in LINK_TEXTS
        ):

            return urljoin(
                page_url,
                a["href"]
            )


    # --------------------------------------------------------
    # Fallback: qualquer PDF
    # --------------------------------------------------------

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a["href"]


        if ".pdf" in href.lower():

            return urljoin(
                page_url,
                href
            )


    return None


# ============================================================
# NOME SEGURO PARA ARQUIVO
# ============================================================

def safe_filename(
    url,
    fallback
):

    path = urlparse(url).path

    name = unquote(
        os.path.basename(path)
    )


    if not name.lower().endswith(
        ".pdf"
    ):

        name = (
            fallback
            + ".pdf"
        )


    name = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        name
    )


    return name[:180]


# ============================================================
# CRIAR SLUG
# ============================================================

def slugify(text):

    text = re.sub(
        r"[^\w\s-]",
        "",
        text
    )

    text = (
        text
        .strip()
        .lower()
    )


    text = re.sub(
        r"[\s]+",
        "-",
        text
    )


    return (
        text[:80]
        or "edital"
    )


# ============================================================
# BAIXAR PDF
# ============================================================

def download_pdf(
    session,
    url,
    dest_folder,
    fallback_name
):

    filename = safe_filename(
        url,
        slugify(
            fallback_name
        )
    )


    dest = os.path.join(
        dest_folder,
        filename
    )


    # --------------------------------------------------------
    # Não baixa novamente
    # --------------------------------------------------------

    if os.path.exists(dest):

        print(
            f"[PULADO] Já existe: "
            f"{filename}"
        )

        return filename


    try:

        with session.get(
            url,
            headers=HEADERS,
            timeout=60,
            stream=True
        ) as response:

            response.raise_for_status()


            content_type = (
                response
                .headers
                .get(
                    "Content-Type",
                    ""
                )
            )


            if (
                "pdf"
                not in content_type.lower()
                and not url.lower().endswith(
                    ".pdf"
                )
            ):

                print(
                    "[AVISO] O arquivo "
                    "pode não ser PDF."
                )


            with open(
                dest,
                "wb"
            ) as arquivo:

                for chunk in (
                    response.iter_content(
                        chunk_size=8192
                    )
                ):

                    if chunk:

                        arquivo.write(
                            chunk
                        )


        tamanho = (
            os.path.getsize(dest)
            / 1024
        )


        print(
            f"[OK] {filename} "
            f"({tamanho:.0f} KB)"
        )


        return filename


    except requests.RequestException as erro:

        print(
            f"[ERRO] Falha ao baixar "
            f"{url}"
        )

        print(erro)


        if os.path.exists(dest):

            os.remove(dest)


        return None


# ============================================================
# DIRETÓRIO PADRÃO
# ============================================================

def default_out_dir():

    script_dir = os.path.dirname(
        os.path.abspath(
            __file__
        )
    )


    project_root = os.path.dirname(
        script_dir
    )


    return os.path.join(
        project_root,
        "dados",
        "fapesc",
        "pdf"
    )


# ============================================================
# FUNÇÃO PRINCIPAL PARA O SITE
# ============================================================

def coletar_editais(
    out=None,
    delay=1.0,
    progresso=None
):

    if out is None:

        out = default_out_dir()


    os.makedirs(
        out,
        exist_ok=True
    )

    indice_path = os.path.join(out, "editais.json")
    cache_anterior = cache_do_arquivo(indice_path)
    reutilizados = 0
    fapesc_root = Path(out).parent

    session = requests.Session()


    print()
    print("=" * 60)
    print(
        "COLETOR FAPESC"
    )
    print("=" * 60)

    print()
    print(
        "Coletando lista "
        "de editais..."
    )


    editais = collect_edital_links(
        session
    )


    encontrados = len(
        editais
    )

    if progresso:
        progresso(
            processados=0,
            total=encontrados,
            coletados=0,
            erros=0,
            etapa="baixando_pdfs",
        )


    print()
    print(
        f"Total encontrado: "
        f"{encontrados}"
    )


    # --------------------------------------------------------
    # Nenhum edital
    # --------------------------------------------------------

    if not editais:

        return {
            "sucesso": False,
            "mensagem": (
                "Nenhum edital "
                "foi encontrado."
            ),
            "encontrados": 0,
            "baixados": 0,
            "erros": 0,
            "editais": []
        }


    print()
    print("=" * 60)
    print(
        "BAIXANDO PDFs"
    )
    print("=" * 60)


    baixados = 0

    sem_pdf = []

    registros = []


    # ========================================================
    # PROCESSAR CADA EDITAL
    # ========================================================

    for indice, (
        titulo,
        pagina_edital
    ) in enumerate(
        editais,
        start=1
    ):

        print()
        print(
            f"[{indice}/{encontrados}]"
        )

        print(
            titulo[:100]
        )


        # ----------------------------------------------------
        # Reaproveitar edital já processado
        # ----------------------------------------------------
        anterior = cache_anterior.buscar(pagina_edital, titulo)
        if anterior and anterior.get("arquivo"):
            nome_arquivo = str(anterior.get("arquivo"))
            stem = Path(nome_arquivo).stem
            pdf_existente = Path(out) / nome_arquivo
            md_existente = fapesc_root / "markdown" / f"{stem}.md"
            analise_existente = fapesc_root / "analisados" / f"{stem}.json"

            if pdf_existente.exists() or md_existente.exists() or analise_existente.exists():
                registro = dict(anterior)
                registro["site"] = SITE
                registro["titulo"] = titulo
                registro["pagina_edital"] = pagina_edital
                registros.append(registro)
                baixados += 1
                reutilizados += 1
                print(f"[PULADO] Já coletado/processado: {nome_arquivo}")
                if progresso:
                    progresso(
                        processados=indice,
                        total=encontrados,
                        coletados=baixados,
                        erros=len(sem_pdf),
                        item=titulo,
                        etapa="baixando_pdfs",
                    )
                continue

        # ----------------------------------------------------
        # Abrir página do edital somente se for novo
        # ----------------------------------------------------

        soup = get_soup(
            session,
            pagina_edital
        )


        if soup is None:

            sem_pdf.append({
                "titulo":
                    titulo,

                "pagina":
                    pagina_edital,

                "motivo":
                    "Erro ao acessar página"
            })

            if progresso:
                progresso(
                    processados=indice,
                    total=encontrados,
                    coletados=baixados,
                    erros=len(sem_pdf),
                    item=titulo,
                    etapa="baixando_pdfs",
                )

            continue


        # ----------------------------------------------------
        # Encontrar PDF
        # ----------------------------------------------------

        pdf_url = find_pdf_url(
            soup,
            pagina_edital
        )


        if not pdf_url:

            print(
                "[AVISO] PDF "
                "não encontrado."
            )


            sem_pdf.append({
                "titulo":
                    titulo,

                "pagina":
                    pagina_edital,

                "motivo":
                    "PDF não encontrado"
            })

            if progresso:
                progresso(
                    processados=indice,
                    total=encontrados,
                    coletados=baixados,
                    erros=len(sem_pdf),
                    item=titulo,
                    etapa="baixando_pdfs",
                )

            continue


        # ----------------------------------------------------
        # Baixar
        # ----------------------------------------------------

        arquivo = download_pdf(
            session,
            pdf_url,
            out,
            titulo
        )


        if arquivo:

            baixados += 1


            registro = {

                "site":
                    SITE,

                "titulo":
                    titulo,

                "pagina_edital":
                    pagina_edital,

                "pdf_url":
                    pdf_url,

                "arquivo":
                    arquivo,

                "baixado_em":
                    datetime.now()
                    .isoformat(
                        timespec="seconds"
                    )

            }


            registros.append(
                registro
            )


        time.sleep(
            delay
        )

        if progresso:
            progresso(
                processados=indice,
                total=encontrados,
                coletados=baixados,
                erros=len(sem_pdf),
                item=titulo,
                etapa="baixando_pdfs",
            )


    # ========================================================
    # SALVAR ÍNDICE JSON
    # ========================================================

    with open(
        indice_path,
        "w",
        encoding="utf-8"
    ) as arquivo_json:

        json.dump(
            registros,
            arquivo_json,
            ensure_ascii=False,
            indent=2
        )


    # ========================================================
    # RESUMO
    # ========================================================

    erros = len(
        sem_pdf
    )


    print()
    print("=" * 60)
    print(
        "RESUMO"
    )
    print("=" * 60)

    print(
        f"Encontrados : "
        f"{encontrados}"
    )

    print(
        f"Disponíveis : "
        f"{baixados}"
    )

    print(
        f"Reutilizados: "
        f"{reutilizados}"
    )

    print(
        f"Erros       : "
        f"{erros}"
    )

    print(
        f"Pasta       : "
        f"{os.path.abspath(out)}"
    )


    # ========================================================
    # RETORNO PARA O SITE
    # ========================================================

    return {

        "sucesso":
            True,

        "encontrados":
            encontrados,

        "baixados":
            baixados,

        "coletados":
            baixados,

        "reutilizados":
            reutilizados,

        "novos":
            max(0, baixados - reutilizados),

        "erros":
            erros,

        "editais":
            registros,

        "sem_pdf":
            sem_pdf,

        "pasta":
            os.path.abspath(
                out
            )

    }


# ============================================================
# EXECUÇÃO DIRETA PELO TERMINAL
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Scraper de editais "
            "da FAPESC"
        )
    )


    parser.add_argument(
        "--out",
        default=default_out_dir(),
        help="Pasta de saída"
    )


    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help=(
            "Segundos de espera "
            "entre requisições"
        )
    )


    args = parser.parse_args()


    resultado = coletar_editais(
        out=args.out,
        delay=args.delay
    )


    if not resultado[
        "sucesso"
    ]:

        print(
            resultado.get(
                "mensagem",
                "Erro"
            )
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()