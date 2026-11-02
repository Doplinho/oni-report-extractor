# Compila OniExtract.dll; -Install instala com backup e -Restore restaura um backup.
param(
    [string]$Managed = "C:\Program Files (x86)\Steam\steamapps\common\OxygenNotIncluded\OxygenNotIncluded_Data\Managed",
    [switch]$Install,
    [string]$Restore
)
$ErrorActionPreference = "Stop"
$dest = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Klei\OxygenNotIncluded\mods\dev\OniExtract"
$files = "OniExtract.dll", "mod.yaml", "mod_info.yaml"

function Assert-GameClosed {
    $game = Get-Process -Name "OxygenNotIncluded" -ErrorAction SilentlyContinue
    if ($game) { throw "Feche OxygenNotIncluded antes de instalar ou restaurar o mod." }
}

function Write-DllHash([string]$Path) {
    $hash = Get-FileHash -LiteralPath $Path -Algorithm SHA256
    Write-Host ("SHA-256 ({0}): {1}" -f $Path, $hash.Hash)
}

if ($Restore) {
    Assert-GameClosed
    if (-not (Test-Path -LiteralPath $Restore -PathType Container)) { throw "Pasta de backup não encontrada: $Restore" }
    New-Item -ItemType Directory -Force $dest | Out-Null
    foreach ($name in $files) {
        $source = Join-Path $Restore $name
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Arquivo ausente no backup: $source" }
        Copy-Item -LiteralPath $source -Destination (Join-Path $dest $name) -Force
    }
    Write-DllHash (Join-Path $dest "OniExtract.dll")
    exit 0
}

if ($Install) { Assert-GameClosed }
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$out = Join-Path $PSScriptRoot "bin"
New-Item -ItemType Directory -Force $out | Out-Null
$refs = "Assembly-CSharp.dll", "Assembly-CSharp-firstpass.dll", "0Harmony.dll", "Newtonsoft.Json.dll",
        "UnityEngine.dll", "UnityEngine.CoreModule.dll", "UnityEngine.UI.dll", "netstandard.dll" |
    Where-Object { Test-Path (Join-Path $Managed $_) } |
    ForEach-Object { "/reference:" + (Join-Path $Managed $_) }

& $csc /nologo /target:library /optimize+ /nostdlib- "/out:$out\OniExtract.dll" @refs (Join-Path $PSScriptRoot "src\*.cs")
if ($LASTEXITCODE -ne 0) { throw "Falha na compilacao" }

if ($Install) {
    $backupRoot = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Klei\OxygenNotIncluded\mods_backup"
    $backup = Join-Path $backupRoot ("OniExtract-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force $backup | Out-Null
    foreach ($name in $files) {
        $installed = Join-Path $dest $name
        if (Test-Path -LiteralPath $installed -PathType Leaf) { Copy-Item -LiteralPath $installed -Destination (Join-Path $backup $name) -Force }
    }
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item -LiteralPath (Join-Path $out "OniExtract.dll"), (Join-Path $PSScriptRoot "mod.yaml"), (Join-Path $PSScriptRoot "mod_info.yaml") -Destination $dest -Force
    Write-Host "Instalado em $dest"
    Write-Host "Backup em $backup"
    Write-DllHash (Join-Path $dest "OniExtract.dll")
}
