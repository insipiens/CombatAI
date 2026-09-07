$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PiperDir = Join-Path $Root 'tools\piper'
$ModelDir = Join-Path $Root 'models\piper'
$Zip = Join-Path $PiperDir 'piper_windows_amd64.zip'
$PiperExe = Join-Path $PiperDir 'piper\piper.exe'
$Model = Join-Path $ModelDir 'en_GB-alan-medium.onnx'
$Config = "$Model.json"

$PiperUrl = 'https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip'
$ModelUrl = 'https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alan/medium/en_GB-alan-medium.onnx?download=true'
$ConfigUrl = 'https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json?download=true'
$ModelMd5 = '8f6b35eeb8ef6269021c6cb6d2414c9b'
$ConfigMd5 = '8927af81e8b16650fb7c9593464daa6e'

New-Item -ItemType Directory -Force -Path $PiperDir, $ModelDir | Out-Null

if (-not (Test-Path $PiperExe)) {
    Write-Host 'Downloading the pinned standalone Piper Windows build...'
    Invoke-WebRequest -Uri $PiperUrl -OutFile $Zip
    Expand-Archive -LiteralPath $Zip -DestinationPath $PiperDir -Force
    Remove-Item $Zip -Force
}

function Get-Md5([string]$Path) {
    return (Get-FileHash -Algorithm MD5 -LiteralPath $Path).Hash.ToLowerInvariant()
}

if (-not (Test-Path $Model) -or (Get-Md5 $Model) -ne $ModelMd5) {
    Write-Host 'Downloading the en_GB-alan-medium Piper voice...'
    Invoke-WebRequest -Uri $ModelUrl -OutFile $Model
}
if ((Get-Md5 $Model) -ne $ModelMd5) {
    throw 'Piper voice model failed its published MD5 check.'
}

if (-not (Test-Path $Config) -or (Get-Md5 $Config) -ne $ConfigMd5) {
    Invoke-WebRequest -Uri $ConfigUrl -OutFile $Config
}
if ((Get-Md5 $Config) -ne $ConfigMd5) {
    throw 'Piper voice configuration failed its published MD5 check.'
}

if (-not (Test-Path $PiperExe)) {
    throw "Piper executable was not found after extraction: $PiperExe"
}

Write-Host 'Piper TTS is ready.'
Write-Host "Executable: $PiperExe"
Write-Host "Voice:      $Model"
