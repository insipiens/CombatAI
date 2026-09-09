$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$PythonVersion = "3.13.15"
$PythonArchive = "python-3.13.15-embed-amd64.zip"
$PythonUrl = "https://www.python.org/ftp/python/3.13.15/$PythonArchive"
$PythonSha256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
$PygameVersion = "2.5.8"
$PygameArchive = "pygame_ce-2.5.8-cp313-cp313-win_amd64.whl"
$PygameUrl = "https://files.pythonhosted.org/packages/c0/1b/da9186e5b88714c16fdb23bc4ba0bca4a75c21e3a5cf9607765773f68d22/$PygameArchive"
$PygameSha256 = "f495b0eb7a5c54c59da58e964bc7f68073c3f43cf307729fd48309104a04c190"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDirectory = Join-Path $ProjectRoot "runtime"
$PythonExe = Join-Path $RuntimeDirectory "python.exe"
$RuntimeManifest = Join-Path $RuntimeDirectory "dcs_radio_voice_control-runtime.json"

function Test-DcsRadioVoiceControlRuntime {
    if (-not (Test-DcsRadioVoiceControlPythonRuntime)) {
        return $false
    }
    try {
        $Manifest = Get-Content -LiteralPath $RuntimeManifest -Raw | ConvertFrom-Json
        if ($Manifest.pygame_version -ne $PygameVersion -or
            $Manifest.pygame_archive_sha256 -ne $PygameSha256) {
            return $false
        }
        $env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
        & $PythonExe -I -c "import pygame; raise SystemExit(0 if pygame.version.ver == '$PygameVersion' else 1)"
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Test-DcsRadioVoiceControlPythonRuntime {
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

if (Test-DcsRadioVoiceControlRuntime) {
    Write-Host "DCS Radio Voice Control private Python $PythonVersion and SDL controller support are already ready."
    exit 0
}

if (Test-Path -LiteralPath $RuntimeDirectory) {
    if (-not (Test-DcsRadioVoiceControlPythonRuntime)) {
        throw "The runtime directory exists but its Python installation failed validation: $RuntimeDirectory`nMove it aside for inspection before running setup again."
    }
}

$DownloadPath = Join-Path ([System.IO.Path]::GetTempPath()) ("DCSRadioVoiceControl-" + [guid]::NewGuid().ToString("N") + ".zip")
$StagingDirectory = Join-Path $ProjectRoot ("runtime.new." + [guid]::NewGuid().ToString("N"))
$PygameDownloadPath = Join-Path ([System.IO.Path]::GetTempPath()) ("DCSRadioVoiceControl-" + [guid]::NewGuid().ToString("N") + ".whl")
$PygameStagingDirectory = Join-Path $ProjectRoot ("pygame.new." + [guid]::NewGuid().ToString("N"))

try {
    if (-not (Test-Path -LiteralPath $RuntimeDirectory)) {
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
            "site-packages"
            "..\src"
            ".."
        ) | Set-Content -LiteralPath $PathConfiguration -Encoding ASCII

        $Manifest = [ordered]@{
            schema = 2
            python_version = $PythonVersion
            architecture = "amd64"
            source_url = $PythonUrl
            archive_sha256 = $PythonSha256
            configured_at = [DateTime]::UtcNow.ToString("o")
        }
        $Manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StagingDirectory "dcs_radio_voice_control-runtime.json") -Encoding UTF8

        $StagedPython = Join-Path $StagingDirectory "python.exe"
        & $StagedPython -I -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 13, 15) else 1)"
        if ($LASTEXITCODE -ne 0) {
            throw "The extracted Python runtime failed its version self-test."
        }

        Move-Item -LiteralPath $StagingDirectory -Destination $RuntimeDirectory
        Write-Host "DCS Radio Voice Control private Python $PythonVersion is ready in: $RuntimeDirectory"
    }

    Write-Host "Downloading pygame-ce $PygameVersion for SDL HOTAS support..."
    Invoke-WebRequest -Uri $PygameUrl -OutFile $PygameDownloadPath -UseBasicParsing
    $ActualPygameSha256 = (Get-FileHash -LiteralPath $PygameDownloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualPygameSha256 -ne $PygameSha256) {
        throw "pygame-ce archive hash mismatch. Expected $PygameSha256 but received $ActualPygameSha256."
    }
    New-Item -ItemType Directory -Path $PygameStagingDirectory | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($PygameDownloadPath, $PygameStagingDirectory)
    $SitePackages = Join-Path $RuntimeDirectory "site-packages"
    if (Test-Path -LiteralPath $SitePackages) {
        throw "The runtime already contains an unvalidated site-packages directory: $SitePackages"
    }
    Move-Item -LiteralPath $PygameStagingDirectory -Destination $SitePackages

    $PathConfiguration = Join-Path $RuntimeDirectory "python313._pth"
    $PathLines = @(Get-Content -LiteralPath $PathConfiguration)
    if ($PathLines -notcontains "site-packages") {
        $Insertion = [Array]::IndexOf($PathLines, "..\src")
        if ($Insertion -lt 0) { $Insertion = 2 }
        $PathLines = @($PathLines[0..($Insertion - 1)]) + "site-packages" + @($PathLines[$Insertion..($PathLines.Length - 1)])
        $PathLines | Set-Content -LiteralPath $PathConfiguration -Encoding ASCII
    }

    $Manifest = Get-Content -LiteralPath $RuntimeManifest -Raw | ConvertFrom-Json
    $Manifest | Add-Member -NotePropertyName schema -NotePropertyValue 2 -Force
    $Manifest | Add-Member -NotePropertyName pygame_version -NotePropertyValue $PygameVersion -Force
    $Manifest | Add-Member -NotePropertyName pygame_source_url -NotePropertyValue $PygameUrl -Force
    $Manifest | Add-Member -NotePropertyName pygame_archive_sha256 -NotePropertyValue $PygameSha256 -Force
    $Manifest | ConvertTo-Json | Set-Content -LiteralPath $RuntimeManifest -Encoding UTF8

    if (-not (Test-DcsRadioVoiceControlRuntime)) {
        throw "SDL controller support failed its import self-test."
    }
    Write-Host "SDL HOTAS support is ready."
}
finally {
    if (Test-Path -LiteralPath $DownloadPath) {
        Remove-Item -LiteralPath $DownloadPath -Force
    }
    if (Test-Path -LiteralPath $StagingDirectory) {
        Remove-Item -LiteralPath $StagingDirectory -Recurse -Force
    }
    if (Test-Path -LiteralPath $PygameDownloadPath) {
        Remove-Item -LiteralPath $PygameDownloadPath -Force
    }
    if (Test-Path -LiteralPath $PygameStagingDirectory) {
        Remove-Item -LiteralPath $PygameStagingDirectory -Recurse -Force
    }
}
