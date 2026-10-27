@echo off
setlocal

echo ===================================================
echo   ATON - Desativar Inicializacao com o Windows
echo ===================================================
echo.

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\ATON.lnk"

if not exist "%SHORTCUT_PATH%" goto :not_active

echo [INFO] Removendo atalho de inicializacao automatica:
echo %SHORTCUT_PATH%
del /f /q "%SHORTCUT_PATH%"

if exist "%SHORTCUT_PATH%" goto :err_del_failed

echo.
echo ===================================================
echo [SUCESSO] Inicializacao automatica DESATIVADA!
echo ===================================================
echo O ATON nao sera mais iniciado automaticamente ao ligar
echo ou fazer login no Windows.
echo.
echo Para reativa-lo no futuro, basta executar:
echo   scripts\ativar_inicializacao_windows.bat
echo ===================================================
goto :end

:not_active
echo [INFO] A inicializacao automatica ja esta desativada.
echo O atalho ATON.lnk nao existe na pasta de inicializacao.
goto :end

:err_del_failed
echo [ERRO] Nao foi possivel remover o atalho. Verifique suas permissoes.
goto :end

:end
echo.
if not "%1"=="--no-pause" pause
exit /b 0
