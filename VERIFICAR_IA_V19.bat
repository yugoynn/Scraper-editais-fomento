@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Verificando o modulo services\ia.py V19...
for /d /r %%D in (__pycache__) do @if exist "%%D" rd /s /q "%%D" >nul 2>&1
python -c "from services.ia import analisar_fontes, analisar_editais, analisar_sebrae, analisar_finep, analisar_fapesp, analisar_fonte_json, FONTES_JSON_CONFIG, ANALISE_VERSION, FINEP_ANALISE_VERSION, FAPESP_ANALISE_VERSION, FONTES_JSON_ANALISE_VERSION, OLLAMA_MODEL; print('IMPORT_OK'); print('versao_geral =', ANALISE_VERSION); print('versao_finep =', FINEP_ANALISE_VERSION); print('versao_fapesp =', FAPESP_ANALISE_VERSION); print('versao_fontes_json =', FONTES_JSON_ANALISE_VERSION); print('fontes_json =', len(FONTES_JSON_CONFIG)); print('modelo =', OLLAMA_MODEL); assert ANALISE_VERSION == 16; assert FINEP_ANALISE_VERSION == 1; assert FAPESP_ANALISE_VERSION == 3; assert FONTES_JSON_ANALISE_VERSION == 1; assert len(FONTES_JSON_CONFIG) == 6; assert OLLAMA_MODEL == 'qwen3.5:9b'"
if errorlevel 1 (
  echo.
  echo [ERRO] Falha na verificacao da IA.
) else (
  echo.
  echo [OK] services\ia.py V19 esta correto.
)
pause
