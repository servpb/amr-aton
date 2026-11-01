' ==============================================================================
' ATON - Launcher Silencioso em Segundo Plano
' Executa o Aton utilizando pythonw.exe sem abrir janelas de console.
' ==============================================================================
Option Explicit

Dim fso, wshShell, scriptDir, pythonwPath, command
Dim objWMIService, colProcesses, objProcess, isBootMode, i

Set fso = CreateObject("Scripting.FileSystemObject")
Set wshShell = CreateObject("WScript.Shell")

' Verifica se foi acionado no boot do Windows (--boot)
isBootMode = False
If WScript.Arguments.Count > 0 Then
    For i = 0 To WScript.Arguments.Count - 1
        If LCase(WScript.Arguments(i)) = "--boot" Then
            isBootMode = True
        End If
    Next
End If

' No login do Windows, aguarda 3 segundos para estabilizar driver de audio e bandeja do Explorer
If isBootMode Then
    WScript.Sleep 3000
End If

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

' Gerencia instancias existentes de src.main para evitar conflito de porta/microfone
On Error Resume Next
Set objWMIService = GetObject("winmgmts:\\.\root\cimv2")
If Err.Number = 0 Then
    Set colProcesses = objWMIService.ExecQuery("SELECT * FROM Win32_Process WHERE (Name = 'pythonw.exe' OR Name = 'python.exe') AND CommandLine LIKE '%src.main%'")
    For Each objProcess In colProcesses
        If isBootMode Then
            ' Se ja estiver rodando no boot, evita duplicidade
            WScript.Quit 0
        Else
            ' Se iniciado manualmente, reinicia de forma limpa encerrando a instancia anterior
            objProcess.Terminate()
        End If
    Next
    If Not isBootMode Then
        WScript.Sleep 600
    End If
End If
On Error GoTo 0

' Monta o comando de execucao
command = """" & pythonwPath & """ -m src.main"

' Executa silenciosamente:
' 0 = Janela Oculta (sem console cmd/dos)
' False = Nao aguarda conclusao (roda desacoplado em background)
wshShell.Run command, 0, False

Set wshShell = Nothing
Set fso = Nothing
