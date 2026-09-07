$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$WhisperVersion = "b4938"
$WhisperArchive = "whisper-bin-x64.zip"
$WhisperUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/$WhisperVersion/$WhisperArchive"
$WhisperSha256 = "c2a4b60edb11f7e11a9191ffb50929535527d4d91c9903dbe3e554583bbbc63d"
$ModelName = "ggml-base.en.bin"
$ModelUrl = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${ModelName}?download=true"
$ModelSha256 = "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SttDirectory = Join-Path $ProjectRoot "stt"
$ManifestPath = Join-Path $SttDirectory "combatai-stt.json"
$WhisperExe = Join-Path $SttDirectory "whisper-cli.exe"
$ModelPath = Join-Path $SttDirectory $ModelName

function Test-CombatAiStt {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $WhisperExe -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
        return $false
    }
    try {
        $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
        if ($Manifest.whisper_version -ne $WhisperVersion -or
            $Manifest.whisper_archive_sha256 -ne $WhisperSha256 -or
            $Manifest.model_name -ne $ModelName -or
            $Manifest.model_sha256 -ne $ModelSha256) {
            return $false
        }
        if ((Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ModelSha256) {
            return $false
        }
        & $WhisperExe --help *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

if (Test-CombatAiStt) {
    Write-Host "CombatAI local speech recognition is already ready."
    exit 0
}

if (Test-Path -LiteralPath $SttDirectory) {
    throw "The stt directory exists but failed validation: $SttDirectory`nMove it aside for inspection before running setup again."
}

$TemporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("CombatAI-STT-" + [guid]::NewGuid().ToString("N"))
$ArchivePath = Join-Path $TemporaryRoot $WhisperArchive
$ExpandedPath = Join-Path $TemporaryRoot "expanded"
$StagingDirectory = Join-Path $ProjectRoot ("stt.new." + [guid]::NewGuid().ToString("N"))

try {
    New-Item -ItemType Directory -Path $TemporaryRoot | Out-Null
    Write-Host "Downloading whisper.cpp $WhisperVersion for Windows x64..."
    Invoke-WebRequest -Uri $WhisperUrl -OutFile $ArchivePath -UseBasicParsing
    $ActualWhisperSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualWhisperSha256 -ne $WhisperSha256) {
        throw "whisper.cpp archive hash mismatch. Expected $WhisperSha256 but received $ActualWhisperSha256."
    }

    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExpandedPath
    $ReleasePath = Join-Path $ExpandedPath "Release"
    if (-not (Test-Path -LiteralPath (Join-Path $ReleasePath "whisper-cli.exe") -PathType Leaf)) {
        throw "The verified whisper.cpp archive did not contain whisper-cli.exe."
    }
    Move-Item -LiteralPath $ReleasePath -Destination $StagingDirectory

    Write-Host "Downloading the English base model (approximately 142 MiB)..."
    $StagedModel = Join-Path $StagingDirectory $ModelName
    Invoke-WebRequest -Uri $ModelUrl -OutFile $StagedModel -UseBasicParsing
    $ActualModelSha256 = (Get-FileHash -LiteralPath $StagedModel -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualModelSha256 -ne $ModelSha256) {
        throw "Whisper model hash mismatch. Expected $ModelSha256 but received $ActualModelSha256."
    }

    $Manifest = [ordered]@{
        schema = 1
        whisper_version = $WhisperVersion
        whisper_archive_sha256 = $WhisperSha256
        model_name = $ModelName
        model_sha256 = $ModelSha256
        configured_at = [DateTime]::UtcNow.ToString("o")
    }
    $Manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StagingDirectory "combatai-stt.json") -Encoding UTF8

    $StagedExe = Join-Path $StagingDirectory "whisper-cli.exe"
    & $StagedExe --help *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "The extracted whisper.cpp executable failed its self-test."
    }

    Move-Item -LiteralPath $StagingDirectory -Destination $SttDirectory
    Write-Host "CombatAI local speech recognition is ready."
}
finally {
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $StagingDirectory) {
        Remove-Item -LiteralPath $StagingDirectory -Recurse -Force
    }
}
