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
if "%1"=="gmail-auth" goto :cmd_gmail_auth
if "%1"=="gmail-status" goto :cmd_gmail_status
if "%1"=="gmail-remove" goto :cmd_gmail_remove
if "%1"=="calendar-auth" goto :cmd_calendar_auth
if "%1"=="calendar-status" goto :cmd_calendar_status
if "%1"=="calendar-remove" goto :cmd_calendar_remove
if "%1"=="youtube-auth" goto :cmd_youtube_auth
if "%1"=="youtube-status" goto :cmd_youtube_status
if "%1"=="youtube-channels" goto :cmd_youtube_channels
if "%1"=="youtube-remove" goto :cmd_youtube_remove
if "%1"=="groq-test" goto :cmd_groq_test
if "%1"=="nemotron-test" goto :cmd_nemotron_test
if "%1"=="" goto :cmd_start

echo Uso:
echo   run.bat                  - Inicia o assistente Aton (com janela de terminal)
echo   run.bat gateway          - Inicia o Mobile Gateway e Servico em Rede para celulares/TVs
echo   run.bat bg               - Inicia o Aton em segundo plano (silencioso, bandeja)
echo   run.bat gmail-auth       - Autentica uma conta do Gmail no navegador (ex: run.bat gmail-auth cursopb@gmail.com)
echo   run.bat gmail-status     - Verifica o status das contas do Gmail conectadas
echo   run.bat gmail-remove     - Remove o token local de uma conta do Gmail (ex: run.bat gmail-remove cursopb@gmail.com [--revoke])
echo   run.bat calendar-auth    - Autentica uma conta do Google Agenda no navegador (ex: run.bat calendar-auth [email])
echo   run.bat calendar-status  - Verifica o status das contas do Google Agenda conectadas
echo   run.bat calendar-remove  - Remove o token local de uma conta do Google Agenda (ex: run.bat calendar-remove <email> [--revoke])
echo   run.bat youtube-auth     - Autentica conta/canal do YouTube (ex: run.bat youtube-auth cursopb@gmail.com [--mode readonly^|manage])
echo   run.bat youtube-status   - Verifica passivamente as contas e canais do YouTube conectados
echo   run.bat youtube-channels - Lista os canais do YouTube autenticados e verifica UCYCmXtIR-tbWCyrwbLdczyA
echo   run.bat youtube-remove   - Remove o token de um canal ou conta do YouTube (ex: run.bat youtube-remove <email_ou_canal> [--revoke])
echo   run.bat groq-test        - Testa a conexao e resposta da API Groq LPU
echo   run.bat nemotron-test    - Avalia planejamento complexo com a NVIDIA Nemotron (OpenRouter)
echo   run.bat autostart-on     - Ativa inicializacao automatica com o Windows
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
powershell -NoProfile -Command "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = 'wscript.exe \"' + (Get-Location).Path + '\launch_aton_background.vbs\"'; CurrentDirectory = (Get-Location).Path } | Out-Null"
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

:cmd_gmail_auth
python scripts\autenticar_gmail.py %2 %3 %4
exit /b 0

:cmd_gmail_status
python scripts\autenticar_gmail.py --status %2 %3 %4
exit /b 0

:cmd_gmail_remove
if "%2"=="" (
    echo [ERRO] Informe o e-mail da conta a remover. Exemplo: run.bat gmail-remove cursopb@gmail.com
    exit /b 1
)
python scripts\autenticar_gmail.py --remove %2 %3 %4
exit /b 0

:cmd_youtube_auth
python scripts\autenticar_youtube.py %2 %3 %4 %5
exit /b 0

:cmd_youtube_status
python scripts\autenticar_youtube.py --status %2 %3 %4
exit /b 0

:cmd_youtube_channels
python scripts\autenticar_youtube.py --channels %2 %3 %4
exit /b 0

:cmd_youtube_remove
if "%2"=="" (
    echo [ERRO] Informe o e-mail da conta ou ID do canal a remover. Exemplo: run.bat youtube-remove cursopb@gmail.com
    exit /b 1
)
python scripts\autenticar_youtube.py --remove %2 %3 %4
exit /b 0

:cmd_groq_test
python scripts\testar_groq.py %2 %3
exit /b 0

:cmd_nemotron_test
python scripts\avaliar_nemotron.py %2 %3 %4
exit /b 0

:cmd_calendar_auth
python scripts\autenticar_agenda.py %2 %3 %4
exit /b 0

:cmd_calendar_status
python scripts\autenticar_agenda.py --status %2 %3 %4
exit /b 0

:cmd_calendar_remove
if "%2"=="" (
    echo [ERRO] Informe o e-mail da conta a remover. Exemplo: run.bat calendar-remove usuario@gmail.com
    exit /b 1
)
python scripts\autenticar_agenda.py --remove %2 %3 %4
exit /b 0


