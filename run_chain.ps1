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
# Carpeta de trabajo
$WorkDir = "C:\Users\fgperez\Documents\Automa\LogHoras"

# PASO 1 y PASO 2 (editá a tu gusto)
# Opción A: usar python del sistema (si está en PATH de la cuenta que corre la tarea)
# $Step1   = "python.exe jira_tracker_JSON.py"
# $Step2   = "python.exe enviar_novedades.py"

# Opción B (recomendada): usar el python del venv (sin necesidad de 'activar' el venv)
$PyVenv  = "C:\Users\fgperez\AppData\Local\Programs\Python313\pythonw.exe"
$Step1   = "`"$PyVenv`" jira_tracker_JSON.py"
$Step2   = "`"$PyVenv`" enviar_novedades.py"

# Archivo de log (un log por día)
$Log     = Join-Path $WorkDir ("\logs\chain_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

# =======================
# ====== Helpers ========
# =======================
function Write-Log($msg) {
  $line = ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
  New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
  Add-Content -Path $Log -Value $line
}

function Run-Step($cmd) {
  Write-Log ("START: {0}" -f $cmd)
  # Ejecuta oculto y espera a que termine
  $proc = Start-Process "cmd.exe" -ArgumentList "/c $cmd" -Wait -PassThru -WindowStyle Hidden -WorkingDirectory $WorkDir
  $code = $proc.ExitCode
  Write-Log ("END:   {0} (exit={1})" -f $cmd, $code)
  if ($code -ne 0) {
    Write-Log ("ABORT: cadena detenida por error en paso: {0}" -f $cmd)
    exit $code
  }
}

# =======================
# ====== Ejecución ======
# =======================
Set-Location $WorkDir
Write-Log "=== CHAIN START ==="

Run-Step $Step1
Run-Step $Step2

Write-Log "=== CHAIN OK ==="
exit 0