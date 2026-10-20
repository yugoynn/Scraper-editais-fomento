from pathlib import Path
import copy
import sys
import threading
import time
import uuid
import logging
import socket

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify, request, send_from_directory, send_file

from scrappers.Sfapesc import coletar_editais
from scrappers.Ssebrae import coletar_oportunidades as coletar_sebrae
from scrappers.Sfinep import coletar_oportunidades as coletar_finep
from scrappers.Sfapesp import coletar_oportunidades as coletar_fapesp
from scrappers.Sbndes import scrape as scrape_bndes, default_out_dir as out_bndes
from scrappers.Sfapeam import scrape as scrape_fapeam, default_out_dir as out_fapeam
from scrappers.Sfapemig import scrape as scrape_fapemig, default_out_dir as out_fapemig
from scrappers.Sfappr import scrape as scrape_fappr, default_out_dir as out_fappr
from scrappers.Spetobras import scrape as scrape_petrobras, default_out_dir as out_petrobras
from scrappers.Srotas_fomento import scrape as scrape_rota_fomento, default_out_dir as out_rota_fomento
from services.pdf_md import converter_pdfs
from services.ia import analisar_fontes
from services.excel import exportar_excel

app = Flask(__name__)

# Evita poluir o terminal com o polling GET /api/jobs/...
logging.getLogger("werkzeug").setLevel(logging.ERROR)

ORDEM_FONTES = [
    "fapesc",
    "sebrae",
    "finep",
    "fapesp",
    "bndes",
    "fapeam",
    "fapemig",
    "fappr",
    "petrobras",
    "rota_fomento",
]

FONTES_VALIDAS = set(ORDEM_FONTES) | {"ambos", "todos"}

NOVOS_COLETORES = {
    "bndes": (scrape_bndes, out_bndes, "editais.json"),
    "fapeam": (scrape_fapeam, out_fapeam, "editais.json"),
    "fapemig": (scrape_fapemig, out_fapemig, "editais.json"),
    "fappr": (scrape_fappr, out_fappr, "editais.json"),
    "petrobras": (scrape_petrobras, out_petrobras, "desafios.json"),
    "rota_fomento": (scrape_rota_fomento, out_rota_fomento, "editais.json"),
}

JOBS = {}
JOBS_LOCK = threading.RLock()

# Apenas uma operação pesada pode ficar ativa no servidor por vez.
# Todos os navegadores conectados acompanham este mesmo job.
JOB_ATIVO_ID = None
EXECUTION_LOCK = threading.Lock()


def normalizar_fonte(valor):
    fonte = str(valor or "fapesc").strip().lower()
    return fonte if fonte in FONTES_VALIDAS else "fapesc"


def normalizar_fontes(valor):
    if isinstance(valor, (list, tuple, set)):
        recebidas = [str(x or "").strip().lower() for x in valor]
    else:
        recebidas = [str(valor or "fapesc").strip().lower()]

    if "todos" in recebidas:
        return ORDEM_FONTES.copy()

    expandidas = []
    for fonte in recebidas:
        if fonte == "ambos":
            expandidas.extend(["fapesc", "sebrae"])
        elif fonte in ORDEM_FONTES:
            expandidas.append(fonte)

    return [fonte for fonte in ORDEM_FONTES if fonte in expandidas] or ["fapesc"]


def fontes_da_requisicao(dados):
    dados = dados or {}
    if isinstance(dados.get("fontes"), list):
        return normalizar_fontes(dados.get("fontes"))
    return normalizar_fontes(dados.get("fonte", "fapesc"))


def coletar_scraper_json(chave, scraper, out_dir_fn, nome_json, progresso=None):
    """Executa um scraper JSON e adapta o retorno ao contrato do backend."""
    resultados = scraper(out_dir_fn(), progresso=progresso) or []
    editais = []

    for item in resultados:
        editais.append({
            "site": item.get("site", chave.upper()),
            "titulo": item.get("titulo", ""),
            "resumo": item.get("resumo", ""),
            "prazo": item.get("prazo", ""),
            "link": item.get("link", ""),
            "pagina_edital": item.get("link", ""),
            "arquivo": nome_json,
            "coletado_em": item.get("coletado_em", ""),
        })

    return {
        "sucesso": True,
        "encontrados": len(resultados),
        "baixados": len(resultados),
        "coletados": len(resultados),
        "erros": 0,
        "editais": editais,
        "json": str(Path(out_dir_fn()) / nome_json),
    }


def somar_resultados_coleta(resultados):
    resposta = {
        "sucesso": True,
        "encontrados": 0,
        "baixados": 0,
        "coletados": 0,
        "erros": 0,
        "editais": [],
        "fontes": {},
    }

    sucessos = 0

    for nome, resultado in resultados.items():
        resposta["fontes"][nome] = resultado
        resposta["encontrados"] += int(resultado.get("encontrados", 0) or 0)
        resposta["baixados"] += int(
            resultado.get("baixados", resultado.get("coletados", 0)) or 0
        )
        resposta["coletados"] += int(
            resultado.get("coletados", resultado.get("baixados", 0)) or 0
        )
        resposta["erros"] += int(resultado.get("erros", 0) or 0)
        resposta["editais"].extend(resultado.get("editais", []))

        if resultado.get("sucesso", False):
            sucessos += 1

    resposta["sucesso"] = sucessos > 0 or not resultados
    return resposta


def erro_coleta(erro):
    return {
        "sucesso": False,
        "encontrados": 0,
        "baixados": 0,
        "coletados": 0,
        "erros": 1,
        "editais": [],
        "erro": str(erro),
    }


def executar_coleta_fonte(fonte, progresso=None):
    if fonte == "fapesc":
        return coletar_editais(progresso=progresso)
    if fonte == "sebrae":
        return coletar_sebrae(progresso=progresso)
    if fonte == "finep":
        return coletar_finep(progresso=progresso)
    if fonte == "fapesp":
        return coletar_fapesp(progresso=progresso)

    scraper, out_dir_fn, nome_json = NOVOS_COLETORES[fonte]
    return coletar_scraper_json(
        fonte,
        scraper,
        out_dir_fn,
        nome_json,
        progresso=progresso,
    )


def novo_job(tipo, fontes=None):
    job_id = uuid.uuid4().hex
    agora = time.time()
    job = {
        "id": job_id,
        "tipo": tipo,
        "status": "rodando",
        "fontes": list(fontes or []),
        "fonte_atual": "",
        "etapa": "iniciando",
        "item_atual": "",
        "inicio": agora,
        "fim": None,
        "duracao_segundos": 0.0,
        "progresso": 0.0,
        "metricas": {},
        "resultado": None,
        "erro": "",
    }
    JOBS[job_id] = job
    return job_id


def criar_job_exclusivo(tipo, fontes=None):
    """Cria um job somente se não houver outra operação global em andamento."""
    global JOB_ATIVO_ID

    with JOBS_LOCK:
        if JOB_ATIVO_ID:
            ativo = JOBS.get(JOB_ATIVO_ID)
            if ativo and ativo.get("status") == "rodando":
                return None, copy.deepcopy(ativo)
            JOB_ATIVO_ID = None

        job_id = novo_job(tipo, fontes)
        JOB_ATIVO_ID = job_id
        return job_id, None


def job_ativo_snapshot():
    with JOBS_LOCK:
        job_id = JOB_ATIVO_ID
        if not job_id:
            return None
        job = JOBS.get(job_id)
        if not job or job.get("status") != "rodando":
            return None
        copia = copy.deepcopy(job)

    copia["duracao_segundos"] = max(0.0, time.time() - copia["inicio"])
    return copia


def atualizar_job(job_id, **campos):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return

        metricas = campos.pop("metricas", None)
        if metricas is not None:
            job["metricas"].update(metricas)

        job.update(campos)
        fim_referencia = job.get("fim") or time.time()
        job["duracao_segundos"] = max(0.0, fim_referencia - job["inicio"])


def finalizar_job(job_id, resultado=None, erro=None):
    global JOB_ATIVO_ID

    agora = time.time()
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return

        job["fim"] = agora
        job["duracao_segundos"] = max(0.0, agora - job["inicio"])

        if erro is None:
            job["status"] = "finalizado"
            job["progresso"] = 100.0
            job["etapa"] = "finalizado"
            job["resultado"] = resultado
        else:
            job["status"] = "erro"
            job["erro"] = str(erro)
            job["etapa"] = "erro"

        if JOB_ATIVO_ID == job_id:
            JOB_ATIVO_ID = None


def snapshot_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        copia = copy.deepcopy(job)

    if copia.get("status") == "rodando":
        copia["duracao_segundos"] = max(0.0, time.time() - copia["inicio"])

    return copia


def calcular_progresso_fontes(estados, fontes):
    if not fontes:
        return 0.0

    completos = 0.0
    for fonte in fontes:
        estado = estados[fonte]
        if estado.get("concluida"):
            completos += 1.0
            continue

        total = estado.get("total")
        processados = int(estado.get("processados", 0) or 0)
        if total:
            completos += min(1.0, processados / max(1, int(total)))

    return max(0.0, min(100.0, (completos / len(fontes)) * 100.0))


def worker_coleta(job_id, fontes):
    resultados = {}
    estados = {
        fonte: {
            "processados": 0,
            "total": None,
            "coletados": 0,
            "erros": 0,
            "concluida": False,
        }
        for fonte in fontes
    }

    try:
        for fonte in fontes:
            atualizar_job(job_id, fonte_atual=fonte, etapa="coletando", item_atual="")

            def progresso_fonte(_fonte=fonte, **dados):
                estado = estados[_fonte]
                estado["processados"] = int(dados.get("processados", estado["processados"]) or 0)
                if dados.get("total") is not None:
                    estado["total"] = int(dados.get("total") or 0)
                estado["coletados"] = int(dados.get("coletados", estado["coletados"]) or 0)
                estado["erros"] = int(dados.get("erros", estado["erros"]) or 0)

                encontrados = sum(
                    max(int(x.get("total") or 0), int(x.get("processados") or 0))
                    for x in estados.values()
                )
                coletados = sum(int(x.get("coletados") or 0) for x in estados.values())
                erros = sum(int(x.get("erros") or 0) for x in estados.values())

                atualizar_job(
                    job_id,
                    fonte_atual=_fonte,
                    etapa=dados.get("etapa", "coletando"),
                    item_atual=dados.get("item", ""),
                    progresso=calcular_progresso_fontes(estados, fontes),
                    metricas={
                        "encontrados": encontrados,
                        "coletados": coletados,
                        "baixados": coletados,
                        "erros": erros,
                        "processados": sum(int(x.get("processados") or 0) for x in estados.values()),
                    },
                )

            try:
                resultado = executar_coleta_fonte(fonte, progresso=progresso_fonte)
            except Exception as erro:
                print(f"[ERRO {fonte.upper()}] {erro}")
                resultado = erro_coleta(erro)

            resultados[fonte] = resultado
            estados[fonte]["total"] = int(resultado.get("encontrados", 0) or 0)
            estados[fonte]["processados"] = int(resultado.get("encontrados", 0) or 0)
            estados[fonte]["coletados"] = int(
                resultado.get("coletados", resultado.get("baixados", 0)) or 0
            )
            estados[fonte]["erros"] = int(resultado.get("erros", 0) or 0)
            estados[fonte]["concluida"] = True

            consolidado_parcial = somar_resultados_coleta(resultados)
            atualizar_job(
                job_id,
                progresso=calcular_progresso_fontes(estados, fontes),
                metricas={
                    "encontrados": consolidado_parcial["encontrados"],
                    "coletados": consolidado_parcial["coletados"],
                    "baixados": consolidado_parcial["baixados"],
                    "erros": consolidado_parcial["erros"],
                    "processados": sum(int(x.get("processados") or 0) for x in estados.values()),
                },
            )

        consolidado = somar_resultados_coleta(resultados)
        if not consolidado["sucesso"]:
            erros_fontes = [
                r.get("erro", "Falha na coleta")
                for r in resultados.values()
                if not r.get("sucesso", False)
            ]
            raise RuntimeError(" | ".join(erros_fontes) or "Falha na coleta")

        finalizar_job(job_id, resultado=consolidado)

    except Exception as erro:
        finalizar_job(job_id, erro=erro)


def worker_markdown(job_id):
    try:
        def progresso_markdown(**dados):
            total = int(dados.get("total", 0) or 0)
            processados = int(dados.get("processados", 0) or 0)
            percentual = 100.0 if total == 0 else (processados / max(1, total)) * 100.0
            atualizar_job(
                job_id,
                etapa=dados.get("etapa", "convertendo"),
                item_atual=dados.get("item", ""),
                progresso=min(100.0, percentual),
                metricas={
                    "encontrados": total,
                    "processados": processados,
                    "convertidos": int(dados.get("convertidos", 0) or 0),
                    "pulados": int(dados.get("pulados", 0) or 0),
                    "erros": int(dados.get("erros", 0) or 0),
                },
            )

        resultado = converter_pdfs(progresso=progresso_markdown)
        finalizar_job(job_id, resultado=resultado)
    except Exception as erro:
        finalizar_job(job_id, erro=erro)


def worker_ia(job_id, fontes):
    try:
        def progresso_ia(**dados):
            total = int(dados.get("total", 0) or 0)
            processados = int(dados.get("processados", 0) or 0)
            percentual = 100.0 if total == 0 else (processados / max(1, total)) * 100.0
            atualizar_job(
                job_id,
                fonte_atual=dados.get("etapa", ""),
                etapa=dados.get("etapa", "analisando"),
                item_atual=dados.get("item", ""),
                progresso=min(100.0, percentual),
                metricas={
                    "encontrados": total,
                    "processados": processados,
                    "analisados": int(dados.get("analisados", 0) or 0),
                    "pulados": int(dados.get("pulados", 0) or 0),
                    "erros": int(dados.get("erros", 0) or 0),
                    "negocios": int(dados.get("negocios", 0) or 0),
                    "academicos": int(dados.get("academicos", 0) or 0),
                    "outros": int(dados.get("outros", 0) or 0),
                },
            )

        resultado = analisar_fontes(fontes, progresso=progresso_ia)
        finalizar_job(job_id, resultado=resultado)
    except Exception as erro:
        finalizar_job(job_id, erro=erro)


def worker_exportar(job_id, fontes):
    try:
        def progresso_excel(**dados):
            total = int(dados.get("total", 0) or 0)
            processados = int(dados.get("processados", 0) or 0)
            percentual = 100.0 if total == 0 else (processados / max(1, total)) * 100.0
            atualizar_job(
                job_id,
                etapa=dados.get("etapa", "exportando"),
                item_atual=dados.get("item", ""),
                progresso=min(100.0, percentual),
                metricas={
                    "encontrados": total,
                    "processados": processados,
                    "exportados": int(dados.get("exportados", 0) or 0),
                    "erros": int(dados.get("erros", 0) or 0),
                },
            )

        caminho = exportar_excel(fontes, progresso=progresso_excel)
        resultado = {
            "sucesso": True,
            "arquivo": str(caminho),
            "nome_arquivo": "editais_fomento.xlsx",
        }
        finalizar_job(job_id, resultado=resultado)
    except Exception as erro:
        finalizar_job(job_id, erro=erro)


def iniciar_thread(target, *args):
    def executar_serializado():
        with EXECUTION_LOCK:
            target(*args)

    thread = threading.Thread(target=executar_serializado, daemon=True)
    thread.start()


@app.route("/")
def home():
    return send_from_directory(str(PROJECT_ROOT), "index.html")


@app.route("/css/<path:arquivo>")
def css(arquivo):
    return send_from_directory(str(PROJECT_ROOT / "css"), arquivo)


@app.route("/js/<path:arquivo>")
def js(arquivo):
    return send_from_directory(str(PROJECT_ROOT / "js"), arquivo)


@app.route("/music/<path:arquivo>")
def music(arquivo):
    return send_from_directory(str(PROJECT_ROOT / "music"), arquivo)


@app.route("/api/estado", methods=["GET"])
def estado_global():
    job = job_ativo_snapshot()
    if not job:
        return jsonify({"sucesso": True, "executando": False, "job": None})

    return jsonify({
        "sucesso": True,
        "executando": True,
        "job_id": job["id"],
        "job": job,
    })


def resposta_ocupado(job):
    return jsonify({
        "sucesso": False,
        "ocupado": True,
        "erro": "Já existe uma operação em andamento. Acompanhando o processo atual.",
        "job_id": job.get("id"),
        "job": job,
    }), 409


@app.route("/api/jobs/coleta", methods=["POST"])
def iniciar_job_coleta():
    dados = request.get_json(silent=True) or {}
    fontes = fontes_da_requisicao(dados)
    job_id, ocupado = criar_job_exclusivo("coleta", fontes)
    if ocupado:
        return resposta_ocupado(ocupado)
    iniciar_thread(worker_coleta, job_id, fontes)
    return jsonify({"sucesso": True, "job_id": job_id, "fontes": fontes})


@app.route("/api/jobs/markdown", methods=["POST"])
def iniciar_job_markdown():
    job_id, ocupado = criar_job_exclusivo("markdown", ["fapesc"])
    if ocupado:
        return resposta_ocupado(ocupado)
    iniciar_thread(worker_markdown, job_id)
    return jsonify({"sucesso": True, "job_id": job_id, "fontes": ["fapesc"]})


@app.route("/api/jobs/ia", methods=["POST"])
def iniciar_job_ia():
    dados = request.get_json(silent=True) or {}
    fontes = fontes_da_requisicao(dados)
    job_id, ocupado = criar_job_exclusivo("ia", fontes)
    if ocupado:
        return resposta_ocupado(ocupado)
    iniciar_thread(worker_ia, job_id, fontes)
    return jsonify({"sucesso": True, "job_id": job_id, "fontes": fontes})


@app.route("/api/jobs/exportar", methods=["POST"])
def iniciar_job_exportar():
    dados = request.get_json(silent=True) or {}
    fontes = fontes_da_requisicao(dados)
    job_id, ocupado = criar_job_exclusivo("exportar", fontes)
    if ocupado:
        return resposta_ocupado(ocupado)
    iniciar_thread(worker_exportar, job_id, fontes)
    return jsonify({"sucesso": True, "job_id": job_id, "fontes": fontes})


@app.route("/api/jobs/<job_id>", methods=["GET"])
def consultar_job(job_id):
    job = snapshot_job(job_id)
    if not job:
        return jsonify({"sucesso": False, "erro": "Job não encontrado."}), 404
    return jsonify({"sucesso": True, "job": job})


@app.route("/api/jobs/<job_id>/arquivo", methods=["GET"])
def baixar_arquivo_job(job_id):
    job = snapshot_job(job_id)
    if not job:
        return jsonify({"sucesso": False, "erro": "Job não encontrado."}), 404
    if job.get("status") != "finalizado" or job.get("tipo") != "exportar":
        return jsonify({"sucesso": False, "erro": "Arquivo ainda não está disponível."}), 409

    resultado = job.get("resultado") or {}
    caminho = resultado.get("arquivo", "")
    if not caminho or not Path(caminho).exists():
        return jsonify({"sucesso": False, "erro": "Arquivo exportado não encontrado."}), 404

    return send_file(
        caminho,
        as_attachment=True,
        download_name=resultado.get("nome_arquivo", "editais_fomento.xlsx"),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# Rotas síncronas antigas: mantidas por compatibilidade com atalhos/versões
# anteriores. A interface V20 usa /api/jobs/* para receber telemetria ao vivo.
# ---------------------------------------------------------------------------
@app.route("/api/coletar", methods=["POST"])
def api_coletar():
    try:
        dados = request.get_json(silent=True) or {}
        fontes = fontes_da_requisicao(dados)
        resultados = {}
        for fonte in fontes:
            try:
                resultados[fonte] = executar_coleta_fonte(fonte)
            except Exception as erro:
                resultados[fonte] = erro_coleta(erro)
        consolidado = somar_resultados_coleta(resultados)
        return jsonify(consolidado), (200 if consolidado["sucesso"] else 500)
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500


@app.route("/api/coletar/fapesc", methods=["POST"])
def api_coletar_fapesc():
    try:
        return jsonify(coletar_editais())
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500


@app.route("/api/coletar/sebrae", methods=["POST"])
def api_coletar_sebrae():
    try:
        return jsonify(coletar_sebrae())
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500


@app.route("/api/coletar/finep", methods=["POST"])
def api_coletar_finep():
    try:
        return jsonify(coletar_finep())
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500


@app.route("/api/coletar/fapesp", methods=["POST"])
def api_coletar_fapesp():
    try:
        return jsonify(coletar_fapesp())
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500


@app.route("/api/converter/markdown", methods=["POST"])
def api_converter_markdown():
    try:
        return jsonify(converter_pdfs())
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500


@app.route("/api/analisar/ia", methods=["POST"])
def api_analisar_ia():
    try:
        dados = request.get_json(silent=True) or {}
        fontes = fontes_da_requisicao(dados)
        return jsonify(analisar_fontes(fontes))
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500


@app.route("/api/exportar/excel", methods=["GET"])
def api_exportar_excel():
    try:
        fontes_param = request.args.get("fontes", "")
        if fontes_param:
            fontes = normalizar_fontes(fontes_param.split(","))
        else:
            fontes = normalizar_fontes(request.args.get("fonte", "todos"))
        caminho = exportar_excel(fontes)
        return send_file(
            caminho,
            as_attachment=True,
            download_name="editais_fomento.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500


def descobrir_ip_lan():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("10.255.255.255", 1))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "IP-DESTE-PC"


if __name__ == "__main__":
    ip_lan = descobrir_ip_lan()
    print()
    print("============================================================")
    print("                  FOMENTO TERMINAL")
    print("============================================================")
    print(f"LOCAL: http://127.0.0.1:5000")
    print(f"LAN:   http://{ip_lan}:5000")
    print("Uma operação global por vez; os clientes acompanham o mesmo processo.")
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True,
    )
