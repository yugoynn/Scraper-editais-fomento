import json
import re
from pathlib import Path

import xlsxwriter


PROJECT_ROOT = Path(__file__).resolve().parent.parent

FAPESC_ANALISES_JSON = PROJECT_ROOT / "dados" / "fapesc" / "analisados" / "analises.json"
FAPESC_EDITAIS_JSON = PROJECT_ROOT / "dados" / "fapesc" / "pdf" / "editais.json"
SEBRAE_JSON = PROJECT_ROOT / "dados" / "sebrae" / "oportunidades.json"
SEBRAE_ANALISADOS_JSON = (
    PROJECT_ROOT / "dados" / "sebrae" / "analisados" / "oportunidades_analisadas.json"
)
FINEP_JSON = PROJECT_ROOT / "dados" / "finep" / "oportunidades.json"
FINEP_ANALISADOS_JSON = (
    PROJECT_ROOT / "dados" / "finep" / "analisados" / "oportunidades_analisadas.json"
)
FAPESP_JSON = PROJECT_ROOT / "dados" / "fapesp" / "chamadas_fapesp.json"
FAPESP_ANALISADOS_JSON = (
    PROJECT_ROOT / "dados" / "fapesp" / "analisados" / "chamadas_analisadas.json"
)

FONTES_JSON_CONFIG = {
    "bndes": (PROJECT_ROOT / "dados" / "bndes" / "editais.json", PROJECT_ROOT / "dados" / "bndes" / "analisados" / "editais_analisados.json", "BNDES"),
    "fapeam": (PROJECT_ROOT / "dados" / "fapeam" / "editais.json", PROJECT_ROOT / "dados" / "fapeam" / "analisados" / "editais_analisados.json", "FAPEAM"),
    "fapemig": (PROJECT_ROOT / "dados" / "fapemig" / "editais.json", PROJECT_ROOT / "dados" / "fapemig" / "analisados" / "editais_analisados.json", "FAPEMIG"),
    "fappr": (PROJECT_ROOT / "dados" / "fappr" / "editais.json", PROJECT_ROOT / "dados" / "fappr" / "analisados" / "editais_analisados.json", "Fundação Araucária (FAPPR)"),
    "petrobras": (PROJECT_ROOT / "dados" / "petrobras" / "desafios.json", PROJECT_ROOT / "dados" / "petrobras" / "analisados" / "desafios_analisados.json", "Petrobras"),
    "rota_fomento": (PROJECT_ROOT / "dados" / "rota_fomento" / "editais.json", PROJECT_ROOT / "dados" / "rota_fomento" / "analisados" / "editais_analisados.json", "Rota do Fomento"),
}
EXPORT_DIR = PROJECT_ROOT / "dados" / "exportados"



def normalizar_url(valor):
    url = str(valor or "").strip()
    if not url:
        return ""

    match_http = re.search(r"https?://[^\\\s]+", url, re.I)
    if match_http:
        return match_http.group(0)

    match_www = re.search(r"www\.[^\\\s]+", url, re.I)
    if match_www:
        return "https://" + match_www.group(0)

    return url


def url_clicavel(valor):
    return bool(re.match(r"^https?://", str(valor or ""), re.I))


# ============================================================
# MARCAÇÃO DE STARTUPS
# ============================================================
#
# Complementa a classificação NEGOCIOS/ACADEMICO/OUTRO: todo edital que
# menciona startups no título, resumo, público-alvo ou evidência da IA recebe
# "Startups" na coluna própria da planilha. Roda na exportação, então vale
# também para editais já analisados (não precisa rodar o Qwen de novo).
#
# O nome da fonte ("Sebrae Startups") e o conteúdo bruto das páginas
# (menus, rodapés) NÃO são considerados, para evitar falsos positivos.

ROTULO_STARTUP = "Startups"

TERMO_STARTUP = re.compile(r"\bstart[\s-]?ups?\b", re.IGNORECASE)

# Menção negada logo antes do termo, ex.: "(não são empresas, startups ou
# pesquisadores elegíveis)" ou "vedada a participação de startups".
NEGACAO_ANTES_STARTUP = re.compile(
    r"(?:\bn[aã]o\s+(?:s[aã]o|[eé]|ser[aã]o|podem|pode|poder[aã]o|"
    r"inclui|incluem|aceita|aceitam|contempla|contemplam|abrange|abrangem)\b"
    r"|\bexceto\b|\bvedad[ao]s?\b|\bexclu[ií]d[ao]s?\b|\bsalvo\b)"
    r"[^.;:()\n]{0,80}$",
    re.IGNORECASE,
)

CAMPOS_TEXTO_STARTUP = (
    "titulo",
    "resumo",
    "publico_alvo",
    "publico_elegivel",
    "justificativa_classificacao",
    "perfil",
    "objetivo",
    "apoio_oferecido",
)


def texto_para_startup(item):
    partes = [item.get(campo) for campo in CAMPOS_TEXTO_STARTUP]

    entrada = item.get("entrada_ia")
    if isinstance(entrada, dict):
        partes.extend([entrada.get("perfil"), entrada.get("objetivo")])

    return "\n".join(str(parte) for parte in partes if parte)


def menciona_startup(texto):
    texto = str(texto or "")
    for achado in TERMO_STARTUP.finditer(texto):
        antes = texto[max(0, achado.start() - 120):achado.start()]
        if not NEGACAO_ANTES_STARTUP.search(antes):
            return True
    return False


def rotulo_startup(item):
    return ROTULO_STARTUP if menciona_startup(texto_para_startup(item)) else ""

def carregar_json(caminho):
    if not caminho.exists():
        return []

    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, list) else []
    except Exception:
        return []


def buscar_data_coleta(nome_arquivo, editais):
    for edital in editais:
        if edital.get("arquivo") == nome_arquivo:
            return edital.get("baixado_em", "")
    return ""


def preparar_fapesc():
    analises = carregar_json(FAPESC_ANALISES_JSON)
    editais_originais = carregar_json(FAPESC_EDITAIS_JSON)
    linhas = []

    for edital in analises:
        arquivo_original = edital.get("arquivo_original", "")
        data_coleta = buscar_data_coleta(arquivo_original, editais_originais)

        linhas.append({
            "titulo": edital.get("titulo", ""),
            "prazo_submissao": edital.get("prazo_submissao", ""),
            "resumo": edital.get("resumo", ""),
            "classificacao": edital.get("classificacao", ""),
            "startups": rotulo_startup(edital),
            "setores": edital.get("setores", ""),
            "publico_alvo": edital.get("publico_alvo", ""),
            "site": edital.get("site", "FAPESC"),
            "data_coleta": data_coleta,
            "pagina_edital": edital.get("pagina_edital", ""),
            "pdf_url": edital.get("pdf_url", ""),
        })

    return linhas


def preparar_sebrae():
    # Prefere os resumos reescritos pela IA. Se a pessoa ainda não rodou a IA,
    # usa o JSON bruto para não fazer as oportunidades desaparecerem da exportação.
    analisados = carregar_json(SEBRAE_ANALISADOS_JSON)

    if analisados:
        origem = analisados
        analisado = True
    else:
        origem = carregar_json(SEBRAE_JSON)
        analisado = False

    linhas = []

    for item in origem:
        if analisado:
            prazo = item.get("prazo_submissao", "")
            pagina = item.get("pagina_edital", "")
            data_coleta = item.get("coletado_em", "")
        else:
            prazo = item.get("prazo", "")
            pagina = item.get("link", "")
            data_coleta = item.get("coletado_em", "")

            if "fluxo contínuo" in prazo.lower() or "fluxo continuo" in prazo.lower():
                prazo = "Prazo continuo"

        linhas.append({
            "titulo": item.get("titulo", ""),
            "prazo_submissao": prazo,
            "resumo": item.get("resumo", ""),
            "classificacao": item.get("classificacao", "") if analisado else "",
            "startups": rotulo_startup(item),
            "setores": item.get("setores", "") if analisado else "",
            "publico_alvo": item.get("publico_alvo", "") if analisado else "",
            "site": item.get("site", "Sebrae Startups"),
            "data_coleta": data_coleta,
            "pagina_edital": pagina,
            "pdf_url": "",
        })

    return linhas



def preparar_finep():
    # Prefere o resumo gerado pela IA. Se a IA ainda não foi executada,
    # exporta o JSON bruto sem esconder as oportunidades coletadas.
    analisados = carregar_json(FINEP_ANALISADOS_JSON)

    if analisados:
        origem = analisados
        analisado = True
    else:
        origem = carregar_json(FINEP_JSON)
        analisado = False

    linhas = []

    for item in origem:
        if analisado:
            prazo = item.get("prazo_submissao", "")
            pagina = item.get("pagina_edital", "")
            data_coleta = item.get("coletado_em", "")
            resumo = item.get("resumo", "")
        else:
            prazo = item.get("prazo", "")
            pagina = item.get("link", "")
            data_coleta = item.get("coletado_em", "")
            resumo = item.get("resumo", "") if item.get("tipo_pagina") != "credito" else ""

            if "fluxo contínuo" in prazo.lower() or "fluxo continuo" in prazo.lower():
                prazo = "Prazo continuo"

        linhas.append({
            "titulo": item.get("titulo", ""),
            "prazo_submissao": prazo,
            "resumo": resumo,
            "classificacao": item.get("classificacao", "") if analisado else "",
            "startups": rotulo_startup(item),
            "setores": item.get("setores", "") if analisado else "",
            "publico_alvo": item.get("publico_alvo", "") if analisado else "",
            "site": item.get("site", "FINEP"),
            "data_coleta": data_coleta,
            "pagina_edital": pagina,
            "pdf_url": item.get("pdf_url", "") if analisado else "",
        })

    return linhas



def preparar_fapesp():
    # A FAPESP, assim como a FAPESC, ganha classificação e resumo na etapa IA.
    # Se ainda não houve análise, mantém os dados brutos disponíveis no export.
    analisados = carregar_json(FAPESP_ANALISADOS_JSON)

    if analisados:
        origem = analisados
        analisado = True
    else:
        origem = carregar_json(FAPESP_JSON)
        analisado = False

    linhas = []

    for item in origem:
        if analisado:
            prazo = item.get("prazo_submissao", "")
            resumo = item.get("resumo", "")
            classificacao = item.get("classificacao", "")
            publico = item.get("publico_alvo", "")
            pagina = item.get("pagina_edital", "")
            data_coleta = item.get("coletado_em", "")
        else:
            prazo = item.get("data_limite", "")
            resumo = ""
            classificacao = ""
            publico = ""
            pagina = item.get("link", "")
            data_coleta = item.get("coletado_em", "")

        linhas.append({
            "titulo": item.get("titulo", ""),
            "prazo_submissao": prazo,
            "resumo": resumo,
            "classificacao": classificacao,
            "startups": rotulo_startup(item),
            "setores": item.get("setores", "") if analisado else "",
            "publico_alvo": publico,
            "site": item.get("site", "FAPESP"),
            "data_coleta": data_coleta,
            "pagina_edital": pagina,
            "pdf_url": "",
        })

    return linhas



def preparar_fonte_json(chave):
    json_bruto, json_analisado, nome_padrao = FONTES_JSON_CONFIG[chave]
    analisados = carregar_json(json_analisado)

    if analisados:
        origem = analisados
        analisado = True
    else:
        origem = carregar_json(json_bruto)
        analisado = False

    linhas = []
    for item in origem:
        if analisado:
            prazo = item.get("prazo_submissao", "")
            resumo = item.get("resumo", "")
            classificacao = item.get("classificacao", "")
            publico = item.get("publico_alvo", "")
            pagina = item.get("pagina_edital", "")
        else:
            prazo = item.get("prazo", "")
            resumo = item.get("resumo", "")
            classificacao = ""
            publico = ""
            link_bruto = item.get("link", "")
            caminho_link = str(link_bruto or "").lower().split("?", 1)[0].split("#", 1)[0]
            pagina = "" if caminho_link.endswith(".pdf") else link_bruto

        if analisado:
            pdf_url = item.get("pdf_url", "")
        else:
            link_bruto = item.get("link", "")
            caminho_link = str(link_bruto or "").lower().split("?", 1)[0].split("#", 1)[0]
            pdf_url = link_bruto if caminho_link.endswith(".pdf") else ""

        linhas.append({
            "titulo": item.get("titulo", ""),
            "prazo_submissao": prazo,
            "resumo": resumo,
            "classificacao": classificacao,
            "startups": rotulo_startup(item),
            "setores": item.get("setores", "") if analisado else "",
            "publico_alvo": publico,
            "site": item.get("site", nome_padrao),
            "data_coleta": item.get("coletado_em", ""),
            "pagina_edital": pagina,
            "pdf_url": pdf_url,
        })

    return linhas

def _fontes_exportacao(fonte="todos"):
    ordem = [
        "fapesc", "sebrae", "finep", "fapesp",
        "bndes", "fapeam", "fapemig", "fappr", "petrobras", "rota_fomento",
    ]

    if isinstance(fonte, (list, tuple, set)):
        recebidas = [str(x or "").strip().lower() for x in fonte]
        selecionadas = [x for x in ordem if x in recebidas]
        return selecionadas or ["fapesc"]

    valor = str(fonte or "todos").strip().lower()
    if valor == "todos":
        return ordem
    if valor == "ambos":
        return ["fapesc", "sebrae"]
    if valor in ordem:
        return [valor]
    return ordem


def exportar_excel(fonte="todos", progresso=None):
    selecionadas = _fontes_exportacao(fonte)

    linhas = []

    if "fapesc" in selecionadas:
        linhas.extend(preparar_fapesc())

    if "sebrae" in selecionadas:
        linhas.extend(preparar_sebrae())

    if "finep" in selecionadas:
        linhas.extend(preparar_finep())

    if "fapesp" in selecionadas:
        linhas.extend(preparar_fapesp())

    for chave_fonte_json in FONTES_JSON_CONFIG:
        if chave_fonte_json in selecionadas:
            linhas.extend(preparar_fonte_json(chave_fonte_json))

    if not linhas:
        raise ValueError("Nenhuma oportunidade encontrada para exportar.")

    total = len(linhas)
    if progresso:
        progresso(
            processados=0,
            total=total,
            exportados=0,
            erros=0,
            etapa="gerando_planilha",
        )

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    caminho = EXPORT_DIR / "editais_fomento.xlsx"

    workbook = xlsxwriter.Workbook(str(caminho))
    worksheet = workbook.add_worksheet("Editais")

    formato_header = workbook.add_format({
        "bold": True,
        "font_color": "#FFFFFF",
        "bg_color": "#155E75",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })

    formato_texto = workbook.add_format({
        "border": 1,
        "valign": "top",
        "text_wrap": True,
    })

    formato_centro = workbook.add_format({
        "border": 1,
        "valign": "top",
        "align": "center",
        "text_wrap": True,
    })

    formato_link = workbook.add_format({
        "font_color": "#0563C1",
        "underline": True,
        "border": 1,
        "valign": "top",
    })

    formato_startup = workbook.add_format({
        "bold": True,
        "font_color": "#7C2D12",
        "bg_color": "#FFEDD5",
        "border": 1,
        "valign": "top",
        "align": "center",
    })

    colunas = [
        "Título",
        "Prazo de submissão",
        "Resumo",
        "Classificação",
        "Startups",
        "Setores",
        "Público-alvo",
        "Fonte",
        "Data de coleta",
        "Página do edital",
        "PDF do edital",
    ]

    for coluna, titulo in enumerate(colunas):
        worksheet.write(0, coluna, titulo, formato_header)

    for linha, edital in enumerate(linhas, start=1):
        worksheet.write(linha, 0, edital.get("titulo", ""), formato_texto)
        worksheet.write(linha, 1, edital.get("prazo_submissao", ""), formato_centro)
        worksheet.write(linha, 2, edital.get("resumo", ""), formato_texto)
        worksheet.write(linha, 3, edital.get("classificacao", ""), formato_centro)

        startups = edital.get("startups", "")
        worksheet.write(linha, 4, startups, formato_startup if startups else formato_centro)

        worksheet.write(linha, 5, edital.get("setores", ""), formato_texto)
        worksheet.write(linha, 6, edital.get("publico_alvo", ""), formato_texto)
        worksheet.write(linha, 7, edital.get("site", ""), formato_centro)
        worksheet.write(linha, 8, edital.get("data_coleta", ""), formato_centro)

        pagina = normalizar_url(edital.get("pagina_edital", ""))
        # Salva a URL VISÍVEL como texto puro. write_string evita que o
        # XlsxWriter converta automaticamente a URL em hyperlink clicável.
        worksheet.write_string(linha, 9, pagina, formato_texto)

        pdf = normalizar_url(edital.get("pdf_url", ""))
        if url_clicavel(pdf):
            worksheet.write_url(linha, 10, pdf, formato_link, "Abrir edital")
        else:
            worksheet.write(linha, 10, pdf, formato_texto)

        if progresso:
            progresso(
                processados=linha,
                total=total,
                exportados=linha,
                erros=0,
                item=edital.get("titulo", ""),
                etapa="gerando_planilha",
            )

    worksheet.set_column("A:A", 50)   # Título
    worksheet.set_column("B:B", 22)   # Prazo de submissão
    worksheet.set_column("C:C", 58)   # Resumo
    worksheet.set_column("D:D", 18)   # Classificação
    worksheet.set_column("E:E", 14)   # Startups
    worksheet.set_column("F:F", 26)   # Setores
    worksheet.set_column("G:G", 45)   # Público-alvo
    worksheet.set_column("H:H", 18)   # Fonte
    worksheet.set_column("I:I", 22)   # Data de coleta
    worksheet.set_column("J:J", 58)   # Página do edital
    worksheet.set_column("K:K", 18)   # PDF do edital
    worksheet.set_row(0, 30)
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, len(linhas), len(colunas) - 1)

    workbook.close()
    return caminho