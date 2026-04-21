param(
  [ValidateSet("start", "restart", "stop", "status", "logs")]
  [string]$Action = "restart",

  [ValidateSet("dev", "prod")]
  [string]$Mode = "dev",

  [string]$Port = "3000",

  [switch]$Build
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DebugDir = Join-Path $Root "debug"
$OutLogFile = Join-Path $DebugDir "next-server.out.log"
$ErrLogFile = Join-Path $DebugDir "next-server.err.log"

if (-not (Test-Path $DebugDir)) {
  New-Item -Path $DebugDir -ItemType Directory | Out-Null
}

function Get-ListeningProcessNumbersByPort($TargetPort) {
  try {
    $lines = netstat -ano | Select-String ":$TargetPort\s" | ForEach-Object { $_.Line }
    $listeners = $lines | Where-Object { $_ -match "LISTENING" }
    $processNumbers = @()

    foreach ($line in $listeners) {
      $parts = ($line -replace "\s+", " ").Trim().Split(" ")
      if ($parts.Count -ge 5) {
        $procNumber = $parts[$parts.Count - 1]
        if ($procNumber -match "^[0-9]+$") {
          $processNumbers += $procNumber
        }
      }
    }

    return $processNumbers | Select-Object -Unique
  }
  catch {
    return @()
  }
}

function Stop-ProcessesOnPort($TargetPort) {
  $processNumbers = Get-ListeningProcessNumbersByPort -TargetPort $TargetPort
  foreach ($number in $processNumbers) {
    if ($number -gt 0) {
      try {
        Stop-Process -Id $number -Force -ErrorAction Stop
        Write-Host "Stopped process $number on port $TargetPort"
      }
      catch {
        Write-Host "Process $number already stopped"
      }
    }
  }
}

function Show-Status {
  $processNumbers = Get-ListeningProcessNumbersByPort -TargetPort $Port
  if ($processNumbers.Count -gt 0) {
    Write-Host "Server is running on port $Port (processes: $($processNumbers -join ', '))"
  }
  else {
    Write-Host "Server is not running"
  }
}

function Resolve-NodeExecutable {
  $nodeFromPath = Get-Command node -ErrorAction SilentlyContinue
  if ($nodeFromPath) {
    return $nodeFromPath.Source
  }

  $wingetBase = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
  if (Test-Path $wingetBase) {
    $packageDir = Get-ChildItem $wingetBase -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -like "OpenJS.NodeJS.LTS*" } |
      Select-Object -First 1

    if ($packageDir) {
      $nodeCandidate = Get-ChildItem $packageDir.FullName -Recurse -Filter "node.exe" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "node-v.*-win-x64\\node\.exe$" } |
        Select-Object -First 1

      if ($nodeCandidate) {
        return $nodeCandidate.FullName
      }
    }
  }

  return $null
}

function Test-NodeAvailable {
  $resolved = Resolve-NodeExecutable
  if (-not $resolved) {
    throw "Node introuvable. Sans admin: lance 'winget install OpenJS.NodeJS.LTS --scope user --accept-package-agreements --accept-source-agreements', puis ferme/reouvre le terminal."
  }

  return $resolved
}

function Start-Server {
  Push-Location $Root
  try {
    $nodeExe = Test-NodeAvailable
    $nextBin = Join-Path $Root "node_modules\next\dist\bin\next"

    if (-not (Test-Path $nextBin)) {
      throw "Next.js introuvable (node_modules manquant). Lance d'abord npm install."
    }

    if ($Mode -eq "prod" -and $Build.IsPresent) {
      Write-Host "Building app..."
      & $nodeExe $nextBin build
      if ($LASTEXITCODE -ne 0) {
        throw "Build failed"
      }
    }

    $nextCommand = if ($Mode -eq "dev") { "dev" } else { "start" }

    Write-Host "Starting server (mode=$Mode, port=$Port)..."

    if (Test-Path $OutLogFile) {
      Remove-Item $OutLogFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $ErrLogFile) {
      Remove-Item $ErrLogFile -Force -ErrorAction SilentlyContinue
    }

    $startArgs = @{
      FilePath = $nodeExe
      ArgumentList = @($nextBin, $nextCommand, "-p", $Port)
      WorkingDirectory = $Root
      PassThru = $true
      WindowStyle = "Hidden"
      RedirectStandardOutput = $OutLogFile
      RedirectStandardError = $ErrLogFile
    }

    $processObj = Start-Process @startArgs
    Write-Host "Started process $($processObj.Id)"
    Write-Host "Logs: $OutLogFile"
  }
  finally {
    Pop-Location
  }
}

switch ($Action) {
  "status" {
    Show-Status
    exit 0
  }

  "logs" {
    if (-not (Test-Path $OutLogFile)) {
      Write-Host "No log file yet: $OutLogFile"
      exit 0
    }
    Write-Host "Streaming logs from $OutLogFile (Ctrl+C to stop)..."
    Get-Content -Path $OutLogFile -Wait
    exit 0
  }

  "stop" {
    Stop-ProcessesOnPort -TargetPort $Port
    Write-Host "Stop completed"
    exit 0
  }

  "start" {
    $alreadyRunning = Get-ListeningProcessNumbersByPort -TargetPort $Port
    if ($alreadyRunning.Count -gt 0) {
      Write-Host "Server already running on port $Port"
      exit 0
    }
    Start-Server
    exit 0
  }

  "restart" {
    Stop-ProcessesOnPort -TargetPort $Port
    Start-Server
    exit 0
  }
}
