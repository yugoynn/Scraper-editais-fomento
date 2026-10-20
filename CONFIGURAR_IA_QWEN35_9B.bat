@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Configurar Qwen 3.5 9B - Fomento Terminal

echo ============================================================
echo  CONFIGURACAO DA IA LOCAL - QWEN 3.5 9B
echo ============================================================
echo.

where ollama >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Ollama nao foi encontrado no PATH.
    echo Instale/abra o Ollama e execute este arquivo novamente.
    pause
    exit /b 1
)

echo [1/4] Verificando modelos instalados...
ollama ls

echo.
echo [2/4] Removendo o modelo antigo gemma3:4b, se estiver instalado...
ollama ls | findstr /I /C:"gemma3:4b" >nul 2>&1
if errorlevel 1 (
    echo [OK] gemma3:4b nao esta instalado.
) else (
    ollama rm gemma3:4b
    if errorlevel 1 (
        echo [AVISO] Nao foi possivel remover gemma3:4b automaticamente.
    ) else (
        echo [OK] gemma3:4b removido.
    )
)

echo.
echo [3/4] Baixando qwen3.5:9b...
ollama pull qwen3.5:9b
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao baixar qwen3.5:9b.
    pause
    exit /b 1
)

echo.
echo [4/4] Modelos instalados:
ollama ls

echo.
echo ============================================================
echo  PRONTO. O projeto esta configurado para qwen3.5:9b.
echo ============================================================
echo.
pause
