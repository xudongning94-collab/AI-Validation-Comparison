[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Python312,

    [ValidateSet("candidates", "all")]
    [string]$Profile = "candidates",

    [string]$Environment = ".tools\vision-worker",

    [string]$Wheelhouse,

    [switch]$AllowNetwork,

    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-Executable([string]$Value) {
    $resolved = Resolve-Path -LiteralPath $Value -ErrorAction SilentlyContinue
    if ($resolved -and (Test-Path -LiteralPath $resolved.ProviderPath -PathType Leaf)) {
        return $resolved.ProviderPath
    }
    $command = Get-Command $Value -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Python executable is unavailable: $Value"
}

function Assert-Python312([string]$Executable) {
    $version = & $Executable -c "import json,sys; print(json.dumps(list(sys.version_info[:3])))"
    if ($LASTEXITCODE -ne 0) {
        throw "Python version probe failed."
    }
    $parts = $version | ConvertFrom-Json
    if ($parts.Count -ne 3 -or $parts[0] -ne 3 -or $parts[1] -ne 12) {
        throw "Vision worker requires CPython 3.12; received $($parts -join '.')."
    }
    return $parts -join "."
}

$sourcePython = Resolve-Executable $Python312
$sourceVersion = Assert-Python312 $sourcePython
if (-not $SkipInstall -and -not $Wheelhouse -and -not $AllowNetwork) {
    throw "Dependency installation needs -Wheelhouse or explicit -AllowNetwork."
}
$environmentPath = if ([System.IO.Path]::IsPathRooted($Environment)) {
    [System.IO.Path]::GetFullPath($Environment)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Environment))
}
$workerPython = Join-Path $environmentPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $workerPython -PathType Leaf)) {
    & $sourcePython -m venv $environmentPath
    if ($LASTEXITCODE -ne 0) {
        throw "Vision-worker virtual environment creation failed."
    }
}
$workerVersion = Assert-Python312 $workerPython

if (-not $SkipInstall) {
    $requirements = if ($Profile -eq "all") {
        Join-Path $repoRoot "requirements-vision-worker.txt"
    } else {
        Join-Path $repoRoot "requirements-vision-candidates.txt"
    }
    $pipArguments = @(
        "-m", "pip", "install", "--disable-pip-version-check"
    )
    if ($Wheelhouse) {
        $resolvedWheelhouse = (Resolve-Path -LiteralPath $Wheelhouse).Path
        $pipArguments += @("--no-index", "--find-links", $resolvedWheelhouse)
    }
    $pipArguments += @("-r", $requirements)
    & $workerPython @pipArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Vision-worker dependency installation failed."
    }
}

$env:BID_COMPARE_VISION_PYTHON = $workerPython
$healthJson = & $workerPython (Join-Path $repoRoot "workers\vision_worker_health.py")
if ($LASTEXITCODE -ne 0) {
    throw "Vision-worker health process failed."
}
$health = $healthJson | ConvertFrom-Json
$capabilityReady = if ($Profile -eq "all") {
    $health.capabilities.signature_candidates -and $health.capabilities.ocr
} else {
    $health.capabilities.signature_candidates
}
$healthExit = if ($capabilityReady) { 0 } else { 3 }
Write-Output $healthJson

[pscustomobject]@{
    source_python_version = $sourceVersion
    worker_python_version = $workerVersion
    environment = $environmentPath
    profile = $Profile
    health_exit_code = $healthExit
} | ConvertTo-Json

exit $healthExit
