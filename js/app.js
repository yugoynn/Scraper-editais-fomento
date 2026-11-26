// Interface simplificada: escolher as fontes, INICIAR (coleta + Markdown da
// FAPESC + IA, tudo em um processo só no servidor) e EXPORTAR PLANILHA.
// A tela acompanha o job global do servidor e mostra, em tempo real, em qual
// etapa o processo está e as quantidades de cada etapa.

const startBtn = document.getElementById("startBtn");
const startBtnLabel = document.getElementById("startBtnLabel");
const exportBtn = document.getElementById("exportBtn");
const statusText = document.getElementById("statusText");
const elapsedText = document.getElementById("elapsedText");
const progressBar = document.getElementById("progressBar");
const progressLabel = document.getElementById("progressLabel");
const currentSource = document.getElementById("currentSource");
const currentItem = document.getElementById("currentItem");

const sourceChecks = Array.from(document.querySelectorAll(".source-check"));
const selectAllSources = document.getElementById("selectAllSources");
const clearSources = document.getElementById("clearSources");
const selectedSourcesCount = document.getElementById("selectedSourcesCount");
const collectorNodeLabel = document.getElementById("collectorNodeLabel");
const collectorAsciiLabel = document.getElementById("collectorAsciiLabel");

const globalSyncBanner = document.getElementById("globalSyncBanner");
const globalSyncTitle = document.getElementById("globalSyncTitle");
const globalSyncText = document.getElementById("globalSyncText");

const stageEls = {};
document.querySelectorAll(".stage").forEach(el => { stageEls[el.dataset.stage] = el; });

const SOURCE_NAMES = {
  fapesc: "FAPESC",
  sebrae: "SEBRAE",
  finep: "FINEP",
  fapesp: "FAPESP",
  bndes: "BNDES",
  fapeam: "FAPEAM",
  fapemig: "FAPEMIG",
  fappr: "FUNDAÇÃO ARAUCÁRIA",
  petrobras: "PETROBRAS",
  rota_fomento: "ROTA DO FOMENTO"
};

const NOME_ETAPA = {
  coleta: "COLETANDO",
  markdown: "GERANDO MARKDOWN",
  ia: "ANALISANDO COM IA",
  exportar: "GERANDO PLANILHA"
};

const NOME_OPERACAO = {
  pipeline: "COLETA + IA",
  exportar: "EXPORTAÇÃO",
  coleta: "COLETA",
  markdown: "MARKDOWN",
  ia: "ANÁLISE IA"
};

const STATUS_BADGE = {
  pendente: ["standby", "AGUARDANDO"],
  rodando: ["running", "EM ANDAMENTO"],
  concluida: ["ok", "CONCLUÍDA"],
  erro: ["error", "ERRO"],
  pulada: ["standby", "NÃO SE APLICA"]
};

let jobMonitoradoId = null;
let monitorToken = 0;
let operacaoGlobalAtiva = false;
let postEmAndamento = false;
const jobsIniciadosNesteNavegador = new Set();
const downloadsFeitos = new Set();

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function n(valor) {
  return Number(valor || 0);
}

function formatarTempo(segundos) {
  const total = Math.max(0, n(segundos));
  const horas = Math.floor(total / 3600);
  const minutos = Math.floor((total % 3600) / 60);
  const seg = Math.floor(total % 60);
  const decimo = Math.floor((total - Math.floor(total)) * 10);
  return `${String(horas).padStart(2, "0")}:${String(minutos).padStart(2, "0")}:${String(seg).padStart(2, "0")}.${decimo}`;
}

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = String(texto ?? "");
  return div.innerHTML;
}

// ------------------------------------------------------------------
// Fontes
// ------------------------------------------------------------------

function fontesSelecionadas() {
  return sourceChecks.filter(input => input.checked).map(input => input.value);
}

function salvarFontes() {
  try {
    localStorage.setItem("fontesColetorV22", JSON.stringify(fontesSelecionadas()));
  } catch { /* armazenamento indisponível: segue sem lembrar */ }
}

function carregarFontes() {
  let salvas = null;
  try {
    salvas = JSON.parse(localStorage.getItem("fontesColetorV22") || "null");
  } catch {
    salvas = null;
  }
  if (!Array.isArray(salvas)) return;
  const validas = new Set(salvas.filter(x => SOURCE_NAMES[x]));
  sourceChecks.forEach(input => { input.checked = validas.has(input.value); });
}

function aplicarFontesDoJob(job) {
  const fontes = Array.isArray(job?.fontes) ? job.fontes.filter(x => SOURCE_NAMES[x]) : [];
  if (!fontes.length) return;
  const selecionadas = new Set(fontes);
  sourceChecks.forEach(input => { input.checked = selecionadas.has(input.value); });
  atualizarInterfaceFontes();
}

function atualizarInterfaceFontes() {
  const fontes = fontesSelecionadas();
  const total = sourceChecks.length;

  if (selectedSourcesCount) {
    selectedSourcesCount.textContent = `${String(fontes.length).padStart(2, "0")}/${String(total).padStart(2, "0")}`;
  }

  let node = "MULTI_NODE";
  let titulo = `${fontes.length === total ? "TODAS AS FONTES" : `${fontes.length} FONTES`} // COLETOR`;
  if (fontes.length === 0) {
    node = "NO_SOURCE";
    titulo = "NENHUMA FONTE // COLETOR";
  } else if (fontes.length === 1) {
    node = `${fontes[0].toUpperCase()}_NODE`;
    titulo = `${SOURCE_NAMES[fontes[0]]} // COLETOR`;
  }
  if (collectorNodeLabel) collectorNodeLabel.textContent = node;
  if (collectorAsciiLabel) collectorAsciiLabel.textContent = titulo;

  if (!operacaoGlobalAtiva && startBtnLabel) {
    startBtnLabel.textContent = fontes.length === 0
      ? "SELECIONE UMA FONTE"
      : `INICIAR (${fontes.length} ${fontes.length === 1 ? "FONTE" : "FONTES"})`;
  }

  // Sem FAPESC, a etapa de Markdown não roda: mostra isso antes de iniciar.
  if (!operacaoGlobalAtiva && stageEls.markdown && !stageEls.markdown.classList.contains("is-done")) {
    definirEstadoEtapa("markdown", fontes.includes("fapesc") ? "pendente" : "pulada");
  }
}

function exigirFontes() {
  const fontes = fontesSelecionadas();
  if (fontes.length === 0) {
    alert("Selecione pelo menos uma fonte.");
    return null;
  }
  return fontes;
}

// ------------------------------------------------------------------
// Etapas / telemetria
// ------------------------------------------------------------------

function definirEstadoEtapa(etapa, estado) {
  const el = stageEls[etapa];
  if (!el) return;
  el.classList.toggle("is-running", estado === "rodando");
  el.classList.toggle("is-done", estado === "concluida");
  el.classList.toggle("is-error", estado === "erro");
  el.classList.toggle("is-skipped", estado === "pulada");
  const badge = el.querySelector('[data-role="status"]');
  if (badge) {
    const [classe, texto] = STATUS_BADGE[estado] || STATUS_BADGE.pendente;
    badge.className = `badge ${classe}`;
    badge.textContent = texto;
  }
}

function definirContagem(chave, valor) {
  const el = document.querySelector(`[data-count="${chave}"]`);
  if (el) el.textContent = valor;
}

function zerarEtapas(etapas) {
  etapas.forEach(etapa => definirEstadoEtapa(etapa, "pendente"));
  const zeros = {
    pipeline: {
      coleta_fontes: "0/0", coleta_encontrados: 0, coleta_coletados: 0, coleta_erros: 0,
      md_progresso: "0/0", md_convertidos: 0, md_pulados: 0, md_erros: 0,
      ia_progresso: "0/0", ia_analisados: 0, ia_negocios: 0, ia_academicos: 0, ia_outros: 0, ia_erros: 0
    },
    exportar: { exp_progresso: "0/0" }
  };
  const alvo = etapas.includes("exportar") ? zeros.exportar : zeros.pipeline;
  Object.entries(alvo).forEach(([chave, valor]) => definirContagem(chave, valor));
}

function atualizarProgresso(percentual) {
  const pct = Math.max(0, Math.min(100, n(percentual)));
  if (progressBar) progressBar.style.width = `${pct}%`;
  if (progressLabel) progressLabel.textContent = `${Math.round(pct)}%`;
}

function atualizarLinhaAtual(job) {
  const fonte = job.fonte_atual ? (SOURCE_NAMES[job.fonte_atual] || job.fonte_atual.toUpperCase()) : "--";
  if (currentSource) currentSource.innerHTML = `<span>&gt;</span> fonte: ${escapar(fonte)}`;
  if (currentItem) {
    const item = job.item_atual || (job.status === "rodando" ? "processando..." : "aguardando instrução...");
    currentItem.innerHTML = `<span>&gt;</span> ${escapar(item)}`;
  }
}

function renderizarPipeline(job) {
  const m = job.metricas || {};
  const etapas = job.etapas || {};

  ["coleta", "markdown", "ia"].forEach(etapa => {
    definirEstadoEtapa(etapa, etapas[etapa] || (etapa === "markdown" ? "pulada" : "pendente"));
  });

  definirContagem("coleta_fontes", `${n(m.coleta_fontes_concluidas)}/${n(m.coleta_fontes_total)}`);
  definirContagem("coleta_encontrados", n(m.coleta_encontrados));
  definirContagem("coleta_coletados", n(m.coleta_coletados));
  definirContagem("coleta_erros", n(m.coleta_erros));

  definirContagem("md_progresso", `${n(m.md_processados)}/${n(m.md_total)}`);
  definirContagem("md_convertidos", n(m.md_convertidos));
  definirContagem("md_pulados", n(m.md_pulados));
  definirContagem("md_erros", n(m.md_erros));

  definirContagem("ia_progresso", `${n(m.ia_processados)}/${n(m.ia_total)}`);
  definirContagem("ia_analisados", n(m.ia_analisados));
  definirContagem("ia_negocios", n(m.ia_negocios));
  definirContagem("ia_academicos", n(m.ia_academicos));
  definirContagem("ia_outros", n(m.ia_outros));
  definirContagem("ia_erros", n(m.ia_erros));
}

function renderizarExportacao(job, jobId) {
  const m = job.metricas || {};
  const estado = job.status === "rodando" ? "rodando" : job.status === "erro" ? "erro" : "concluida";
  definirEstadoEtapa("exportar", estado);
  definirContagem("exp_progresso", `${n(m.exportados)}/${n(m.encontrados)}`);

  if (job.status === "finalizado" && jobsIniciadosNesteNavegador.has(jobId) && !downloadsFeitos.has(jobId)) {
    downloadsFeitos.add(jobId);
    const link = document.createElement("a");
    link.href = `/api/jobs/${jobId}/arquivo`;
    link.download = "editais_fomento.xlsx";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }
}

function textoStatus(job) {
  if (job.status === "erro") return "ERRO";
  if (job.status === "finalizado") return "FINALIZADO";
  if (job.tipo === "exportar") return NOME_ETAPA.exportar;
  return NOME_ETAPA[job.etapa] || "EM ANDAMENTO";
}

// ------------------------------------------------------------------
// Bloqueio da tela e avisos
// ------------------------------------------------------------------

function bloquearInterface(ativo) {
  operacaoGlobalAtiva = ativo;
  sourceChecks.forEach(input => { input.disabled = ativo; });
  [selectAllSources, clearSources, startBtn, exportBtn].forEach(btn => {
    if (btn) btn.disabled = ativo;
  });
  if (ativo && startBtnLabel) startBtnLabel.textContent = "PROCESSO EM ANDAMENTO";
  if (!ativo) atualizarInterfaceFontes();
}

function mostrarBannerJob(job) {
  if (!globalSyncBanner) return;
  const local = jobsIniciadosNesteNavegador.has(job.id);
  const nome = NOME_OPERACAO[job.tipo] || String(job.tipo || "PROCESSO").toUpperCase();
  globalSyncBanner.hidden = false;
  globalSyncBanner.classList.remove("sync-error", "sync-done");
  if (globalSyncTitle) globalSyncTitle.textContent = local ? `${nome} EM EXECUÇÃO` : `ACOMPANHANDO ${nome}`;
  if (globalSyncText) {
    globalSyncText.textContent = local
      ? "Quem abrir o site na rede verá este mesmo processo."
      : "Processo iniciado em outro dispositivo. Esta tela está sincronizada com o servidor.";
  }
}

function mostrarBannerFinal(job, erro = false) {
  if (!globalSyncBanner) return;
  globalSyncBanner.hidden = false;
  globalSyncBanner.classList.toggle("sync-error", erro);
  globalSyncBanner.classList.toggle("sync-done", !erro);
  if (globalSyncTitle) globalSyncTitle.textContent = erro ? "PROCESSO ENCERRADO COM ERRO" : "PROCESSO FINALIZADO";
  if (globalSyncText) {
    globalSyncText.textContent = erro
      ? (job.erro || "O processo encontrou um erro.")
      : job.tipo === "exportar" ? "Planilha gerada." : "Coleta e análise concluídas. Já dá para exportar a planilha.";
  }
  if (!erro) {
    window.setTimeout(() => {
      if (!operacaoGlobalAtiva && globalSyncBanner) globalSyncBanner.hidden = true;
    }, 5000);
  }
}

function atualizarJobNaTela(job, jobId) {
  aplicarFontesDoJob(job);

  if (job.status === "rodando") {
    bloquearInterface(true);
    mostrarBannerJob(job);
  }

  if (statusText) statusText.textContent = textoStatus(job);
  if (elapsedText) elapsedText.textContent = formatarTempo(job.duracao_segundos);
  atualizarProgresso(job.status === "finalizado" ? 100 : job.progresso);
  atualizarLinhaAtual(job);

  if (job.tipo === "exportar") renderizarExportacao(job, jobId);
  else renderizarPipeline(job);

  if (job.status !== "rodando") {
    bloquearInterface(false);
    mostrarBannerFinal(job, job.status === "erro");
  }
}

// ------------------------------------------------------------------
// Comunicação com o servidor
// ------------------------------------------------------------------

async function acompanharJob(jobId, snapshotInicial = null) {
  if (!jobId) return;
  if (jobMonitoradoId === jobId) {
    if (snapshotInicial) atualizarJobNaTela(snapshotInicial, jobId);
    return;
  }

  const token = ++monitorToken;
  jobMonitoradoId = jobId;
  if (snapshotInicial) atualizarJobNaTela(snapshotInicial, jobId);

  while (token === monitorToken && jobMonitoradoId === jobId) {
    try {
      const resposta = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
      const dados = await resposta.json();
      if (!resposta.ok || !dados.sucesso || !dados.job) {
        throw new Error(dados.erro || "Não foi possível consultar o progresso.");
      }
      atualizarJobNaTela(dados.job, jobId);
      if (dados.job.status === "finalizado" || dados.job.status === "erro") {
        if (jobMonitoradoId === jobId) jobMonitoradoId = null;
        return;
      }
    } catch (erro) {
      console.error("Falha temporária ao acompanhar o processo:", erro);
    }
    await sleep(300);
  }
}

async function sincronizarEstadoGlobal() {
  if (postEmAndamento) return;
  try {
    const resposta = await fetch("/api/estado", { cache: "no-store" });
    const dados = await resposta.json();
    if (!resposta.ok || !dados.sucesso) return;

    if (dados.executando && dados.job?.id) {
      if (jobMonitoradoId !== dados.job.id) acompanharJob(dados.job.id, dados.job);
      else atualizarJobNaTela(dados.job, dados.job.id);
    } else if (!jobMonitoradoId && operacaoGlobalAtiva) {
      bloquearInterface(false);
    }
  } catch (erro) {
    console.error("Não foi possível consultar o estado global:", erro);
  }
}

async function iniciarOperacao(tipo, endpoint, payload) {
  if (postEmAndamento) return;
  if (operacaoGlobalAtiva) {
    await sincronizarEstadoGlobal();
    return;
  }

  postEmAndamento = true;
  bloquearInterface(true);
  zerarEtapas(tipo === "exportar" ? ["exportar"] : ["coleta", "markdown", "ia"]);
  if (tipo !== "exportar" && !payload.fontes.includes("fapesc")) definirEstadoEtapa("markdown", "pulada");
  if (statusText) statusText.textContent = "INICIANDO...";
  if (elapsedText) elapsedText.textContent = "00:00:00.0";
  atualizarProgresso(0);

  try {
    const resposta = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    });
    const dados = await resposta.json();

    if (resposta.status === 409 && dados.ocupado && dados.job_id) {
      await acompanharJob(dados.job_id, dados.job || null);
      return;
    }
    if (!resposta.ok || !dados.sucesso || !dados.job_id) {
      throw new Error(dados.erro || "Não foi possível iniciar o processo.");
    }

    jobsIniciadosNesteNavegador.add(dados.job_id);
    await acompanharJob(dados.job_id);
  } catch (erro) {
    console.error(erro);
    bloquearInterface(false);
    if (statusText) statusText.textContent = "ERRO";
    if (globalSyncBanner) {
      globalSyncBanner.hidden = false;
      globalSyncBanner.classList.add("sync-error");
      if (globalSyncTitle) globalSyncTitle.textContent = "NÃO FOI POSSÍVEL INICIAR";
      if (globalSyncText) globalSyncText.textContent = erro.message;
    }
  } finally {
    postEmAndamento = false;
  }
}

// ------------------------------------------------------------------
// Eventos
// ------------------------------------------------------------------

sourceChecks.forEach(input => {
  input.addEventListener("change", () => {
    if (operacaoGlobalAtiva) return;
    salvarFontes();
    atualizarInterfaceFontes();
  });
});

if (selectAllSources) {
  selectAllSources.addEventListener("click", () => {
    if (operacaoGlobalAtiva) return;
    sourceChecks.forEach(input => { input.checked = true; });
    salvarFontes();
    atualizarInterfaceFontes();
  });
}

if (clearSources) {
  clearSources.addEventListener("click", () => {
    if (operacaoGlobalAtiva) return;
    sourceChecks.forEach(input => { input.checked = false; });
    salvarFontes();
    atualizarInterfaceFontes();
  });
}

if (startBtn) {
  startBtn.addEventListener("click", async () => {
    const fontes = exigirFontes();
    if (!fontes) return;
    await iniciarOperacao("pipeline", "/api/jobs/pipeline", { fontes });
  });
}

if (exportBtn) {
  exportBtn.addEventListener("click", async () => {
    const fontes = exigirFontes();
    if (!fontes) return;
    await iniciarOperacao("exportar", "/api/jobs/exportar", { fontes });
  });
}

carregarFontes();
atualizarInterfaceFontes();
sincronizarEstadoGlobal();

window.setInterval(sincronizarEstadoGlobal, 1000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) sincronizarEstadoGlobal();
});
