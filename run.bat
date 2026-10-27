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
if "%1"=="bg" goto :cmd_bg
if "%1"=="background" goto :cmd_bg
if "%1"=="autostart" goto :cmd_autostart_on
if "%1"=="autostart-on" goto :cmd_autostart_on
if "%1"=="autostart-off" goto :cmd_autostart_off
if "%1"=="status" goto :cmd_status
if "%1"=="stop" goto :cmd_stop
if "%1"=="gateway" goto :cmd_gateway
if "%1"=="rede" goto :cmd_gateway
if "%1"=="" goto :cmd_start

echo Uso:
echo   run.bat               - Inicia o assistente Aton (com janela de terminal)
echo   run.bat gateway       - Inicia o Mobile Gateway e Servico em Rede para celulares/TVs
echo   run.bat bg            - Inicia o Aton em segundo plano (silencioso, bandeja)
echo   run.bat autostart-on  - Ativa inicializacao automatica com o Windows
echo   run.bat autostart-off - Desativa inicializacao automatica com o Windows
echo   run.bat status        - Verifica se o Aton e o autostart estao ativos
echo   run.bat stop          - Encerra instâncias do Aton em execucao
echo   run.bat install       - Instala ou atualiza as dependencias
echo   run.bat test          - Roda a suite de testes automatizados
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

:cmd_bg
if not exist ".env" (
    echo [AVISO] Arquivo .env nao encontrado.
    echo Copiando .env.example para .env...
    copy .env.example .env
    echo [IMPORTANTE] Por favor, abra o arquivo .env e adicione sua GEMINI_API_KEY.
    pause
    exit /b 1
)
echo [INFO] Iniciando o assistente Aton em segundo plano silencioso...
wscript launch_aton_background.vbs
echo [SUCESSO] Aton iniciado em background! Verifique o icone na bandeja do sistema.
exit /b 0

:cmd_autostart_on
call scripts\ativar_inicializacao_windows.bat
exit /b 0

:cmd_autostart_off
call scripts\desativar_inicializacao_windows.bat
exit /b 0

:cmd_status
echo [STATUS DO PROCESSO ATON]
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*src.main*' } | Select-Object ProcessId, Name, CommandLine | Format-Table -AutoSize"
echo.
echo [STATUS DA INICIALIZACAO COM O WINDOWS]
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ATON.lnk" (
    echo [ATIVADO] O atalho 'ATON.lnk' esta presente na pasta de inicializacao do Windows.
) else (
    echo [DESATIVADO] A inicializacao automatica com o Windows nao esta configurada.
)
exit /b 0

:cmd_stop
echo [INFO] Encerrando processos do Aton...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*src.main*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Processo ' + $_.ProcessId + ' encerrado.') }"
echo [SUCESSO] Processos encerrados.
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

:cmd_gateway
echo [INFO] Iniciando Aton Mobile Gateway e Descoberta em Rede...
python scripts\iniciar_gateway_rede.py
exit /b 0

