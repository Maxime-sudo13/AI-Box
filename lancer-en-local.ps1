# Business AI Box — test sur votre ordinateur (Windows). Prérequis : Docker Desktop démarré.
# Lancer depuis PowerShell :  .\lancer-en-local.ps1
# (si Windows bloque le script : Set-ExecutionPolicy -Scope Process Bypass, puis relancer)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "deploy")
$compose = @("compose", "-f", "docker-compose.local.yml")

Write-Host "1/3  Construction et démarrage (la première fois : 5 à 10 minutes)..."
& docker @compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "Échec du démarrage. Docker Desktop est-il lancé ?"; exit 1 }

Write-Host "2/3  Attente du serveur..."
$ready = $false
for ($i = 0; $i -lt 90; $i++) {
  & docker @compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { $ready = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $ready) { Write-Host "Le serveur ne démarre pas. Détails : docker compose -f deploy\docker-compose.local.yml logs api"; exit 1 }

Write-Host "3/3  Chargement du restaurant de démonstration (la première fois : environ 1 minute)..."
& docker @compose exec -T api python -m app.demo seed --admin-email gerant@bistrot.local --admin-password demo-bistrot-2026

Write-Host ""
Write-Host "Prêt : http://localhost:8080"
Write-Host "  Adresse e-mail : gerant@bistrot.local"
Write-Host "  Mot de passe   : demo-bistrot-2026"
Write-Host "Arrêter : cd deploy ; docker compose -f docker-compose.local.yml down   (vos données sont conservées)"
Start-Process "http://localhost:8080"
