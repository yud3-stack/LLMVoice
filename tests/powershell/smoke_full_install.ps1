param(
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [Parameter(Mandatory = $true)][string]$WheelPath,
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [Parameter(Mandatory = $true)][string]$FfmpegDirectory
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Normalize-DirectoryPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($resolved)
    if ($resolved -eq $root) {
        return $resolved
    }
    return $resolved.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
}

foreach ($path in @($InstallerPath, $ManifestPath, $WheelPath, $PythonPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required smoke-test file was not found: $path"
    }
}
if (-not (Test-Path -LiteralPath $FfmpegDirectory -PathType Container)) {
    throw "FFmpeg directory was not found: $FfmpegDirectory"
}

$tokens = $null
$parseErrors = $null
$installerAst = [Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $InstallerPath),
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
    throw "Installer parser validation failed."
}
$requiredFunctions = @(
    "Throw-InstallerError",
    "Write-Ok",
    "Write-Warn",
    "Invoke-Native",
    "Get-RuntimeRequirementVersion",
    "Assert-RuntimeProbe",
    "New-IsolatedRuntime",
    "Add-UserPath",
    "Publish-Installation"
)
$definitions = $installerAst.FindAll(
    {
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $requiredFunctions -contains $node.Name
    },
    $true
)
foreach ($functionName in $requiredFunctions) {
    $definition = $definitions |
        Where-Object { $_.Name -eq $functionName } |
        Select-Object -First 1
    if ($null -eq $definition) {
        throw "Installer function '$functionName' was not found."
    }
    . ([scriptblock]::Create($definition.Extent.Text))
}

# Publish-Installation resolves these names dynamically. Keep the smoke test
# isolated from the registry while exercising the real Add-UserPath function.
$script:SmokeUserPath = "C:\Existing\User\Bin"
function Get-PersistedUserPath {
    return $script:SmokeUserPath
}
function Set-PersistedUserPath {
    param([AllowNull()][string]$Value)
    $script:SmokeUserPath = $Value
}

$script:LauncherMoveCount = 0
function Move-Item {
    [CmdletBinding(DefaultParameterSetName = "Path")]
    param(
        [Parameter(ParameterSetName = "Path", Position = 0)]
        [string[]]$Path,
        [Parameter(ParameterSetName = "LiteralPath", Mandatory = $true)]
        [string[]]$LiteralPath,
        [Parameter(Position = 1)][string]$Destination,
        [switch]$Force
    )
    $source = if ($PSCmdlet.ParameterSetName -eq "LiteralPath") {
        [string]$LiteralPath[0]
    }
    else {
        [string]$Path[0]
    }
    if ([IO.Path]::GetFileName($source) -eq "llmvoice.cmd.new") {
        $script:LauncherMoveCount += 1
    }
    Microsoft.PowerShell.Management\Move-Item @PSBoundParameters
}

$tempParent = Normalize-DirectoryPath -Path ([IO.Path]::GetTempPath())
$testRoot = Join-Path $tempParent (
    "LLMVoice-full-install-" + [Guid]::NewGuid().ToString("N")
)
$testRoot = Normalize-DirectoryPath -Path $testRoot
$runningOnWindows =
    [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$pathComparison = if ($runningOnWindows) {
    [StringComparison]::OrdinalIgnoreCase
}
else {
    [StringComparison]::Ordinal
}
if (
    -not [IO.Path]::GetDirectoryName($testRoot).Equals(
        $tempParent,
        $pathComparison
    )
) {
    throw "Refusing to create a smoke root outside the system temp directory."
}

$oldPath = $env:Path
$oldDataDirectory = $env:LLMVOICE_DATA_DIR
$succeeded = $false
try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    $installRoot = Join-Path $testRoot "LLMVoice"
    $runtimeRoot = Join-Path $installRoot "runtime"
    $script:RuntimeVersionsRoot = Join-Path $runtimeRoot "versions"
    $script:BinDirectory = Join-Path $installRoot "bin"
    $script:StatePath = Join-Path $runtimeRoot "install-state.json"
    $script:InstallationCommitted = $false
    $script:NewRuntimeRoot = $null
    $env:LLMVOICE_DATA_DIR = Join-Path $testRoot "user-data"
    $env:Path = "$FfmpegDirectory;$oldPath"

    foreach ($directory in @("voices", "models", "cache")) {
        $userDirectory = Join-Path $installRoot $directory
        New-Item -ItemType Directory -Path $userDirectory -Force | Out-Null
        [IO.File]::WriteAllText(
            (Join-Path $userDirectory "sentinel.txt"),
            $directory,
            [Text.Encoding]::UTF8
        )
    }
    [IO.File]::WriteAllText(
        (Join-Path $installRoot "config.json"),
        '{"sentinel":true}',
        [Text.Encoding]::UTF8
    )

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $runtimeId = "$($manifest.version)-cuda-full-smoke"
    $python = [pscustomobject]@{
        File = (Resolve-Path $PythonPath).Path
        Prefix = @()
    }
    $runtimeResult = New-IsolatedRuntime `
        -Python $python `
        -Manifest $manifest `
        -ProfileName "cuda" `
        -WheelPath (Resolve-Path $WheelPath).Path `
        -RuntimeId $runtimeId
    Write-Output "RUNTIME_VALIDATION=PASSED"

    Publish-Installation `
        -Manifest $manifest `
        -ProfileName "cuda" `
        -RuntimeId $runtimeId `
        -RuntimeResult $runtimeResult

    $launcherPath = Join-Path $script:BinDirectory "llmvoice.cmd"
    if (-not (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
        throw "Committed launcher was not found."
    }
    if (-not (Test-Path -LiteralPath $script:StatePath -PathType Leaf)) {
        throw "Committed install-state was not found."
    }
    if ($script:LauncherMoveCount -ne 1) {
        throw "Launcher was moved $($script:LauncherMoveCount) times."
    }
    if (-not $script:InstallationCommitted) {
        throw "Publish transaction did not mark the installation committed."
    }
    $state = Get-Content -LiteralPath $script:StatePath -Raw | ConvertFrom-Json
    if ([string]$state.version -ne [string]$manifest.version) {
        throw "Committed install-state version is incorrect."
    }
    foreach ($directory in @("voices", "models", "cache")) {
        $sentinel = Join-Path (Join-Path $installRoot $directory) "sentinel.txt"
        if ([IO.File]::ReadAllText($sentinel) -ne $directory) {
            throw "User-data sentinel changed: $directory"
        }
    }
    if (
        [IO.File]::ReadAllText((Join-Path $installRoot "config.json")) -ne
        '{"sentinel":true}'
    ) {
        throw "User config changed during publish."
    }

    $launcherVersion = (& $launcherPath --version | Out-String).Trim()
    $expectedVersion = "LLMVoice $($manifest.version)"
    if ($launcherVersion -ne $expectedVersion) {
        throw "Installed launcher reported '$launcherVersion'; expected '$expectedVersion'."
    }

    Write-Output "PUBLISH_TRANSACTION=PASSED"
    Write-Output "LAUNCHER_SINGLE_MOVE=PASSED"
    Write-Output "INSTALL_STATE_COMMITTED=PASSED"
    Write-Output "INSTALLED_LAUNCHER_VERSION=$($manifest.version)"
    Write-Output "FULL_INSTALL_SMOKE=PASSED"
    $succeeded = $true
}
finally {
    $env:Path = $oldPath
    $env:LLMVOICE_DATA_DIR = $oldDataDirectory
    if (Test-Path -LiteralPath $testRoot -PathType Container) {
        $resolvedRoot = Normalize-DirectoryPath -Path $testRoot
        if (
            -not [IO.Path]::GetDirectoryName($resolvedRoot).Equals(
                $tempParent,
                $pathComparison
            )
        ) {
            throw "Refusing smoke cleanup outside the system temp directory."
        }
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
    }
    if (-not $succeeded) {
        Write-Output "FULL_INSTALL_SMOKE=FAILED"
    }
}
