$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Dashboard ONI.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '-m oni_dashboard --open'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Save()
