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
    throw "Installer could not be parsed for Python detection tests."
}
$neededFunctions = @(
    "Throw-InstallerError",
    "New-PythonCandidate",
    "Select-PythonCandidate"
)
$definitions = $ast.FindAll(
    {
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $neededFunctions -contains $node.Name
    },
    $true
)
foreach ($definition in $definitions) {
    . ([scriptblock]::Create($definition.Extent.Text))
}

function Normalize-DirectoryPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [IO.Path]::GetFullPath($Path)
    $rootPath = [IO.Path]::GetPathRoot($fullPath)
    if ($fullPath.Length -eq $rootPath.Length) {
        return $rootPath
    }
    $separators = [char[]]@(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    return $fullPath.TrimEnd($separators)
}

function Join-TestPath {
    param([Parameter(Mandatory = $true)][string[]]$Segments)

    $path = $testRoot
    foreach ($segment in $Segments) {
        $path = Join-Path $path $segment
    }
    return $path
}

$isWindows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$pathComparison = if ($isWindows) {
    [StringComparison]::OrdinalIgnoreCase
}
else {
    [StringComparison]::Ordinal
}
$tempParent = Normalize-DirectoryPath ([IO.Path]::GetTempPath())
$testRoot = Join-Path $tempParent (
    "LLMVoice-python-detection-tests-" + [Guid]::NewGuid().ToString("N")
)
$null = New-Item -ItemType Directory -Path $testRoot
$script:Passed = 0

function New-FakeExecutable {
    param([Parameter(Mandatory = $true)][string[]]$Segments)

    $path = Join-TestPath -Segments $Segments
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force
    [IO.File]::WriteAllBytes($path, [byte[]]@())
    return $path
}

function New-TestCandidate {
    param(
        [string]$Source,
        [string]$Path,
        [int]$Priority,
        [string]$Selector = ""
    )
    return New-PythonCandidate `
        -File $Path `
        -Source $Source `
        -Selector $Selector `
        -Priority $Priority
}

function New-SuccessResult {
    param(
        [string]$Version,
        [int]$Bits,
        [string]$Executable
    )
    $parts = $Version.Split(".")
    return [pscustomobject]@{
        Success = $true
        ExitCode = 0
        Reason = ""
        Probe = [pscustomobject]@{
            version = $Version
            major = [int]$parts[0]
            minor = [int]$parts[1]
            bits = $Bits
            executable = $Executable
        }
    }
}

function New-FailureResult {
    param([string]$Reason)
    return [pscustomobject]@{
        Success = $false
        ExitCode = 1
        Reason = $Reason
        Probe = $null
    }
}

function Invoke-SelectionCase {
    param(
        [string]$Name,
        [object[]]$Candidates,
        [hashtable]$Results,
        [string]$ExpectedSource,
        [string]$ExpectedVersion
    )
    $caseResults = $Results
    $runner = {
        param($candidate)
        return $caseResults[[string]$candidate.Source]
    }.GetNewClosure()
    $selected = Select-PythonCandidate `
        -Candidates $Candidates `
        -Minimum "3.11" `
        -MaximumExclusive "3.15" `
        -ProbeRunner $runner
    if ([string]::IsNullOrWhiteSpace($ExpectedSource)) {
        if ($null -ne $selected) {
            throw "$Name selected an unsupported candidate."
        }
    }
    else {
        if ($null -eq $selected) {
            throw "$Name did not select a supported candidate."
        }
        if (
            [string]$selected.Source -ne $ExpectedSource -or
            [string]$selected.Version -ne $ExpectedVersion
        ) {
            throw (
                "$Name selected $($selected.Source) $($selected.Version); " +
                "expected $ExpectedSource $ExpectedVersion."
            )
        }
    }
    $script:Passed++
}

try {
    foreach ($version in @("3.11.9", "3.12.8", "3.13.14", "3.14.5")) {
        $source = "python-$version"
        $path = New-FakeExecutable -Segments @($source, "python.exe")
        Invoke-SelectionCase `
            -Name "$version x64 accepted" `
            -Candidates @((New-TestCandidate $source $path 0)) `
            -Results @{ $source = New-SuccessResult $version 64 $path } `
            -ExpectedSource $source `
            -ExpectedVersion $version
    }

    foreach ($version in @("3.10.14", "3.15.0")) {
        $source = "python-$version"
        $path = New-FakeExecutable -Segments @($source, "python.exe")
        Invoke-SelectionCase `
            -Name "$version rejected" `
            -Candidates @((New-TestCandidate $source $path 0)) `
            -Results @{ $source = New-SuccessResult $version 64 $path } `
            -ExpectedSource "" `
            -ExpectedVersion ""
    }

    $path32 = New-FakeExecutable -Segments @("python-32", "python.exe")
    Invoke-SelectionCase `
        -Name "32-bit rejected" `
        -Candidates @((New-TestCandidate "python-32" $path32 0)) `
        -Results @{ "python-32" = New-SuccessResult "3.14.5" 32 $path32 } `
        -ExpectedSource "" `
        -ExpectedVersion ""

    $storeAlias = New-FakeExecutable `
        -Segments @("Microsoft", "WindowsApps", "python.exe")
    $fallback = New-FakeExecutable -Segments @("fallback", "python.exe")
    Invoke-SelectionCase `
        -Name "broken Store alias rejected" `
        -Candidates @(
            (New-TestCandidate "store-alias" $storeAlias 0),
            (New-TestCandidate "fallback" $fallback 1)
        ) `
        -Results @{
            "store-alias" = New-FailureResult "execution alias did not launch"
            "fallback" = New-SuccessResult "3.13.14" 64 $fallback
        } `
        -ExpectedSource "fallback" `
        -ExpectedVersion "3.13.14"

    $python311 = New-FakeExecutable -Segments @("multiple", "311", "python.exe")
    $python314 = New-FakeExecutable -Segments @("multiple", "314", "python.exe")
    $python313 = New-FakeExecutable -Segments @("multiple", "313", "python.exe")
    Invoke-SelectionCase `
        -Name "highest supported version selected" `
        -Candidates @(
            (New-TestCandidate "v311" $python311 0),
            (New-TestCandidate "v313" $python313 1),
            (New-TestCandidate "v314" $python314 2)
        ) `
        -Results @{
            "v311" = New-SuccessResult "3.11.9" 64 $python311
            "v313" = New-SuccessResult "3.13.14" 64 $python313
            "v314" = New-SuccessResult "3.14.5" 64 $python314
        } `
        -ExpectedSource "v314" `
        -ExpectedVersion "3.14.5"

    $launcherPython = New-FakeExecutable -Segments @("launcher", "python.exe")
    Invoke-SelectionCase `
        -Name "py.exe 3.14 selector" `
        -Candidates @(
            (New-TestCandidate "py.exe" $launcherPython 0 "-3.14")
        ) `
        -Results @{
            "py.exe" = New-SuccessResult "3.14.5" 64 $launcherPython
        } `
        -ExpectedSource "py.exe" `
        -ExpectedVersion "3.14.5"

    $directPython = New-FakeExecutable -Segments @("direct", "python.exe")
    Invoke-SelectionCase `
        -Name "direct Python fallback" `
        -Candidates @((New-TestCandidate "python.exe" $directPython 0)) `
        -Results @{
            "python.exe" = New-SuccessResult "3.12.8" 64 $directPython
        } `
        -ExpectedSource "python.exe" `
        -ExpectedVersion "3.12.8"

    $spacePython = New-FakeExecutable -Segments @("path with spaces", "python.exe")
    Invoke-SelectionCase `
        -Name "path with spaces" `
        -Candidates @((New-TestCandidate "spaces" $spacePython 0)) `
        -Results @{ "spaces" = New-SuccessResult "3.14.5" 64 $spacePython } `
        -ExpectedSource "spaces" `
        -ExpectedVersion "3.14.5"

    $broken = New-FakeExecutable -Segments @("broken", "python.exe")
    $later = New-FakeExecutable -Segments @("later", "python.exe")
    Invoke-SelectionCase `
        -Name "failed candidate does not stop probing" `
        -Candidates @(
            (New-TestCandidate "broken" $broken 0),
            (New-TestCandidate "later" $later 1)
        ) `
        -Results @{
            "broken" = New-FailureResult "probe failed"
            "later" = New-SuccessResult "3.11.9" 64 $later
        } `
        -ExpectedSource "later" `
        -ExpectedVersion "3.11.9"

    Write-Output "PYTHON_DETECTION_CASES_PASSED=$script:Passed"
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
