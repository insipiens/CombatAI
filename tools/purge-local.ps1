param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectRoot
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$Errors = [System.Collections.Generic.List[string]]::new()

$Targets = [System.Collections.Generic.List[string]]::new()
foreach ($RelativePath in @("runtime", "stt", "tools\piper", "models\piper")) {
    $Targets.Add((Join-Path $Root $RelativePath))
}
foreach ($Pattern in @("runtime.new.*", "pygame.new.*")) {
    Get-ChildItem -LiteralPath $Root -Directory -Filter $Pattern -ErrorAction SilentlyContinue |
        ForEach-Object { $Targets.Add($_.FullName) }
}
if ($env:TEMP) {
    Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter "DCSRadioVoiceControl-STT-*" -ErrorAction SilentlyContinue |
        ForEach-Object { $Targets.Add($_.FullName) }
}

foreach ($Target in $Targets | Select-Object -Unique) {
    try {
        if (Test-Path -LiteralPath $Target) {
            Remove-Item -LiteralPath $Target -Recurse -Force -ErrorAction Stop
        }
        if (Test-Path -LiteralPath $Target) {
            $Errors.Add("Path remains: $Target")
        }
    }
    catch {
        $Errors.Add("Could not remove $Target : $($_.Exception.Message)")
    }
}

try {
    Get-ChildItem -LiteralPath $Root -Directory -Filter "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue |
        Sort-Object { $_.FullName.Length } -Descending |
        Remove-Item -Recurse -Force -ErrorAction Stop
    Get-ChildItem -LiteralPath $Root -File -Filter "*.pyc" -Recurse -Force -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction Stop
    $PytestCache = Join-Path $Root ".pytest_cache"
    if (Test-Path -LiteralPath $PytestCache) {
        Remove-Item -LiteralPath $PytestCache -Recurse -Force -ErrorAction Stop
    }
}
catch {
    $Errors.Add("Could not remove Python cache files: $($_.Exception.Message)")
}

foreach ($Target in $Targets | Select-Object -Unique) {
    if (Test-Path -LiteralPath $Target) {
        $Errors.Add("Cleanup verification failed: $Target")
    }
}

if ($Errors.Count -gt 0) {
    foreach ($Message in $Errors) {
        [Console]::Error.WriteLine("DCS Radio Voice Control uninstall failed: $Message")
    }
    throw "DCS Radio Voice Control uninstall was incomplete. Close processes using these files and run uninstall.bat again."
}

Write-Host "Removed DCS Radio Voice Control runtime, speech components, models, and temporary setup files."
