param(
    [Parameter(Mandatory)][string]$EngineDirectory,
    [Parameter(Mandatory)][string]$DriverDirectory
)
$ErrorActionPreference = 'Stop'
# App-local deployment: Windows 10/11 already provides the system UCRT API set.
$runtime = Join-Path $EngineDirectory '_internal'
foreach ($name in @('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    $source = Join-Path $runtime $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing DD installer runtime: $name" }
    $signature = Get-AuthenticodeSignature -LiteralPath $source
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw "Untrusted Microsoft runtime: $name"
    }
    $bytes = [IO.File]::ReadAllBytes($source)
    if ($bytes.Length -lt 64) { throw "Invalid runtime PE: $name" }
    $offset = [BitConverter]::ToInt32($bytes, 60)
    if ($offset -lt 0 -or $offset -gt $bytes.Length - 6 -or
        [BitConverter]::ToUInt32($bytes, $offset) -ne 0x4550 -or
        [BitConverter]::ToUInt16($bytes, $offset + 4) -ne 0x8664) { throw "Runtime must be AMD64 PE: $name" }
    $target = Join-Path $DriverDirectory $name
    Copy-Item -LiteralPath $source -Destination $target
    if ((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $target).Hash) {
        throw "Runtime copy verification failed: $name"
    }
}
