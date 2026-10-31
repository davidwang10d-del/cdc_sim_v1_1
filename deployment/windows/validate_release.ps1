[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BundlePath,
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [string]$InstallerPath,
    [string]$PythonExe = "python",
    [switch]$RequireSignatures,
    [switch]$SkipExecutableSelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $scriptRoot "release_config.json"
$toolsPath = Join-Path $scriptRoot "release_tools.py"
$bundle = (Resolve-Path -LiteralPath $BundlePath).Path
$manifest = (Resolve-Path -LiteralPath $ManifestPath).Path

function Assert-LastExit([string]$label) {
    if ($LASTEXITCODE -ne 0) {
        throw "$label failed with exit code $LASTEXITCODE."
    }
}

& $PythonExe $toolsPath bundle --path $bundle --config $configPath
Assert-LastExit "Bundle policy validation"
& $PythonExe $toolsPath verify --path $bundle --manifest $manifest
Assert-LastExit "Release-manifest verification"

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$executable = Join-Path $bundle $config.executable_name
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Packaged executable is missing: $executable"
}

if ($RequireSignatures) {
    if ((Get-AuthenticodeSignature -LiteralPath $executable).Status -ne "Valid") {
        throw "The packaged executable does not have a valid Authenticode signature."
    }
    if (-not $InstallerPath) {
        throw "A signed beta validation requires InstallerPath."
    }
}

if (-not $SkipExecutableSelfTest) {
    $temporaryData = Join-Path ([System.IO.Path]::GetTempPath()) ("cdc-sim-release-test-" + [guid]::NewGuid().ToString("N"))
    $previousData = $env:CDC_DATA_DIR
    $previousContent = $env:CDC_CONTENT_DIR
    $previousBrowser = $env:CDC_OPEN_BROWSER
    $previousSelfTestScenario = $env:CDC_SELF_TEST_SCENARIO
    $selfTestScenario = $config.bundled_scenarios | Where-Object { -not $_.StartsWith("_") } | Select-Object -First 1
    if (-not $selfTestScenario) { throw "Release configuration has no playable self-test scenario." }
    try {
        New-Item -ItemType Directory -Path $temporaryData | Out-Null
        $env:CDC_DATA_DIR = $temporaryData
        Remove-Item Env:CDC_CONTENT_DIR -ErrorAction SilentlyContinue
        $env:CDC_OPEN_BROWSER = "false"
        $env:CDC_SELF_TEST_SCENARIO = $selfTestScenario
        & $executable --self-test
        Assert-LastExit "Installed executable self-test"
    }
    finally {
        if ($null -eq $previousData) { Remove-Item Env:CDC_DATA_DIR -ErrorAction SilentlyContinue } else { $env:CDC_DATA_DIR = $previousData }
        if ($null -eq $previousContent) { Remove-Item Env:CDC_CONTENT_DIR -ErrorAction SilentlyContinue } else { $env:CDC_CONTENT_DIR = $previousContent }
        if ($null -eq $previousBrowser) { Remove-Item Env:CDC_OPEN_BROWSER -ErrorAction SilentlyContinue } else { $env:CDC_OPEN_BROWSER = $previousBrowser }
        if ($null -eq $previousSelfTestScenario) { Remove-Item Env:CDC_SELF_TEST_SCENARIO -ErrorAction SilentlyContinue } else { $env:CDC_SELF_TEST_SCENARIO = $previousSelfTestScenario }
        $resolvedTemporary = [System.IO.Path]::GetFullPath($temporaryData)
        $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\') + '\'
        if ($resolvedTemporary.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedTemporary)) {
            Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
        }
    }
}

if ($InstallerPath) {
    $installer = (Resolve-Path -LiteralPath $InstallerPath).Path
    if ([System.IO.Path]::GetExtension($installer) -ne ".exe") {
        throw "InstallerPath must identify an executable installer."
    }
    if ((Get-Item -LiteralPath $installer).Length -lt 1MB) {
        throw "Installer is unexpectedly small."
    }
    if ($RequireSignatures -and (Get-AuthenticodeSignature -LiteralPath $installer).Status -ne "Valid") {
        throw "The beta installer does not have a valid Authenticode signature."
    }
}

Write-Host "Release validation passed: $bundle"
