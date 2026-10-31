# Compila OniExtract.dll com o csc do .NET Framework e instala na pasta mods\dev do jogo.
param(
    [string]$Managed = "C:\Program Files (x86)\Steam\steamapps\common\OxygenNotIncluded\OxygenNotIncluded_Data\Managed",
    [switch]$Install
)
$ErrorActionPreference = "Stop"
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
    $dest = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Klei\OxygenNotIncluded\mods\dev\OniExtract"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item "$out\OniExtract.dll", (Join-Path $PSScriptRoot "mod.yaml"), (Join-Path $PSScriptRoot "mod_info.yaml") $dest -Force
    Write-Host "Instalado em $dest"
}
