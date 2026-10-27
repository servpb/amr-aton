@echo off
setlocal

echo ===================================================
echo               ATON - Assistente Pessoal
echo ===================================================

:: Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado no sistema.
    echo Por favor, instale o Python 3.10 ou superior e adicione-o ao PATH.
    pause
    exit /b 1
)

:: Virtual environment setup
if not exist ".venv" (
    echo [INFO] Criando ambiente virtual Python .venv...
    python -m venv .venv
)

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Route commands
if "%1"=="install" goto :cmd_install
if "%1"=="test" goto :cmd_test
if "%1"=="" goto :cmd_start

echo Uso:
echo   run.bat          - Inicia o assistente Aton
echo   run.bat install  - Instala ou atualiza as dependencias
echo   run.bat test     - Roda a suite de testes automatizados
exit /b 0

:cmd_install
echo [INFO] Instalando dependencias do projeto...
python -m pip install --upgrade pip
python -m pip install -e .[dev]
echo [SUCESSO] Dependencias instaladas com sucesso.
exit /b 0

:cmd_test
echo [INFO] Executando testes automatizados com pytest...
python -m pytest
exit /b 0

:cmd_start
if not exist ".env" (
    echo [AVISO] Arquivo .env nao encontrado.
    echo Copiando .env.example para .env...
    copy .env.example .env
    echo [IMPORTANTE] Por favor, abra o arquivo .env e adicione sua GEMINI_API_KEY.
    pause
    exit /b 1
)
echo [INFO] Iniciando o assistente Aton...
python -m src.main
exit /b 0
