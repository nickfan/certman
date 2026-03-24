[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CertmanArgs
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$Image = if ($env:CERTMAN_IMAGE) { $env:CERTMAN_IMAGE } else { "nickfan/certman:edge" }
$DataDirHost = if ($env:CERTMAN_DATA_DIR_HOST) { $env:CERTMAN_DATA_DIR_HOST } else { Join-Path $ProjectRoot "data" }

docker run --rm `
  -v "${DataDirHost}:/data" `
  -e CERTMAN_DATA_DIR=/data `
  $Image `
  @CertmanArgs