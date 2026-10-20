const collectBtn = document.getElementById("collectBtn");
const statusText = document.getElementById("statusText");
const progressBar = document.getElementById("progressBar");
const progressLabel = document.getElementById("progressLabel");
const progressTrack = progressBar ? progressBar.parentElement : null;
const lastRun = document.getElementById("lastRun");
const collectorElapsed = document.getElementById("collectorElapsed");

const foundCount = document.getElementById("foundCount");
const downloadedCount = document.getElementById("downloadedCount");
const errorCount = document.getElementById("errorCount");
const tableCount = document.getElementById("tableCount");
const resultTable = document.getElementById("resultTable");

const sourceChecks = Array.from(document.querySelectorAll(".source-check"));
const selectAllSources = document.getElementById("selectAllSources");
const clearSources = document.getElementById("clearSources");
const selectedSourcesCount = document.getElementById("selectedSourcesCount");
const collectorNodeLabel = document.getElementById("collectorNodeLabel");
const collectorAsciiLabel = document.getElementById("collectorAsciiLabel");
const collectorModeValue = document.getElementById("collectorModeValue");
const collectorDestinationValue = document.getElementById("collectorDestinationValue");
const processedMetricLabel = document.getElementById("processedMetricLabel");
const collectorScraperStatus = document.getElementById("collectorScraperStatus");

const tabCollector = document.getElementById("tabCollector");
const tabMarkdown = document.getElementById("tabMarkdown");
const tabIA = document.getElementById("tabIA");
const tabExport = document.getElementById("tabExport");
const collectorScreen = document.getElementById("collectorScreen");
const markdownScreen = document.getElementById("markdownScreen");
const iaScreen = document.getElementById("iaScreen");
const exportScreen = document.getElementById("exportScreen");

const markdownBtn = document.getElementById("markdownBtn");
const markdownStatus = document.getElementById("markdownStatus");
const markdownConverted = document.getElementById("markdownConverted");
const markdownFound = document.getElementById("markdownFound");
const markdownErrors = document.getElementById("markdownErrors");
const markdownProgress = document.getElementById("markdownProgress");
const markdownProgressBar = document.getElementById("markdownProgressBar");
const markdownProgressTrack = markdownProgressBar ? markdownProgressBar.parentElement : null;
const markdownTable = document.getElementById("markdownTable");
const markdownTableCount = document.getElementById("markdownTableCount");
const markdownElapsed = document.getElementById("markdownElapsed");

const iaBtn = document.getElementById("iaBtn");
const iaStatus = document.getElementById("iaStatus");
const iaProgress = document.getElementById("iaProgress");
const iaProgressBar = document.getElementById("iaProgressBar");
const iaProgressTrack = iaProgressBar ? iaProgressBar.parentElement : null;
const iaAnalyzed = document.getElementById("iaAnalyzed");
const iaCompanies = document.getElementById("iaCompanies");
const iaAcademic = document.getElementById("iaAcademic");
const iaMixed = document.getElementById("iaMixed");
const iaErrors = document.getElementById("iaErrors");
const iaTable = document.getElementById("iaTable");
const iaTableCount = document.getElementById("iaTableCount");
const iaElapsed = document.getElementById("iaElapsed");

const exportBtn = document.getElementById("exportBtn");
const exportStatus = document.getElementById("exportStatus");
const exportProgress = document.getElementById("exportProgress");
const exportProgressBar = document.getElementById("exportProgressBar");
const exportProgressTrack = exportProgressBar ? exportProgressBar.parentElement : null;
const exportedCount = document.getElementById("exportedCount");
const exportFound = document.getElementById("exportFound");
const exportErrors = document.getElementById("exportErrors");
const exportElapsed = document.getElementById("exportElapsed");

const globalSyncBanner = document.getElementById("globalSyncBanner");
const globalSyncTitle = document.getElementById("globalSyncTitle");
const globalSyncText = document.getElementById("globalSyncText");

const SOURCE_CONFIG = {
  fapesc: { nome: "FAPESC", node: "FAPESC_NODE", modo: "DOWNLOAD DE EDITAIS", destino: "/dados/fapesc/pdf/" },
  sebrae: { nome: "SEBRAE", node: "SEBRAE_NODE", modo: "COLETA JSON", destino: "/dados/sebrae/oportunidades.json" },
  finep: { nome: "FINEP", node: "FINEP_NODE", modo: "COLETA JSON", destino: "/dados/finep/oportunidades.json" },
  fapesp: { nome: "FAPESP", node: "FAPESP_NODE", modo: "COLETA JSON", destino: "/dados/fapesp/chamadas_fapesp.json" },
  bndes: { nome: "BNDES", node: "BNDES_NODE", modo: "COLETA JSON", destino: "/dados/bndes/editais.json" },
  fapeam: { nome: "FAPEAM", node: "FAPEAM_NODE", modo: "COLETA JSON", destino: "/dados/fapeam/editais.json" },
  fapemig: { nome: "FAPEMIG", node: "FAPEMIG_NODE", modo: "COLETA JSON", destino: "/dados/fapemig/editais.json" },
  fappr: { nome: "FUNDAÇÃO ARAUCÁRIA", node: "FAPPR_NODE", modo: "COLETA JSON", destino: "/dados/fappr/editais.json" },
  petrobras: { nome: "PETROBRAS", node: "PETROBRAS_NODE", modo: "COLETA JSON", destino: "/dados/petrobras/desafios.json" },
  rota_fomento: { nome: "ROTA DO FOMENTO", node: "ROTA_FOMENTO_NODE", modo: "COLETA JSON", destino: "/dados/rota_fomento/editais.json" }
};

const TELA_POR_TIPO = {
  coleta: "collector",
  markdown: "markdown",
  ia: "ia",
  exportar: "export"
};

const NOME_OPERACAO = {
  coleta: "COLETA",
  markdown: "MARKDOWN",
  ia: "ANÁLISE IA",
  exportar: "EXPORTAÇÃO"
};

let jobMonitoradoId = null;
let monitorToken = 0;
let operacaoGlobalAtiva = false;
let postEmAndamento = false;
const jobsIniciadosNesteNavegador = new Set();
const downloadsFeitos = new Set();

function formatarNumero(numero) {
  return String(Number(numero || 0)).padStart(3, "0");
}

function formatarTempo(segundos) {
  const total = Math.max(0, Number(segundos || 0));
  const horas = Math.floor(total / 3600);
  const minutos = Math.floor((total % 3600) / 60);
  const seg = Math.floor(total % 60);
  const decimo = Math.floor((total - Math.floor(total)) * 10);
  return `${String(horas).padStart(2, "0")}:${String(minutos).padStart(2, "0")}:${String(seg).padStart(2, "0")}.${decimo}`;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function fontesSelecionadas() {
  return sourceChecks.filter(input => input.checked).map(input => input.value);
}

function salvarFontes() {
  localStorage.setItem("fontesColetorV22", JSON.stringify(fontesSelecionadas()));
}

function carregarFontes() {
  let salvas = null;
  try {
    salvas = JSON.parse(localStorage.getItem("fontesColetorV22") || localStorage.getItem("fontesColetorV20") || "null");
  } catch {
    salvas = null;
  }

  if (!Array.isArray(salvas)) return;
  const validas = new Set(salvas.filter(x => SOURCE_CONFIG[x]));
  sourceChecks.forEach(input => {
    input.checked = validas.has(input.value);
  });
}

function aplicarFontesDoJob(job) {
  const fontes = Array.isArray(job?.fontes) ? job.fontes.filter(x => SOURCE_CONFIG[x]) : [];
  if (!fontes.length) return;

  const selecionadas = new Set(fontes);
  sourceChecks.forEach(input => {
    input.checked = selecionadas.has(input.value);
  });
  salvarFontes();
  atualizarInterfaceFontes();
}

function atualizarInterfaceFontes() {
  const fontes = fontesSelecionadas();
  const total = sourceChecks.length;

  if (selectedSourcesCount) {
    selectedSourcesCount.textContent = `${String(fontes.length).padStart(2, "0")}/${String(total).padStart(2, "0")}`;
  }

  if (fontes.length === 0) {
    if (collectorNodeLabel) collectorNodeLabel.textContent = "NO_SOURCE";
    if (collectorAsciiLabel) collectorAsciiLabel.textContent = "NENHUMA FONTE // COLETOR";
    if (collectorModeValue) collectorModeValue.textContent = "SELECIONE AO MENOS 1 FONTE";
    if (collectorDestinationValue) collectorDestinationValue.textContent = "--";
    if (collectorScraperStatus) collectorScraperStatus.innerHTML = "<span>&gt;</span> nenhum_scraper: selecionado";
    if (collectBtn && !operacaoGlobalAtiva) collectBtn.innerHTML = '<span class="btn-prefix">&gt;</span> SELECIONE UMA FONTE <span class="cursor">_</span>';
    return;
  }

  if (fontes.length === 1) {
    const cfg = SOURCE_CONFIG[fontes[0]];
    if (collectorNodeLabel) collectorNodeLabel.textContent = cfg.node;
    if (collectorAsciiLabel) collectorAsciiLabel.textContent = `${cfg.nome} // COLETOR`;
    if (collectorModeValue) collectorModeValue.textContent = cfg.modo;
    if (collectorDestinationValue) collectorDestinationValue.textContent = cfg.destino;
    if (collectorScraperStatus && !operacaoGlobalAtiva) collectorScraperStatus.innerHTML = `<span>&gt;</span> scraper_${fontes[0]}: standby`;
    if (processedMetricLabel) processedMetricLabel.textContent = fontes[0] === "fapesc" ? "BAIXADOS" : "COLETADOS";
    if (collectBtn && !operacaoGlobalAtiva) collectBtn.innerHTML = `<span class="btn-prefix">&gt;</span> INICIAR COLETA ${cfg.nome} <span class="cursor">_</span>`;
    return;
  }

  const todas = fontes.length === total;
  if (collectorNodeLabel) collectorNodeLabel.textContent = "MULTI_NODE";
  if (collectorAsciiLabel) collectorAsciiLabel.textContent = `${todas ? "TODAS AS FONTES" : `${fontes.length} FONTES`} // COLETOR`;
  if (collectorModeValue) collectorModeValue.textContent = `COLETA MULTIFONTE (${fontes.length})`;
  if (collectorDestinationValue) collectorDestinationValue.textContent = `/dados/ (${fontes.length} fontes selecionadas)`;
  if (collectorScraperStatus && !operacaoGlobalAtiva) collectorScraperStatus.innerHTML = `<span>&gt;</span> multi_scraper: ${fontes.length} fontes em standby`;
  if (processedMetricLabel) processedMetricLabel.textContent = "COLETADOS";
  if (collectBtn && !operacaoGlobalAtiva) collectBtn.innerHTML = `<span class="btn-prefix">&gt;</span> INICIAR COLETA (${fontes.length} FONTES) <span class="cursor">_</span>`;
}

function exigirFontes() {
  const fontes = fontesSelecionadas();
  if (fontes.length === 0) {
    alert("Selecione pelo menos uma fonte.");
    return null;
  }
  return fontes;
}

function configurarSegmentos(track, total) {
  if (!track) return;
  const n = Number(total || 0);
  if (n > 1 && n <= 500) {
    track.classList.add("segmented-progress");
    track.style.backgroundImage = "linear-gradient(to right, transparent calc(100% - 1px), rgba(85,255,214,.35) 0)";
    track.style.backgroundSize = `${100 / n}% 100%`;
  } else {
    track.classList.remove("segmented-progress");
    track.style.backgroundImage = "";
    track.style.backgroundSize = "";
  }
}

function atualizarProgresso(track, bar, label, processados, total, percentual) {
  const pct = Math.max(0, Math.min(100, Number(percentual || 0)));
  if (bar) bar.style.width = `${pct}%`;
  configurarSegmentos(track, total);

  if (label) {
    const p = Number(processados || 0);
    const t = Number(total || 0);
    label.textContent = t > 0 ? `${p}/${t} · ${Math.round(pct)}%` : `${Math.round(pct)}%`;
  }
}

function mostrarTela(tela) {
  if (collectorScreen) collectorScreen.style.display = tela === "collector" ? "block" : "none";
  if (markdownScreen) markdownScreen.style.display = tela === "markdown" ? "block" : "none";
  if (iaScreen) iaScreen.style.display = tela === "ia" ? "block" : "none";
  if (exportScreen) exportScreen.style.display = tela === "export" ? "block" : "none";
  if (tabCollector) tabCollector.classList.toggle("active", tela === "collector");
  if (tabMarkdown) tabMarkdown.classList.toggle("active", tela === "markdown");
  if (tabIA) tabIA.classList.toggle("active", tela === "ia");
  if (tabExport) tabExport.classList.toggle("active", tela === "export");
}

function bloquearInterface(ativo, tipo = null) {
  operacaoGlobalAtiva = ativo;

  sourceChecks.forEach(input => { input.disabled = ativo; });
  if (selectAllSources) selectAllSources.disabled = ativo;
  if (clearSources) clearSources.disabled = ativo;

  [collectBtn, markdownBtn, iaBtn, exportBtn].forEach(btn => {
    if (btn) btn.disabled = ativo;
  });

  const telaAtiva = tipo ? TELA_POR_TIPO[tipo] : null;
  const tabs = [
    [tabCollector, "collector"],
    [tabMarkdown, "markdown"],
    [tabIA, "ia"],
    [tabExport, "export"]
  ];

  tabs.forEach(([tab, tela]) => {
    if (!tab) return;
    tab.disabled = ativo && tela !== telaAtiva;
  });

  if (!ativo) {
    if (iaBtn) iaBtn.innerHTML = '<span class="btn-prefix">&gt;</span> ANALISAR EDITAIS <span class="cursor">_</span>';
    if (exportBtn) exportBtn.innerHTML = '<span class="btn-prefix">&gt;</span> EXPORTAR PLANILHA <span class="cursor">_</span>';
    if (markdownBtn) markdownBtn.innerHTML = '<span class="btn-prefix">&gt;</span> CONVERTER PDFs <span class="cursor">_</span>';
    atualizarInterfaceFontes();
  }
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
      ? "Este é o processo global da rede. Quem abrir o site verá esta mesma tela."
      : "Processo iniciado em outro dispositivo. Esta tela está sincronizada com o servidor.";
  }
}

function mostrarBannerFinal(job, erro = false) {
  if (!globalSyncBanner) return;
  globalSyncBanner.hidden = false;
  globalSyncBanner.classList.toggle("sync-error", erro);
  globalSyncBanner.classList.toggle("sync-done", !erro);
  if (globalSyncTitle) globalSyncTitle.textContent = erro ? "OPERAÇÃO ENCERRADA COM ERRO" : "OPERAÇÃO FINALIZADA";
  if (globalSyncText) globalSyncText.textContent = erro ? (job.erro || "O processo encontrou um erro.") : "O servidor está livre para uma nova operação.";
  window.setTimeout(() => {
    if (!operacaoGlobalAtiva && globalSyncBanner) globalSyncBanner.hidden = true;
  }, 3500);
}

function prepararInicio(tipo) {
  const tela = TELA_POR_TIPO[tipo] || "collector";
  mostrarTela(tela);
  bloquearInterface(true, tipo);

  if (tipo === "coleta") {
    if (statusText) statusText.textContent = "INICIANDO...";
    if (foundCount) foundCount.textContent = "000";
    if (downloadedCount) downloadedCount.textContent = "000";
    if (errorCount) errorCount.textContent = "000";
    if (tableCount) tableCount.textContent = "000 REGISTROS";
    if (collectorElapsed) collectorElapsed.textContent = "00:00:00.0";
    atualizarProgresso(progressTrack, progressBar, progressLabel, 0, 0, 0);
  }

  if (tipo === "markdown") {
    if (markdownStatus) markdownStatus.textContent = "INICIANDO...";
    if (markdownFound) markdownFound.textContent = "000";
    if (markdownConverted) markdownConverted.textContent = "000";
    if (markdownErrors) markdownErrors.textContent = "000";
    if (markdownElapsed) markdownElapsed.textContent = "00:00:00.0";
    atualizarProgresso(markdownProgressTrack, markdownProgressBar, markdownProgress, 0, 0, 0);
  }

  if (tipo === "ia") {
    if (iaStatus) iaStatus.textContent = "INICIANDO...";
    if (iaAnalyzed) iaAnalyzed.textContent = "000";
    if (iaCompanies) iaCompanies.textContent = "000";
    if (iaAcademic) iaAcademic.textContent = "000";
    if (iaMixed) iaMixed.textContent = "000";
    if (iaErrors) iaErrors.textContent = "000";
    if (iaElapsed) iaElapsed.textContent = "00:00:00.0";
    atualizarProgresso(iaProgressTrack, iaProgressBar, iaProgress, 0, 0, 0);
  }

  if (tipo === "exportar") {
    if (exportStatus) exportStatus.textContent = "INICIANDO...";
    if (exportedCount) exportedCount.textContent = "000";
    if (exportFound) exportFound.textContent = "000";
    if (exportErrors) exportErrors.textContent = "000";
    if (exportElapsed) exportElapsed.textContent = "00:00:00.0";
    atualizarProgresso(exportProgressTrack, exportProgressBar, exportProgress, 0, 0, 0);
  }
}

function adicionarEdital(edital, indice) {
  const linha = document.createElement("tr");
  const numero = document.createElement("td");
  numero.textContent = String(indice + 1).padStart(2, "0");

  const tituloCol = document.createElement("td");
  const titulo = document.createElement("div");
  titulo.textContent = edital.titulo || "SEM TÍTULO";
  const arquivo = document.createElement("small");
  arquivo.textContent = edital.arquivo || edital.site || "";
  tituloCol.append(titulo, document.createElement("br"), arquivo);

  const paginaCol = document.createElement("td");
  const pagina = edital.pagina_edital || edital.link || "";
  if (pagina) {
    const link = document.createElement("a");
    link.href = pagina;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "ABRIR PÁGINA";
    paginaCol.appendChild(link);
  } else {
    paginaCol.textContent = "--";
  }

  const statusCol = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = "badge ok";
  badge.textContent = String(edital.site || "").toLowerCase().includes("fapesc") ? "BAIXADO" : "COLETADO";
  statusCol.appendChild(badge);

  linha.append(numero, tituloCol, paginaCol, statusCol);
  resultTable.appendChild(linha);
}

function renderizarColetaFinal(resultado) {
  const editais = Array.isArray(resultado?.editais) ? resultado.editais : [];
  if (!resultTable) return;
  resultTable.innerHTML = "";

  if (editais.length === 0) {
    const linha = document.createElement("tr");
    const coluna = document.createElement("td");
    coluna.colSpan = 4;
    coluna.textContent = "NENHUMA OPORTUNIDADE NOVA COLETADA";
    linha.appendChild(coluna);
    resultTable.appendChild(linha);
  } else {
    editais.forEach(adicionarEdital);
  }

  if (tableCount) tableCount.textContent = `${editais.length} REGISTROS`;
}

function adicionarMarkdown(arquivo, indice) {
  const linha = document.createElement("tr");
  const numero = document.createElement("td");
  numero.textContent = String(indice + 1).padStart(2, "0");
  const pdf = document.createElement("td");
  pdf.textContent = arquivo.pdf || "--";
  const md = document.createElement("td");
  md.textContent = arquivo.markdown || "--";
  const status = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = "badge ok";
  badge.textContent = "CONVERTIDO";
  status.appendChild(badge);
  linha.append(numero, pdf, md, status);
  markdownTable.appendChild(linha);
}

function renderizarMarkdownFinal(resultado) {
  const arquivos = Array.isArray(resultado?.arquivos) ? resultado.arquivos : [];
  if (!markdownTable) return;
  markdownTable.innerHTML = "";
  if (!arquivos.length) {
    const linha = document.createElement("tr");
    const coluna = document.createElement("td");
    coluna.colSpan = 4;
    coluna.textContent = Number(resultado?.encontrados || 0) === 0 ? "NENHUM PDF ENCONTRADO" : "NENHUM NOVO PDF CONVERTIDO";
    linha.appendChild(coluna);
    markdownTable.appendChild(linha);
  } else {
    arquivos.forEach(adicionarMarkdown);
  }
  if (markdownTableCount) markdownTableCount.textContent = `${arquivos.length} REGISTROS`;
}

function adicionarResultadoIA(edital, indice) {
  const linha = document.createElement("tr");
  const numero = document.createElement("td");
  numero.textContent = String(indice + 1).padStart(2, "0");

  const titulo = document.createElement("td");
  const tituloTexto = document.createElement("strong");
  tituloTexto.textContent = edital.titulo || "NÃO IDENTIFICADO";
  titulo.appendChild(tituloTexto);
  if (edital.resumo) {
    titulo.appendChild(document.createElement("br"));
    const resumo = document.createElement("small");
    resumo.textContent = edital.resumo;
    titulo.appendChild(resumo);
  }

  const prazo = document.createElement("td");
  prazo.textContent = edital.prazo_submissao || "--";

  const classificacao = document.createElement("td");
  const badge = document.createElement("span");
  const classe = String(edital.classificacao || "").toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  if (classe === "NEGOCIOS") badge.className = "badge ok";
  else if (classe === "ACADEMICO") badge.className = "badge standby";
  else badge.className = classe ? "badge" : "badge standby";
  badge.textContent = edital.classificacao || "N/A";
  classificacao.appendChild(badge);

  const publico = document.createElement("td");
  publico.textContent = edital.publico_alvo || "--";

  linha.append(numero, titulo, prazo, classificacao, publico);
  iaTable.appendChild(linha);
}

function renderizarIAFinal(resultado) {
  const editais = Array.isArray(resultado?.editais) ? resultado.editais : [];
  if (!iaTable) return;
  iaTable.innerHTML = "";
  if (!editais.length) {
    const linha = document.createElement("tr");
    const coluna = document.createElement("td");
    coluna.colSpan = 5;
    coluna.textContent = "NENHUM NOVO EDITAL ANALISADO";
    linha.appendChild(coluna);
    iaTable.appendChild(linha);
  } else {
    editais.forEach(adicionarResultadoIA);
  }
  if (iaTableCount) iaTableCount.textContent = `${editais.length} REGISTROS`;
}

function atualizarJobNaTela(job, jobId) {
  const tipo = job.tipo;
  const tela = TELA_POR_TIPO[tipo] || "collector";
  const m = job.metricas || {};

  mostrarTela(tela);
  aplicarFontesDoJob(job);

  if (job.status === "rodando") {
    bloquearInterface(true, tipo);
    mostrarBannerJob(job);
  }

  if (tipo === "coleta") {
    if (statusText) statusText.textContent = job.status === "rodando" ? "COLETANDO..." : job.status === "erro" ? "ERRO" : "FINALIZADO";
    if (foundCount) foundCount.textContent = formatarNumero(m.encontrados);
    if (downloadedCount) downloadedCount.textContent = formatarNumero(m.coletados ?? m.baixados);
    if (errorCount) errorCount.textContent = formatarNumero(m.erros);
    if (tableCount && job.status === "rodando") tableCount.textContent = `${Number(m.coletados || 0)} REGISTROS`;
    if (collectorElapsed) collectorElapsed.textContent = formatarTempo(job.duracao_segundos);
    atualizarProgresso(progressTrack, progressBar, progressLabel, m.processados, m.encontrados, job.progresso);

    const fonteAtual = job.fonte_atual || "";
    const item = job.item_atual || "";
    if (collectorScraperStatus && job.status === "rodando") {
      collectorScraperStatus.innerHTML = `<span>&gt;</span> ${fonteAtual ? `scraper_${fonteAtual}` : "multi_scraper"}: ${item || job.etapa}`;
    }

    if (job.status === "finalizado") {
      const resultado = job.resultado || {};
      if (foundCount) foundCount.textContent = formatarNumero(resultado.encontrados);
      if (downloadedCount) downloadedCount.textContent = formatarNumero(resultado.coletados ?? resultado.baixados);
      if (errorCount) errorCount.textContent = formatarNumero(resultado.erros);
      renderizarColetaFinal(resultado);
      atualizarProgresso(progressTrack, progressBar, progressLabel, resultado.encontrados, resultado.encontrados, 100);
      if (lastRun) lastRun.textContent = new Date().toLocaleString("pt-BR");
    }
  }

  if (tipo === "markdown") {
    if (markdownStatus) markdownStatus.textContent = job.status === "rodando" ? "CONVERTENDO..." : job.status === "erro" ? "ERRO" : "FINALIZADO";
    if (markdownFound) markdownFound.textContent = formatarNumero(m.encontrados);
    if (markdownConverted) markdownConverted.textContent = formatarNumero(m.convertidos);
    if (markdownErrors) markdownErrors.textContent = formatarNumero(m.erros);
    if (markdownTableCount && job.status === "rodando") markdownTableCount.textContent = `${Number(m.convertidos || 0)} REGISTROS`;
    if (markdownElapsed) markdownElapsed.textContent = formatarTempo(job.duracao_segundos);
    atualizarProgresso(markdownProgressTrack, markdownProgressBar, markdownProgress, m.processados, m.encontrados, job.progresso);

    if (job.status === "finalizado") {
      const resultado = job.resultado || {};
      if (markdownFound) markdownFound.textContent = formatarNumero(resultado.encontrados);
      if (markdownConverted) markdownConverted.textContent = formatarNumero(resultado.convertidos);
      if (markdownErrors) markdownErrors.textContent = formatarNumero(resultado.erros);
      renderizarMarkdownFinal(resultado);
      atualizarProgresso(markdownProgressTrack, markdownProgressBar, markdownProgress, resultado.encontrados, resultado.encontrados, 100);
    }
  }

  if (tipo === "ia") {
    if (iaStatus) iaStatus.textContent = job.status === "rodando" ? "ANALISANDO..." : job.status === "erro" ? "ERRO" : "FINALIZADO";
    if (iaAnalyzed) iaAnalyzed.textContent = formatarNumero(m.processados);
    if (iaCompanies) iaCompanies.textContent = formatarNumero(m.negocios);
    if (iaAcademic) iaAcademic.textContent = formatarNumero(m.academicos);
    if (iaMixed) iaMixed.textContent = formatarNumero(m.outros);
    if (iaErrors) iaErrors.textContent = formatarNumero(m.erros);
    if (iaTableCount && job.status === "rodando") iaTableCount.textContent = `${Number(m.processados || 0)} REGISTROS`;
    if (iaElapsed) iaElapsed.textContent = formatarTempo(job.duracao_segundos);
    atualizarProgresso(iaProgressTrack, iaProgressBar, iaProgress, m.processados, m.encontrados, job.progresso);

    if (job.status === "finalizado") {
      const resultado = job.resultado || {};
      if (iaAnalyzed) iaAnalyzed.textContent = formatarNumero(Number(resultado.analisados || 0) + Number(resultado.pulados || 0));
      if (iaCompanies) iaCompanies.textContent = formatarNumero(resultado.negocios);
      if (iaAcademic) iaAcademic.textContent = formatarNumero(resultado.academicos);
      if (iaMixed) iaMixed.textContent = formatarNumero(resultado.outros);
      if (iaErrors) iaErrors.textContent = formatarNumero(resultado.erros);
      renderizarIAFinal(resultado);
      atualizarProgresso(iaProgressTrack, iaProgressBar, iaProgress, resultado.encontrados, resultado.encontrados, 100);
    }
  }

  if (tipo === "exportar") {
    if (exportStatus) exportStatus.textContent = job.status === "rodando" ? "EXPORTANDO..." : job.status === "erro" ? "ERRO" : "FINALIZADO";
    if (exportedCount) exportedCount.textContent = formatarNumero(m.exportados);
    if (exportFound) exportFound.textContent = formatarNumero(m.encontrados);
    if (exportErrors) exportErrors.textContent = formatarNumero(m.erros);
    if (exportElapsed) exportElapsed.textContent = formatarTempo(job.duracao_segundos);
    atualizarProgresso(exportProgressTrack, exportProgressBar, exportProgress, m.processados, m.encontrados, job.progresso);

    if (job.status === "finalizado") {
      atualizarProgresso(exportProgressTrack, exportProgressBar, exportProgress, m.encontrados, m.encontrados, 100);
      if (jobsIniciadosNesteNavegador.has(jobId) && !downloadsFeitos.has(jobId)) {
        downloadsFeitos.add(jobId);
        const link = document.createElement("a");
        link.href = `/api/jobs/${jobId}/arquivo`;
        link.download = "editais_fomento.xlsx";
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
    }
  }

  if (job.status !== "rodando") {
    bloquearInterface(false);
    mostrarBannerFinal(job, job.status === "erro");
  }
}

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

      const job = dados.job;
      atualizarJobNaTela(job, jobId);

      if (job.status === "finalizado" || job.status === "erro") {
        if (jobMonitoradoId === jobId) jobMonitoradoId = null;
        return;
      }
    } catch (erro) {
      console.error("Falha temporária ao acompanhar o job:", erro);
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
      if (jobMonitoradoId !== dados.job.id) {
        acompanharJob(dados.job.id, dados.job);
      } else {
        atualizarJobNaTela(dados.job, dados.job.id);
      }
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
  prepararInicio(tipo);

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
      throw new Error(dados.erro || "Não foi possível iniciar a operação.");
    }

    jobsIniciadosNesteNavegador.add(dados.job_id);
    await acompanharJob(dados.job_id);
  } catch (erro) {
    console.error(erro);
    bloquearInterface(false);
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

if (tabCollector) tabCollector.addEventListener("click", () => { if (!operacaoGlobalAtiva) mostrarTela("collector"); });
if (tabMarkdown) tabMarkdown.addEventListener("click", () => { if (!operacaoGlobalAtiva) mostrarTela("markdown"); });
if (tabIA) tabIA.addEventListener("click", () => { if (!operacaoGlobalAtiva) mostrarTela("ia"); });
if (tabExport) tabExport.addEventListener("click", () => { if (!operacaoGlobalAtiva) mostrarTela("export"); });

if (collectBtn) {
  collectBtn.addEventListener("click", async () => {
    const fontes = exigirFontes();
    if (!fontes) return;
    await iniciarOperacao("coleta", "/api/jobs/coleta", { fontes });
  });
}

if (markdownBtn) {
  markdownBtn.addEventListener("click", async () => {
    const fontes = exigirFontes();
    if (!fontes) return;
    if (!fontes.includes("fapesc")) {
      alert("A etapa MARKDOWN usa somente os PDFs da FAPESC. Selecione FAPESC para executar esta etapa.");
      return;
    }
    await iniciarOperacao("markdown", "/api/jobs/markdown", {});
  });
}

if (iaBtn) {
  iaBtn.addEventListener("click", async () => {
    const fontes = exigirFontes();
    if (!fontes) return;
    await iniciarOperacao("ia", "/api/jobs/ia", { fontes });
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
mostrarTela("collector");
sincronizarEstadoGlobal();

window.setInterval(sincronizarEstadoGlobal, 1000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) sincronizarEstadoGlobal();
});
