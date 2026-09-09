param(
    [ValidateSet("base.en", "small.en", "medium.en")]
    [string]$Model = "base.en",
    [ValidateSet("auto", "cpu", "cuda12")]
    [string]$Compute = "auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$WhisperVersion = "b4938"
$Archives = @{
    "cpu" = @{
        Name = "whisper-bin-x64.zip"
        Sha256 = "c2a4b60edb11f7e11a9191ffb50929535527d4d91c9903dbe3e554583bbbc63d"
    }
    "cuda12" = @{
        Name = "whisper-cublas-12.4.0-bin-x64.zip"
        Sha256 = "c1b17166e1e31a91cc8e9c1f910d3785e3ce757bb2958bf9dce13fdb4880005f"
    }
}
$Models = @{
    "base.en" = @{
        Name = "ggml-base.en.bin"
        Sha256 = "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"
        Size = "142 MiB"
    }
    "small.en" = @{
        Name = "ggml-small.en.bin"
        Sha256 = "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"
        Size = "466 MiB"
    }
    "medium.en" = @{
        Name = "ggml-medium.en.bin"
        Sha256 = "cc37e93478338ec7700281a7ac30a10128929eb8f427dda2e865faa8f6da4356"
        Size = "1.5 GiB"
    }
}
$Selected = $Models[$Model]
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SttDirectory = Join-Path $ProjectRoot "stt"
$ManifestPath = Join-Path $SttDirectory "dcs_radio_voice_control-stt.json"
$WorkerExe = Join-Path $SttDirectory "dcs_radio_voice_control-whisper.exe"
$ModelPath = Join-Path $SttDirectory $Selected.Name
$ModelUrl = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$($Selected.Name)?download=true"

if ($Compute -eq "auto") {
    $Compute = "cpu"
    if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
        try {
            $ExistingManifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
            if ($ExistingManifest.compute -eq "cuda12") { $Compute = "cuda12" }
        }
        catch { $Compute = "cpu" }
    }
}
$SelectedArchive = $Archives[$Compute]
$WhisperArchive = $SelectedArchive.Name
$WhisperUrl = "https://github.com/ggml-org/whisper.cpp/releases/download/$WhisperVersion/$WhisperArchive"
$WhisperSha256 = $SelectedArchive.Sha256

function Test-Worker([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $Path
    $StartInfo.Arguments = "--version"
    $StartInfo.UseShellExecute = $false
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $StartInfo.CreateNoWindow = $true
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $StartInfo
    try {
        if (-not $Process.Start()) { return $false }
        $StandardOutput = $Process.StandardOutput.ReadToEndAsync()
        $StandardError = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        $null = $StandardOutput.Result
        $null = $StandardError.Result
        return $Process.ExitCode -eq 0
    }
    catch { return $false }
    finally { $Process.Dispose() }
}

$TemporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("DCSRadioVoiceControl-STT-" + [guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Force -Path $SttDirectory, $TemporaryRoot | Out-Null

    $InstalledCompute = $null
    if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
        try { $InstalledCompute = (Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json).compute }
        catch { $InstalledCompute = $null }
    }
    $NeedsWorker = -not (Test-Worker $WorkerExe) -or $InstalledCompute -ne $Compute
    if ($NeedsWorker) {
        $ExistingServer = Join-Path $SttDirectory "whisper-server.exe"
        if ($Compute -eq "cpu" -and $null -eq $InstalledCompute -and
            (Test-Path -LiteralPath $ExistingServer -PathType Leaf)) {
            Copy-Item -LiteralPath $ExistingServer -Destination $WorkerExe
        }
        else {
            $ArchivePath = Join-Path $TemporaryRoot $WhisperArchive
            $ExpandedPath = Join-Path $TemporaryRoot "expanded"
            Write-Host "Downloading whisper.cpp $WhisperVersion native worker..."
            Invoke-WebRequest -Uri $WhisperUrl -OutFile $ArchivePath -UseBasicParsing
            $Actual = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($Actual -ne $WhisperSha256) {
                throw "whisper.cpp archive hash mismatch. Expected $WhisperSha256 but received $Actual."
            }
            Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExpandedPath
            $ReleasePath = Join-Path $ExpandedPath "Release"
            if (-not (Test-Path -LiteralPath (Join-Path $ReleasePath "whisper-server.exe"))) {
                throw "The verified whisper.cpp archive did not contain whisper-server.exe."
            }
            Copy-Item -Path (Join-Path $ReleasePath "*") -Destination $SttDirectory -Force
            Copy-Item -LiteralPath (Join-Path $ReleasePath "whisper-server.exe") -Destination $WorkerExe -Force
        }
    }
    if (-not (Test-Worker $WorkerExe)) {
        throw "The DCS Radio Voice Control Whisper worker failed its self-test."
    }

    $NeedsModel = -not (Test-Path -LiteralPath $ModelPath -PathType Leaf)
    if (-not $NeedsModel) {
        $NeedsModel = (Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Selected.Sha256
    }
    if ($NeedsModel) {
        $StagedModel = Join-Path $TemporaryRoot $Selected.Name
        Write-Host "Downloading Whisper $Model model ($($Selected.Size))..."
        Invoke-WebRequest -Uri $ModelUrl -OutFile $StagedModel -UseBasicParsing
        $Actual = (Get-FileHash -LiteralPath $StagedModel -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Actual -ne $Selected.Sha256) {
            throw "Whisper model hash mismatch. Expected $($Selected.Sha256) but received $Actual."
        }
        Move-Item -LiteralPath $StagedModel -Destination $ModelPath -Force
    }

    $InstalledModels = @{}
    foreach ($Entry in $Models.GetEnumerator()) {
        $Candidate = Join-Path $SttDirectory $Entry.Value.Name
        if ((Test-Path -LiteralPath $Candidate -PathType Leaf) -and
            (Get-FileHash -LiteralPath $Candidate -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Entry.Value.Sha256) {
            $InstalledModels[$Entry.Key] = $Entry.Value.Sha256
        }
    }
    [ordered]@{
        schema = 2
        whisper_version = $WhisperVersion
        whisper_archive_sha256 = $WhisperSha256
        worker = "dcs_radio_voice_control-whisper.exe"
        compute = $Compute
        models = $InstalledModels
        configured_at = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

    Write-Host "DCS Radio Voice Control local speech recognition is ready."
    Write-Host "Worker: $WorkerExe"
    Write-Host "Model:  $ModelPath"
    Write-Host "Compute: $Compute"
}
finally {
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
}
