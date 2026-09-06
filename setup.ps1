$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PythonVersion = "3.13.15"
$PythonArchive = "python-3.13.15-embed-amd64.zip"
$PythonUrl = "https://www.python.org/ftp/python/3.13.15/$PythonArchive"
$PythonSha256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDirectory = Join-Path $ProjectRoot "runtime"
$PythonExe = Join-Path $RuntimeDirectory "python.exe"
$RuntimeManifest = Join-Path $RuntimeDirectory "combatai-runtime.json"

function Test-CombatAiRuntime {
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $RuntimeManifest -PathType Leaf)) {
        return $false
    }
    try {
        $Manifest = Get-Content -LiteralPath $RuntimeManifest -Raw | ConvertFrom-Json
        if ($Manifest.python_version -ne $PythonVersion -or
            $Manifest.archive_sha256 -ne $PythonSha256) {
            return $false
        }
        & $PythonExe -I -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 13, 15) else 1)"
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

if (Test-CombatAiRuntime) {
    Write-Host "CombatAI private Python $PythonVersion is already ready."
    exit 0
}

if (Test-Path -LiteralPath $RuntimeDirectory) {
    throw "The runtime directory exists but failed validation: $RuntimeDirectory`nMove it aside for inspection before running setup again."
}

$DownloadPath = Join-Path ([System.IO.Path]::GetTempPath()) ("CombatAI-" + [guid]::NewGuid().ToString("N") + ".zip")
$StagingDirectory = Join-Path $ProjectRoot ("runtime.new." + [guid]::NewGuid().ToString("N"))

try {
    Write-Host "Downloading official CPython $PythonVersion embedded runtime..."
    Invoke-WebRequest -Uri $PythonUrl -OutFile $DownloadPath -UseBasicParsing

    $ActualSha256 = (Get-FileHash -LiteralPath $DownloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $PythonSha256) {
        throw "Python archive hash mismatch. Expected $PythonSha256 but received $ActualSha256."
    }

    New-Item -ItemType Directory -Path $StagingDirectory | Out-Null
    Expand-Archive -LiteralPath $DownloadPath -DestinationPath $StagingDirectory

    $PathConfiguration = Join-Path $StagingDirectory "python313._pth"
    if (-not (Test-Path -LiteralPath $PathConfiguration -PathType Leaf)) {
        throw "The verified Python archive did not contain python313._pth."
    }

    @(
        "python313.zip"
        "."
        "..\src"
        ".."
    ) | Set-Content -LiteralPath $PathConfiguration -Encoding ASCII

    $Manifest = [ordered]@{
        schema = 1
        python_version = $PythonVersion
        architecture = "amd64"
        source_url = $PythonUrl
        archive_sha256 = $PythonSha256
        configured_at = [DateTime]::UtcNow.ToString("o")
    }
    $Manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StagingDirectory "combatai-runtime.json") -Encoding UTF8

    $StagedPython = Join-Path $StagingDirectory "python.exe"
    & $StagedPython -I -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 13, 15) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "The extracted Python runtime failed its version self-test."
    }

    Move-Item -LiteralPath $StagingDirectory -Destination $RuntimeDirectory
    Write-Host "CombatAI private Python $PythonVersion is ready in: $RuntimeDirectory"
}
finally {
    if (Test-Path -LiteralPath $DownloadPath) {
        Remove-Item -LiteralPath $DownloadPath -Force
    }
    if (Test-Path -LiteralPath $StagingDirectory) {
        Remove-Item -LiteralPath $StagingDirectory -Recurse -Force
    }
}
