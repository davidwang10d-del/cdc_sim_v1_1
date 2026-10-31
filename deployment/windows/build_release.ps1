[CmdletBinding()]
param(
    [ValidateSet("qa", "beta")]
    [string]$Channel = "qa",
    [string]$PythonExe,
    [string]$CertificateThumbprint,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$InnoCompiler,
    [switch]$DistributionReviewApproved,
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "../.."))
$configPath = Join-Path $scriptRoot "release_config.json"
$toolsPath = Join-Path $scriptRoot "release_tools.py"
$licenseCollectorPath = Join-Path $scriptRoot "collect_runtime_licenses.py"
$specPath = Join-Path $scriptRoot "cdc_sim_beta.spec"
$runtimeRequirements = Join-Path $scriptRoot "runtime-requirements.txt"
$buildRequirements = Join-Path $scriptRoot "build-requirements.txt"
$eulaSource = Join-Path $sourceRoot "EULA.txt"
$buildInfoSource = Join-Path $sourceRoot "build_info.json"
$buildStamp = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")
$workRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot ".build/$buildStamp"))
$artifactsRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "artifacts"))

function Assert-LastExit([string]$label) {
    if ($LASTEXITCODE -ne 0) {
        throw "$label failed with exit code $LASTEXITCODE."
    }
}

function Assert-ChildPath([string]$path, [string]$parent, [string]$label) {
    $full = [System.IO.Path]::GetFullPath($path)
    $parentPrefix = [System.IO.Path]::GetFullPath($parent).TrimEnd('\') + '\'
    if (-not $full.StartsWith($parentPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$label must remain under $parent"
    }
    return $full
}

function Write-Utf8Json([string]$path, [object]$value) {
    $json = $value | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($path, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}

if ($Channel -eq "beta") {
    if (-not $DistributionReviewApproved) {
        throw "Beta artifacts require -DistributionReviewApproved after ownership, legacy-license, dependency, content, and attribution review is recorded."
    }
    if (-not $CertificateThumbprint) {
        throw "Beta artifacts require an Authenticode certificate thumbprint. Use Channel qa for an unsigned engineering build."
    }
    $workingChanges = & git -C $sourceRoot status --porcelain --untracked-files=all
    Assert-LastExit "Git status check"
    if ($workingChanges) {
        throw "Beta artifacts must be built from a clean, reviewed working tree."
    }
}

if ($PythonExe) {
    $bootstrapPython = (Get-Command $PythonExe -ErrorAction Stop).Source
    & $bootstrapPython -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version"
} else {
    $py = (Get-Command py.exe -ErrorAction Stop).Source
    & $py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version"
}
Assert-LastExit "Python 3.12 prerequisite check"

$workRoot = Assert-ChildPath $workRoot (Join-Path $scriptRoot ".build") "Build work directory"
New-Item -ItemType Directory -Path $workRoot | Out-Null
$venv = Join-Path $workRoot "venv"
if ($PythonExe) {
    & $bootstrapPython -m venv $venv
} else {
    & $py -3.12 -m venv $venv
}
Assert-LastExit "Clean build environment creation"
$python = Join-Path $venv "Scripts/python.exe"

& $python -m pip install --disable-pip-version-check -r $runtimeRequirements -r $buildRequirements
Assert-LastExit "Pinned application and build dependency installation"
& $python -m pip check
Assert-LastExit "Dependency consistency check"

$sourceArgs = @($toolsPath, "source", "--root", $sourceRoot, "--config", $configPath)
if ($Channel -eq "beta") { $sourceArgs += "--beta" }
& $python @sourceArgs
Assert-LastExit "Release source policy"

if (-not $SkipTests) {
    & $python -m unittest discover -s (Join-Path $sourceRoot "tests") -p "test*.py"
    Assert-LastExit "Application regression tests"
    & $python -m unittest discover -s (Join-Path $scriptRoot "tests") -p "test*.py"
    Assert-LastExit "Windows release tests"
}

$sourceRevision = (& git -C $sourceRoot rev-parse --verify HEAD 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $sourceRevision) {
    if ($Channel -eq "beta") { throw "A beta build requires an identifiable Git revision." }
    $sourceRevision = "unknown"
}
$sourceRevision = $sourceRevision.Trim()
$baseInfo = Get-Content -LiteralPath $buildInfoSource -Raw | ConvertFrom-Json
$baseInfo.channel = if ($Channel -eq "beta") { "private-beta" } else { "qa" }
$baseInfo.build_id = if ($sourceRevision -eq "unknown") { "qa-$buildStamp" } else { "$Channel-$($sourceRevision.Substring(0, 12))" }
$baseInfo.source_revision = $sourceRevision
$baseInfo.built_at_utc = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$generated = Join-Path $workRoot "generated"
New-Item -ItemType Directory -Path $generated | Out-Null
$buildInfo = Join-Path $generated "build_info.json"
Write-Utf8Json $buildInfo $baseInfo

$semver = [regex]::Match($baseInfo.version, '^(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]*?(\d+))?')
if (-not $semver.Success) { throw "Product version is not valid semantic version text." }
$revision = if ($semver.Groups[4].Success) { [int]$semver.Groups[4].Value } else { 0 }
$windowsVersion = "{0}.{1}.{2}.{3}" -f $semver.Groups[1].Value, $semver.Groups[2].Value, $semver.Groups[3].Value, $revision
$versionInfo = Join-Path $generated "windows-version-info.txt"
$versionTemplate = @'
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({FILE_TUPLE}), prodvers=({FILE_TUPLE}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{PUBLISHER}'),
      StringStruct('FileDescription', 'CDC Sim private beta'),
      StringStruct('FileVersion', '{PRODUCT_VERSION}'),
      StringStruct('InternalName', 'CDC Sim'),
      StringStruct('OriginalFilename', 'CDC Sim.exe'),
      StringStruct('ProductName', 'CDC Sim'),
      StringStruct('ProductVersion', '{PRODUCT_VERSION}')
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'@
$fileTuple = $windowsVersion.Replace('.', ', ')
$versionText = $versionTemplate.Replace('{FILE_TUPLE}', $fileTuple).Replace('{PUBLISHER}', [string]$baseInfo.product).Replace('{PRODUCT_VERSION}', [string]$baseInfo.version)
[System.IO.File]::WriteAllText($versionInfo, $versionText, [System.Text.UTF8Encoding]::new($false))

$dependencyInventory = Join-Path $generated "dependency-inventory.json"
$dependencyInventoryError = Join-Path $generated "dependency-inventory.stderr.txt"
$inspectProcess = Start-Process -FilePath $python -ArgumentList @(
    "-X", "utf8", "-m", "pip", "inspect", "--local"
) -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput $dependencyInventory -RedirectStandardError $dependencyInventoryError
if ($inspectProcess.ExitCode -ne 0) {
    $inspectError = if (Test-Path -LiteralPath $dependencyInventoryError) {
        Get-Content -LiteralPath $dependencyInventoryError -Raw
    } else {
        "No diagnostic output was produced."
    }
    throw "Dependency inventory generation failed with exit code $($inspectProcess.ExitCode): $inspectError"
}

$dist = Join-Path $workRoot "dist"
$pyiWork = Join-Path $workRoot "pyinstaller"
$env:CDC_BUILD_SOURCE_ROOT = $sourceRoot
$env:CDC_BUILD_RELEASE_CONFIG = $configPath
$env:CDC_BUILD_INFO_FILE = $buildInfo
$env:CDC_BUILD_VERSION_INFO = $versionInfo
& $python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $pyiWork $specPath
Assert-LastExit "PyInstaller application build"

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$builtBundle = Join-Path $dist $config.bundle_name
if (-not (Test-Path -LiteralPath $builtBundle -PathType Container)) {
    throw "PyInstaller did not create the configured application bundle."
}

$stageName = "{0}-{1}-windows-x64-{2}" -f ($config.product_name -replace '\s+', '-'), $baseInfo.version, $buildStamp
$stage = Assert-ChildPath (Join-Path $artifactsRoot $stageName) $artifactsRoot "Artifact stage"
if (Test-Path -LiteralPath $stage) { throw "Artifact stage already exists: $stage" }
New-Item -ItemType Directory -Path $stage | Out-Null
$stageBundle = Join-Path $stage "bundle"
Copy-Item -LiteralPath $builtBundle -Destination $stageBundle -Recurse
$runtimeNoticePath = Join-Path $stageBundle "_internal/third-party-licenses"
& $python $licenseCollectorPath --requirements (Join-Path $scriptRoot "runtime-requirements.txt") --output $runtimeNoticePath
Assert-LastExit "Runtime third-party notice collection"
Copy-Item -LiteralPath $dependencyInventory -Destination (Join-Path $stage "dependency-inventory.json")
Copy-Item -LiteralPath (Join-Path $scriptRoot "BETA-TESTER-README.txt") -Destination $stage
Copy-Item -LiteralPath (Join-Path $scriptRoot "private-beta-config.example.json") -Destination $stage
Copy-Item -LiteralPath $eulaSource -Destination $stage

$executable = Join-Path $stageBundle $config.executable_name
$signatureRequired = $Channel -eq "beta"
if ($CertificateThumbprint) {
    $signTool = (Get-Command signtool.exe -ErrorAction Stop).Source
    & $signTool sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $executable
    Assert-LastExit "Application signing"
    if ((Get-AuthenticodeSignature -LiteralPath $executable).Status -ne "Valid") {
        throw "Application signature verification failed."
    }
}

$manifest = Join-Path $stage "release-manifest.json"
& $python $toolsPath manifest --path $stageBundle --config $configPath --build-info $buildInfo --output $manifest
Assert-LastExit "Release manifest generation"

$installer = $null
if (-not $SkipInstaller) {
    if (-not $InnoCompiler) {
        $candidates = @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6/ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6/ISCC.exe")
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
        if ($candidates) { $InnoCompiler = $candidates[0] }
    }
    if (-not $InnoCompiler -or -not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)) {
        if ($Channel -eq "beta") { throw "Inno Setup 6 is required for a beta installer." }
        Write-Warning "Inno Setup 6 was not found; the QA bundle remains available without an installer."
    } else {
        $installerOutput = Join-Path $stage "installer"
        New-Item -ItemType Directory -Path $installerOutput | Out-Null
        & $InnoCompiler "/DAppVersion=$($baseInfo.version)" "/DWindowsVersion=$windowsVersion" "/DAppPublisher=$($config.publisher)" "/DSourceDir=$stage" "/DOutputDir=$installerOutput" "/DLicensePath=$eulaSource" (Join-Path $scriptRoot "CDC-Sim-Beta.iss")
        Assert-LastExit "Installer compilation"
        $installer = Get-ChildItem -LiteralPath $installerOutput -Filter "*.exe" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if (-not $installer) { throw "Inno Setup completed without producing an installer." }
        $installer = $installer.FullName
        if ($CertificateThumbprint) {
            & $signTool sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $installer
            Assert-LastExit "Installer signing"
        }
    }
}

$validationArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $scriptRoot "validate_release.ps1"),
    "-BundlePath", $stageBundle, "-ManifestPath", $manifest, "-PythonExe", $python
)
if ($installer) { $validationArgs += @("-InstallerPath", $installer) }
if ($signatureRequired) { $validationArgs += "-RequireSignatures" }
& powershell.exe @validationArgs
Assert-LastExit "Final installed-artifact validation"

$summary = [ordered]@{
    schema_version = 1
    product = $config.product_name
    version = $baseInfo.version
    channel = $baseInfo.channel
    build_id = $baseInfo.build_id
    source_revision = $sourceRevision
    bundle_manifest_sha256 = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant()
    installer = if ($installer) { Split-Path -Leaf $installer } else { $null }
    installer_sha256 = if ($installer) { (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
    eula_sha256 = (Get-FileHash -LiteralPath $eulaSource -Algorithm SHA256).Hash.ToLowerInvariant()
    signed = [bool]$CertificateThumbprint
}
Write-Utf8Json (Join-Path $stage "artifact-summary.json") $summary

Write-Host ""
Write-Host "CDC Sim release artifact passed validation."
Write-Host "Stage: $stage"
if ($installer) { Write-Host "Tester download: $installer" }
