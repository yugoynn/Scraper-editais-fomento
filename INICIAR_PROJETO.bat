@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Fomento Terminal - V22 LAN SYNC MOBILE

echo ============================================================
echo  FOMENTO TERMINAL - V22 LAN SYNC MOBILE
echo  IA: qwen3.5:9b
echo  Classificacao: NEGOCIOS / ACADEMICO / OUTRO
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado no PATH.
    pause
    exit /b 1
)

where ollama >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Ollama nao foi encontrado no PATH.
    pause
    exit /b 1
)

ollama ls | findstr /I /C:"qwen3.5:9b" >nul 2>&1
if errorlevel 1 (
    echo [ERRO] O modelo qwen3.5:9b nao esta instalado.
    echo Execute primeiro: CONFIGURAR_IA_QWEN35_9B.bat
    pause
    exit /b 1
)

echo [OK] qwen3.5:9b encontrado.
echo [TESTE] Verificando services\ia.py...

for /d /r %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D" >nul 2>&1

python -c "from services.ia import analisar_fontes, analisar_finep, analisar_fapesp, analisar_fonte_json, FONTES_JSON_CONFIG, ANALISE_VERSION, FINEP_ANALISE_VERSION, FAPESP_ANALISE_VERSION, FONTES_JSON_ANALISE_VERSION, OLLAMA_MODEL; assert ANALISE_VERSION == 16; assert FINEP_ANALISE_VERSION == 1; assert FAPESP_ANALISE_VERSION == 3; assert FONTES_JSON_ANALISE_VERSION == 1; assert len(FONTES_JSON_CONFIG) == 6; assert OLLAMA_MODEL == 'qwen3.5:9b'; print('[OK] services.ia carregado corretamente.')"
if errorlevel 1 (
    echo.
    echo [ERRO] O arquivo services\ia.py nao passou na verificacao.
    echo Use esta pasta V22 completa e nao misture com arquivos de versoes antigas.
    pause
    exit /b 1
)

echo [OK] Iniciando servidor local e LAN na porta 5000
echo [INFO] O IP da rede sera mostrado pelo servidor abaixo.
echo.
python backend\server.py

echo.
pause
