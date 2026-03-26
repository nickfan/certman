[CmdletBinding()]
param(
    [string]$Tag = "edge",
    [string]$DockerHubImage = "nickfan/certman",
    [string]$GhcrImage = "ghcr.io/nickfan/certman",
    [switch]$Push,
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$dockerHubRef = "${DockerHubImage}:${Tag}"
$ghcrRef = "${GhcrImage}:${Tag}"

Write-Host "[certman-image] project root: $ProjectRoot"
Write-Host "[certman-image] docker hub tag: $dockerHubRef"
Write-Host "[certman-image] ghcr tag: $ghcrRef"

if (-not $SkipBuild) {
    Write-Host "[certman-image] building image..."
    docker build -t $dockerHubRef -t $ghcrRef $ProjectRoot
}

if ($Push) {
    Write-Host "[certman-image] pushing $dockerHubRef"
    docker push $dockerHubRef

    Write-Host "[certman-image] pushing $ghcrRef"
    docker push $ghcrRef

    Write-Host "[certman-image] push completed"
} else {
    Write-Host "[certman-image] build completed (push skipped). Use -Push to publish."
}
