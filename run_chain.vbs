Option Explicit

Dim workDir, logDir, exportDir, logFile, pythonw
workDir   = "C:\Users\fgperez\OneDrive - Topaz Evolution\Documentos\Automa\LogHoras"
logDir    = workDir & "\logs"
exportDir = workDir & "\exports"
pythonw   = "C:\Users\fgperez\AppData\Local\Programs\Python313\python.exe"

Dim fso: Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FolderExists(workDir)   Then fso.CreateFolder workDir
If Not fso.FolderExists(logDir)    Then fso.CreateFolder logDir
If Not fso.FolderExists(exportDir) Then fso.CreateFolder exportDir

logFile = logDir & "\chain_" & Year(Now) & Right("0" & Month(Now),2) & Right("0" & Day(Now),2) & ".log"

Function Q(s)
  Q = """" & s & """"
End Function

Sub WriteLog(msg)
  Dim ts: Set ts = fso.OpenTextFile(logFile, 8, True, 0)
  ts.WriteLine "[" & Year(Now) & "-" & Right("0"&Month(Now),2) & "-" & Right("0"&Day(Now),2) & " " & _
                Right("0"&Hour(Now),2) & ":" & Right("0"&Minute(Now),2) & ":" & Right("0"&Second(Now),2) & "] " & msg
  ts.Close
End Sub

Sub WriteDivider(title)
  WriteLog "----- " & title & " -----"
End Sub

Function RunStep(stepName, exe, args)
  Dim sh, cmd, wrappedCmd, exitCode
  Set sh = CreateObject("WScript.Shell")
  cmd = Q(exe) & " " & args
  WriteDivider "START " & stepName
  WriteLog "CMD: " & cmd
  wrappedCmd = "cmd.exe /c cd /d " & Q(workDir) & " && (" & cmd & ") >> " & Q(logFile) & " 2>&1"
  exitCode = sh.Run(wrappedCmd, 0, True)
  If exitCode = 0 Then
    WriteLog "RESULT: " & stepName & " OK (exit=" & exitCode & ")"
  Else
    WriteLog "RESULT: " & stepName & " ERROR (exit=" & exitCode & ")"
    WriteLog "ABORT: revisar salida capturada arriba en este mismo archivo de log."
  End If
  RunStep = exitCode
End Function

Sub RunStepAsync(stepName, exe, args)
  Dim sh, cmd, wrappedCmd
  Set sh = CreateObject("WScript.Shell")
  cmd = Q(exe) & " " & args
  WriteDivider "START ASYNC " & stepName
  WriteLog "CMD: " & cmd
  wrappedCmd = "cmd.exe /c cd /d " & Q(workDir) & " && (" & cmd & ") >> " & Q(logFile) & " 2>&1"
  sh.Run wrappedCmd, 0, False
End Sub

Function FindLatestJsonByName()
  Dim folder, f, latestPath, latestKey, base, rest, digits, i, ch, y, m, key
  latestPath = ""
  latestKey  = -1

  Set folder = fso.GetFolder(workDir & "\resultado")
  For Each f In folder.Files
    If LCase(Right(f.Name, 5)) = ".json" Then
      base = fso.GetBaseName(f.Name)
      If LCase(Left(base, 9)) = "jira_log_" Then
        rest = Mid(base, 10)
        digits = ""
        For i = 1 To Len(rest)
          ch = Mid(rest, i, 1)
          If ch >= "0" And ch <= "9" Then digits = digits & ch
        Next
        If Len(digits) >= 6 Then
          y = CLng(Left(digits, 4))
          m = CLng(Mid(digits, 5, 2))
          If m >= 1 And m <= 12 Then
            key = y * 100 + m
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
  base = fso.GetBaseName(jsonPath)
  rest = Mid(base, 10)
  digits = ""
  For i = 1 To Len(rest)
    ch = Mid(rest, i, 1)
    If ch >= "0" And ch <= "9" Then digits = digits & ch
  Next

  If Len(digits) >= 6 Then
    monthPart = Left(digits,4) & "-" & Mid(digits,5,2)
  Else
    monthPart = base
  End If

  csvName = "jira_entries_flat_" & monthPart & ".csv"
  DeriveCsvOutFromJson = exportDir & "\" & csvName
End Function

WriteLog "=== CHAIN START ==="

Dim rc
rc = RunStep("jira_tracker_JSON.py", pythonw, Q(workDir & "\jira_tracker_JSON.py"))
If rc <> 0 Then
  WriteLog "ABORT: error en paso 1"
  WScript.Quit rc
End If

Dim jsonIn, csvOut
jsonIn = FindLatestJsonByName()
If jsonIn = "" Then
  WriteLog "ABORT: no se encontró jira_log_*.json en " & workDir
  WScript.Quit 3
End If
csvOut = DeriveCsvOutFromJson(jsonIn)
WriteLog "JSON detectado: " & jsonIn
WriteLog "CSV destino:    " & csvOut

Dim argsCSV
argsCSV = Q(workDir & "\json_to_csv.py") & " " & Q(jsonIn) & " " & Q(csvOut)
RunStepAsync "json_to_csv.py", pythonw, argsCSV

WriteLog "=== CHAIN OK ==="
WScript.Quit 0
