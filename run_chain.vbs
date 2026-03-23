Option Explicit

Dim workDir, logDir, exportDir, logFile, pythonw
workDir   = "C:\Users\fgperez\OneDrive - Topaz Evolution\Documentos\Automa\LogHoras"
logDir    = workDir & "\logs"
exportDir = workDir & "\exports"
pythonw   = "C:\Users\fgperez\AppData\Local\Programs\Python313\pythonw.exe"

' Helpers de FS
Dim fso: Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FolderExists(workDir)   Then fso.CreateFolder workDir
If Not fso.FolderExists(logDir)    Then fso.CreateFolder logDir
If Not fso.FolderExists(exportDir) Then fso.CreateFolder exportDir

logFile = logDir & "\chain_" & Year(Now) & Right("0" & Month(Now),2) & Right("0" & Day(Now),2) & ".log"

' === Helpers ==============================================================
Function Q(s)
  Q = """" & s & """"
End Function

Sub WriteLog(msg)
  Dim ts: Set ts = fso.OpenTextFile(logFile, 8, True, 0) 'ASCII
  ts.WriteLine "[" & Year(Now) & "-" & Right("0"&Month(Now),2) & "-" & Right("0"&Day(Now),2) & " " & _
                Right("0"&Hour(Now),2) & ":" & Right("0"&Minute(Now),2) & ":" & Right("0"&Second(Now),2) & "] " & msg
  ts.Close
End Sub

Function RunStep(exe, args)
  Dim sh, cmd, exitCode
  Set sh = CreateObject("WScript.Shell")
  cmd = Q(exe) & " " & args
  WriteLog "START: " & cmd
  exitCode = sh.Run("cmd.exe /c cd /d " & Q(workDir) & " && " & cmd, 0, True)  ' espera
  WriteLog "END:   " & cmd & " (exit=" & exitCode & ")"
  RunStep = exitCode
End Function

Sub RunStepAsync(exe, args)
  Dim sh, cmd
  Set sh = CreateObject("WScript.Shell")
  cmd = Q(exe) & " " & args
  WriteLog "START (async): " & cmd
  ' 0 = oculto, False = NO esperar
  sh.Run "cmd.exe /c cd /d " & Q(workDir) & " && " & cmd, 0, False
End Sub

Function FindLatestJsonByName()
  Dim folder, f, latestPath, latestKey, base, rest, digits, i, ch, y, m, key
  latestPath = ""
  latestKey  = -1

  Set folder = fso.GetFolder(workDir & "\resultado")
  For Each f In folder.Files
    If LCase(Right(f.Name, 5)) = ".json" Then
      base = fso.GetBaseName(f.Name)           ' ej: jira_log_2025-10
      If LCase(Left(base, 9)) = "jira_log_" Then
        rest = Mid(base, 10)                   ' 2025-10 (u otro formato)
        digits = ""
        For i = 1 To Len(rest)                 ' conservar solo dígitos
          ch = Mid(rest, i, 1)
          If ch >= "0" And ch <= "9" Then digits = digits & ch
        Next
        If Len(digits) >= 6 Then               ' YYYYMM
          y = CLng(Left(digits, 4))
          m = CLng(Mid(digits, 5, 2))
          If m >= 1 And m <= 12 Then
            key = y * 100 + m                  ' compara YYYYMM
            If key > latestKey Then
              latestKey  = key
              latestPath = f.Path
            End If
          End If
        End If
      End If
    End If
  Next
  FindLatestJsonByName = latestPath
End Function

Function DeriveCsvOutFromJson(jsonPath)
  Dim base, rest, digits, i, ch, monthPart, csvName
  base = fso.GetBaseName(jsonPath)            ' jira_log_2025-10

  rest = Mid(base, 10)                         ' 2025-10
  digits = ""
  For i = 1 To Len(rest)
    ch = Mid(rest, i, 1)
    If ch >= "0" And ch <= "9" Then digits = digits & ch
  Next

  If Len(digits) >= 6 Then
    monthPart = Left(digits,4) & "-" & Mid(digits,5,2) ' YYYY-MM
  Else
    monthPart = base
  End If

  csvName = "jira_entries_flat_" & monthPart & ".csv"
  DeriveCsvOutFromJson = exportDir & "\" & csvName
End Function
' ========================================================================

WriteLog "=== CHAIN START ==="

Dim rc
' Paso 1: generar JSON
rc = RunStep(pythonw, Q(workDir & "\jira_tracker_JSON.py"))
If rc <> 0 Then
  WriteLog "ABORT: error en paso 1"
  WScript.Quit rc
End If

' Detectar último JSON y derivar CSV (mismo YYYY-MM)
Dim jsonIn, csvOut
jsonIn = FindLatestJsonByName()
If jsonIn = "" Then
  WriteLog "ABORT: no se encontró jira_log_*.json en " & workDir
  WScript.Quit 3
End If
csvOut = DeriveCsvOutFromJson(jsonIn)
WriteLog "JSON detectado: " & jsonIn
WriteLog "CSV destino:    " & csvOut

' Paso 3 (async): convertir JSON -> CSV en paralelo con el paso 2
Dim argsCSV
argsCSV = Q(workDir & "\json_to_csv.py") & " " & Q(jsonIn) & " " & Q(csvOut)
RunStepAsync pythonw, argsCSV

' Paso 2: enviar novedades (espera)
rc = RunStep(pythonw, Q(workDir & "\enviar_novedades.py"))
If rc <> 0 Then
  WriteLog "ABORT: error en paso 2"
  WScript.Quit rc
End If

WriteLog "=== CHAIN OK ==="
WScript.Quit 0
