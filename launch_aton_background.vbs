' ==============================================================================
' ATON - Launcher Silencioso em Segundo Plano
' Executa o Aton utilizando pythonw.exe sem abrir janelas de console.
' ==============================================================================
Option Explicit

Dim fso, wshShell, scriptDir, pythonwPath, command

Set fso = CreateObject("Scripting.FileSystemObject")
Set wshShell = CreateObject("WScript.Shell")

' Diretorio raiz do projeto (onde este script reside)
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
wshShell.CurrentDirectory = scriptDir

pythonwPath = scriptDir & "\.venv\Scripts\pythonw.exe"

' Verifica se o executavel pythonw existe no ambiente virtual
If Not fso.FileExists(pythonwPath) Then
    MsgBox "Erro: O ambiente virtual (.venv) nao foi encontrado em:" & vbCrLf & _
           pythonwPath & vbCrLf & vbCrLf & _
           "Por favor, execute 'run.bat install' antes de iniciar o Aton.", _
           vbCritical, "ATON - Erro de Inicializacao"
    WScript.Quit 1
End If

' Monta o comando de execucao
command = """" & pythonwPath & """ -m src.main"

' Executa silenciosamente:
' 0 = Janela Oculta (sem console cmd/dos)
' False = Nao aguarda conclusao (roda desacoplado em background)
wshShell.Run command, 0, False

Set wshShell = Nothing
Set fso = Nothing
