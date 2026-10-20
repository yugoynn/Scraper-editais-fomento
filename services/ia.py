import json
import hashlib
import re
import unicodedata
import traceback
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent

MARKDOWN_DIR = PROJECT_ROOT / "dados" / "fapesc" / "markdown"
ANALISADOS_DIR = PROJECT_ROOT / "dados" / "fapesc" / "analisados"
INDICE_EDITAIS = PROJECT_ROOT / "dados" / "fapesc" / "pdf" / "editais.json"
SEBRAE_JSON = PROJECT_ROOT / "dados" / "sebrae" / "oportunidades.json"
SEBRAE_ANALISADOS_DIR = PROJECT_ROOT / "dados" / "sebrae" / "analisados"
SEBRAE_ANALISADOS_JSON = SEBRAE_ANALISADOS_DIR / "oportunidades_analisadas.json"
FINEP_JSON = PROJECT_ROOT / "dados" / "finep" / "oportunidades.json"
FINEP_ANALISADOS_DIR = PROJECT_ROOT / "dados" / "finep" / "analisados"
FINEP_ANALISADOS_JSON = FINEP_ANALISADOS_DIR / "oportunidades_analisadas.json"
FAPESP_JSON = PROJECT_ROOT / "dados" / "fapesp" / "chamadas_fapesp.json"
FAPESP_ANALISADOS_DIR = PROJECT_ROOT / "dados" / "fapesp" / "analisados"
FAPESP_ANALISADOS_JSON = FAPESP_ANALISADOS_DIR / "chamadas_analisadas.json"

FONTES_JSON_CONFIG = {
    "bndes": {"nome": "BNDES", "json": PROJECT_ROOT / "dados" / "bndes" / "editais.json", "analisados": PROJECT_ROOT / "dados" / "bndes" / "analisados" / "editais_analisados.json"},
    "fapeam": {"nome": "FAPEAM", "json": PROJECT_ROOT / "dados" / "fapeam" / "editais.json", "analisados": PROJECT_ROOT / "dados" / "fapeam" / "analisados" / "editais_analisados.json"},
    "fapemig": {"nome": "FAPEMIG", "json": PROJECT_ROOT / "dados" / "fapemig" / "editais.json", "analisados": PROJECT_ROOT / "dados" / "fapemig" / "analisados" / "editais_analisados.json"},
    "fappr": {"nome": "Fundação Araucária (FAPPR)", "json": PROJECT_ROOT / "dados" / "fappr" / "editais.json", "analisados": PROJECT_ROOT / "dados" / "fappr" / "analisados" / "editais_analisados.json"},
    "petrobras": {"nome": "Petrobras", "json": PROJECT_ROOT / "dados" / "petrobras" / "desafios.json", "analisados": PROJECT_ROOT / "dados" / "petrobras" / "analisados" / "desafios_analisados.json"},
    "rota_fomento": {"nome": "Rota do Fomento", "json": PROJECT_ROOT / "dados" / "rota_fomento" / "editais.json", "analisados": PROJECT_ROOT / "dados" / "rota_fomento" / "analisados" / "editais_analisados.json"},
}

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_MODEL = "qwen3.5:9b"
OLLAMA_NUM_CTX = 8192
ANALISE_VERSION = 16
IA_BUILD = "2026-08-24-multifontes-qwen-classificacao-resumo-v19"
FINEP_ANALISE_VERSION = 1
FAPESP_ANALISE_VERSION = 3
FONTES_JSON_ANALISE_VERSION = 1

ANALISADOS_DIR.mkdir(parents=True, exist_ok=True)
SEBRAE_ANALISADOS_DIR.mkdir(parents=True, exist_ok=True)
FINEP_ANALISADOS_DIR.mkdir(parents=True, exist_ok=True)
FAPESP_ANALISADOS_DIR.mkdir(parents=True, exist_ok=True)
for _cfg_fonte_json in FONTES_JSON_CONFIG.values():
    _cfg_fonte_json["analisados"].parent.mkdir(parents=True, exist_ok=True)

# Diagnóstico proposital: prova qual arquivo o backend realmente importou.
print(
    f">>> IA CARREGADA: {Path(__file__).resolve()} | versão {ANALISE_VERSION} | "
    f"{IA_BUILD} | modelo {OLLAMA_MODEL} | contexto {OLLAMA_NUM_CTX}"
)


SCHEMA_FATOS = {
    "type": "object",
    "properties": {
        "objetivo": {
            "type": "string"
        },
        "apoio_oferecido": {
            "type": "string"
        },
        "valor_apoio": {
            "type": "string"
        }
    },
    "required": [
        "objetivo",
        "apoio_oferecido",
        "valor_apoio"
    ],
    "additionalProperties": False
}


SCHEMA_CLASSIFICACAO = {
    "type": "object",
    "properties": {
        "publico_elegivel": {
            "type": "string"
        },
        "classificacao": {
            "type": "string",
            "enum": [
                "NEGOCIOS",
                "ACADEMICO",
                "OUTRO"
            ]
        },
        "evidencia": {
            "type": "string"
        }
    },
    "required": [
        "publico_elegivel",
        "classificacao",
        "evidencia"
    ],
    "additionalProperties": False
}


SCHEMA_RESUMO = {
    "type": "object",
    "properties": {
        "resumo": {
            "type": "string"
        }
    },
    "required": [
        "resumo"
    ],
    "additionalProperties": False
}


INICIOS_PROIBIDOS = [
    "este documento",
    "este edital",
    "esta documentação",
    "esta documentacao",
    "esta análise",
    "esta analise",
    "este texto",
    "o texto",
    "o documento",
    "o edital",
    "a chamada pública",
    "a chamada publica",
    "esta chamada pública",
    "esta chamada publica",
    "essa chamada pública",
    "essa chamada publica",
    "a presente chamada",
    "o presente edital",
    "os principais pontos",
    "resumo:"
]


TERMOS_BUROCRATICOS_RESUMO = [
    "sigfapesc",
    "certidão negativa",
    "certidao negativa",
    "documentação necessária",
    "documentacao necessaria",
    "análise de admissibilidade",
    "analise de admissibilidade",
    "comissão avaliadora",
    "comissao avaliadora",
    "currículo lattes",
    "curriculo lattes",
    "prestação de contas",
    "prestacao de contas",
    "recurso administrativo",
    "recursos administrativos",
    "cronograma detalhado",
    "critérios de desempate",
    "criterios de desempate"
]


MESES = {
    "january": 1,
    "jan": 1,
    "janeiro": 1,

    "february": 2,
    "feb": 2,
    "fevereiro": 2,

    "march": 3,
    "mar": 3,
    "marco": 3,
    "março": 3,

    "april": 4,
    "apr": 4,
    "abril": 4,

    "may": 5,
    "maio": 5,

    "june": 6,
    "jun": 6,
    "junho": 6,

    "july": 7,
    "jul": 7,
    "julho": 7,

    "august": 8,
    "aug": 8,
    "agosto": 8,

    "september": 9,
    "sep": 9,
    "sept": 9,
    "setembro": 9,

    "october": 10,
    "oct": 10,
    "outubro": 10,

    "november": 11,
    "nov": 11,
    "novembro": 11,

    "december": 12,
    "dec": 12,
    "dezembro": 12
}


def normalizar(texto):
    texto = texto or ""

    texto = unicodedata.normalize(
        "NFD",
        texto
    )

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    return texto.lower().strip()


def carregar_indice():
    if not INDICE_EDITAIS.exists():
        return []

    try:
        with open(
            INDICE_EDITAIS,
            "r",
            encoding="utf-8"
        ) as arquivo:
            dados = json.load(arquivo)

        if isinstance(dados, list):
            return dados

        return []

    except Exception:
        return []


def procurar_dados_originais(nome_markdown, indice):
    nome_base = Path(nome_markdown).stem

    for edital in indice:
        arquivo_pdf = edital.get(
            "arquivo",
            ""
        )

        if Path(arquivo_pdf).stem == nome_base:
            return edital

    return {}


def verificar_ollama():
    try:
        resposta = requests.get(
            OLLAMA_TAGS_URL,
            timeout=5
        )

        resposta.raise_for_status()

    except requests.RequestException:
        raise RuntimeError(
            "O Ollama não está rodando. Abra o Ollama antes de iniciar a análise."
        )

    try:
        dados = resposta.json()

        modelos = [
            modelo.get("name", "")
            for modelo in dados.get("models", [])
        ]

        encontrado = any(
            modelo == OLLAMA_MODEL
            or modelo.startswith(OLLAMA_MODEL)
            for modelo in modelos
        )

        if not encontrado:
            raise RuntimeError(
                f"O modelo {OLLAMA_MODEL} não está instalado. "
                f"Execute: ollama pull {OLLAMA_MODEL}"
            )

    except ValueError:
        raise RuntimeError(
            "Não foi possível verificar os modelos instalados no Ollama."
        )



def chamar_ollama_texto(
    prompt,
    temperatura=0,
    num_predict=500,
    tentativas=3
):
    """
    Chama o Ollama sem exigir JSON do modelo.

    O endpoint do Ollama continua retornando seu envelope HTTP em JSON, mas o
    conteúdo gerado pelo modelo é texto simples. Assim evitamos o erro
    "Unterminated string" causado por respostas estruturadas cortadas no meio.
    """
    ultimo_erro = None

    for tentativa in range(1, tentativas + 1):
        limite_saida = max(num_predict * tentativa, num_predict)

        prompt_tentativa = prompt
        if tentativa > 1:
            prompt_tentativa += f"""

NOVA TENTATIVA {tentativa}:
Seja ainda mais curto e siga exatamente o formato de linhas solicitado.
Não use Markdown, não use bloco de código e não acrescente explicações.
"""

        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Responda de forma curta e objetiva. "
                        "Siga exatamente os rótulos de saída pedidos pelo usuário. "
                        "Não use JSON e não use bloco de código."
                    )
                },
                {
                    "role": "user",
                    "content": prompt_tentativa
                }
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperatura,
                "num_predict": limite_saida,
                "num_ctx": OLLAMA_NUM_CTX
            }
        }

        try:
            resposta = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=600
            )
            resposta.raise_for_status()

            # Este JSON é apenas o envelope da API do Ollama, não a resposta
            # semântica produzida pelo modelo.
            dados = resposta.json()
            conteudo = dados.get("message", {}).get("content", "")
            conteudo = (conteudo or "").strip()

            if conteudo:
                return conteudo

            ultimo_erro = ValueError("O Ollama retornou texto vazio.")
            print(
                f"  [OLLAMA] Resposta vazia na tentativa {tentativa}/{tentativas}. "
                "Tentando novamente..."
            )

        except Exception as erro:
            ultimo_erro = erro
            print(
                f"  [OLLAMA] Falha na tentativa {tentativa}/{tentativas}: "
                f"{type(erro).__name__}: {erro}. Tentando novamente..."
            )

    raise RuntimeError(
        "O Ollama falhou após "
        f"{tentativas} tentativas. Último erro: {ultimo_erro}"
    )


def extrair_campo_rotulado(texto, rotulo):
    """Extrai 'ROTULO: valor' sem depender de JSON."""
    padrao = rf"(?im)^\s*{re.escape(rotulo)}\s*:\s*(.*)$"
    resultado = re.search(padrao, texto or "")
    if not resultado:
        return ""
    return " ".join(resultado.group(1).strip().split())


def remover_anexos(texto):
    padroes = [
        r"(?im)^\s*#{0,6}\s*\*{0,2}ANEXO\s+[IVXLCDM0-9]+\b",
        r"(?im)^\s*ANEXO\s+[IVXLCDM0-9]+\b"
    ]

    posicoes = []

    for padrao in padroes:
        resultado = re.search(
            padrao,
            texto
        )

        if resultado:
            posicoes.append(
                resultado.start()
            )

    if posicoes:
        return texto[:min(posicoes)]

    return texto


def limpar_titulo(linha):
    linha = linha.strip()

    linha = re.sub(
        r"^[#>\-\s]+",
        "",
        linha
    )

    linha = linha.replace("**", "")
    linha = linha.replace("__", "")
    linha = linha.replace("<u>", "")
    linha = linha.replace("</u>", "")

    return " ".join(
        linha.split()
    ).strip()


def extrair_titulo_markdown(texto):
    linhas = texto.splitlines()[:120]

    termos = [
        "edital de chamada publica",
        "chamada publica",
        "edital suplementar",
        "edital de subvencao",
        "edital fapesc"
    ]

    for linha in linhas:
        titulo = limpar_titulo(
            linha
        )

        if len(titulo) < 15:
            continue

        titulo_normalizado = normalizar(
            titulo
        )

        if any(
            termo in titulo_normalizado
            for termo in termos
        ):
            return titulo

    return ""


def extrair_trechos(
    texto,
    palavras,
    antes=1000,
    depois=5000,
    max_trechos=10
):
    texto_normalizado = normalizar(
        texto
    )

    partes = []

    for palavra in palavras:
        termo = normalizar(
            palavra
        )

        inicio_busca = 0

        while True:
            posicao = texto_normalizado.find(
                termo,
                inicio_busca
            )

            if posicao == -1:
                break

            inicio = max(
                0,
                posicao - antes
            )

            fim = min(
                len(texto),
                posicao + depois
            )

            trecho = texto[
                inicio:fim
            ]

            if trecho not in partes:
                partes.append(
                    trecho
                )

            if len(partes) >= max_trechos:
                return partes

            inicio_busca = (
                posicao
                + len(termo)
            )

    return partes


def extrair_contexto_geral(texto):
    texto = remover_anexos(
        texto
    )

    palavras = [
        "objetivo",
        "objetivos",
        "finalidade",
        "apoio",
        "recursos financeiros",
        "valor global",
        "valor do apoio",
        "recursos disponíveis",
        "recursos disponiveis",
        "itens financiáveis",
        "itens financiaveis",
        "bolsas",
        "projetos"
    ]

    partes = [
        texto[:8000]
    ]

    partes.extend(
        extrair_trechos(
            texto,
            palavras,
            antes=800,
            depois=4500,
            max_trechos=8
        )
    )

    return (
        "\n\n--- TRECHO ---\n\n"
    ).join(partes)[:26000]


def extrair_contexto_classificacao(texto):
    texto = remover_anexos(
        texto
    )

    # Termos fortes: eles apontam para QUEM pode apresentar/submeter a proposta.
    # Evitamos usar "beneficiário", "bolsista" e "admissibilidade" isoladamente,
    # porque esses termos também aparecem em regras de bolsa, equipe e execução.
    palavras_fortes = [
        "público-alvo",
        "publico-alvo",
        "público alvo",
        "publico alvo",
        "quem pode participar",
        "quem poderá participar",
        "quem podera participar",
        "convida",
        "convidam",
        "apresentarem propostas",
        "apresentem propostas",
        "são elegíveis",
        "sao elegiveis",
        "poderão ser proponentes",
        "poderao ser proponentes",
        "podem ser proponentes",
        "destina-se a",
        "poderão submeter",
        "poderao submeter",
        "pode submeter",
        "podem submeter",
        "poderão apresentar proposta",
        "poderao apresentar proposta",
        "poderão apresentar propostas",
        "poderao apresentar propostas",
        "apresentar proposta",
        "apresentar propostas",
        "proponente deverá",
        "proponente devera",
        "o proponente deve",
        "requisitos do proponente",
        "requisitos para o proponente",
        "elegibilidade do proponente",
        "elegibilidade da proponente",
        "instituição proponente",
        "instituicao proponente",
        "proponente/beneficiário",
        "proponente/beneficiario",
        "proponente beneficiário",
        "proponente beneficiario",
        "podem participar",
        "poderão participar",
        "poderao participar",
        "poderá participar",
        "podera participar",
        "inscrever-se",
        "se inscrever",
        "candidatar-se"
    ]

    partes = extrair_trechos(
        texto,
        palavras_fortes,
        antes=700,
        depois=2600,
        max_trechos=8
    )

    # Só usa o começo do edital como fallback quando nenhum trecho forte foi achado.
    if not partes:
        partes = [texto[:9000]]

    contexto = (
        "\n\n--- REGRA DE ELEGIBILIDADE ---\n\n"
    ).join(partes)

    return contexto[:10000]


def criar_prompt_fatos(texto):
    return f"""
Extraia apenas informações factuais importantes para divulgar esta oportunidade
em um portal de fomentos.

Não classifique o edital.
Não procure o prazo nesta etapa.
Não faça o resumo final.

OBJETIVO

Informe em uma frase qual é o objetivo principal da oportunidade.

Não descreva o documento.
Não fale sobre cronograma, documentação ou admissibilidade.

APOIO OFERECIDO

Informe o que será apoiado, financiado ou oferecido.

Exemplos:

"Apoio financeiro para realização de eventos."
"Bolsas para profissionais atuarem em projetos."
"Recursos para desenvolvimento de projetos de inovação."

VALOR DO APOIO

Informe somente quando existir valor financeiro claramente informado.

Se houver vários valores importantes, resuma de forma curta.

Se não estiver claro, retorne string vazia.

Não invente informações.

TRECHOS DO EDITAL:

{texto}
"""


def extrair_fatos(texto):
    prompt = criar_prompt_fatos(texto) + """

FORMATO OBRIGATÓRIO DA RESPOSTA:
OBJETIVO: uma frase curta
APOIO: uma frase curta
VALOR: valor ou vazio

Use exatamente essas três linhas. Não use JSON.
"""

    try:
        resposta = chamar_ollama_texto(
            prompt,
            temperatura=0,
            num_predict=260,
            tentativas=3
        )

        objetivo = extrair_campo_rotulado(resposta, "OBJETIVO")
        apoio = extrair_campo_rotulado(resposta, "APOIO")
        valor = extrair_campo_rotulado(resposta, "VALOR")

        # Se o modelo ignorar parcialmente o formato, não derruba o edital.
        if not objetivo and not apoio:
            print("  [FATOS] Ollama não seguiu os rótulos; usando campos vazios.")

        return {
            "objetivo": objetivo,
            "apoio_oferecido": apoio,
            "valor_apoio": valor
        }

    except Exception as erro:
        print(
            "  [FATOS] Ollama falhou; continuando sem fatos estruturados "
            f"({type(erro).__name__}: {erro})."
        )
        return {
            "objetivo": "",
            "apoio_oferecido": "",
            "valor_apoio": ""
        }


# ============================================================
# CLASSIFICAÇÃO FAPESC/FAPESP - REGRA V16 (3 CATEGORIAS)
# ============================================================
#
# O objetivo do classificador é responder uma pergunta prática:
# "QUEM pode se inscrever/submeter/participar desta oportunidade?"
#
# NEGOCIOS
#   - empresa, startup, empreendedor, setor produtivo;
#   - ICT / ICTI quando a própria ICT é elegível;
#   - Centro de Inovação quando ele é o proponente;
#   - mistura de público acadêmico com empresa/ICT => NEGOCIOS.
#
# ACADEMICO
#   - oportunidade exclusivamente acadêmica/universitária;
#   - pesquisadores, docentes, estudantes, grupos de pesquisa;
#   - universidades, UDESC, UFSC, Institutos Federais etc.;
#   - sem empresa/ICT elegível no mesmo público.
#
# OUTRO
#   - seleção individual de bolsistas/candidatos/profissionais;
#   - servidores ou pessoas físicas;
#   - qualquer situação em que não exista prova de que uma empresa/ICT pode
#     concorrer e que também não seja uma chamada exclusivamente acadêmica.
#
# IMPORTANTE:
# - "FAPESC é uma fundação", "CIASC é uma ICT" ou "EPAGRI é uma empresa"
#   NÃO define a classificação. A instituição parceira/beneficiária não é
#   automaticamente o público que pode se inscrever.
# - A classificação usa primeiro o trecho que descreve o público elegível.

TERMOS_NEGOCIOS_DIRETOS = [
    "empresa",
    "empresas",
    "microempresa",
    "microempresas",
    "pequena empresa",
    "pequenas empresas",
    "startup",
    "startups",
    "empreendedor",
    "empreendedores",
    "empreendimento",
    "empreendimentos",
    "pessoa juridica com fins lucrativos",
    "pessoas juridicas com fins lucrativos",
    "setor produtivo",
    "centro de inovacao",
    "centros de inovacao",
    "incubadora",
    "incubadoras",
    "aceleradora",
    "aceleradoras",
    "cooperativa",
    "cooperativas",
]

TERMOS_ICT_NEGOCIOS = [
    "ict",
    "icts",
    "icti",
    "ictis",
    "instituicao cientifica tecnologica e de inovacao",
    "instituicoes cientificas tecnologicas e de inovacao",
    "instituicao cientifica, tecnologica e de inovacao",
    "instituicoes cientificas, tecnologicas e de inovacao",
]

TERMOS_ACADEMICOS_PESSOAS = [
    "pesquisador",
    "pesquisadores",
    "pesquisadora",
    "pesquisadoras",
    "docente",
    "docentes",
    "professor",
    "professores",
    "professora",
    "professoras",
    "estudante",
    "estudantes",
    "discente",
    "discentes",
    "lider de grupo de pesquisa",
    "lideres de grupos de pesquisa",
]

TERMOS_ACADEMICOS_INSTITUICOES = [
    "grupo de pesquisa",
    "grupos de pesquisa",
    "programa de pos-graduacao",
    "programas de pos-graduacao",
    "pesquisa universitaria",
    "pesquisas universitarias",
    "universidade",
    "universidades",
    "universidade federal",
    "universidades federais",
    "universidade estadual",
    "universidades estaduais",
    "universidade publica",
    "universidades publicas",
    "centro universitario",
    "centros universitarios",
    "instituto federal",
    "institutos federais",
    "instituicao publica de ensino",
    "instituicoes publicas de ensino",
    "instituicao federal de ensino",
    "instituicoes federais de ensino",
    "instituicao estadual de ensino",
    "instituicoes estaduais de ensino",
    "instituicao de ensino superior",
    "instituicoes de ensino superior",
    "instituicao de pesquisa",
    "instituicoes de pesquisa",
    "instituicao de ciencia e tecnologia",
    "instituicoes de ciencia e tecnologia",
    # Instituições catarinenses recorrentes nos editais analisados.
    "udesc",
    "ufsc",
    "ifsc",
    "ifc",
    "unisenaI",
    "unisenaI/sc",
]

TERMOS_OUTROS_INDIVIDUAIS = [
    "bolsista",
    "bolsistas",
    "candidato",
    "candidatos",
    "candidata",
    "candidatas",
    "pessoa fisica",
    "pessoas fisicas",
    "profissional",
    "profissionais",
    "servidor",
    "servidores",
    "servidora",
    "servidoras",
    "tecnico",
    "tecnicos",
    "tecnica",
    "tecnicas",
    "especialista",
    "especialistas",
]

# Compatibilidade com trechos antigos do módulo.
TERMOS_NEGOCIOS = TERMOS_NEGOCIOS_DIRETOS + TERMOS_ICT_NEGOCIOS
TERMOS_ACADEMICOS = TERMOS_ACADEMICOS_PESSOAS + TERMOS_ACADEMICOS_INSTITUICOES
TERMOS_OUTROS = TERMOS_OUTROS_INDIVIDUAIS


# ============================================================
# CLASSIFICAÇÃO DE SETORES (HÍBRIDA: PALAVRAS-CHAVE + QWEN)
# ============================================================
#
# Um edital pode servir a nenhum, a um ou a vários setores.
#
# 1) Primeiro tentamos casar por palavras-chave (rápido, gratuito e roda para
#    TODAS as fontes, inclusive os editais que não chamam o Qwen).
# 2) Só quando NENHUM setor é detectado por palavra-chave chamamos o Qwen para
#    decidir (fallback do modo híbrido). Se o Qwen estiver indisponível ou
#    falhar, o edital não é derrubado: recebe "Não identificado".
#
# A ordem das chaves deste dicionário é a ordem em que os setores aparecem na
# planilha. As listas usam termos SEM acento porque a comparação é feita sobre
# o texto normalizado (normalizar()).

SETOR_NAO_IDENTIFICADO = "Não identificado"

SETORES_KEYWORDS = {
    "Plástico": [
        "plastico",
        "plasticos",
        "termoplastico",
        "termoplasticos",
        "polimero",
        "polimeros",
        "polietileno",
        "polipropileno",
        "poliuretano",
        "pvc",
        "embalagem plastica",
        "embalagens plasticas",
        "injecao plastica",
        "transformados plasticos",
    ],
    "Comércio": [
        "comercio",
        "comercio varejista",
        "comercio atacadista",
        "varejo",
        "varejista",
        "atacado",
        "atacadista",
        "lojista",
        "loja",
        "lojas",
        "ponto de venda",
        "franquia",
        "franquias",
        "comercio eletronico",
        "e-commerce",
        "ecommerce",
    ],
    "Turismo": [
        "turismo",
        "turistico",
        "turistica",
        "turisticos",
        "turisticas",
        "hotelaria",
        "hotel",
        "hoteis",
        "pousada",
        "pousadas",
        "agencia de viagem",
        "agencias de viagem",
        "agencia de viagens",
        "hospitalidade",
        "ecoturismo",
        "receptivo turistico",
    ],
    "Mineral": [
        "mineral",
        "minerais",
        "mineracao",
        "minerio",
        "minerios",
        "extracao mineral",
        "beneficiamento mineral",
        "jazida",
        "jazidas",
        "lavra",
        "geologia",
        "extrativismo mineral",
    ],
    "Metalmecânico": [
        "metalmecanico",
        "metalmecanica",
        "metal-mecanico",
        "metal-mecanica",
        "metal mecanico",
        "metal mecanica",
        "metalurgia",
        "metalurgico",
        "siderurgia",
        "siderurgico",
        "usinagem",
        "fundicao",
        "caldeiraria",
        "estamparia",
        "ferramentaria",
        "forjaria",
        "soldagem",
        "maquinas e equipamentos",
    ],
    "Cerâmico": [
        "ceramico",
        "ceramica",
        "ceramicos",
        "ceramicas",
        "porcelanato",
        "revestimento ceramico",
        "revestimentos ceramicos",
        "refratario",
        "refratarios",
        "louca",
        "loucas",
        "telha ceramica",
        "argila",
    ],
    "Químico": [
        "quimico",
        "quimica",
        "quimicos",
        "quimicas",
        "petroquimico",
        "petroquimica",
        "farmoquimico",
        "farmoquimica",
        "fertilizante",
        "fertilizantes",
        "defensivo agricola",
        "defensivos agricolas",
        "tintas e vernizes",
        "industria quimica",
        "reagente quimico",
    ],
    "Tecnologia": [
        "software",
        "hardware",
        "aplicativo",
        "aplicativos",
        "tecnologia da informacao",
        "tecnologias da informacao",
        "desenvolvimento de sistemas",
        "desenvolvimento de software",
        "inteligencia artificial",
        "startup de base tecnologica",
        "base tecnologica",
        "internet das coisas",
        "jogos digitais",
        "games",
        "deeptech",
        "fintech",
        "biotecnologia",
    ],
    "Confecção": [
        "confeccao",
        "confeccoes",
        "textil",
        "texteis",
        "vestuario",
        "malharia",
        "tecelagem",
        "fiacao",
        "costura",
        "roupas",
        "uniformes",
        "industria da moda",
        "jeans",
    ],
    "Agronegócio": [
        "agronegocio",
        "agronegocios",
        "agroneg",
        "agricultura",
        "agricola",
        "agropecuaria",
        "agropecuario",
        "pecuaria",
        "agroindustria",
        "agroindustrial",
        "lavoura",
        "cafeicultura",
        "hortifruti",
        "produtor rural",
        "produtores rurais",
        "producao rural",
        "agtech",
        "agritech",
    ],
}

# Variantes aceitas ao INTERPRETAR a resposta do Qwen (que devolve os NOMES dos
# setores). São stems separados dos keywords acima, porque na fonte procuramos
# termos específicos (ex.: "software") e não a palavra "tecnologia".
SETORES_NOMES_ALIASES = {
    "Plástico": ["plastic"],
    "Comércio": ["comercio", "varejo", "atacado"],
    "Turismo": ["turism", "hotelaria"],
    "Mineral": ["mineral", "mineracao", "minerio"],
    "Metalmecânico": ["metalmec", "metal mecanic", "metal-mecanic", "metalurg"],
    "Cerâmico": ["ceramic"],
    "Químico": ["quimic"],
    "Tecnologia": ["tecnolog", "software", "tecnologia da informacao"],
    "Confecção": ["confec", "textil", "vestuario", "moda"],
    "Agronegócio": ["agroneg", "agronegocio", "agro", "agricult", "agropecu", "pecuaria"],
}


def classificar_setores_por_regras(texto):
    """Retorna a lista de setores detectados por palavra-chave, na ordem oficial."""
    n = normalizar(texto)
    if not n:
        return []

    encontrados = []
    for setor, termos in SETORES_KEYWORDS.items():
        if any(normalizar(termo) in n for termo in termos):
            encontrados.append(setor)

    return encontrados


def _parse_setores_resposta_ia(resposta):
    """Converte a resposta do Qwen (nomes de setores) na lista canônica."""
    n = normalizar(resposta)
    if not n or "nenhum" in n or "nao identificado" in n:
        return []

    encontrados = []
    for setor, aliases in SETORES_NOMES_ALIASES.items():
        if any(alias in n for alias in aliases):
            encontrados.append(setor)

    return encontrados


def criar_prompt_setores_ia(contexto):
    lista = "\n".join(f"- {setor}" for setor in SETORES_KEYWORDS)

    return f"""
Identifique a quais SETORES ECONÔMICOS esta oportunidade se destina.

Escolha SOMENTE entre os setores abaixo (pode escolher um ou mais):
{lista}

REGRAS:
- baseie-se apenas no conteúdo fornecido; não invente;
- se a oportunidade servir a mais de um setor, liste todos os que se aplicam;
- se ela não se encaixar claramente em nenhum desses setores, responda NENHUM;
- não crie setores novos fora da lista;
- responda em UMA única linha, sem Markdown.

FORMATO OBRIGATÓRIO:
SETORES: setor1, setor2

ou:
SETORES: NENHUM

CONTEÚDO DA OPORTUNIDADE:
{contexto}
"""


def classificar_setores_ia(texto):
    """Fallback do modo híbrido: usa o Qwen quando as palavras-chave não acham nada."""
    verificar_ollama()

    contexto = _texto_compacto_classificacao(texto, limite=12000)

    resposta = chamar_ollama_texto(
        criar_prompt_setores_ia(contexto),
        temperatura=0,
        num_predict=120,
        tentativas=2,
    )

    linha = extrair_campo_rotulado(resposta, "SETORES") or resposta
    return _parse_setores_resposta_ia(linha)


def analisar_setores(texto):
    """Classificação HÍBRIDA de setores.

    1) tenta por palavras-chave;
    2) se nada casar, tenta o Qwen;
    3) se ainda assim nada, retorna "Não identificado".

    Sempre retorna uma string pronta para a planilha (setores separados por
    vírgula, ou "Não identificado").
    """
    try:
        setores = classificar_setores_por_regras(texto)

        if not setores:
            try:
                setores = classificar_setores_ia(texto)
                if setores:
                    print(f"  [SETORES] IA detectou: {', '.join(setores)}")
            except Exception as erro:
                print(
                    "  [SETORES] IA indisponível/falhou; usando 'Não identificado' "
                    f"({type(erro).__name__}: {erro})."
                )
                setores = []
        else:
            print(f"  [SETORES] Palavras-chave: {', '.join(setores)}")

        if setores:
            return ", ".join(setores)

        return SETOR_NAO_IDENTIFICADO

    except Exception as erro:
        print(
            "  [SETORES] Falha interna; usando 'Não identificado' "
            f"({type(erro).__name__}: {erro})."
        )
        return SETOR_NAO_IDENTIFICADO


def _tem_termo(texto_normalizado, termos):
    return any(normalizar(termo) in texto_normalizado for termo in termos)


def _tem_ict_como_publico(texto_normalizado):
    # Limite de palavra evita confundir ICT com CTI.
    if re.search(r"\bict(?:s|i|is)?\b", texto_normalizado):
        return True

    return _tem_termo(texto_normalizado, TERMOS_ICT_NEGOCIOS[4:])


def _limpar_trecho_publico(texto):
    texto = texto or ""
    texto = re.sub(r"</?mark>", "", texto, flags=re.IGNORECASE)
    texto = texto.replace("**", "").replace("__", "")
    texto = re.sub(r"^[#>\-\s]+", "", texto)
    return " ".join(texto.split()).strip(" .,:;-")


def _texto_compacto_classificacao(texto, limite=18000):
    texto = remover_anexos(texto or "")[:limite]
    texto = re.sub(r"</?mark>", "", texto, flags=re.IGNORECASE)
    texto = texto.replace("**", "").replace("__", "")
    return " ".join(texto.split())


def extrair_publicos_elegiveis(texto):
    """
    Extrai candidatos a público-alvo e mantém a posição em que aparecem.

    O primeiro trecho forte do edital normalmente define o certame. Isso evita
    que uma regra posterior sobre bolsistas/equipe substitua um proponente
    empresarial ou acadêmico definido logo na abertura.
    """
    compacto = _texto_compacto_classificacao(texto)
    achados = []

    # Ex.: "convida empresas ... a apresentarem propostas"
    padrao_convite = re.compile(
        r"\bconvid(?:a|am)\s+(?P<publico>.{2,650}?)\s+a\s+"
        r"(?:submeter(?:em)?|apresentar(?:em)?|inscrever(?:em)?|"
        r"participar(?:em)?|candidatar(?:em)?)\b",
        flags=re.IGNORECASE,
    )
    for m in padrao_convite.finditer(compacto):
        publico = _limpar_trecho_publico(m.group("publico"))
        if publico:
            achados.append((m.start(), 0, publico, "convite"))

    # Ex.: "convida empresas ... interessadas em participar de projetos".
    padrao_convite_interesse = re.compile(
        r"\bconvid(?:a|am)\s+(?P<publico>.{2,450}?)\s+"
        r"(?:interessad(?:a|as|o|os)\s+em|para)\s+participar\b",
        flags=re.IGNORECASE,
    )
    for m in padrao_convite_interesse.finditer(compacto):
        publico = _limpar_trecho_publico(m.group("publico"))
        if publico:
            achados.append((m.start(), 0, publico, "convite"))

    # Ex.: "seleção de bolsistas qualificados" / "seleção dos candidatos".
    padrao_selecao = re.compile(
        r"\bsele[cç][aã]o\s+(?:de|dos|das)\s+"
        r"(?P<publico>bolsistas?|candidatos?|candidatas?|profissionais?|"
        r"estudantes?|discentes?|pesquisadores?|pesquisadoras?|servidores?|"
        r"servidoras?|especialistas?)\b",
        flags=re.IGNORECASE,
    )
    for m in padrao_selecao.finditer(compacto):
        publico = _limpar_trecho_publico(m.group("publico"))
        achados.append((m.start(), 1, publico, "selecao"))

    # Ex.: "selecionar bolsistas qualificados para..."
    padrao_selecionar = re.compile(
        r"\bselecionar\s+(?P<publico>bolsistas?|candidatos?|candidatas?|"
        r"profissionais?|estudantes?|discentes?|pesquisadores?|pesquisadoras?|"
        r"servidores?|servidoras?|especialistas?)\b",
        flags=re.IGNORECASE,
    )
    for m in padrao_selecionar.finditer(compacto):
        publico = _limpar_trecho_publico(m.group("publico"))
        achados.append((m.start(), 1, publico, "selecionar"))

    # Ex.: "Elegibilidade: Pesquisadores..." / "Público-alvo: empresas..."
    padrao_elegibilidade = re.compile(
        r"\b(?:elegibilidade|p[uú]blico\s*[- ]?alvo|quem\s+pode\s+"
        r"(?:participar|submeter|solicitar))\s*:?\s*"
        r"(?P<publico>.{2,650}?)(?=(?:\bmodalidade\b|\bsubmiss[aã]o\b|"
        r"\bcontato\b|\bcronograma\b|\b\d+[.)]\s)|[.;]|$)",
        flags=re.IGNORECASE,
    )
    for m in padrao_elegibilidade.finditer(compacto):
        publico = _limpar_trecho_publico(m.group("publico"))
        if publico:
            achados.append((m.start(), 0, publico, "elegibilidade"))

    # Ex.: "destina-se a pequenas empresas..." / "destinada a pesquisadores..."
    padrao_destinado = re.compile(
        r"\b(?:destina-se|destinad[ao]s?|direcionad[ao]s?|voltad[ao]s?)\s+"
        r"(?:a|ao|aos|as|para)\s+(?P<publico>.{2,500}?)(?:[.;]|$)",
        flags=re.IGNORECASE,
    )
    for m in padrao_destinado.finditer(compacto):
        publico = _limpar_trecho_publico(m.group("publico"))
        if publico:
            achados.append((m.start(), 1, publico, "destinado"))

    # Ex.: "empresas poderão submeter propostas".
    padrao_publico_acao = re.compile(
        r"(?P<publico>(?:micro|pequenas?\s+)?empresas?|startups?|"
        r"empreendedores?|(?:institui[cç][oõ]es?\s+)?(?:ict|icti)s?|"
        r"pesquisadores?|pesquisadoras?|estudantes?|docentes?)"
        r"[^.;]{0,220}\b(?:podem|poder[aã]o|dever[aã]o)\s+"
        r"(?:submeter|apresentar|enviar|inscrever|solicitar|participar)",
        flags=re.IGNORECASE,
    )
    for m in padrao_publico_acao.finditer(compacto):
        publico = _limpar_trecho_publico(m.group("publico"))
        if publico:
            achados.append((m.start(), 1, publico, "acao_publico"))

    # Ex.: "o proponente deverá ser uma empresa..."
    padrao_proponente = re.compile(
        r"\b(?:o\s+)?proponente\s+(?:dever[aá]|deve|poder[aá]|pode)\s+ser\s+"
        r"(?P<publico>.{2,300}?)(?:[.;]|$)",
        flags=re.IGNORECASE,
    )
    for m in padrao_proponente.finditer(compacto):
        publico = _limpar_trecho_publico(m.group("publico"))
        if publico:
            achados.append((m.start(), 2, publico, "proponente"))

    # Remove duplicatas preservando o achado mais cedo/forte.
    saida = []
    vistos = set()
    for posicao, prioridade, publico, origem in sorted(achados, key=lambda x: (x[0], x[1])):
        chave = normalizar(publico)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        saida.append({
            "posicao": posicao,
            "publico": publico,
            "origem": origem,
        })

    return saida


def _classificar_publico(publico):
    n = normalizar(publico)
    if not n:
        return ""

    # Empresa/ICT elegível tem prioridade em uma chamada mista.
    if _tem_ict_como_publico(n) or _tem_termo(n, TERMOS_NEGOCIOS_DIRETOS):
        return "NEGOCIOS"

    # Bolsista/candidato/profissional é pessoa física: não é negócio.
    if _tem_termo(n, TERMOS_OUTROS_INDIVIDUAIS):
        return "OUTRO"

    # Público acadêmico explícito.
    if (
        _tem_termo(n, TERMOS_ACADEMICOS_INSTITUICOES)
        or _tem_termo(n, TERMOS_ACADEMICOS_PESSOAS)
    ):
        return "ACADEMICO"

    return ""


def _fallback_classificacao_inicio(texto):
    """Fallback conservador. NEGOCIOS nunca é presumido sem evidência."""
    inicio = normalizar(_texto_compacto_classificacao(texto, limite=9000))

    # Seleção individual de bolsa/candidato no enunciado do edital.
    if re.search(
        r"\b(?:selecao\s+(?:de|dos|das)|selecionar)\s+"
        r"(?:bolsistas?|candidatos?|candidatas?|profissionais?|servidores?|"
        r"servidoras?|especialistas?)\b",
        inicio,
    ):
        return "OUTRO"

    # Sinais empresariais somente quando ligados à ação de participação.
    padroes_negocios = [
        r"convida[^.;]{0,500}\bempresas?\b[^.;]{0,500}\b(?:submeter|apresentar|participar)",
        r"convida[^.;]{0,500}\b(?:ict|icts|icti|ictis)\b[^.;]{0,500}\b(?:submeter|apresentar|participar)",
        r"convida[^.;]{0,500}\bcentros? de inovacao\b[^.;]{0,500}\b(?:submeter|apresentar|participar)",
        r"proponente[^.;]{0,120}\b(?:empresa|startup|ict|icti|centro de inovacao)\b",
        r"elegibilidade[^.;]{0,500}\b(?:empresas?|startups?|empreendedores?|ict|icts|icti|ictis)\b",
        r"(?:destina-se|destinada|destinado|direcionada|direcionado)[^.;]{0,450}\b(?:empresas?|startups?|empreendedores?|ict|icts|icti|ictis)\b",
        r"\bpipe\b[^.;]{0,900}\bpequenas empresas\b",
        r"pesquisa[^.;]{0,350}\bem pequenas empresas\b",
        r"projeto[^.;]{0,350}\bexecutad[oa] em empresas\b",
    ]
    if any(re.search(padrao, inicio) for padrao in padroes_negocios):
        return "NEGOCIOS"

    # Acadêmico só quando existe vínculo claro com universidade/grupo/pesquisa.
    tem_pessoa_academica = _tem_termo(inicio, TERMOS_ACADEMICOS_PESSOAS)
    tem_instituicao_academica = _tem_termo(inicio, TERMOS_ACADEMICOS_INSTITUICOES)
    tem_convite_academico = any(
        marcador in inicio
        for marcador in [
            "convida pesquisadores",
            "convidam pesquisadores",
            "grupos de pesquisa",
            "pesquisadores da udesc",
            "pesquisadores da ufsc",
            "instituto federal",
        ]
    )

    tem_elegibilidade_academica = bool(re.search(
        r"(?:elegibilidade|pesquisadores? elegiveis?|destinad[ao]s?)[^.;]{0,650}"
        r"(?:pesquisadores?|docentes?|estudantes?)[^.;]{0,650}"
        r"(?:instituicoes? de pesquisa|universidades?|institutos? federais?|instituicoes? de ensino)",
        inicio,
    ))

    if tem_pessoa_academica and tem_instituicao_academica and (
        tem_convite_academico or tem_elegibilidade_academica
    ):
        return "ACADEMICO"

    return "OUTRO"


def classificar_por_regras(texto):
    """
    Motor V16: NEGOCIOS, ACADEMICO e OUTRO.

    A classificação é conservadora para NEGOCIOS: só entra nessa categoria
    quando o público elegível demonstra empresa/ICT/centro de inovação etc.
    """
    publicos = extrair_publicos_elegiveis(texto)

    if publicos:
        # O primeiro público forte costuma ser a definição principal do edital.
        # Porém, se esse mesmo convite for misto, _classificar_publico já dá
        # prioridade a empresa/ICT.
        for item in publicos:
            classificacao = _classificar_publico(item["publico"])
            if classificacao:
                return classificacao

    return _fallback_classificacao_inicio(texto)


def extrair_publico_fallback(texto):
    publicos = extrair_publicos_elegiveis(texto)

    for item in publicos:
        if _classificar_publico(item["publico"]):
            return item["publico"]

    # Se o edital é claramente uma seleção individual, ao menos registra isso.
    inicio = normalizar(_texto_compacto_classificacao(texto, limite=9000))
    if "selecao de bolsistas" in inicio or "selecionar bolsistas" in inicio:
        return "bolsistas"
    if "selecao dos candidatos" in inicio or "selecao de candidatos" in inicio:
        return "candidatos"

    return ""


def criar_prompt_classificacao(contexto):
    """Prompt de referência; a classificação oficial é feita em Python."""
    return f"""
Classifique apenas QUEM pode se inscrever/submeter/participar.

NEGOCIOS:
- empresa, startup, empreendedor ou setor produtivo elegível;
- ICT/ICTI elegível;
- Centro de Inovação elegível;
- se houver mistura de acadêmicos com empresa/ICT, use NEGOCIOS.

ACADEMICO:
- exclusivamente pesquisadores/docentes/estudantes/grupos de pesquisa;
- universidades públicas, federais ou estaduais e Institutos Federais;
- pesquisa universitária exclusiva;
- sem empresa/ICT elegível.

OUTRO:
- seleção individual de bolsistas, candidatos ou profissionais;
- pessoas físicas, servidores ou outros públicos que não sejam empresa/ICT e
  não formem uma chamada exclusivamente acadêmica.

Não classifique pela instituição parceira. Ex.: CIASC ser ICT não torna uma
seleção de bolsistas em NEGOCIOS.

TRECHOS:
{contexto}
"""


def analisar_classificacao(texto):
    """Classificação determinística V16, sem Ollama."""
    try:
        classificacao = classificar_por_regras(texto)
        publico = extrair_publico_fallback(texto)

        print(
            "  [CLASSIFICAÇÃO] Motor local V16: "
            "NEGOCIOS somente com empresa/ICT elegível; "
            "ACADEMICO para chamada acadêmica exclusiva; "
            "OUTRO para bolsistas/candidatos/pessoas físicas."
        )

        return {
            "publico_elegivel": publico,
            "classificacao": classificacao,
            "evidencia": publico,
        }

    except Exception as erro:
        print(
            "  [CLASSIFICAÇÃO] Falha interna; usando OUTRO "
            f"({type(erro).__name__}: {erro})."
        )
        return {
            "publico_elegivel": "",
            "classificacao": "OUTRO",
            "evidencia": "",
        }


def classificar_resultado(resultado):
    classificacao = resultado.get("classificacao", "OUTRO").strip().upper()

    if classificacao in {"NEGOCIOS", "ACADEMICO", "OUTRO"}:
        return classificacao

    return "OUTRO"


def _contexto_classificacao_fapesp_ia(texto):
    """Monta contexto focado no público elegível da FAPESP para o Qwen."""
    texto = remover_anexos(str(texto or ""))

    termos = [
        "elegibilidade", "elegível", "elegiveis", "quem pode",
        "público-alvo", "publico-alvo", "proponente", "proponentes",
        "pesquisador responsável", "pesquisador responsavel",
        "instituição sede", "instituicao sede", "instituição de pesquisa",
        "instituição de ensino", "universidade", "empresa", "empresas",
        "pequena empresa", "startup", "empreendedor", "ICT", "ICTI",
        "centro de inovação", "submeter propostas", "apresentar propostas",
        "poderão submeter", "poderao submeter", "podem submeter",
        "destina-se", "destinada", "destinado", "PIPE",
    ]

    partes = [texto[:7000]]
    partes.extend(
        extrair_trechos(
            texto,
            termos,
            antes=1000,
            depois=4200,
            max_trechos=10,
        )
    )

    unicas = []
    vistos = set()
    for parte in partes:
        chave = normalizar(parte[:1200])
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        unicas.append(parte)

    return ("\n\n--- TRECHO ---\n\n".join(unicas))[:28000]


def criar_prompt_classificacao_fapesp_ia(texto):
    contexto = _contexto_classificacao_fapesp_ia(texto)

    return f"""
Você vai classificar UMA chamada da FAPESP.
Analise QUEM É ELEGÍVEL PARA SUBMETER/APRESENTAR A PROPOSTA.
Não classifique pelo tema, pelo órgão financiador, por parceiros citados ou por
quem apenas executa/apoia o projeto.

Use EXATAMENTE UMA destas categorias:
NEGOCIOS
ACADEMICO
OUTRO

REGRA DE NEGOCIOS:
- use NEGOCIOS quando empresa, pequena empresa, startup, empreendedor, setor
  produtivo, ICT/ICTI ou Centro de Inovação puder efetivamente ser proponente,
  beneficiário elegível ou submeter a proposta;
- se houver pesquisadores/universidades JUNTO com empresa/ICT elegível, a
  classificação continua sendo NEGOCIOS;
- chamadas PIPE devem ser NEGOCIOS quando o título/conteúdo identificar o
  Programa PIPE e não houver indicação clara de que se trata apenas de seleção
  individual de bolsista/candidato. PIPE é Pesquisa Inovativa em Pequenas Empresas.

REGRA DE ACADEMICO:
- use ACADEMICO quando a oportunidade for exclusivamente para pesquisadores,
  docentes, estudantes, grupos de pesquisa, universidades, Institutos Federais
  ou instituições de ensino/pesquisa, SEM empresa/ICT explicitamente elegível;
- menções a indústria, inovação, startup como resultado futuro, impacto
  econômico ou parceiro NÃO transformam uma chamada acadêmica em NEGOCIOS.

REGRA DE OUTRO:
- use OUTRO para seleção individual de bolsistas, candidatos, profissionais,
  servidores ou pessoas físicas que não formem uma chamada acadêmica;
- use OUTRO apenas quando realmente não se encaixar nas duas categorias acima.

EXEMPLOS IMPORTANTES:
- projeto executado em pequena empresa / empresa pode submeter -> NEGOCIOS
- pesquisador de universidade + empresa elegível -> NEGOCIOS
- pesquisadores vinculados somente a universidades/instituições de pesquisa -> ACADEMICO
- seleção de bolsistas para trabalhar em uma ICT -> OUTRO

A palavra "Acadêmica" no nome de um programa é forte sinal de ACADEMICO, mas
a decisão final deve considerar o público elegível.

Responda SOMENTE nestas 3 linhas, sem Markdown:
CLASSIFICACAO: NEGOCIOS|ACADEMICO|OUTRO
PUBLICO: descrição curta de quem pode submeter
EVIDENCIA: trecho curto do conteúdo que sustenta a decisão

CONTEÚDO DA CHAMADA:
{contexto}
"""


def analisar_classificacao_fapesp_ia(texto):
    """Classifica a FAPESP de verdade com o Qwen, sem regra Python decidir."""
    verificar_ollama()
    ultimo = ""

    for tentativa in range(1, 4):
        prompt = criar_prompt_classificacao_fapesp_ia(texto)
        if tentativa > 1:
            prompt += f"""

ATENÇÃO - TENTATIVA {tentativa}:
A resposta anterior não pôde ser validada. Use exatamente os três rótulos
CLASSIFICACAO, PUBLICO e EVIDENCIA e uma categoria permitida.
"""

        resposta = chamar_ollama_texto(
            prompt,
            temperatura=0,
            num_predict=220,
            tentativas=2,
        )
        ultimo = resposta

        classificacao = extrair_campo_rotulado(resposta, "CLASSIFICACAO")
        classificacao = normalizar(classificacao).upper()
        classificacao = classificacao.replace("Ó", "O").replace("Ê", "E")
        classificacao = re.sub(r"[^A-Z]", "", classificacao)

        aliases = {
            "NEGOCIO": "NEGOCIOS",
            "NEGOCIOS": "NEGOCIOS",
            "ACADEMICO": "ACADEMICO",
            "ACADEMICA": "ACADEMICO",
            "OUTRO": "OUTRO",
            "OUTROS": "OUTRO",
        }
        classificacao = aliases.get(classificacao, "")

        publico = extrair_campo_rotulado(resposta, "PUBLICO")
        evidencia = extrair_campo_rotulado(resposta, "EVIDENCIA")

        if classificacao in {"NEGOCIOS", "ACADEMICO", "OUTRO"}:
            print(
                "  [CLASSIFICAÇÃO IA] Qwen 3.5 9B decidiu pela elegibilidade "
                "do proponente; nenhuma regex escolheu a categoria."
            )
            return {
                "publico_elegivel": publico,
                "classificacao": classificacao,
                "evidencia": evidencia,
            }

        print(
            f"  [CLASSIFICAÇÃO IA] Formato inválido na tentativa {tentativa}/3. "
            "Tentando novamente..."
        )

    raise ValueError(
        "O Qwen não retornou uma classificação válida após 3 tentativas. "
        f"Última resposta: {ultimo[:300]!r}"
    )


TERMOS_SUBMISSAO_PRAZO = [
    "submissão das propostas",
    "submissao das propostas",
    "submissão de propostas",
    "submissao de propostas",
    "submissão da proposta",
    "submissao da proposta",
    "período de submissão",
    "periodo de submissao",
    "prazo de submissão",
    "prazo de submissao",
    "prazo para submissão",
    "prazo para submissao",
    "data limite para submissão",
    "data limite para submissao",
    "envio da proposta",
    "envio de proposta",
    "apresentação da proposta",
    "apresentacao da proposta",
    "inscrições",
    "inscricoes",
    "período de inscrição",
    "periodo de inscricao",
    "prazo de inscrição",
    "prazo de inscricao",
    "prazo para inscrição",
    "prazo para inscricao",
    "submission deadline",
    "application deadline"
]


TERMOS_EVENTOS_NAO_SUBMISSAO = [
    "resultado preliminar",
    "resultado final",
    "divulgação do resultado",
    "divulgacao do resultado",
    "interposição de recurso",
    "interposicao de recurso",
    "prazo para recurso",
    "recursos administrativos",
    "contratação",
    "contratacao",
    "assinatura do termo",
    "prestação de contas",
    "prestacao de contas",
    "execução do projeto",
    "execucao do projeto",
    "vigência do projeto",
    "vigencia do projeto",
    "entrega de relatório",
    "entrega de relatorio",
    "preliminary result",
    "final result",
    "appeal period",
    "contract signing",
    "project execution"
]


TERMOS_CONTINUO_EXPLICITOS = [
    "fluxo contínuo",
    "fluxo continuo",
    "prazo contínuo",
    "prazo continuo",
    "submissão contínua",
    "submissao continua",
    "submissões contínuas",
    "submissoes continuas",
    "chamada em fluxo contínuo",
    "chamada em fluxo continuo",
    "chamada de fluxo contínuo",
    "chamada de fluxo continuo",
    "continuous submission",
    "rolling basis"
]


def prazo_continuo(texto):
    linhas = texto.splitlines()

    for indice, linha in enumerate(linhas):
        linha_normalizada = normalizar(
            linha
        )

        if not any(
            normalizar(termo) in linha_normalizada
            for termo in TERMOS_CONTINUO_EXPLICITOS
        ):
            continue

        # "chamada em/de fluxo contínuo" já é explícito por si só.
        if (
            "chamada em fluxo continuo" in linha_normalizada
            or "chamada de fluxo continuo" in linha_normalizada
        ):
            return True

        inicio = max(
            0,
            indice - 2
        )

        fim = min(
            len(linhas),
            indice + 3
        )

        bloco = normalizar(
            " ".join(linhas[inicio:fim])
        )

        if any(
            normalizar(termo) in bloco
            for termo in TERMOS_SUBMISSAO_PRAZO
        ):
            return True

    return False


def validar_data(
    dia,
    mes,
    ano
):
    try:
        data = datetime(
            int(ano),
            int(mes),
            int(dia)
        )

        return data.strftime(
            "%d/%m/%Y"
        )

    except ValueError:
        return ""


def extrair_datas_numericas(texto):
    resultados = []

    padrao_br = re.findall(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
        texto
    )

    for dia, mes, ano in padrao_br:
        data = validar_data(
            dia,
            mes,
            ano
        )

        if data:
            resultados.append(
                data
            )

    padrao_iso = re.findall(
        r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b",
        texto
    )

    for ano, mes, dia in padrao_iso:
        data = validar_data(
            dia,
            mes,
            ano
        )

        if data:
            resultados.append(
                data
            )

    return resultados


def extrair_datas_por_extenso(texto):
    resultados = []

    texto_normalizado = normalizar(
        texto
    )

    for nome_mes, numero_mes in MESES.items():
        mes = normalizar(
            nome_mes
        )

        padrao_portugues = re.finditer(
            rf"\b(\d{{1,2}})(?:º|o|st|nd|rd|th)?\s+(?:de\s+)?{re.escape(mes)}\s+(?:de\s+)?(\d{{4}})\b",
            texto_normalizado
        )

        for resultado in padrao_portugues:
            data = validar_data(
                resultado.group(1),
                numero_mes,
                resultado.group(2)
            )

            if data:
                resultados.append(
                    data
                )

        padrao_ingles = re.finditer(
            rf"\b{re.escape(mes)}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,)?\s+(\d{{4}})\b",
            texto_normalizado
        )

        for resultado in padrao_ingles:
            data = validar_data(
                resultado.group(1),
                numero_mes,
                resultado.group(2)
            )

            if data:
                resultados.append(
                    data
                )

    return resultados


def extrair_datas_texto(texto):
    datas = []

    datas.extend(
        extrair_datas_numericas(
            texto
        )
    )

    datas.extend(
        extrair_datas_por_extenso(
            texto
        )
    )

    return datas


def linha_e_submissao(linha):
    linha = normalizar(
        linha
    )

    return any(
        normalizar(termo) in linha
        for termo in TERMOS_SUBMISSAO_PRAZO
    )


def linha_e_outro_evento(linha):
    linha = normalizar(
        linha
    )

    return any(
        normalizar(termo) in linha
        for termo in TERMOS_EVENTOS_NAO_SUBMISSAO
    )


def extrair_prazo_de_linhas(texto):
    linhas = texto.splitlines()
    candidatos = []

    for indice, linha in enumerate(linhas):
        if not linha_e_submissao(
            linha
        ):
            continue

        bloco = [linha]
        datas_bloco = extrair_datas_texto(
            linha
        )

        linha_norm_inicial = normalizar(
            linha
        ).strip()

        linha_termina_intervalo = bool(
            re.search(
                r"(?:\ba\b|\bate\b|[-–—])\s*$",
                linha_norm_inicial
            )
        )

        # Em tabelas PDF->Markdown, o rótulo e as datas podem cair em linhas
        # separadas. Se a linha do rótulo já tem uma data completa e não termina
        # em conector de intervalo, ela é suficiente e não lemos o próximo evento.
        max_deslocamento = 3 if (not datas_bloco or linha_termina_intervalo) else 0

        for deslocamento in range(
            1,
            max_deslocamento + 1
        ):
            proximo_indice = indice + deslocamento

            if proximo_indice >= len(linhas):
                break

            proxima = linhas[proximo_indice]

            if linha_e_outro_evento(
                proxima
            ):
                break

            if (
                deslocamento > 1
                and linha_e_submissao(proxima)
            ):
                break

            bloco.append(
                proxima
            )

            novas_datas = extrair_datas_texto(
                proxima
            )

            if novas_datas:
                datas_bloco.extend(
                    novas_datas
                )

                # Depois de encontrar datas, só continua mais uma linha quando
                # a linha parece terminar em conector de intervalo ("a", "até").
                linha_norm = normalizar(
                    proxima
                ).strip()

                if not re.search(
                    r"(?:\ba\b|\bate\b|[-–—])\s*$",
                    linha_norm
                ):
                    break

        if not datas_bloco:
            continue

        evidencia = " ".join(
            parte.strip()
            for parte in bloco
            if parte.strip()
        )

        # Para intervalo, a última data textual é o encerramento.
        candidatos.append(
            (
                indice,
                datas_bloco[-1],
                evidencia
            )
        )

    if not candidatos:
        return "", ""

    # Se houver retificação no mesmo documento, a ocorrência posterior tende
    # a ser a regra mais nova (por exemplo "leia-se").
    _, data_final, evidencia = candidatos[-1]

    return data_final, evidencia


def extrair_prazo_por_janela(texto):
    texto_normalizado = normalizar(
        texto
    )

    candidatos = []

    for termo in TERMOS_SUBMISSAO_PRAZO:
        termo_normalizado = normalizar(
            termo
        )

        inicio_busca = 0

        while True:
            posicao = texto_normalizado.find(
                termo_normalizado,
                inicio_busca
            )

            if posicao == -1:
                break

            inicio = max(
                0,
                posicao - 100
            )

            fim = min(
                len(texto),
                posicao + 500
            )

            trecho = texto[inicio:fim]
            trecho_normalizado = normalizar(
                trecho
            )

            # Evita usar uma janela cujo rótulo principal já seja outro evento.
            if not any(
                normalizar(evento) in trecho_normalizado[:180]
                for evento in TERMOS_EVENTOS_NAO_SUBMISSAO
            ):
                datas = extrair_datas_texto(
                    trecho
                )

                if datas:
                    candidatos.append(
                        (
                            posicao,
                            datas[-1],
                            trecho.strip()
                        )
                    )

            inicio_busca = posicao + len(
                termo_normalizado
            )

    if not candidatos:
        return "", ""

    _, data_final, evidencia = candidatos[-1]

    return data_final, evidencia


def analisar_prazo(texto):
    texto_sem_anexos = remover_anexos(
        texto
    )

    # "Prazo continuo" só existe quando o edital disser isso explicitamente
    # em contexto de submissão. "Mensalmente", "todo mês" e "cada mês" não
    # são mais suficientes.
    if prazo_continuo(
        texto_sem_anexos
    ):
        return "Prazo continuo"

    prazo, _ = extrair_prazo_de_linhas(
        texto_sem_anexos
    )

    if prazo:
        return prazo

    prazo, _ = extrair_prazo_por_janela(
        texto_sem_anexos
    )

    if prazo:
        return prazo

    return ""


def _contexto_prazo_ia(texto):
    texto_sem_anexos = remover_anexos(texto)

    termos = list(TERMOS_SUBMISSAO_PRAZO) + list(TERMOS_CONTINUO_EXPLICITOS) + [
        "pré-proposta",
        "pre-proposta",
        "proposta completa",
        "propostas completas",
        "cronograma",
        "calendário",
        "calendario",
    ]

    partes = extrair_trechos(
        texto_sem_anexos,
        termos,
        antes=900,
        depois=2800,
        max_trechos=10,
    )

    if partes:
        return ("\n\n--- TRECHO DE PRAZO ---\n\n".join(partes))[:24000]

    return texto_sem_anexos[:16000]


def criar_prompt_prazo_ia(texto):
    contexto = _contexto_prazo_ia(texto)

    return f"""
Identifique SOMENTE o prazo que o interessado precisa cumprir para entrar
nesta chamada da FAPESP.

REGRAS OBRIGATÓRIAS:
- Procure a data de submissão, inscrição, apresentação ou envio da proposta.
- Se existir uma PRÉ-PROPOSTA obrigatória antes da proposta completa, use a
  data limite da pré-proposta, pois ela é a primeira etapa necessária para
  participar da chamada.
- Se não houver pré-proposta obrigatória, use a data limite da proposta.
- Se houver um período de inscrições/submissão, use a DATA DE ENCERRAMENTO.
- Se o texto disser explicitamente que a submissão é em fluxo/prazo contínuo,
  retorne exatamente: Prazo continuo
- Ignore datas de lançamento, abertura do sistema, divulgação de resultados,
  recursos, contratação, início do projeto, duração do projeto e prestação de contas.
- NÃO invente data. A data escolhida precisa estar escrita no conteúdo fornecido.
- Converta datas por extenso para DD/MM/AAAA.
- Se não existir um prazo identificável, retorne NAO_ENCONTRADO.

FORMATO OBRIGATÓRIO:
PRAZO: DD/MM/AAAA

ou:
PRAZO: Prazo continuo

ou:
PRAZO: NAO_ENCONTRADO

CONTEÚDO DA CHAMADA:
{contexto}
"""


def analisar_prazo_com_ia(texto):
    """Extrai o prazo com o Qwen e valida a resposta contra o texto-fonte."""
    verificar_ollama()

    resposta = chamar_ollama_texto(
        criar_prompt_prazo_ia(texto),
        temperatura=0,
        num_predict=80,
        tentativas=3,
    )

    valor = extrair_campo_rotulado(resposta, "PRAZO")
    if not valor:
        # O modelo às vezes devolve apenas o valor, apesar do rótulo pedido.
        valor = resposta.strip().splitlines()[0].strip() if resposta.strip() else ""

    normal = normalizar(valor)

    if "nao_encontrado" in normal or "nao encontrado" in normal:
        return ""

    if "prazo continuo" in normal or "fluxo continuo" in normal:
        # Só aceita contínuo quando isso também aparece de forma explícita na fonte.
        fonte_normal = normalizar(remover_anexos(texto))
        tem_continuo = any(
            normalizar(termo) in fonte_normal
            for termo in TERMOS_CONTINUO_EXPLICITOS
        )
        tem_contexto_submissao = any(
            termo in fonte_normal
            for termo in (
                "submiss", "inscri", "proposta", "prazo", "data limite",
                "application", "submission"
            )
        )
        if tem_continuo and tem_contexto_submissao:
            return "Prazo continuo"
        raise ValueError("A IA retornou prazo contínuo sem evidência no texto.")

    datas_resposta = extrair_datas_texto(valor)
    if not datas_resposta:
        raise ValueError(f"A IA não retornou uma data válida: {valor!r}")

    prazo = datas_resposta[-1]

    # Anti-alucinação: a data normalizada precisa existir no conteúdo original.
    datas_fonte = set(extrair_datas_texto(remover_anexos(texto)))
    if prazo not in datas_fonte:
        raise ValueError(
            f"A IA retornou {prazo}, mas essa data não foi encontrada no texto-fonte."
        )

    return prazo


def criar_prompt_resumo(
    fatos,
    publico,
    tentativa=1
):
    reforco = ""

    if tentativa > 1:
        reforco = """
A versão anterior não ficou natural o suficiente.

Reescreva de forma mais fluida e diferente na construção das frases,
sem alterar nenhum fato e sem acrescentar informação nova.
"""

    return f"""
Escreva um resumo para ser publicado em um portal de oportunidades de fomento.

Use SOMENTE as informações fornecidas abaixo como base.

PÚBLICO:
{publico}

OBJETIVO:
{fatos.get("objetivo", "")}

APOIO:
{fatos.get("apoio_oferecido", "")}

VALOR:
{fatos.get("valor_apoio", "")}

REGRAS OBRIGATÓRIAS:

- mantenha exatamente o sentido e os fatos das informações fornecidas;
- não invente público, valores, datas, benefícios ou condições;
- não acrescente informações que não estejam nos dados fornecidos;
- escreva em português do Brasil;
- use uma linguagem natural, clara e profissional;
- escreva de 1 a 3 frases objetivas;
- varie a construção das frases de acordo com cada oportunidade;
- não use uma estrutura fixa para todos os resumos;
- não é obrigatório começar pelo público;
- não é obrigatório começar pela oportunidade;
- não siga modelos prontos de abertura;
- destaque de forma natural o objetivo e o tipo de apoio oferecido;
- mencione o público apenas quando ele estiver informado;
- mencione o valor apenas quando ele estiver informado;
- não mencione prazo, cronograma ou data de submissão;
- não fale sobre documentação, admissibilidade, comissão, recursos,
  prestação de contas, SIGFAPESC, certidões ou currículo Lattes;
- não escreva lista;
- retorne SOMENTE o resumo final, sem rótulos, aspas, JSON ou Markdown.

NÃO COMECE o resumo com nenhum destes termos:

"Este documento"
"Este edital"
"Esta documentação"
"Esta análise"
"Este texto"
"O texto"
"O documento"
"O edital"
"A chamada pública"
"Esta chamada pública"
"Essa chamada pública"
"A presente chamada"
"O presente edital"
"Os principais pontos"
"Resumo:"

Também evite frases burocráticas como:

"detalha os requisitos"
"apresenta os requisitos"
"apresenta as regras"
"detalha as regras"
"estabelece os critérios"
"detalha o cronograma"

O objetivo é produzir um texto com a mesma naturalidade de um resumo editorial
de portal de oportunidades: direto, informativo e agradável de ler, sem parecer
uma descrição automática de um edital.

{reforco}

Retorne apenas o resumo.
"""

def limpar_resumo(resumo):
    resumo = resumo or ""

    resumo = resumo.strip(
        "\"' "
    )

    resumo = re.sub(
        r"^\s*resumo\s*:\s*",
        "",
        resumo,
        flags=re.IGNORECASE
    )

    resumo = resumo.replace(
        "\n",
        " "
    )

    resumo = resumo.replace(
        "\r",
        " "
    )

    resumo = re.sub(
        r"\s+",
        " ",
        resumo
    )

    return resumo.strip()


def resumo_valido(resumo):
    resumo = limpar_resumo(
        resumo
    )

    if len(resumo) < 70:
        return False

    if len(resumo) > 320:
        return False

    texto = normalizar(
        resumo
    )

    for inicio in INICIOS_PROIBIDOS:
        if texto.startswith(
            normalizar(inicio)
        ):
            return False

    for termo in TERMOS_BUROCRATICOS_RESUMO:
        if normalizar(termo) in texto:
            return False

    frases_ruins = [
        "detalha os requisitos",
        "apresenta os requisitos",
        "detalha as regras",
        "apresenta as regras",
        "estabelece os criterios",
        "detalha o cronograma",
        "documentacao exigida",
        "processo de admissibilidade"
    ]

    for frase in frases_ruins:
        if normalizar(frase) in texto:
            return False

    return True


def resumo_fallback(
    fatos,
    publico
):
    publico = publico.strip().rstrip(".")
    objetivo = fatos.get(
        "objetivo",
        ""
    ).strip().rstrip(".")

    if publico and objetivo:
        resumo = (
            f"Oportunidade para {publico}, "
            f"com foco em {objetivo[0].lower() + objetivo[1:]}."
        )

        if len(resumo) <= 320:
            return resumo

    if objetivo:
        return objetivo[:320]

    return (
        "Oportunidade de fomento com informações "
        "disponíveis no edital completo."
    )


def gerar_resumo(
    fatos,
    publico
):
    for tentativa in range(1, 4):
        try:
            prompt = criar_prompt_resumo(
                fatos,
                publico,
                tentativa
            ) + """

Retorne SOMENTE o texto final do resumo.
Não use JSON, rótulo, aspas ou bloco de código.
"""

            resumo = chamar_ollama_texto(
                prompt,
                temperatura=0.35,
                num_predict=260,
                tentativas=2
            )
            resumo = limpar_resumo(resumo)

            if resumo_valido(resumo):
                return resumo

            print(
                f"  [RESUMO] Tentativa {tentativa} rejeitada."
            )

        except Exception as erro:
            print(
                f"  [RESUMO] Tentativa {tentativa} falhou "
                f"({type(erro).__name__})."
            )

    print("  [RESUMO] Usando resumo de segurança.")
    return resumo_fallback(fatos, publico)


def analisar_arquivo(
    arquivo,
    indice
):
    print(
        f"Analisando: {arquivo.name}"
    )

    texto = arquivo.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    if len(texto.strip()) < 100:
        raise ValueError(
            "Markdown vazio ou com conteúdo insuficiente."
        )

    original = procurar_dados_originais(
        arquivo.name,
        indice
    )

    titulo = extrair_titulo_markdown(texto)

    if not titulo:
        titulo = original.get(
            "titulo",
            ""
        ).strip()

    # A classificação é local e vem primeiro justamente para economizar IA.
    print(
        "  [1/4] Analisando classificação..."
    )

    dados_classificacao = analisar_classificacao(texto)
    classificacao = classificar_resultado(dados_classificacao)
    publico = dados_classificacao.get(
        "publico_elegivel",
        ""
    ).strip()

    print(
        f"  [CLASSIFICAÇÃO] {classificacao}"
    )

    # Classificação de setores (híbrida: palavras-chave + Qwen).
    setores = analisar_setores(texto)

    print(
        "  [2/4] Procurando prazo..."
    )

    prazo = analisar_prazo(texto)

    if prazo:
        print(
            f"  [PRAZO] {prazo}"
        )
    else:
        print(
            "  [PRAZO] Não encontrado"
        )

    # O Qwen só trabalha nos editais FAPESC que realmente entram em NEGOCIOS.
    if classificacao == "NEGOCIOS":
        verificar_ollama()
        print(
            "  [3/4] Extraindo objetivo e apoio com IA..."
        )
        contexto_geral = extrair_contexto_geral(texto)
        fatos = extrair_fatos(contexto_geral)

        print(
            "  [4/4] Gerando resumo com IA..."
        )
        resumo = gerar_resumo(
            fatos,
            publico
        )
        modelo_usado = OLLAMA_MODEL
    else:
        # Nenhuma chamada ao Qwen para edital exclusivamente acadêmico.
        print(
            "  [3/4] IA pulada: edital não classificado como NEGOCIOS."
        )
        print(
            "  [4/4] Resumo não gerado para economizar processamento."
        )
        resumo = ""
        modelo_usado = ""

    resultado = {
        "versao_analise": ANALISE_VERSION,
        "modelo_ia": modelo_usado,
        "titulo": titulo,
        "prazo_submissao": prazo,
        "resumo": resumo,
        "classificacao": classificacao,
        "setores": setores,
        "publico_alvo": publico,
        "justificativa_classificacao": dados_classificacao.get(
            "evidencia",
            ""
        ).strip(),
        "site": original.get(
            "site",
            "FAPESC"
        ),
        "pagina_edital": original.get(
            "pagina_edital",
            ""
        ),
        "pdf_url": original.get(
            "pdf_url",
            ""
        ),
        "arquivo_original": original.get(
            "arquivo",
            ""
        ),
        "arquivo_markdown": arquivo.name
    }

    return resultado


def salvar_resultado(
    arquivo_md,
    resultado
):
    destino = (
        ANALISADOS_DIR
        / f"{arquivo_md.stem}.json"
    )

    with open(
        destino,
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            resultado,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

    return destino


def salvar_indice_geral(
    resultados
):
    destino = (
        ANALISADOS_DIR
        / "analises.json"
    )

    with open(
        destino,
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            resultados,
            arquivo,
            ensure_ascii=False,
            indent=2
        )


def contar_classificacao(
    classificacao,
    contadores
):
    if classificacao == "NEGOCIOS":
        contadores[
            "negocios"
        ] += 1

    elif classificacao == "ACADEMICO":
        contadores[
            "academicos"
        ] += 1

    else:
        contadores[
            "outros"
        ] += 1


def analise_esta_atualizada(destino):
    """Reaproveita análise existente independentemente da versão do código.

    Só refaz quando o arquivo não existe, está corrompido/incompleto ou quando
    uma análise de NEGOCIOS ficou sem resumo. Assim atualizar prompt/modelo não
    gasta IA de novo nos editais que já foram concluídos.
    """
    if not destino.exists():
        return False

    try:
        with open(destino, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

        if dados.get("erro_analise"):
            return False

        classificacao = str(dados.get("classificacao", "")).strip().upper()
        if not classificacao:
            return False

        if classificacao == "NEGOCIOS" and not str(dados.get("resumo", "")).strip():
            return False

        # Força reanálise dos editais antigos que ainda não têm o campo setores.
        if not str(dados.get("setores", "")).strip():
            return False

        return True
    except Exception:
        return False


def analisar_editais(progresso=None):
    arquivos = sorted(
        MARKDOWN_DIR.glob(
            "*.md"
        )
    )

    indice = carregar_indice()

    total = len(
        arquivos
    )

    analisados = 0
    pulados = 0
    erros = 0

    contadores = {
        "negocios": 0,
        "academicos": 0,
        "outros": 0
    }

    resultados = []

    print()
    print(
        "IA - ANALISE DE EDITAIS"
    )
    print(
        f"Modelo: {OLLAMA_MODEL}"
    )
    print(
        f"Arquivo IA em uso: {Path(__file__).resolve()}"
    )
    print(
        f"Versão da análise: {ANALISE_VERSION} | build: {IA_BUILD}"
    )
    print(
        f"Markdown encontrados: {total}"
    )
    print()

    if total == 0:
        return {
            "sucesso": True,
            "encontrados": 0,
            "analisados": 0,
            "pulados": 0,
            "erros": 0,
            "negocios": 0,
            "academicos": 0,
            "outros": 0,
            "editais": []
        }

    if progresso:
        progresso(
            processados=0,
            total=total,
            analisados=0,
            pulados=0,
            erros=0,
            negocios=0,
            academicos=0,
            outros=0,
            etapa="fapesc",
        )

    novos = [
        arquivo
        for arquivo in arquivos
        if not analise_esta_atualizada(
            ANALISADOS_DIR
            / f"{arquivo.stem}.json"
        )
    ]

    for numero, arquivo in enumerate(
        arquivos,
        start=1
    ):
        print(
            f"[{numero}/{total}] {arquivo.name}"
        )

        destino = (
            ANALISADOS_DIR
            / f"{arquivo.stem}.json"
        )

        if analise_esta_atualizada(
            destino
        ):
            print(
                "  [PULADO] Já analisado; cache reaproveitado."
            )

            try:
                with open(
                    destino,
                    "r",
                    encoding="utf-8"
                ) as json_file:
                    resultado = json.load(
                        json_file
                    )

                resultados.append(
                    resultado
                )

                pulados += 1

                contar_classificacao(
                    resultado.get(
                        "classificacao",
                        "OUTRO"
                    ),
                    contadores
                )

            except Exception as erro:
                erros += 1

                print(
                    f"  [ERRO LEITURA] {erro}"
                )

            if progresso:
                progresso(
                    processados=numero,
                    total=total,
                    analisados=analisados,
                    pulados=pulados,
                    erros=erros,
                    negocios=contadores["negocios"],
                    academicos=contadores["academicos"],
                    outros=contadores["outros"],
                    item=arquivo.name,
                    etapa="fapesc",
                )

            continue

        try:
            resultado = analisar_arquivo(
                arquivo,
                indice
            )

            salvar_resultado(
                arquivo,
                resultado
            )

            resultados.append(
                resultado
            )

            analisados += 1

            classificacao = resultado.get(
                "classificacao",
                "OUTRO"
            )

            contar_classificacao(
                classificacao,
                contadores
            )

            print(
                f"  [OK] {classificacao}"
            )

        except Exception as erro:
            erros += 1

            print(
                f"  [ERRO] {type(erro).__name__}: {erro}"
            )
            print(
                f"  [DEBUG] IA em uso: {Path(__file__).resolve()} | "
                f"versão {ANALISE_VERSION} | {IA_BUILD}"
            )
            print("  [DEBUG] Traceback completo:")
            traceback.print_exc()

        if progresso:
            progresso(
                processados=numero,
                total=total,
                analisados=analisados,
                pulados=pulados,
                erros=erros,
                negocios=contadores["negocios"],
                academicos=contadores["academicos"],
                outros=contadores["outros"],
                item=arquivo.name,
                etapa="fapesc",
            )

    salvar_indice_geral(
        resultados
    )

    print()
    print(
        "Finalizado."
    )
    print(
        f"Analisados: {analisados}"
    )
    print(
        f"Pulados: {pulados}"
    )
    print(
        f"Erros: {erros}"
    )
    print(
        f"Negócios: {contadores['negocios']}"
    )
    print(
        f"Acadêmicos: {contadores['academicos']}"
    )
    print(
        f"Outros: {contadores['outros']}"
    )

    return {
        "sucesso": True,
        "encontrados": total,
        "analisados": analisados,
        "pulados": pulados,
        "erros": erros,
        "negocios": contadores[
            "negocios"
        ],
        "academicos": contadores[
            "academicos"
        ],
        "outros": contadores[
            "outros"
        ],
        "editais": resultados
    }



# ============================================================
# SEBRAE - REESCRITA DOS RESUMOS
# ============================================================

def _carregar_lista_json(caminho):
    if not caminho.exists():
        return []

    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, list) else []
    except Exception:
        return []


def _normalizar_prazo_sebrae(prazo):
    valor = (prazo or "").strip()
    normal = normalizar(valor)

    if "fluxo continuo" in normal or "prazo continuo" in normal:
        return "Prazo continuo"

    return valor


def _resumo_sebrae_valido(original, novo):
    original = " ".join((original or "").split()).strip()
    novo = " ".join((novo or "").split()).strip()

    if not novo or len(novo) < 35:
        return False

    if normalizar(original) == normalizar(novo):
        return False

    similaridade = SequenceMatcher(
        None,
        normalizar(original),
        normalizar(novo)
    ).ratio()

    return similaridade < 0.94


def reescrever_resumo_sebrae(titulo, resumo_original):
    resumo_original = " ".join((resumo_original or "").split()).strip()

    if not resumo_original:
        return ""

    prompt_base = f"""
Reescreva o resumo abaixo para ser publicado em um portal de oportunidades.

REGRAS OBRIGATÓRIAS:
- mantenha exatamente o mesmo sentido e os mesmos fatos do texto original;
- não invente público, valores, datas, benefícios ou requisitos;
- não acrescente informações que não estejam no resumo original;
- use palavras e construção de frases diferentes do original;
- não copie frases inteiras literalmente;
- escreva em português do Brasil;
- use 1 a 3 frases objetivas;
- não comece com "Este edital", "Este documento" ou "O texto";
- retorne SOMENTE o novo resumo, sem rótulos, aspas, JSON ou Markdown.

TÍTULO:
{titulo}

RESUMO ORIGINAL:
{resumo_original}
"""

    melhor = ""

    for tentativa in range(1, 4):
        reforco = ""
        if tentativa > 1:
            reforco = (
                "\nA versão anterior ficou parecida demais com o original. "
                "Mude mais a estrutura das frases sem alterar nenhum fato.\n"
            )

        try:
            resposta = chamar_ollama_texto(
                prompt_base + reforco,
                temperatura=0.35,
                num_predict=260,
                tentativas=2
            )
            resposta = limpar_resumo(resposta)

            if resposta:
                melhor = resposta

            if _resumo_sebrae_valido(resumo_original, resposta):
                return resposta

            print(
                f"  [SEBRAE] Reescrita {tentativa}/3 parecida demais; tentando novamente..."
            )

        except Exception as erro:
            print(
                f"  [SEBRAE] Falha na reescrita {tentativa}/3: "
                f"{type(erro).__name__}: {erro}"
            )

    if melhor and normalizar(melhor) != normalizar(resumo_original):
        return melhor

    raise RuntimeError("Não foi possível reescrever o resumo do SEBRAE sem copiá-lo.")


def analisar_sebrae(progresso=None):
    oportunidades = _carregar_lista_json(SEBRAE_JSON)

    if not oportunidades:
        return {
            "sucesso": True,
            "encontrados": 0,
            "analisados": 0,
            "pulados": 0,
            "erros": 0,
            "negocios": 0,
            "academicos": 0,
            "outros": 0,
            "editais": []
        }

    anteriores = _carregar_lista_json(SEBRAE_ANALISADOS_JSON)
    cache = {}

    for item in anteriores:
        chave = item.get("pagina_edital") or item.get("link") or item.get("titulo", "")
        if chave:
            cache[chave] = item

    novos = []
    for oportunidade in oportunidades:
        chave = oportunidade.get("link") or oportunidade.get("titulo", "")
        anterior = cache.get(chave)
        if (
            not anterior
            or anterior.get("resumo_original", "") != oportunidade.get("resumo", "")
        ):
            novos.append(oportunidade)

    resultados = []
    analisados = 0
    pulados = 0
    erros = 0

    print()
    print("IA - REESCRITA SEBRAE")
    print(f"Oportunidades encontradas: {len(oportunidades)}")

    if progresso:
        progresso(
            processados=0,
            total=len(oportunidades),
            analisados=0,
            pulados=0,
            erros=0,
            negocios=0,
            academicos=0,
            outros=0,
            etapa="sebrae",
        )

    for numero, oportunidade in enumerate(oportunidades, start=1):
        titulo = (oportunidade.get("titulo") or "").strip()
        link = (oportunidade.get("link") or "").strip()
        pagina_edital = link
        pdf_url = ""
        original = (oportunidade.get("resumo") or "").strip()
        chave = link or titulo
        anterior = cache.get(chave)

        print(f"[{numero}/{len(oportunidades)}] {titulo[:90]}")

        if (
            anterior
            and anterior.get("resumo_original", "") == original
            and anterior.get("resumo", "").strip()
            and anterior.get("setores", "").strip()
        ):
            resultados.append(anterior)
            pulados += 1
            print("  [PULADO] Resumo do SEBRAE já reescrito.")
            if progresso:
                progresso(
                    processados=numero,
                    total=len(oportunidades),
                    analisados=analisados,
                    pulados=pulados,
                    erros=erros,
                    negocios=0,
                    academicos=0,
                    outros=0,
                    item=titulo,
                    etapa="sebrae",
                )
            continue

        # Setores classificados a partir do título + resumo original do SEBRAE.
        setores = analisar_setores(f"{titulo}\n{original}")

        try:
            novo_resumo = reescrever_resumo_sebrae(titulo, original)

            resultado = {
                "versao_analise": ANALISE_VERSION,
                "modelo_ia": OLLAMA_MODEL,
                "titulo": titulo,
                "prazo_submissao": _normalizar_prazo_sebrae(
                    oportunidade.get("prazo", "")
                ),
                "resumo": novo_resumo,
                "resumo_original": original,
                "classificacao": "",
                "setores": setores,
                "publico_alvo": "",
                "justificativa_classificacao": "",
                "site": oportunidade.get("site", "Sebrae Startups"),
                "pagina_edital": pagina_edital,
                "pdf_url": pdf_url,
                "arquivo_original": "oportunidades.json",
                "arquivo_markdown": "",
                "coletado_em": oportunidade.get("coletado_em", ""),
            }

            resultados.append(resultado)
            analisados += 1
            print("  [OK] Resumo reescrito.")

        except Exception as erro:
            erros += 1
            print(f"  [ERRO SEBRAE] {type(erro).__name__}: {erro}")

            resultados.append({
                "versao_analise": ANALISE_VERSION,
                "modelo_ia": OLLAMA_MODEL,
                "titulo": titulo,
                "prazo_submissao": _normalizar_prazo_sebrae(
                    oportunidade.get("prazo", "")
                ),
                "resumo": original,
                "resumo_original": original,
                "classificacao": "",
                "setores": setores,
                "publico_alvo": "",
                "justificativa_classificacao": "",
                "site": oportunidade.get("site", "Sebrae Startups"),
                "pagina_edital": pagina_edital,
                "pdf_url": pdf_url,
                "arquivo_original": "oportunidades.json",
                "arquivo_markdown": "",
                "coletado_em": oportunidade.get("coletado_em", ""),
                "erro_reescrita": str(erro),
            })

        if progresso:
            progresso(
                processados=numero,
                total=len(oportunidades),
                analisados=analisados,
                pulados=pulados,
                erros=erros,
                negocios=0,
                academicos=0,
                outros=0,
                item=titulo,
                etapa="sebrae",
            )

    with open(SEBRAE_ANALISADOS_JSON, "w", encoding="utf-8") as arquivo:
        json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    return {
        "sucesso": True,
        "encontrados": len(oportunidades),
        "analisados": analisados,
        "pulados": pulados,
        "erros": erros,
        "negocios": 0,
        "academicos": 0,
        "outros": 0,
        "editais": resultados,
    }



# ============================================================
# FINEP - RESUMOS DOS DOIS TIPOS DE PÁGINA
# ============================================================

def _normalizar_prazo_finep(prazo):
    valor = " ".join((prazo or "").split()).strip()
    normal = normalizar(valor)

    if "fluxo continuo" in normal or "prazo continuo" in normal:
        return "Prazo continuo"

    return valor


def _entrada_finep(oportunidade):
    tipo = normalizar(oportunidade.get("tipo_pagina", ""))

    if tipo == "credito":
        return {
            "tipo_pagina": "credito",
            "perfil": " ".join((oportunidade.get("perfil") or "").split()).strip(),
            "objetivo": " ".join((oportunidade.get("objetivo") or "").split()).strip(),
            "modelo_operacao": " ".join((oportunidade.get("modelo_operacao") or "").split()).strip(),
        }

    return {
        "tipo_pagina": tipo or "chamada",
        "resumo": " ".join((oportunidade.get("resumo") or "").split()).strip(),
    }


def _resumo_finep_valido(resumo):
    resumo = limpar_resumo(resumo)

    if len(resumo) < 60 or len(resumo) > 420:
        return False

    texto = normalizar(resumo)

    for inicio in INICIOS_PROIBIDOS:
        if texto.startswith(normalizar(inicio)):
            return False

    # Evita que o modelo simplesmente devolva lixo de navegação do site.
    sinais_ruins = [
        "voltar ao topo",
        "redefinir cookies",
        "todos os direitos reservados",
        "lista de documentos data nome do arquivo",
        "conheca a finep sobre a finep",
    ]

    return not any(sinal in texto for sinal in sinais_ruins)


def _prompt_finep_chamada(resumo_original):
    return f"""
Crie um resumo curto para publicar esta oportunidade em um portal de fomentos.

Use EXCLUSIVAMENTE as informações contidas no campo RESUMO DA PÁGINA abaixo.
Não use o título, não procure informações externas e não complete lacunas por conta própria.

REGRAS OBRIGATÓRIAS:
- preserve o sentido e os fatos realmente presentes no texto fornecido;
- não invente público, valores, datas, requisitos, benefícios ou condições;
- identifique a oportunidade principal e explique de forma natural o que ela apoia, financia ou seleciona;
- se o texto capturado contiver menu, navegação, rodapé, contatos, lista de documentos ou outros elementos do site, ignore esses trechos e use somente o conteúdo útil da oportunidade;
- escreva em português do Brasil;
- use 1 a 3 frases objetivas;
- deixe o texto aproximadamente do tamanho dos resumos do SEBRAE, preferencialmente entre 120 e 320 caracteres;
- não comece com "Este edital", "Este documento", "O texto", "A página" ou "A Finep informa";
- não use lista;
- retorne SOMENTE o resumo final, sem rótulos, aspas, JSON ou Markdown.

RESUMO DA PÁGINA:
{resumo_original}
"""


def _prompt_finep_credito(perfil, objetivo, modelo_operacao):
    return f"""
Crie um resumo curto para publicar esta oportunidade de financiamento em um portal de fomentos.

Use EXCLUSIVAMENTE os três campos fornecidos abaixo: PERFIL, OBJETIVO e MODELO DE OPERAÇÃO.
Não use outras informações e não invente nada que não esteja nesses campos.

REGRAS OBRIGATÓRIAS:
- explique de forma natural para quem é a oportunidade, qual é a finalidade do financiamento e como a operação funciona;
- combine as informações em um texto corrido, sem repetir os rótulos "Perfil", "Objetivo" ou "Modelo de Operação";
- não invente valores, taxas, prazos, benefícios, exigências ou condições;
- não mencione valor de financiamento, pois ele não faz parte dos campos autorizados para este resumo;
- escreva em português do Brasil;
- use 1 a 3 frases objetivas;
- deixe o texto aproximadamente do tamanho dos resumos do SEBRAE, preferencialmente entre 120 e 320 caracteres;
- não comece com "Este edital", "Este documento", "O texto", "A página" ou "A Finep informa";
- não use lista;
- retorne SOMENTE o resumo final, sem rótulos, aspas, JSON ou Markdown.

PERFIL:
{perfil}

OBJETIVO:
{objetivo}

MODELO DE OPERAÇÃO:
{modelo_operacao}
"""


def gerar_resumo_finep(oportunidade):
    entrada = _entrada_finep(oportunidade)
    tipo = entrada.get("tipo_pagina", "chamada")

    if tipo == "credito":
        perfil = entrada.get("perfil", "")
        objetivo = entrada.get("objetivo", "")
        modelo = entrada.get("modelo_operacao", "")

        if not any([perfil, objetivo, modelo]):
            return ""

        prompt_base = _prompt_finep_credito(perfil, objetivo, modelo)
    else:
        resumo_original = entrada.get("resumo", "")
        if not resumo_original:
            return ""
        prompt_base = _prompt_finep_chamada(resumo_original)

    melhor = ""

    for tentativa in range(1, 4):
        reforco = ""
        if tentativa > 1:
            reforco = (
                "\nA resposta anterior não ficou adequada. Reescreva de forma mais "
                "curta, natural e informativa, sem acrescentar nenhum fato.\n"
            )

        try:
            resposta = chamar_ollama_texto(
                prompt_base + reforco,
                temperatura=0.35,
                num_predict=260,
                tentativas=2,
            )
            resposta = limpar_resumo(resposta)

            if resposta:
                melhor = resposta

            if _resumo_finep_valido(resposta):
                return resposta

            print(
                f"  [FINEP] Resumo {tentativa}/3 fora do padrão; tentando novamente..."
            )

        except Exception as erro:
            print(
                f"  [FINEP] Falha no resumo {tentativa}/3: "
                f"{type(erro).__name__}: {erro}"
            )

    if melhor:
        return melhor[:420].strip()

    # Segurança: não derruba a oportunidade se o modelo falhar.
    if tipo == "credito":
        base = " ".join(
            parte for parte in [
                entrada.get("perfil", ""),
                entrada.get("objetivo", ""),
                entrada.get("modelo_operacao", ""),
            ] if parte
        )
    else:
        base = entrada.get("resumo", "")

    return base[:420].strip()


def analisar_finep(progresso=None):
    oportunidades = _carregar_lista_json(FINEP_JSON)

    if not oportunidades:
        return {
            "sucesso": True,
            "encontrados": 0,
            "analisados": 0,
            "pulados": 0,
            "erros": 0,
            "negocios": 0,
            "academicos": 0,
            "outros": 0,
            "editais": [],
        }

    anteriores = _carregar_lista_json(FINEP_ANALISADOS_JSON)
    cache = {}

    for item in anteriores:
        chave = item.get("chave_finep", "")
        if chave:
            cache[chave] = item

    resultados = []
    analisados = 0
    pulados = 0
    erros = 0

    print()
    print("IA - RESUMOS FINEP")
    print(f"Oportunidades encontradas: {len(oportunidades)}")

    if progresso:
        progresso(
            processados=0,
            total=len(oportunidades),
            analisados=0,
            pulados=0,
            erros=0,
            negocios=0,
            academicos=0,
            outros=0,
            etapa="finep",
        )

    for numero, oportunidade in enumerate(oportunidades, start=1):
        titulo = " ".join((oportunidade.get("titulo") or "").split()).strip()
        link = " ".join((oportunidade.get("link") or "").split()).strip()
        tipo = normalizar(oportunidade.get("tipo_pagina", "")) or "chamada"
        chave = f"{tipo}|{titulo}|{link}"
        entrada = _entrada_finep(oportunidade)
        anterior = cache.get(chave)

        print(f"[{numero}/{len(oportunidades)}] ({tipo}) {titulo[:85]}")

        if (
            anterior
            and anterior.get("entrada_ia") == entrada
            and anterior.get("resumo", "").strip()
            and anterior.get("setores", "").strip()
        ):
            resultados.append(anterior)
            pulados += 1
            print("  [PULADO] Resumo FINEP já gerado.")
            if progresso:
                progresso(
                    processados=numero,
                    total=len(oportunidades),
                    analisados=analisados,
                    pulados=pulados,
                    erros=erros,
                    negocios=0,
                    academicos=0,
                    outros=0,
                    item=titulo,
                    etapa="finep",
                )
            continue

        # Setores a partir dos campos textuais coletados pela FINEP.
        texto_setores_finep = " ".join(
            parte for parte in [
                titulo,
                entrada.get("resumo", ""),
                entrada.get("perfil", ""),
                entrada.get("objetivo", ""),
                entrada.get("modelo_operacao", ""),
            ] if parte
        )
        setores = analisar_setores(texto_setores_finep)

        try:
            novo_resumo = gerar_resumo_finep(oportunidade)

            resultado = {
                "versao_analise": ANALISE_VERSION,
                "versao_finep": FINEP_ANALISE_VERSION,
                "modelo_ia": OLLAMA_MODEL,
                "chave_finep": chave,
                "tipo_pagina": tipo,
                "titulo": titulo,
                "prazo_submissao": _normalizar_prazo_finep(
                    oportunidade.get("prazo", "")
                ),
                "resumo": novo_resumo,
                "entrada_ia": entrada,
                "classificacao": "",
                "setores": setores,
                "publico_alvo": "",
                "justificativa_classificacao": "",
                "site": oportunidade.get("site", "FINEP"),
                "pagina_edital": link,
                "pdf_url": "",
                "arquivo_original": "oportunidades.json",
                "arquivo_markdown": "",
                "coletado_em": oportunidade.get("coletado_em", ""),
            }

            # Mantém os campos do tipo crédito para auditoria, sem usá-los como
            # novas fontes de informação na exportação.
            if tipo == "credito":
                resultado["perfil"] = oportunidade.get("perfil", "")
                resultado["objetivo"] = oportunidade.get("objetivo", "")
                resultado["modelo_operacao"] = oportunidade.get("modelo_operacao", "")
                resultado["valor_financiamento"] = oportunidade.get("valor_financiamento", "")

            resultados.append(resultado)
            analisados += 1
            print("  [OK] Resumo FINEP gerado.")

        except Exception as erro:
            erros += 1
            print(f"  [ERRO FINEP] {type(erro).__name__}: {erro}")

            resultados.append({
                "versao_analise": ANALISE_VERSION,
                "versao_finep": FINEP_ANALISE_VERSION,
                "modelo_ia": OLLAMA_MODEL,
                "chave_finep": chave,
                "tipo_pagina": tipo,
                "titulo": titulo,
                "prazo_submissao": _normalizar_prazo_finep(
                    oportunidade.get("prazo", "")
                ),
                "resumo": "",
                "entrada_ia": entrada,
                "classificacao": "",
                "setores": setores,
                "publico_alvo": "",
                "justificativa_classificacao": "",
                "site": oportunidade.get("site", "FINEP"),
                "pagina_edital": link,
                "pdf_url": "",
                "arquivo_original": "oportunidades.json",
                "arquivo_markdown": "",
                "coletado_em": oportunidade.get("coletado_em", ""),
                "erro_resumo": str(erro),
            })

        if progresso:
            progresso(
                processados=numero,
                total=len(oportunidades),
                analisados=analisados,
                pulados=pulados,
                erros=erros,
                negocios=0,
                academicos=0,
                outros=0,
                item=titulo,
                etapa="finep",
            )

    with open(FINEP_ANALISADOS_JSON, "w", encoding="utf-8") as arquivo:
        json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    return {
        "sucesso": True,
        "encontrados": len(oportunidades),
        "analisados": analisados,
        "pulados": pulados,
        "erros": erros,
        "negocios": 0,
        "academicos": 0,
        "outros": 0,
        "editais": resultados,
    }


def _entrada_fapesp(chamada):
    titulo = " ".join((chamada.get("titulo") or "").split()).strip()
    prazo = " ".join((chamada.get("data_limite") or "").split()).strip()
    paragrafo = str(chamada.get("paragrafo") or "").strip()
    link = " ".join((chamada.get("link") or "").split()).strip()

    return {
        "titulo": titulo,
        "data_limite": prazo,
        "paragrafo": paragrafo,
        "link": link,
    }


def _hash_entrada_fapesp(entrada):
    bruto = json.dumps(
        entrada,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def analisar_fapesp(progresso=None):
    """Analisa FAPESP com os mesmos CRITÉRIOS da FAPESC, mas via Qwen.

    Na FAPESP, o Qwen decide a classificação a partir do público elegível e
    também identifica o prazo. O resumo continua exclusivo de NEGOCIOS.
    """
    chamadas = _carregar_lista_json(FAPESP_JSON)

    if not chamadas:
        return {
            "sucesso": True,
            "encontrados": 0,
            "analisados": 0,
            "pulados": 0,
            "erros": 0,
            "negocios": 0,
            "academicos": 0,
            "outros": 0,
            "editais": [],
        }

    anteriores = _carregar_lista_json(FAPESP_ANALISADOS_JSON)
    cache = {}
    for item in anteriores:
        chave = item.get("chave_fapesp", "")
        if chave:
            cache[chave] = item

    resultados = []
    analisados = 0
    pulados = 0
    erros = 0
    contadores = {"negocios": 0, "academicos": 0, "outros": 0}

    print()
    print("IA - CLASSIFICAÇÃO/RESUMOS FAPESP")
    print(f"Chamadas encontradas: {len(chamadas)}")
    print("Regra: critérios FAPESC; CLASSIFICAÇÃO + PRAZO pelo Qwen; resumo só para NEGOCIOS.")

    if progresso:
        progresso(
            processados=0,
            total=len(chamadas),
            analisados=0,
            pulados=0,
            erros=0,
            negocios=0,
            academicos=0,
            outros=0,
            etapa="fapesp",
        )

    for numero, chamada in enumerate(chamadas, start=1):
        entrada = _entrada_fapesp(chamada)
        titulo = entrada["titulo"]
        link = entrada["link"]
        chave = f"{titulo}|{link}"
        hash_entrada = _hash_entrada_fapesp(entrada)
        anterior = cache.get(chave)

        print(f"[{numero}/{len(chamadas)}] {titulo[:90]}")

        if (
            anterior
            and anterior.get("hash_entrada") == hash_entrada
            and anterior.get("classificacao")
            and anterior.get("setores", "").strip()
            and (
                anterior.get("classificacao") != "NEGOCIOS"
                or anterior.get("resumo", "").strip()
            )
        ):
            resultados.append(anterior)
            contar_classificacao(anterior.get("classificacao", "OUTRO"), contadores)
            pulados += 1
            print("  [PULADO] Análise FAPESP já está atualizada.")
            if progresso:
                progresso(
                    processados=numero,
                    total=len(chamadas),
                    analisados=analisados,
                    pulados=pulados,
                    erros=erros,
                    negocios=contadores["negocios"],
                    academicos=contadores["academicos"],
                    outros=contadores["outros"],
                    item=titulo,
                    etapa="fapesp",
                )
            continue

        setores = SETOR_NAO_IDENTIFICADO

        try:
            # O parágrafo do scraper contém o conteúdo da página de detalhe.
            # O prazo bruto do scraper NÃO é usado como resposta: a IA precisa
            # identificar a data diretamente no conteúdo da chamada.
            texto = "\n".join(
                parte for parte in [
                    entrada.get("titulo", ""),
                    entrada.get("paragrafo", ""),
                ] if parte
            ).strip()

            # Setores classificados a partir do título + conteúdo da chamada.
            setores = analisar_setores(texto)

            print("  [1/4] Qwen classificando público elegível (critérios FAPESC)...")
            dados_classificacao = analisar_classificacao_fapesp_ia(texto)
            classificacao = classificar_resultado(dados_classificacao)
            publico = dados_classificacao.get("publico_elegivel", "").strip()
            print(f"  [CLASSIFICAÇÃO] {classificacao}")

            print("  [2/4] IA identificando prazo de submissão...")
            try:
                prazo = analisar_prazo_com_ia(texto)
                modelo_prazo_usado = OLLAMA_MODEL
                if prazo:
                    print(f"  [PRAZO IA] {prazo}")
                else:
                    print("  [PRAZO IA] Não encontrado")
            except Exception as erro_prazo:
                # A classificação já foi concluída e não deve ser perdida se
                # apenas a extração de data falhar. O fallback local mantém o
                # registro utilizável e, por não marcar modelo_ia_prazo, o cache
                # tentará novamente com a IA na próxima execução.
                print(
                    "  [PRAZO IA] Falhou; usando fallback local temporário "
                    f"({type(erro_prazo).__name__}: {erro_prazo})."
                )
                prazo = analisar_prazo(texto)
                modelo_prazo_usado = ""

            if classificacao == "NEGOCIOS":
                print("  [3/4] Extraindo objetivo e apoio com IA...")
                contexto_geral = extrair_contexto_geral(texto)
                fatos = extrair_fatos(contexto_geral)

                print("  [4/4] Gerando resumo com IA...")
                resumo = gerar_resumo(fatos, publico)
                modelo_usado = OLLAMA_MODEL
            else:
                print("  [3/4] IA pulada: chamada não classificada como NEGOCIOS.")
                print("  [4/4] Resumo não gerado para economizar processamento.")
                resumo = ""
                modelo_usado = ""

            resultado = {
                "versao_analise": ANALISE_VERSION,
                "versao_fapesp": FAPESP_ANALISE_VERSION,
                "modelo_ia": modelo_usado,
                "modelo_ia_classificacao": OLLAMA_MODEL,
                "modelo_ia_prazo": modelo_prazo_usado,
                "chave_fapesp": chave,
                "hash_entrada": hash_entrada,
                "titulo": titulo,
                "prazo_submissao": prazo,
                "resumo": resumo,
                "classificacao": classificacao,
                "setores": setores,
                "publico_alvo": publico,
                "justificativa_classificacao": dados_classificacao.get(
                    "evidencia", ""
                ).strip(),
                "site": chamada.get("site", "FAPESP"),
                "pagina_edital": link,
                "pdf_url": "",
                "arquivo_original": "chamadas_fapesp.json",
                "arquivo_markdown": "",
                "coletado_em": chamada.get("coletado_em", ""),
            }

            resultados.append(resultado)
            contar_classificacao(classificacao, contadores)
            analisados += 1
            print("  [OK] FAPESP analisada.")

        except Exception as erro:
            erros += 1
            print(f"  [ERRO FAPESP] {type(erro).__name__}: {erro}")

            resultado = {
                "versao_analise": ANALISE_VERSION,
                "versao_fapesp": FAPESP_ANALISE_VERSION,
                "modelo_ia": "",
                "modelo_ia_classificacao": "",
                "modelo_ia_prazo": "",
                "chave_fapesp": chave,
                "hash_entrada": hash_entrada,
                "titulo": titulo,
                "prazo_submissao": analisar_prazo(
                    "\n".join([
                        entrada.get("data_limite", ""),
                        entrada.get("paragrafo", ""),
                    ])
                ),
                "resumo": "",
                "classificacao": "OUTRO",
                "setores": setores,
                "publico_alvo": "",
                "justificativa_classificacao": "",
                "site": chamada.get("site", "FAPESP"),
                "pagina_edital": link,
                "pdf_url": "",
                "arquivo_original": "chamadas_fapesp.json",
                "arquivo_markdown": "",
                "coletado_em": chamada.get("coletado_em", ""),
                "erro_analise": str(erro),
            }
            resultados.append(resultado)
            contar_classificacao("OUTRO", contadores)

        if progresso:
            progresso(
                processados=numero,
                total=len(chamadas),
                analisados=analisados,
                pulados=pulados,
                erros=erros,
                negocios=contadores["negocios"],
                academicos=contadores["academicos"],
                outros=contadores["outros"],
                item=titulo,
                etapa="fapesp",
            )

    with open(FAPESP_ANALISADOS_JSON, "w", encoding="utf-8") as arquivo:
        json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    return {
        "sucesso": True,
        "encontrados": len(chamadas),
        "analisados": analisados,
        "pulados": pulados,
        "erros": erros,
        "negocios": contadores["negocios"],
        "academicos": contadores["academicos"],
        "outros": contadores["outros"],
        "editais": resultados,
    }



# --------------------------------------------------------------------------- #
# FONTES JSON ADICIONAIS - CLASSIFICAÇÃO QWEN + RESUMO APENAS PARA NEGOCIOS
# O prazo vem do próprio JSON do scraper; a IA NÃO é chamada para procurar data.
# --------------------------------------------------------------------------- #

def _texto_item_fonte_json(item):
    campos = [
        ("TÍTULO", item.get("titulo", "")),
        ("RESUMO/OBJETIVO", item.get("resumo", "")),
        ("PERFIL", item.get("perfil", "")),
        ("PRIMEIRO PARÁGRAFO", item.get("primeiro_paragrafo", "")),
        ("PROGRAMA", item.get("programa", "")),
        ("CATEGORIA", item.get("categoria", "")),
        ("FONTE INFORMADA", item.get("fonte", "")),
        ("VIGÊNCIA", item.get("vigencia", "")),
        ("CONTEÚDO DA PÁGINA", item.get("conteudo", "")),
    ]

    partes = []
    for rotulo, valor in campos:
        valor = str(valor or "").strip()
        if valor:
            partes.append(f"{rotulo}: {valor}")

    return "\n".join(partes).strip()


def _normalizar_prazo_json(valor):
    """Normaliza apenas o campo prazo já coletado. Não procura prazo no conteúdo."""
    bruto = str(valor or "").strip()
    if not bruto:
        return ""

    norm = normalizar(bruto)
    if norm in {"nao informado", "não informado", "nao encontrada", "nao encontrado"}:
        return "Não informado"

    if any(termo in norm for termo in [
        "fluxo continuo", "prazo continuo", "a qualquer tempo",
        "submetidas a qualquer tempo", "submissao continua",
    ]):
        return "Prazo continuo"

    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", bruto)
    if m:
        dia, mes, ano = [int(x) for x in m.groups()]
        if ano < 100:
            ano += 2000
        try:
            datetime(ano, mes, dia)
            return f"{dia:02d}/{mes:02d}/{ano:04d}"
        except ValueError:
            pass

    meses = {
        "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    norm_sem_acento = normalizar(bruto)
    m = re.search(
        r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b",
        norm_sem_acento,
    )
    if m:
        dia = int(m.group(1))
        mes = meses[m.group(2)]
        ano = int(m.group(3))
        try:
            datetime(ano, mes, dia)
            return f"{dia:02d}/{mes:02d}/{ano:04d}"
        except ValueError:
            pass

    # Se o scraper trouxe outro formato, preserva o valor em vez de inventar.
    return bruto


def criar_prompt_classificacao_fonte_json(texto, nome_fonte):
    contexto = _contexto_classificacao_fapesp_ia(texto)
    return f"""
Você vai classificar UMA oportunidade coletada da fonte {nome_fonte}.
Analise QUEM É ELEGÍVEL PARA SUBMETER/APRESENTAR A PROPOSTA OU RECEBER O APOIO.
Não classifique pelo tema, pelo órgão financiador, por parceiros citados ou por
quem apenas executa/apoia o projeto.

Use EXATAMENTE UMA destas categorias:
NEGOCIOS
ACADEMICO
OUTRO

REGRA DE NEGOCIOS:
- use NEGOCIOS quando empresa, pequena empresa, startup, empreendedor, setor
  produtivo, ICT/ICTI ou Centro de Inovação puder efetivamente ser proponente,
  beneficiário elegível ou submeter a proposta;
- se houver pesquisadores/universidades JUNTO com empresa/ICT elegível, a
  classificação continua sendo NEGOCIOS;
- não transforme uma oportunidade em NEGOCIOS só porque uma empresa/ICT é
  parceira, executora ou é citada no texto;
- se a oportunidade for explicitamente do Programa PIPE e não for uma seleção
  individual de bolsista/candidato, classifique como NEGOCIOS.

REGRA DE ACADEMICO:
- use ACADEMICO quando a oportunidade for exclusivamente para pesquisadores,
  docentes, estudantes, grupos de pesquisa, universidades, Institutos Federais
  ou instituições de ensino/pesquisa, SEM empresa/ICT explicitamente elegível;
- pesquisa, inovação ou relação com indústria por si só não significam NEGOCIOS.

REGRA DE OUTRO:
- use OUTRO para seleção individual de bolsistas, candidatos, profissionais,
  servidores ou pessoas físicas que não formem uma chamada acadêmica;
- use OUTRO quando o conteúdo realmente não permitir enquadrar nas duas
  categorias anteriores.

EXEMPLOS:
- pequena empresa pode submeter -> NEGOCIOS
- pesquisador + empresa/ICT elegível -> NEGOCIOS
- somente pesquisadores de universidades/instituições de pesquisa -> ACADEMICO
- seleção individual de bolsista para atuar numa ICT -> OUTRO

Responda SOMENTE nestas 3 linhas, sem Markdown:
CLASSIFICACAO: NEGOCIOS|ACADEMICO|OUTRO
PUBLICO: descrição curta de quem pode submeter/receber o apoio
EVIDENCIA: trecho curto do conteúdo que sustenta a decisão

CONTEÚDO DA OPORTUNIDADE:
{contexto}
"""


def analisar_classificacao_fonte_json_ia(texto, nome_fonte):
    verificar_ollama()
    ultimo = ""

    for tentativa in range(1, 4):
        prompt = criar_prompt_classificacao_fonte_json(texto, nome_fonte)
        if tentativa > 1:
            prompt += f"""

ATENÇÃO - TENTATIVA {tentativa}:
A resposta anterior não pôde ser validada. Use exatamente CLASSIFICACAO,
PUBLICO e EVIDENCIA e uma categoria permitida.
"""

        resposta = chamar_ollama_texto(
            prompt,
            temperatura=0,
            num_predict=220,
            tentativas=2,
        )
        ultimo = resposta

        classificacao = extrair_campo_rotulado(resposta, "CLASSIFICACAO")
        classificacao = normalizar(classificacao).upper()
        classificacao = re.sub(r"[^A-Z]", "", classificacao)
        aliases = {
            "NEGOCIO": "NEGOCIOS",
            "NEGOCIOS": "NEGOCIOS",
            "ACADEMICO": "ACADEMICO",
            "ACADEMICA": "ACADEMICO",
            "OUTRO": "OUTRO",
            "OUTROS": "OUTRO",
        }
        classificacao = aliases.get(classificacao, "")
        publico = extrair_campo_rotulado(resposta, "PUBLICO").strip()
        evidencia = extrair_campo_rotulado(resposta, "EVIDENCIA").strip()

        if classificacao in {"NEGOCIOS", "ACADEMICO", "OUTRO"}:
            return {
                "publico_elegivel": publico,
                "classificacao": classificacao,
                "evidencia": evidencia,
            }

        print(
            f"  [CLASSIFICAÇÃO IA] Formato inválido {tentativa}/3 em {nome_fonte}; tentando novamente..."
        )

    raise ValueError(
        f"Qwen não retornou classificação válida para {nome_fonte}. "
        f"Última resposta: {ultimo[:300]!r}"
    )


def gerar_resumo_fonte_json_ia(texto, publico, nome_fonte):
    """Resumo curto de divulgação; chamado somente quando a classe é NEGOCIOS."""
    contexto = str(texto or "").strip()[:18000]
    prompt = f"""
Reescreva a oportunidade abaixo como um resumo curto de divulgação para negócios.

REGRAS:
- escreva em português do Brasil;
- use apenas informações presentes no conteúdo;
- não invente valor, prazo, benefício, elegibilidade ou condição;
- priorize objetivo, tipo de apoio/benefício e o que a oportunidade viabiliza;
- quando o público elegível estiver claro, pode mencioná-lo de forma natural;
- não comece com frases genéricas como "Este edital" ou "A chamada tem como objetivo";
- produza UM único parágrafo, preferencialmente entre 120 e 320 caracteres;
- não coloque data de prazo no resumo, pois ela já vem do JSON do scraper;
- não use Markdown, título, rótulos ou listas.

FONTE: {nome_fonte}
PÚBLICO IDENTIFICADO: {publico or 'não informado'}

CONTEÚDO:
{contexto}
"""

    ultimo = ""
    for tentativa in range(1, 4):
        resposta = chamar_ollama_texto(
            prompt,
            temperatura=0.15,
            num_predict=220,
            tentativas=2,
        )
        ultimo = re.sub(r"\s+", " ", str(resposta or "")).strip().strip('"')
        if 60 <= len(ultimo) <= 520:
            return ultimo
        print(f"  [RESUMO IA] Tentativa {tentativa}/3 fora do tamanho esperado.")

    if ultimo:
        return ultimo[:520].rstrip()
    raise ValueError("Qwen não retornou resumo utilizável.")


def _separar_link_json(link):
    link = str(link or "").strip()
    caminho = link.lower().split("?", 1)[0].split("#", 1)[0]
    if caminho.endswith(".pdf"):
        return "", link
    return link, ""


def _hash_item_fonte_json(item):
    # Campos de execução não representam mudança real no edital. Se entrassem
    # no hash, cada nova coleta (com outro horário) forçaria a IA a analisar
    # novamente exatamente o mesmo conteúdo.
    volateis = {
        "coletado_em", "baixado_em", "processado_em", "atualizado_em",
        "erro", "erro_coleta", "aviso_detalhe",
    }
    estavel = {k: v for k, v in item.items() if k not in volateis}
    bruto = json.dumps(estavel, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def analisar_fonte_json(chave_fonte, progresso=None):
    cfg = FONTES_JSON_CONFIG[chave_fonte]
    nome_fonte = cfg["nome"]
    oportunidades = _carregar_lista_json(cfg["json"])

    if not oportunidades:
        return {
            "sucesso": True, "encontrados": 0, "analisados": 0, "pulados": 0,
            "erros": 0, "negocios": 0, "academicos": 0, "outros": 0, "editais": [],
        }

    # Não verificamos o Ollama aqui. Se tudo já estiver analisado e o conteúdo
    # não tiver mudado, o cache deve funcionar até com a IA desligada. A
    # disponibilidade do modelo é checada apenas quando surgir item novo/alterado.
    anteriores = _carregar_lista_json(cfg["analisados"])
    cache = {item.get("chave_fonte_json", ""): item for item in anteriores if item.get("chave_fonte_json")}

    resultados = []
    analisados = 0
    pulados = 0
    erros = 0
    contadores = {"negocios": 0, "academicos": 0, "outros": 0}

    print()
    print(f"IA - CLASSIFICAÇÃO/RESUMOS {nome_fonte}")
    print(f"Oportunidades encontradas: {len(oportunidades)}")
    print("Prazo: usado do JSON do scraper; Qwen NÃO procura data.")
    print("Resumo: gerado somente para NEGOCIOS.")

    if progresso:
        progresso(
            processados=0,
            total=len(oportunidades),
            analisados=0,
            pulados=0,
            erros=0,
            negocios=0,
            academicos=0,
            outros=0,
            etapa=chave_fonte,
        )

    for numero, item in enumerate(oportunidades, start=1):
        titulo = str(item.get("titulo", "")).strip()
        link = str(item.get("link", "")).strip()
        pagina_edital, pdf_url = _separar_link_json(link)
        chave = f"{titulo}|{link}"
        hash_entrada = _hash_item_fonte_json(item)
        anterior = cache.get(chave)

        print(f"[{numero}/{len(oportunidades)}] {titulo[:90]}")

        if (
            anterior
            and anterior.get("hash_entrada") == hash_entrada
            and anterior.get("classificacao")
            and anterior.get("setores", "").strip()
            and (
                anterior.get("classificacao") != "NEGOCIOS"
                or anterior.get("resumo", "").strip()
            )
        ):
            resultados.append(anterior)
            contar_classificacao(anterior.get("classificacao", "OUTRO"), contadores)
            pulados += 1
            print("  [PULADO] Análise já atualizada.")
            if progresso:
                progresso(
                    processados=numero,
                    total=len(oportunidades),
                    analisados=analisados,
                    pulados=pulados,
                    erros=erros,
                    negocios=contadores["negocios"],
                    academicos=contadores["academicos"],
                    outros=contadores["outros"],
                    item=titulo,
                    etapa=chave_fonte,
                )
            continue

        setores = SETOR_NAO_IDENTIFICADO

        try:
            texto = _texto_item_fonte_json(item)
            if not texto:
                texto = titulo

            # Setores classificados a partir do conteúdo coletado da fonte.
            setores = analisar_setores(texto)

            print("  [1/3] Qwen classificando público elegível...")
            dados_classificacao = analisar_classificacao_fonte_json_ia(texto, nome_fonte)
            classificacao = classificar_resultado(dados_classificacao)
            publico = dados_classificacao.get("publico_elegivel", "").strip()
            print(f"  [CLASSIFICAÇÃO] {classificacao}")

            prazo = _normalizar_prazo_json(item.get("prazo", ""))
            print(f"  [2/3] Prazo do JSON: {prazo or 'não informado'}")

            if classificacao == "NEGOCIOS":
                print("  [3/3] Gerando resumo com Qwen...")
                resumo = gerar_resumo_fonte_json_ia(texto, publico, nome_fonte)
                modelo_resumo = OLLAMA_MODEL
            else:
                print("  [3/3] Resumo pulado: não é NEGOCIOS.")
                resumo = ""
                modelo_resumo = ""

            resultado = {
                "versao_analise": ANALISE_VERSION,
                "versao_fonte_json": FONTES_JSON_ANALISE_VERSION,
                "modelo_ia": modelo_resumo,
                "modelo_ia_classificacao": OLLAMA_MODEL,
                "modelo_ia_prazo": "",
                "prazo_origem": "json",
                "chave_fonte_json": chave,
                "hash_entrada": hash_entrada,
                "titulo": titulo,
                "prazo_submissao": prazo,
                "resumo": resumo,
                "classificacao": classificacao,
                "setores": setores,
                "publico_alvo": publico,
                "justificativa_classificacao": dados_classificacao.get("evidencia", "").strip(),
                "site": item.get("site", nome_fonte),
                "pagina_edital": pagina_edital,
                "pdf_url": pdf_url,
                "arquivo_original": cfg["json"].name,
                "arquivo_markdown": "",
                "coletado_em": item.get("coletado_em", ""),
            }
            resultados.append(resultado)
            contar_classificacao(classificacao, contadores)
            analisados += 1
            print("  [OK] Análise concluída.")

        except Exception as erro:
            erros += 1
            print(f"  [ERRO {nome_fonte}] {type(erro).__name__}: {erro}")
            resultados.append({
                "versao_analise": ANALISE_VERSION,
                "versao_fonte_json": FONTES_JSON_ANALISE_VERSION,
                "modelo_ia": "",
                "modelo_ia_classificacao": "",
                "modelo_ia_prazo": "",
                "prazo_origem": "json",
                "chave_fonte_json": chave,
                "hash_entrada": hash_entrada,
                "titulo": titulo,
                "prazo_submissao": _normalizar_prazo_json(item.get("prazo", "")),
                "resumo": "",
                "classificacao": "ERRO",
                "setores": setores,
                "publico_alvo": "",
                "justificativa_classificacao": "",
                "site": item.get("site", nome_fonte),
                "pagina_edital": pagina_edital,
                "pdf_url": pdf_url,
                "arquivo_original": cfg["json"].name,
                "arquivo_markdown": "",
                "coletado_em": item.get("coletado_em", ""),
                "erro_analise": str(erro),
            })

        if progresso:
            progresso(
                processados=numero,
                total=len(oportunidades),
                analisados=analisados,
                pulados=pulados,
                erros=erros,
                negocios=contadores["negocios"],
                academicos=contadores["academicos"],
                outros=contadores["outros"],
                item=titulo,
                etapa=chave_fonte,
            )

    with open(cfg["analisados"], "w", encoding="utf-8") as arquivo:
        json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    return {
        "sucesso": erros == 0,
        "encontrados": len(oportunidades),
        "analisados": analisados,
        "pulados": pulados,
        "erros": erros,
        "negocios": contadores["negocios"],
        "academicos": contadores["academicos"],
        "outros": contadores["outros"],
        "editais": resultados,
    }

def _fontes_ia_selecionadas(fonte="todos"):
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


def _total_itens_fonte_ia(chave):
    if chave == "fapesc":
        return len(list(MARKDOWN_DIR.glob("*.md")))
    if chave == "sebrae":
        return len(_carregar_lista_json(SEBRAE_JSON))
    if chave == "finep":
        return len(_carregar_lista_json(FINEP_JSON))
    if chave == "fapesp":
        return len(_carregar_lista_json(FAPESP_JSON))
    if chave in FONTES_JSON_CONFIG:
        return len(_carregar_lista_json(FONTES_JSON_CONFIG[chave]["json"]))
    return 0


def analisar_fontes(fonte="todos", progresso=None):
    selecionadas = _fontes_ia_selecionadas(fonte)
    total_global = sum(_total_itens_fonte_ia(chave) for chave in selecionadas)

    resultado = {
        "sucesso": True,
        "encontrados": 0,
        "analisados": 0,
        "pulados": 0,
        "erros": 0,
        "negocios": 0,
        "academicos": 0,
        "outros": 0,
        "editais": [],
        "fontes": selecionadas,
    }

    if progresso:
        progresso(
            processados=0,
            total=total_global,
            analisados=0,
            pulados=0,
            erros=0,
            negocios=0,
            academicos=0,
            outros=0,
            etapa="iniciando",
        )

    processados_anteriores = 0

    def executar_fonte(chave, funcao):
        nonlocal processados_anteriores

        base = {
            "analisados": resultado["analisados"],
            "pulados": resultado["pulados"],
            "erros": resultado["erros"],
            "negocios": resultado["negocios"],
            "academicos": resultado["academicos"],
            "outros": resultado["outros"],
        }
        offset = processados_anteriores

        def progresso_local(**dados):
            if not progresso:
                return
            progresso(
                processados=offset + int(dados.get("processados", 0) or 0),
                total=total_global,
                analisados=base["analisados"] + int(dados.get("analisados", 0) or 0),
                pulados=base["pulados"] + int(dados.get("pulados", 0) or 0),
                erros=base["erros"] + int(dados.get("erros", 0) or 0),
                negocios=base["negocios"] + int(dados.get("negocios", 0) or 0),
                academicos=base["academicos"] + int(dados.get("academicos", 0) or 0),
                outros=base["outros"] + int(dados.get("outros", 0) or 0),
                item=dados.get("item", ""),
                etapa=chave,
            )

        parte = funcao(progresso=progresso_local)

        resultado["encontrados"] += int(parte.get("encontrados", 0) or 0)
        resultado["analisados"] += int(parte.get("analisados", 0) or 0)
        resultado["pulados"] += int(parte.get("pulados", 0) or 0)
        resultado["erros"] += int(parte.get("erros", 0) or 0)
        resultado["negocios"] += int(parte.get("negocios", 0) or 0)
        resultado["academicos"] += int(parte.get("academicos", 0) or 0)
        resultado["outros"] += int(parte.get("outros", 0) or 0)
        resultado["editais"].extend(parte.get("editais", []))

        processados_anteriores += int(parte.get("encontrados", 0) or 0)

    for chave in selecionadas:
        if chave == "fapesc":
            executar_fonte(chave, analisar_editais)
        elif chave == "sebrae":
            executar_fonte(chave, analisar_sebrae)
        elif chave == "finep":
            executar_fonte(chave, analisar_finep)
        elif chave == "fapesp":
            executar_fonte(chave, analisar_fapesp)
        elif chave in FONTES_JSON_CONFIG:
            executar_fonte(
                chave,
                lambda progresso=None, chave_fonte=chave: analisar_fonte_json(
                    chave_fonte, progresso=progresso
                ),
            )

    resultado["sucesso"] = resultado["erros"] == 0

    if progresso:
        progresso(
            processados=total_global,
            total=total_global,
            analisados=resultado["analisados"],
            pulados=resultado["pulados"],
            erros=resultado["erros"],
            negocios=resultado["negocios"],
            academicos=resultado["academicos"],
            outros=resultado["outros"],
            etapa="finalizado",
        )

    return resultado


if __name__ == "__main__":
    analisar_fontes("todos")