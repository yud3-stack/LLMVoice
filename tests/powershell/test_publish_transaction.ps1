param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $InstallerPath),
    [ref]$tokens,
    [ref]$errors
)
if ($errors.Count -ne 0) {
    throw "Installer could not be parsed for publish transaction tests."
}
$neededFunctions = @(
    "Throw-InstallerError",
    "Write-Warn",
    "Get-PersistedUserPath",
    "Set-PersistedUserPath",
    "Add-UserPath",
    "Publish-Installation",
    "Remove-SafeRuntimeDirectory"
)
$definitions = $ast.FindAll(
    {
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $neededFunctions -contains $node.Name
    },
    $true
)
foreach ($name in $neededFunctions) {
    $definition = $definitions |
        Where-Object { $_.Name -eq $name } |
        Select-Object -First 1
    if ($null -eq $definition) {
        throw "Required installer function was not found: $name"
    }
    . ([scriptblock]::Create($definition.Extent.Text))
}

function Normalize-DirectoryPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    $rootPath = [IO.Path]::GetPathRoot($fullPath)
    if ($fullPath.Length -eq $rootPath.Length) {
        return $rootPath
    }
    return $fullPath.TrimEnd([char[]]@(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    ))
}

function Assert-True {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Assert-BytesEqual {
    param(
        [Parameter(Mandatory = $true)][byte[]]$Actual,
        [Parameter(Mandatory = $true)][byte[]]$Expected,
        [Parameter(Mandatory = $true)][string]$Message
    )
    if (
        [Convert]::ToBase64String($Actual) -ne
        [Convert]::ToBase64String($Expected)
    ) {
        throw $Message
    }
}

function Get-PersistedUserPath {
    return $script:PersistedUserPath
}

function Set-PersistedUserPath {
    param([AllowNull()][string]$Value)
    $script:PersistedUserPath = $Value
    if ($script:FailPathAfterWrite) {
        $script:FailPathAfterWrite = $false
        throw "Injected User PATH update failure."
    }
}

function Move-Item {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][string]$Destination,
        [switch]$Force
    )
    $script:MoveCount++
    if ([IO.Path]::GetFileName($LiteralPath) -eq "llmvoice.cmd.new") {
        $script:LauncherMoveCount++
    }
    if ($script:MoveFailureAt -eq $script:MoveCount) {
        throw "Injected move failure $($script:MoveCount)."
    }
    Microsoft.PowerShell.Management\Move-Item @PSBoundParameters
}

$tempParent = Normalize-DirectoryPath ([IO.Path]::GetTempPath())
$testRoot = Join-Path $tempParent (
    "LLMVoice-publish-transaction-tests-" + [Guid]::NewGuid().ToString("N")
)
$null = New-Item -ItemType Directory -Path $testRoot
$originalProcessPath = $env:Path
$script:Passed = 0

function Initialize-Case {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [switch]$PreviousInstall,
        [switch]$DanglingLauncher,
        [switch]$PathAlreadyPresent
    )
    $caseRoot = Join-Path $testRoot $Name
    $installRoot = Join-Path $caseRoot "LLMVoice"
    $script:BinDirectory = Join-Path $installRoot "bin"
    $runtimeRoot = Join-Path $installRoot "runtime"
    $script:StatePath = Join-Path $runtimeRoot "install-state.json"
    $script:RuntimeVersionsRoot = Join-Path $runtimeRoot "versions"
    $runtimeId = "0.1.7-cuda-test"
    $script:NewRuntimeRoot = Join-Path $script:RuntimeVersionsRoot $runtimeId
    $venvPath = Join-Path $script:NewRuntimeRoot "venv"
    $null = New-Item -ItemType Directory -Path $venvPath -Force
    $null = New-Item -ItemType Directory -Path $script:BinDirectory -Force
    $null = New-Item `
        -ItemType Directory `
        -Path (Split-Path -Parent $script:StatePath) `
        -Force

    foreach ($directory in @("voices", "models", "cache")) {
        $path = Join-Path $installRoot $directory
        $null = New-Item -ItemType Directory -Path $path
        [IO.File]::WriteAllText(
            (Join-Path $path "sentinel.txt"),
            "$directory-unchanged"
        )
    }
    [IO.File]::WriteAllText(
        (Join-Path $installRoot "config.json"),
        '{"sentinel":true}'
    )

    $oldLauncher = [Text.Encoding]::UTF8.GetBytes("old-launcher-$Name")
    $oldState = [Text.Encoding]::UTF8.GetBytes("old-state-$Name")
    if ($PreviousInstall -or $DanglingLauncher) {
        [IO.File]::WriteAllBytes(
            (Join-Path $script:BinDirectory "llmvoice.cmd"),
            $oldLauncher
        )
    }
    if ($PreviousInstall) {
        [IO.File]::WriteAllBytes($script:StatePath, $oldState)
    }

    $script:PersistedUserPath = if ($PathAlreadyPresent) {
        "C:\Existing;$($script:BinDirectory)"
    }
    else {
        "C:\Existing"
    }
    $env:Path = "C:\ProcessExisting"
    $script:OriginalUserPath = $script:PersistedUserPath
    $script:OriginalProcessPath = $env:Path
    $script:MoveCount = 0
    $script:LauncherMoveCount = 0
    $script:MoveFailureAt = 0
    $script:FailPathAfterWrite = $false
    $script:InstallationCommitted = $false

    return [pscustomobject]@{
        InstallRoot = $installRoot
        RuntimeId = $runtimeId
        RuntimeResult = [pscustomobject]@{
            Root = $script:NewRuntimeRoot
            Venv = $venvPath
        }
        Manifest = [pscustomobject]@{
            version = "0.1.7"
            tag = "v0.1.7"
        }
        LauncherPath = Join-Path $script:BinDirectory "llmvoice.cmd"
        OldLauncher = $oldLauncher
        OldState = $oldState
    }
}

function Invoke-Publish {
    param([Parameter(Mandatory = $true)]$Case)
    Publish-Installation `
        -Manifest $Case.Manifest `
        -ProfileName "cuda" `
        -RuntimeId $Case.RuntimeId `
        -RuntimeResult $Case.RuntimeResult
}

function Assert-UserDataUnchanged {
    param([Parameter(Mandatory = $true)]$Case)
    foreach ($directory in @("voices", "models", "cache")) {
        $content = [IO.File]::ReadAllText(
            (Join-Path (Join-Path $Case.InstallRoot $directory) "sentinel.txt")
        )
        Assert-True `
            -Condition ($content -eq "$directory-unchanged") `
            -Message "$directory user data changed."
    }
    Assert-True `
        -Condition (
            [IO.File]::ReadAllText(
                (Join-Path $Case.InstallRoot "config.json")
            ) -eq '{"sentinel":true}'
        ) `
        -Message "config.json changed."
}

function Assert-NoTransactionFiles {
    param([Parameter(Mandatory = $true)]$Case)
    Assert-True `
        -Condition (-not (Test-Path "$($Case.LauncherPath).new")) `
        -Message "Launcher transaction file was not cleaned."
    Assert-True `
        -Condition (-not (Test-Path "$($script:StatePath).new")) `
        -Message "State transaction file was not cleaned."
}

try {
    $fresh = Initialize-Case -Name "fresh-success"
    Invoke-Publish $fresh
    Assert-True $script:InstallationCommitted "Fresh publish was not committed."
    Assert-True ($script:MoveCount -eq 2) "Fresh publish did not use two moves."
    Assert-True `
        ($script:LauncherMoveCount -eq 1) `
        "Launcher temporary file was moved more than once."
    Assert-NoTransactionFiles $fresh
    Assert-UserDataUnchanged $fresh
    Write-Output "LAUNCHER_SINGLE_MOVE=PASSED"
    $script:Passed++

    $upgrade = Initialize-Case `
        -Name "upgrade-success" `
        -PreviousInstall `
        -PathAlreadyPresent
    Invoke-Publish $upgrade
    Assert-True $script:InstallationCommitted "Upgrade was not committed."
    Assert-True `
        ([IO.File]::ReadAllText($upgrade.LauncherPath) -match "0.1.7") `
        "Upgrade launcher does not target v0.1.7."
    Assert-True `
        ((Get-Content $script:StatePath -Raw | ConvertFrom-Json).version -eq "0.1.7") `
        "Upgrade state version is incorrect."
    Assert-True `
        ($script:PersistedUserPath -eq $script:OriginalUserPath) `
        "Pre-existing PATH entry was changed."
    Assert-NoTransactionFiles $upgrade
    Assert-UserDataUnchanged $upgrade
    $script:Passed++

    $launcherFailure = Initialize-Case -Name "launcher-failure"
    $script:MoveFailureAt = 1
    try {
        Invoke-Publish $launcherFailure
        throw "Launcher move failure did not abort."
    }
    catch {
        Assert-True `
            ($_.Exception.Message -match "Injected move failure") `
            "Launcher failure returned an unexpected error."
    }
    Assert-True `
        (-not (Test-Path $launcherFailure.LauncherPath)) `
        "Fresh launcher remained after failed publish."
    Assert-True `
        (-not (Test-Path $script:StatePath)) `
        "Fresh state remained after failed publish."
    Assert-True `
        (-not $script:InstallationCommitted) `
        "Failed launcher publish was marked committed."
    Assert-NoTransactionFiles $launcherFailure
    Remove-SafeRuntimeDirectory -Path $script:NewRuntimeRoot
    Assert-True `
        (-not (Test-Path $script:NewRuntimeRoot)) `
        "Failed candidate runtime was not cleanable."
    Assert-UserDataUnchanged $launcherFailure
    $script:Passed++

    $stateFailure = Initialize-Case -Name "state-failure" -PreviousInstall
    $script:MoveFailureAt = 2
    try {
        Invoke-Publish $stateFailure
        throw "State move failure did not abort."
    }
    catch {
        Assert-True `
            ($_.Exception.Message -match "Injected move failure") `
            "State failure returned an unexpected error."
    }
    Assert-BytesEqual `
        -Actual ([IO.File]::ReadAllBytes($stateFailure.LauncherPath)) `
        -Expected $stateFailure.OldLauncher `
        -Message "Old launcher was not restored byte-identically."
    Assert-BytesEqual `
        -Actual ([IO.File]::ReadAllBytes($script:StatePath)) `
        -Expected $stateFailure.OldState `
        -Message "Old state was not restored byte-identically."
    Assert-NoTransactionFiles $stateFailure
    Assert-UserDataUnchanged $stateFailure
    $script:Passed++

    $pathFailure = Initialize-Case -Name "path-failure" -PreviousInstall
    $script:FailPathAfterWrite = $true
    try {
        Invoke-Publish $pathFailure
        throw "PATH failure did not abort."
    }
    catch {
        Assert-True `
            ($_.Exception.Message -match "Injected User PATH") `
            "PATH failure returned an unexpected error."
    }
    Assert-BytesEqual `
        -Actual ([IO.File]::ReadAllBytes($pathFailure.LauncherPath)) `
        -Expected $pathFailure.OldLauncher `
        -Message "PATH failure did not restore the launcher."
    Assert-BytesEqual `
        -Actual ([IO.File]::ReadAllBytes($script:StatePath)) `
        -Expected $pathFailure.OldState `
        -Message "PATH failure did not restore install-state."
    Assert-True `
        ($script:PersistedUserPath -eq $script:OriginalUserPath) `
        "Persistent User PATH was not restored."
    Assert-True `
        ($env:Path -eq $script:OriginalProcessPath) `
        "Process PATH was not restored."
    Assert-NoTransactionFiles $pathFailure
    Assert-UserDataUnchanged $pathFailure
    $script:Passed++

    $freshPathFailure = Initialize-Case -Name "fresh-path-failure"
    $script:FailPathAfterWrite = $true
    try {
        Invoke-Publish $freshPathFailure
        throw "Fresh PATH failure did not abort."
    }
    catch {
        Assert-True `
            ($_.Exception.Message -match "Injected User PATH") `
            "Fresh PATH failure returned an unexpected error."
    }
    Assert-True `
        (-not (Test-Path $freshPathFailure.LauncherPath)) `
        "Fresh PATH failure left a launcher."
    Assert-True `
        (-not (Test-Path $script:StatePath)) `
        "Fresh PATH failure left install-state."
    Assert-NoTransactionFiles $freshPathFailure
    Assert-UserDataUnchanged $freshPathFailure
    $script:Passed++

    $repair = Initialize-Case -Name "dangling-repair" -DanglingLauncher
    Invoke-Publish $repair
    Assert-True $script:InstallationCommitted "Dangling launcher repair failed."
    Assert-True `
        ([IO.File]::ReadAllText($repair.LauncherPath) -match "0.1.7") `
        "Dangling launcher was not replaced."
    Assert-True `
        ((Get-Content $script:StatePath -Raw | ConvertFrom-Json).version -eq "0.1.7") `
        "Dangling repair did not create install-state."
    Assert-NoTransactionFiles $repair
    Assert-UserDataUnchanged $repair
    Write-Output "DANGLING_V016_LAUNCHER_REPAIR=PASSED"
    $script:Passed++

    Write-Output "PUBLISH_TRANSACTION=PASSED"
    Write-Output "PUBLISH_TRANSACTION_CASES_PASSED=$script:Passed"
}
finally {
    $env:Path = $originalProcessPath
    $resolved = Normalize-DirectoryPath $testRoot
    $resolvedParent = Normalize-DirectoryPath (
        [IO.Path]::GetDirectoryName($resolved)
    )
    $comparison = if (
        [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
    ) {
        [StringComparison]::OrdinalIgnoreCase
    }
    else {
        [StringComparison]::Ordinal
    }
    if (-not [string]::Equals($resolvedParent, $tempParent, $comparison)) {
        throw "Refusing cleanup outside the system temp directory."
    }
    if ([IO.Directory]::Exists($resolved)) {
        [IO.Directory]::Delete($resolved, $true)
    }
}
