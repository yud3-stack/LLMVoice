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
    throw "Installer could not be parsed for native invocation tests."
}
$neededFunctions = @("Throw-InstallerError", "Invoke-Native")
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

function Assert-Equal {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        $Actual,
        $Expected
    )
    if ($Actual -ne $Expected) {
        throw "$Name failed. Expected '$Expected', got '$Actual'."
    }
    $script:Passed++
}

function Assert-ThrowsWithExitCode {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][int]$ExitCode
    )
    $threw = $false
    try {
        Invoke-Native -FilePath $powerShellExecutable -Arguments $Arguments
    }
    catch {
        $threw = $true
        if ($_.Exception.Message -notmatch "exit code $ExitCode") {
            throw "$Name reported an unexpected error: $($_.Exception.Message)"
        }
    }
    if (-not $threw) {
        throw "$Name did not throw for exit code $ExitCode."
    }
    $script:Passed++
}

function New-HelperArguments {
    param(
        [string]$Stdout = "",
        [string]$Stderr = "",
        [int]$ExitCode = 0
    )
    $arguments = @(
        "-NoProfile",
        "-NonInteractive"
    )
    if ($runningOnWindows) {
        $arguments += @("-ExecutionPolicy", "Bypass")
    }
    $arguments += @("-File", $helperPath)
    if (-not [string]::IsNullOrEmpty($Stdout)) {
        $arguments += @("-Stdout", $Stdout)
    }
    if (-not [string]::IsNullOrEmpty($Stderr)) {
        $arguments += @("-Stderr", $Stderr)
    }
    $arguments += @("-ExitCode", [string]$ExitCode)
    return $arguments
}

$runningOnWindows =
    [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$pathComparison = if ($runningOnWindows) {
    [StringComparison]::OrdinalIgnoreCase
}
else {
    [StringComparison]::Ordinal
}
$tempParent = Normalize-DirectoryPath ([IO.Path]::GetTempPath())
$testRoot = Join-Path $tempParent (
    "LLMVoice-native-invocation-tests-" + [Guid]::NewGuid().ToString("N")
)
$null = New-Item -ItemType Directory -Path $testRoot
$helperPath = Join-Path $testRoot "native-helper.ps1"
$powerShellExecutable = (Get-Process -Id $PID).Path
$script:Passed = 0

try {
    @'
param(
    [string]$Stdout = "",
    [string]$Stderr = "",
    [int]$ExitCode = 0
)
if (-not [string]::IsNullOrEmpty($Stdout)) {
    [Console]::Out.WriteLine($Stdout)
}
if (-not [string]::IsNullOrEmpty($Stderr)) {
    [Console]::Error.WriteLine($Stderr)
}
exit $ExitCode
'@ | Set-Content -LiteralPath $helperPath -Encoding UTF8

    Invoke-Native `
        -FilePath $powerShellExecutable `
        -Arguments (New-HelperArguments -Stdout "stdout-success")
    $script:Passed++

    Invoke-Native `
        -FilePath $powerShellExecutable `
        -Arguments (New-HelperArguments -Stderr "WARNING: harmless")
    Write-Output "NATIVE_STDERR_WARNING_EXIT_0=PASSED"
    $script:Passed++

    Invoke-Native `
        -FilePath $powerShellExecutable `
        -Arguments (
            New-HelperArguments `
                -Stdout "combined-stdout" `
                -Stderr "combined-stderr"
        )
    $script:Passed++

    Assert-ThrowsWithExitCode `
        -Name "stderr error with exit 1" `
        -Arguments (New-HelperArguments -Stderr "ERROR: failed" -ExitCode 1) `
        -ExitCode 1

    Assert-ThrowsWithExitCode `
        -Name "stdout with exit 1" `
        -Arguments (New-HelperArguments -Stdout "failed output" -ExitCode 1) `
        -ExitCode 1

    $spacedDirectory = Join-Path $testRoot "executable path with spaces"
    $null = New-Item -ItemType Directory -Path $spacedDirectory
    if ($runningOnWindows) {
        $spacedExecutable = Join-Path $spacedDirectory "cmd.exe"
        Copy-Item -LiteralPath $env:ComSpec -Destination $spacedExecutable
        Invoke-Native `
            -FilePath $spacedExecutable `
            -Arguments @("/d", "/c", "exit /b 0")
    }
    else {
        $shellExecutable = (Get-Command "sh" -CommandType Application).Source
        $spacedExecutable = Join-Path $spacedDirectory "sh"
        Copy-Item -LiteralPath $shellExecutable -Destination $spacedExecutable
        & chmod "+x" $spacedExecutable
        if ($LASTEXITCODE -ne 0) {
            throw "Could not make the copied test executable runnable."
        }
        Invoke-Native -FilePath $spacedExecutable -Arguments @("-c", "exit 0")
    }
    $script:Passed++

    $argumentWithSpaces = Invoke-Native `
        -FilePath $powerShellExecutable `
        -Arguments (
            New-HelperArguments -Stdout "argument value with spaces"
        ) `
        -Capture
    Assert-Equal `
        -Name "argument containing spaces" `
        -Actual $argumentWithSpaces `
        -Expected "argument value with spaces"

    $captured = Invoke-Native `
        -FilePath $powerShellExecutable `
        -Arguments (New-HelperArguments -Stdout "captured-output") `
        -Capture
    Assert-Equal `
        -Name "capture stdout" `
        -Actual $captured `
        -Expected "captured-output"

    $capturedWithWarning = Invoke-Native `
        -FilePath $powerShellExecutable `
        -Arguments (
            New-HelperArguments `
                -Stdout "clean-captured-output" `
                -Stderr "WARNING: cache ignored"
        ) `
        -Capture
    Assert-Equal `
        -Name "capture ignores successful stderr" `
        -Actual $capturedWithWarning `
        -Expected "clean-captured-output"

    $ErrorActionPreference = "Stop"
    Invoke-Native `
        -FilePath $powerShellExecutable `
        -Arguments (New-HelperArguments -Stderr "WARNING: restore test")
    Assert-Equal `
        -Name "ErrorActionPreference restoration" `
        -Actual $ErrorActionPreference `
        -Expected "Stop"

    Write-Output "NATIVE_INVOCATION_CASES_PASSED=$script:Passed"
}
finally {
    $resolved = Normalize-DirectoryPath $testRoot
    $resolvedParent = Normalize-DirectoryPath (
        [IO.Path]::GetDirectoryName($resolved)
    )
    if (
        -not [string]::Equals(
            $resolvedParent,
            $tempParent,
            $pathComparison
        )
    ) {
        throw "Refusing test cleanup outside the system temp directory."
    }
    if ([IO.Directory]::Exists($resolved)) {
        [IO.Directory]::Delete($resolved, $true)
    }
}
