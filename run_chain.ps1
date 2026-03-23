# run_chain.ps1
# Ejecuta dos pasos en secuencia (A -> B) y no muestra ventanas.
# Se auto-relanza oculto y registra logs con fecha/hora.

param([switch]$HiddenRun)

# --- Auto-relaunch oculto ---
if (-not $HiddenRun) {
  if ($PSCommandPath) {
    Start-Process -FilePath "powershell.exe" `
      -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -HiddenRun" `
      -WindowStyle Hidden
    exit 0
  }
}

$ErrorActionPreference = 'Stop'

# =======================
# ======= CONFIG ========
# =======================
$WorkDir = "C:\Users\fgperez\Documents\Automa\LogHoras"
$PyVenv  = "C:\Users\fgperez\AppData\Local\Programs\Python313\python.exe"
$Step1   = "`"$PyVenv`" jira_tracker_JSON.py"
$Step2   = "`"$PyVenv`" enviar_novedades.py"
$LogDir  = Join-Path $WorkDir "logs"
$Log     = Join-Path $LogDir ("chain_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

# =======================
# ====== Helpers ========
# =======================
function Ensure-LogDir {
  New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

function Write-Log($msg) {
  Ensure-LogDir
  $line = ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
  Add-Content -Path $Log -Value $line
}

function Write-StepDivider($title) {
  Write-Log ("----- {0} -----" -f $title)
}

function Run-Step($name, $cmd) {
  Write-StepDivider ("START $name")
  Write-Log ("CMD: {0}" -f $cmd)

  $wrappedCmd = "/c cd /d `"$WorkDir`" && ({0}) >> `"$Log`" 2>&1" -f $cmd
  $proc = Start-Process "cmd.exe" -ArgumentList $wrappedCmd -Wait -PassThru -WindowStyle Hidden
  $code = $proc.ExitCode

  if ($code -eq 0) {
    Write-Log ("RESULT: {0} OK (exit={1})" -f $name, $code)
    return
  }

  Write-Log ("RESULT: {0} ERROR (exit={1})" -f $name, $code)
  Write-Log ("ABORT: cadena detenida por error en paso: {0}" -f $name)
  Write-Log ("ABORT: revisar salida capturada arriba en este mismo archivo de log.")
  exit $code
}

# =======================
# ====== Ejecución ======
# =======================
Set-Location $WorkDir
Write-Log "=== CHAIN START ==="

Run-Step "jira_tracker_JSON.py" $Step1
Run-Step "enviar_novedades.py" $Step2

Write-Log "=== CHAIN OK ==="
exit 0
