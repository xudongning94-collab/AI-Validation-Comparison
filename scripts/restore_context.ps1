[CmdletBinding()]
param(
    [switch]$Verify
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$statePath = Join-Path $repoRoot 'PROJECT_STATE.json'
$pythonPath = Join-Path $repoRoot '.tools\python313\python.exe'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $pythonPath = $pythonCommand.Source
}

Push-Location $repoRoot
try {
    $actualRoot = (& git rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to resolve the Git repository root.'
    }
    if ([IO.Path]::GetFullPath($actualRoot) -ne [IO.Path]::GetFullPath($repoRoot)) {
        throw "Git root mismatch. Expected '$repoRoot', got '$actualRoot'."
    }

    & $pythonPath 'scripts\check_recovery_state.py'
    if ($LASTEXITCODE -ne 0) {
        throw 'Recovery state validation failed.'
    }

    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Output ''
    Write-Output 'RECOVERY_SUMMARY'
    Write-Output ("history_source={0}" -f $state.recovery.history_source)
    Write-Output ("checkpoint_id={0}" -f $state.recovery.checkpoint_id)
    Write-Output ("historical_origin_thread_id={0}" -f $state.recovery.historical_origin_thread_id)
    Write-Output ("phase={0}:{1}" -f $state.phase.id, $state.phase.status)
    Write-Output ("completed_scope={0}" -f $state.phase.completed_scope)
    Write-Output ("next_gate={0}" -f $state.phase.next_gate)
    Write-Output ("product_complete={0}" -f $state.product.development_complete)
    Write-Output 'next_actions='
    $actionNumber = 1
    foreach ($action in $state.next_actions) {
        Write-Output ("  {0}. {1}" -f $actionNumber, $action)
        $actionNumber += 1
    }
    Write-Output ''
    & git status --short --branch

    if ($Verify) {
        & $pythonPath -m compileall -q src scripts tests workers
        if ($LASTEXITCODE -ne 0) {
            throw 'compileall failed.'
        }

        $pytestOutput = & $pythonPath -m pytest --basetemp .pytest-tmp 2>&1
        $pytestExitCode = $LASTEXITCODE
        $pytestOutput | Write-Output
        if ($pytestExitCode -ne 0) {
            throw 'pytest failed.'
        }

        $summary = $pytestOutput -join "`n"
        $match = [regex]::Match($summary, '(?m)(\d+) passed')
        if (-not $match.Success) {
            throw 'Unable to read the pytest pass count.'
        }
        $actualPassed = [int]$match.Groups[1].Value
        $expectedPassed = [int]$state.verification.expected_passed_tests
        if ($actualPassed -ne $expectedPassed) {
            throw "Test-count mismatch. PROJECT_STATE expects $expectedPassed, pytest reported $actualPassed."
        }

        & git diff --check
        if ($LASTEXITCODE -ne 0) {
            throw 'git diff --check failed.'
        }
        & git diff --cached --check
        if ($LASTEXITCODE -ne 0) {
            throw 'git diff --cached --check failed.'
        }
        Write-Output 'RECOVERY_VERIFICATION_OK'
    }
}
finally {
    Pop-Location
}
