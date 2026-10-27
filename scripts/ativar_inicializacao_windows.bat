@echo off
setlocal

echo ===================================================
echo   ATON - Configurar Inicializacao com o Windows
echo ===================================================
echo.

:: Determina o diretorio raiz do projeto (um nivel acima da pasta scripts)
set "CURRENT_DIR=%~dp0"
set "PROJECT_DIR=%CURRENT_DIR:~0,-1%"
for %%I in ("%PROJECT_DIR%") do set "PROJECT_DIR=%%~dpI"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "LAUNCHER_VBS=%PROJECT_DIR%\launch_aton_background.vbs"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\ATON.lnk"
set "ICON_PATH=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"

if not exist "%LAUNCHER_VBS%" goto :err_no_launcher

echo [1/2] Criando atalho de inicializacao em segundo plano...
echo Destino: %SHORTCUT_PATH%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT_PATH%'); $sc.TargetPath = 'wscript.exe'; $sc.Arguments = '\"%LAUNCHER_VBS%\"'; $sc.WorkingDirectory = '%PROJECT_DIR%'; $sc.Description = 'ATON - Assistente Pessoal Inteligente em Segundo Plano'; $sc.WindowStyle = 7; if (Test-Path '%ICON_PATH%') { $sc.IconLocation = '%ICON_PATH%,0' }; $sc.Save();"

if errorlevel 1 goto :err_failed

echo [2/2] Validando criacao do atalho...
if not exist "%SHORTCUT_PATH%" goto :err_shortcut_missing

echo.
echo ===================================================
echo [SUCESSO] Inicializacao automatica configurada!
echo ===================================================
echo O ATON agora iniciara automaticamente sempre que voce
echo fizer login no Windows, ficando em segundo plano na
echo bandeja do sistema, proximo ao relogio.
echo.
echo Modos de operacao:
echo - Aguarda a palavra-chave falada: "aton"
echo - Clique com botao direito no icone da bandeja para ver o status ou encerrar
echo - Para desativar a qualquer momento, execute:
echo   scripts\desativar_inicializacao_windows.bat
echo ===================================================
echo.
goto :end

:err_no_launcher
echo [ERRO] O arquivo launcher silencioso nao foi encontrado em:
echo "%LAUNCHER_VBS%"
goto :end

:err_failed
echo [ERRO] Falha ao criar o atalho de inicializacao automatica.
goto :end

:err_shortcut_missing
echo [ERRO] O atalho nao foi encontrado na pasta de inicializacao apos a criacao.
goto :end

:end
if not "%1"=="--no-pause" pause
exit /b 0
