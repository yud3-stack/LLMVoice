#requires -Version 5.1

[CmdletBinding()]
param(
    [ValidateSet("auto", "cuda", "cpu")]
    [string]$Runtime = "auto",

    [string]$Version = "latest",

    [switch]$Force
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$script:Repository = "yud3-stack/LLMVoice"
$script:InstallRoot = $null
$script:RuntimeVersionsRoot = $null
$script:BinDirectory = $null
$script:StatePath = $null
$script:TemporaryDirectory = $null
$script:NewRuntimeRoot = $null
$script:InstallationCommitted = $false

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ""
}

function Write-Ok {
    param([string]$Text)
    Write-Host ("OK    " + $Text) -ForegroundColor Green
}

function Write-Warn {
    param([string]$Text)
    Write-Host ("WARN  " + $Text) -ForegroundColor Yellow
}

function Throw-InstallerError {
    param([string]$Message)
    throw [System.InvalidOperationException]::new($Message)
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Capture
    )

    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        Throw-InstallerError "Native executable was not found: $FilePath"
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $stderrPath = $null
    try {
        # Windows PowerShell 5.1 can surface native stderr as ErrorRecord
        # objects. Native success is determined only by the process exit code.
        $ErrorActionPreference = "Continue"

        if ($Capture) {
            $stderrPath = [IO.Path]::GetTempFileName()
            $stdout = @(& $FilePath @Arguments 2> $stderrPath)
            $exitCode = $LASTEXITCODE
            $stderr = @()
            if ((Get-Item -LiteralPath $stderrPath).Length -gt 0) {
                $stderr = @(Get-Content -LiteralPath $stderrPath)
                if ($exitCode -eq 0) {
                    Write-Debug (
                        "Native command wrote to stderr but exited successfully: " +
                        $FilePath
                    )
                }
            }
            if ($exitCode -ne 0) {
                $detail = @($stdout) + @($stderr) |
                    Select-Object -Last 8
                $detailText = ($detail -join [Environment]::NewLine).Trim()
                Throw-InstallerError (
                    "Command failed with exit code $exitCode`: $FilePath" +
                    $(if ($detailText) {
                        "`n$detailText"
                    }
                    else {
                        ""
                    })
                )
            }
            return (($stdout | ForEach-Object { [string]$_ }) -join (
                [Environment]::NewLine
            )).Trim()
        }

        $combinedOutput = New-Object System.Collections.Generic.List[string]
        & $FilePath @Arguments 2>&1 | ForEach-Object {
            $line = [string]$_
            $null = $combinedOutput.Add($line)
            Write-Host $line
        }
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            $detailText = (
                $combinedOutput |
                Select-Object -Last 8
            ) -join [Environment]::NewLine
            Throw-InstallerError (
                "Command failed with exit code $exitCode`: $FilePath" +
                $(if ($detailText) {
                    "`n$detailText"
                }
                else {
                    ""
                })
            )
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if (
            $null -ne $stderrPath -and
            (Test-Path -LiteralPath $stderrPath -PathType Leaf)
        ) {
            Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-CommandPath {
    param([string]$Name)
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) {
        return $null
    }
    return $command.Source
}

function Assert-System {
    if ($PSVersionTable.PSVersion -lt [version]"5.1") {
        Throw-InstallerError "PowerShell 5.1 or newer is required."
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        Throw-InstallerError "This installer supports Windows only."
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        Throw-InstallerError "LLMVoice requires 64-bit Windows."
    }
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        Throw-InstallerError "LOCALAPPDATA is not available for this user."
    }
    $script:InstallRoot = Join-Path $env:LOCALAPPDATA "LLMVoice"
    $script:RuntimeVersionsRoot = Join-Path $script:InstallRoot "runtime\versions"
    $script:BinDirectory = Join-Path $script:InstallRoot "bin"
    $script:StatePath = Join-Path $script:InstallRoot "runtime\install-state.json"
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

function Invoke-SecureDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $parsed = [Uri]$Uri
    if ($parsed.Scheme -ne "https" -or $parsed.Host -ne "github.com") {
        Throw-InstallerError "Refusing non-GitHub or non-HTTPS download URL: $Uri"
    }

    $lastError = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing -TimeoutSec 120
            if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
                Throw-InstallerError "Download completed without creating a file."
            }
            return
        }
        catch {
            $lastError = $_.Exception.Message
            if ($attempt -lt 3) {
                Start-Sleep -Seconds 2
            }
        }
    }
    Throw-InstallerError "Download failed after three attempts.`n$lastError"
}

function Get-ReleaseManifest {
    param([string]$RequestedVersion)

    if ($RequestedVersion -eq "latest") {
        $uri = "https://github.com/$($script:Repository)/releases/latest/download/install-manifest.json"
    }
    else {
        if ($RequestedVersion -notmatch "^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.-]+)?$") {
            Throw-InstallerError "Invalid version '$RequestedVersion'. Use latest or a version such as 0.1.6."
        }
        $uri = "https://github.com/$($script:Repository)/releases/download/v$RequestedVersion/install-manifest.json"
    }

    $manifestPath = Join-Path $script:TemporaryDirectory "install-manifest.json"
    Invoke-SecureDownload -Uri $uri -Destination $manifestPath
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
    }
    catch {
        Throw-InstallerError "The release manifest is not valid JSON."
    }
    return $manifest
}

function Assert-Manifest {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$RequestedVersion
    )

    if ([int]$Manifest.schemaVersion -ne 2) {
        Throw-InstallerError "Unsupported installer manifest schema."
    }
    if ([string]$Manifest.repository -ne $script:Repository) {
        Throw-InstallerError "Manifest repository identity is invalid."
    }
    $releaseVersion = [string]$Manifest.version
    $releaseTag = [string]$Manifest.tag
    if ($releaseVersion -notmatch "^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9.-]+)?$") {
        Throw-InstallerError "Manifest version is invalid."
    }
    if ($releaseTag -ne "v$releaseVersion") {
        Throw-InstallerError "Manifest tag and version do not match."
    }
    if ($RequestedVersion -ne "latest" -and $releaseVersion -ne $RequestedVersion) {
        Throw-InstallerError "Requested version and downloaded manifest do not match."
    }
    $expectedWheel = "llmvoice-$releaseVersion-py3-none-any.whl"
    if ([string]$Manifest.wheel.file -ne $expectedWheel) {
        Throw-InstallerError "Manifest wheel filename is invalid."
    }
    if ([string]$Manifest.wheel.sha256 -notmatch "^[A-Fa-f0-9]{64}$") {
        Throw-InstallerError "Manifest wheel checksum is invalid."
    }
    if ([string]$Manifest.python.architecture -ne "x64") {
        Throw-InstallerError "This installer supports x64 Python runtimes only."
    }
    foreach ($profileName in @("cuda", "cpu")) {
        $profileProperty = $Manifest.runtimeProfiles.PSObject.Properties[$profileName]
        if ($null -eq $profileProperty) {
            Throw-InstallerError "Manifest is missing the $profileName runtime profile."
        }
        $profile = $profileProperty.Value
        $groups = @($profile.groups)
        if ($groups.Count -eq 0) {
            Throw-InstallerError "Manifest runtime profile contains no package groups."
        }
        $groupNames = @{}
        $packageLocations = @{}
        foreach ($group in $groups) {
            $groupName = [string]$group.name
            if (
                $groupName -notmatch "^[a-z][a-z0-9-]*$" -or
                $groupNames.ContainsKey($groupName)
            ) {
                Throw-InstallerError "Manifest contains an invalid runtime group."
            }
            $groupNames[$groupName] = $true
            $indexUrl = [string]$group.indexUrl
            if (
                $indexUrl -notin @(
                    "https://download.pytorch.org/whl/cu130",
                    "https://download.pytorch.org/whl/cpu"
                )
            ) {
                Throw-InstallerError "Manifest contains an unsafe PyTorch index URL."
            }
            $noDependenciesProperty =
                $group.PSObject.Properties["noDependencies"]
            if (
                $null -eq $noDependenciesProperty -or
                $noDependenciesProperty.Value -isnot [bool]
            ) {
                Throw-InstallerError "Manifest runtime group dependency mode is invalid."
            }
            $groupPackages = @($group.packages)
            if ($groupPackages.Count -eq 0) {
                Throw-InstallerError "Manifest runtime group contains no packages."
            }
            foreach ($package in $groupPackages) {
                $requirement = [string]$package
                if ($requirement -notmatch "^[A-Za-z0-9_.+-]+==[A-Za-z0-9_.+-]+$") {
                    Throw-InstallerError "Manifest contains an invalid runtime package."
                }
                $packageName = $requirement.Split("==")[0].ToLowerInvariant()
                if ($packageLocations.ContainsKey($packageName)) {
                    Throw-InstallerError "Manifest repeats a runtime package."
                }
                $packageLocations[$packageName] = [pscustomobject]@{
                    Group = $groupName
                    IndexUrl = $indexUrl
                    NoDependencies = [bool]$noDependenciesProperty.Value
                }
            }
        }
        if (
            $packageLocations.Count -ne 3 -or
            -not $packageLocations.ContainsKey("torch") -or
            -not $packageLocations.ContainsKey("torchaudio") -or
            -not $packageLocations.ContainsKey("torchcodec")
        ) {
            Throw-InstallerError (
                "Manifest runtime profile must contain torch, torchaudio, " +
                "and torchcodec exactly once."
            )
        }
        if ($profileName -eq "cuda") {
            foreach ($computePackage in @("torch", "torchaudio")) {
                $location = $packageLocations[$computePackage]
                if (
                    $location.Group -ne "compute" -or
                    $location.IndexUrl -ne "https://download.pytorch.org/whl/cu130" -or
                    $location.NoDependencies
                ) {
                    Throw-InstallerError (
                        "CUDA compute packages must use the cu130 index."
                    )
                }
            }
            $codecLocation = $packageLocations["torchcodec"]
            if (
                $codecLocation.Group -ne "codec" -or
                $codecLocation.IndexUrl -ne "https://download.pytorch.org/whl/cpu" -or
                -not $codecLocation.NoDependencies
            ) {
                Throw-InstallerError (
                    "CUDA TorchCodec must use the isolated CPU codec group."
                )
            }
        }
        else {
            foreach ($packageName in @("torch", "torchaudio", "torchcodec")) {
                $location = $packageLocations[$packageName]
                if (
                    $location.Group -ne "runtime" -or
                    $location.IndexUrl -ne "https://download.pytorch.org/whl/cpu" -or
                    $location.NoDependencies
                ) {
                    Throw-InstallerError (
                        "CPU runtime packages must use the CPU index."
                    )
                }
            }
        }
    }
    if (@($Manifest.application.extras) -notcontains "tts") {
        Throw-InstallerError "Manifest does not request the LLMVoice TTS extra."
    }
    $applicationDependencies = @($Manifest.application.dependencies)
    if ($applicationDependencies.Count -eq 0) {
        Throw-InstallerError "Manifest contains no application dependencies."
    }
    foreach ($dependency in $applicationDependencies) {
        if ([string]$dependency -notmatch "^[A-Za-z0-9_.+-]+==[A-Za-z0-9_.+-]+$") {
            Throw-InstallerError "Manifest contains an invalid application dependency."
        }
    }
}

function Get-RuntimeRequirementVersion {
    param(
        [Parameter(Mandatory = $true)]$Profile,
        [Parameter(Mandatory = $true)][string]$PackageName
    )

    foreach ($group in @($Profile.groups)) {
        foreach ($requirement in @($group.packages)) {
            $parts = ([string]$requirement).Split(
                @("=="),
                2,
                [StringSplitOptions]::None
            )
            if (
                $parts.Count -eq 2 -and
                $parts[0].Equals(
                    $PackageName,
                    [StringComparison]::OrdinalIgnoreCase
                )
            ) {
                return $parts[1]
            }
        }
    }
    Throw-InstallerError "Runtime profile is missing package: $PackageName"
}

function Assert-RuntimeProbe {
    param(
        [Parameter(Mandatory = $true)][string]$ProfileName,
        [Parameter(Mandatory = $true)]$Profile,
        [Parameter(Mandatory = $true)]$Probe
    )

    foreach ($packageName in @("torch", "torchaudio", "torchcodec")) {
        $expectedVersion = Get-RuntimeRequirementVersion `
            -Profile $Profile `
            -PackageName $packageName
        $actualVersion = [string]$Probe.$packageName
        if ($actualVersion -ne $expectedVersion) {
            Throw-InstallerError (
                "Runtime package version mismatch for $packageName.`n" +
                "Expected: $expectedVersion`n" +
                "Actual  : $actualVersion"
            )
        }
    }
    if ($ProfileName -eq "cuda" -and -not [bool]$Probe.cuda) {
        Throw-InstallerError (
            "CUDA-enabled PyTorch was installed, but PyTorch cannot access the NVIDIA GPU.`n`n" +
            "Review the NVIDIA driver and run the installer again."
        )
    }
    if (
        $ProfileName -eq "cuda" -and
        [string]::IsNullOrWhiteSpace([string]$Probe.gpu)
    ) {
        Throw-InstallerError "CUDA is available, but no GPU name was reported."
    }
    if (-not [bool]$Probe.audioDecode) {
        Throw-InstallerError (
            "TorchCodec could not decode audio through the shared FFmpeg runtime."
        )
    }
    if (
        [string]::IsNullOrWhiteSpace([string]$Probe.ffmpegDirectory) -or
        [string]::IsNullOrWhiteSpace([string]$Probe.ffmpegVersion) -or
        [string]::IsNullOrWhiteSpace([string]$Probe.avcodecDll) -or
        -not [bool]$Probe.dllDirectoryRegistered
    ) {
        Throw-InstallerError (
            "The shared FFmpeg DLL directory was not registered correctly."
        )
    }
}

function New-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$File,
        [string[]]$Prefix = @(),
        [Parameter(Mandatory = $true)][string]$Source,
        [string]$Selector = "",
        [int]$Priority = 0
    )
    return [pscustomobject]@{
        File = $File
        Prefix = @($Prefix)
        Source = $Source
        Selector = $Selector
        Priority = $Priority
    }
}

function Add-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)]$Candidates,
        [Parameter(Mandatory = $true)][hashtable]$Seen,
        [Parameter(Mandatory = $true)][string]$File,
        [string[]]$Prefix = @(),
        [Parameter(Mandatory = $true)][string]$Source,
        [string]$Selector = ""
    )
    if ([string]::IsNullOrWhiteSpace($File)) {
        return
    }
    $key = (
        $File.Trim().ToLowerInvariant() + [char]0 +
        ((@($Prefix) -join [char]0).ToLowerInvariant())
    )
    if ($Seen.ContainsKey($key)) {
        return
    }
    $Seen[$key] = $true
    $null = $Candidates.Add(
        (New-PythonCandidate `
            -File $File `
            -Prefix $Prefix `
            -Source $Source `
            -Selector $Selector `
            -Priority $Candidates.Count)
    )
}

function Get-PythonPathsFromLauncher {
    param(
        [Parameter(Mandatory = $true)][string]$Launcher,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )

    Write-Debug "Trying Python runtime listing: $Description"
    try {
        $output = & $Launcher @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    catch {
        Write-Debug "Runtime listing failed: $($_.Exception.Message)"
        return
    }
    Write-Debug "Runtime listing exit code: $exitCode"
    if ($exitCode -ne 0) {
        return
    }

    foreach ($outputLine in @($output)) {
        $line = ([string]$outputLine).Trim()
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $path = $null
        if (
            [IO.Path]::IsPathRooted($line) -and
            $line.EndsWith(".exe", [StringComparison]::OrdinalIgnoreCase)
        ) {
            $path = $line
        }
        else {
            # Legacy `py -0p` output is locale-independent only at the path
            # boundary. Ignore the selector text and extract the final absolute
            # executable path.
            $match = [regex]::Match($line, "([A-Za-z]:\\.*\.exe)\s*$")
            if ($match.Success) {
                $path = $match.Groups[1].Value.Trim()
            }
        }
        if ($null -ne $path) {
            Write-Debug "Discovered Python executable: $path"
            Write-Output $path
        }
    }
}

function Invoke-PythonCandidateProbe {
    param([Parameter(Mandatory = $true)]$Candidate)

    $display = $Candidate.Source
    if (-not [string]::IsNullOrWhiteSpace([string]$Candidate.Selector)) {
        $display += " $($Candidate.Selector)"
    }
    Write-Debug "Trying $display"

    # Use only single-quoted Python literals. Windows PowerShell 5.1 removes
    # embedded double quotes when forwarding a native `-c` argument.
    $probeCode = 'import json,struct,sys; print(json.dumps({''version'':''.''.join(map(str,sys.version_info[:3])),''major'':sys.version_info[0],''minor'':sys.version_info[1],''bits'':struct.calcsize(''P'')*8,''executable'':sys.executable}))'
    $arguments = @($Candidate.Prefix) + @("-c", $probeCode)
    try {
        $output = & $Candidate.File @arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    catch {
        return [pscustomobject]@{
            Success = $false
            ExitCode = $null
            Reason = $_.Exception.Message
            Probe = $null
        }
    }
    Write-Debug "Probe exit code: $exitCode"
    if ($exitCode -ne 0) {
        $detail = (@($output) | Select-Object -Last 4) -join " "
        if (
            $Candidate.File -match "\\Microsoft\\WindowsApps\\python(?:3)?\.exe$"
        ) {
            $detail = "Microsoft Store execution alias did not launch a real interpreter. $detail"
        }
        return [pscustomobject]@{
            Success = $false
            ExitCode = $exitCode
            Reason = $detail.Trim()
            Probe = $null
        }
    }

    try {
        $jsonLine = @($output) |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_.StartsWith("{") -and $_.EndsWith("}") } |
            Select-Object -Last 1
        if ([string]::IsNullOrWhiteSpace($jsonLine)) {
            throw "Probe produced no JSON object."
        }
        $probe = $jsonLine | ConvertFrom-Json
        return [pscustomobject]@{
            Success = $true
            ExitCode = $exitCode
            Reason = ""
            Probe = $probe
        }
    }
    catch {
        return [pscustomobject]@{
            Success = $false
            ExitCode = $exitCode
            Reason = "Probe output was not valid JSON: $($_.Exception.Message)"
            Probe = $null
        }
    }
}

function Select-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)]$Candidates,
        [Parameter(Mandatory = $true)][string]$Minimum,
        [Parameter(Mandatory = $true)][string]$MaximumExclusive,
        [scriptblock]$ProbeRunner = {
            param($Candidate)
            Invoke-PythonCandidateProbe -Candidate $Candidate
        }
    )

    $minimumVersion = [version]$Minimum
    $maximumVersion = [version]$MaximumExclusive
    $accepted = New-Object System.Collections.Generic.List[object]
    $acceptedExecutables = @{}

    foreach ($candidate in $Candidates) {
        $result = & $ProbeRunner $candidate
        if (-not [bool]$result.Success) {
            Write-Debug "Rejected $($candidate.Source) $($candidate.Selector)"
            Write-Debug "Reason: $($result.Reason)"
            continue
        }

        try {
            $probe = $result.Probe
            $foundVersion = [version]"$($probe.major).$($probe.minor)"
            $fullVersion = [version]([string]$probe.version)
            $bits = [int]$probe.bits
            $executable = [string]$probe.executable
            Write-Debug "Found Python $fullVersion $bits-bit"
            Write-Debug "Executable: $executable"

            if ($foundVersion -lt $minimumVersion) {
                throw "Python $fullVersion is older than the supported minimum $Minimum."
            }
            if ($foundVersion -ge $maximumVersion) {
                throw "Python $fullVersion is not below $MaximumExclusive."
            }
            if ($bits -ne 64) {
                throw "Python $fullVersion is $bits-bit; 64-bit is required."
            }
            if (
                -not [IO.Path]::IsPathRooted($executable) -or
                -not $executable.EndsWith(
                    ".exe",
                    [StringComparison]::OrdinalIgnoreCase
                ) -or
                -not (Test-Path -LiteralPath $executable -PathType Leaf)
            ) {
                throw "Probe did not return a real absolute Python executable path."
            }
            $resolvedExecutable = [IO.Path]::GetFullPath($executable)
            $executableKey = $resolvedExecutable.ToLowerInvariant()
            if (-not $acceptedExecutables.ContainsKey($executableKey)) {
                $acceptedExecutables[$executableKey] = $true
                $null = $accepted.Add([pscustomobject]@{
                    File = $resolvedExecutable
                    Prefix = @()
                    Version = [string]$probe.version
                    VersionObject = $fullVersion
                    Executable = $resolvedExecutable
                    Source = [string]$candidate.Source
                    Selector = [string]$candidate.Selector
                    Priority = [int]$candidate.Priority
                })
            }
            Write-Debug "Accepted candidate"
        }
        catch {
            Write-Debug "Rejected $($candidate.Source) $($candidate.Selector)"
            Write-Debug "Reason: $($_.Exception.Message)"
        }
    }
    if ($accepted.Count -gt 0) {
        $selected = $accepted |
            Sort-Object `
                @{ Expression = { $_.VersionObject }; Descending = $true }, `
                @{ Expression = { $_.Priority }; Ascending = $true } |
            Select-Object -First 1
        Write-Debug "Selected highest supported Python $($selected.Version)"
        Write-Debug "Selected executable: $($selected.Executable)"
        return $selected
    }
    return $null
}

function Get-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$Minimum,
        [Parameter(Mandatory = $true)][string]$MaximumExclusive
    )

    $minimumVersion = [version]$Minimum
    $maximumVersion = [version]$MaximumExclusive
    $candidates = New-Object System.Collections.Generic.List[object]
    $seen = @{}
    $launcher = Get-CommandPath "py.exe"

    $automaticInstallWasSet = Test-Path Env:PYTHON_MANAGER_AUTOMATIC_INSTALL
    $previousAutomaticInstall = $env:PYTHON_MANAGER_AUTOMATIC_INSTALL
    $env:PYTHON_MANAGER_AUTOMATIC_INSTALL = "false"
    try {
        if ($null -ne $launcher -and $minimumVersion.Major -eq $maximumVersion.Major) {
            for (
                $minor = $maximumVersion.Minor - 1;
                $minor -ge $minimumVersion.Minor;
                $minor--
            ) {
                $versionSelector = "$($minimumVersion.Major).$minor"
                Add-PythonCandidate `
                    -Candidates $candidates `
                    -Seen $seen `
                    -File $launcher `
                    -Prefix @("-$versionSelector") `
                    -Source "py.exe" `
                    -Selector "-$versionSelector"
                Add-PythonCandidate `
                    -Candidates $candidates `
                    -Seen $seen `
                    -File $launcher `
                    -Prefix @("-V:$versionSelector") `
                    -Source "py.exe" `
                    -Selector "-V:$versionSelector"
            }

            foreach ($path in @(
                Get-PythonPathsFromLauncher `
                    -Launcher $launcher `
                    -Arguments @("list", "--format=exe") `
                    -Description "py list --format=exe"
            )) {
                Add-PythonCandidate `
                    -Candidates $candidates `
                    -Seen $seen `
                    -File ([string]$path) `
                    -Source "py list --format=exe"
            }
            foreach ($path in @(
                Get-PythonPathsFromLauncher `
                    -Launcher $launcher `
                    -Arguments @("-0p") `
                    -Description "py -0p"
            )) {
                Add-PythonCandidate `
                    -Candidates $candidates `
                    -Seen $seen `
                    -File ([string]$path) `
                    -Source "py -0p"
            }
        }

        foreach ($name in @("python.exe", "python3.exe")) {
            $path = Get-CommandPath $name
            if ($null -ne $path) {
                Add-PythonCandidate `
                    -Candidates $candidates `
                    -Seen $seen `
                    -File $path `
                    -Source $name
            }
        }

        $selected = Select-PythonCandidate `
            -Candidates $candidates `
            -Minimum $Minimum `
            -MaximumExclusive $MaximumExclusive
        if ($null -ne $selected) {
            return $selected
        }
    }
    finally {
        if ($automaticInstallWasSet) {
            $env:PYTHON_MANAGER_AUTOMATIC_INSTALL = $previousAutomaticInstall
        }
        else {
            Remove-Item Env:PYTHON_MANAGER_AUTOMATIC_INSTALL -ErrorAction SilentlyContinue
        }
    }

    $lastSupportedMinor = ([version]$MaximumExclusive).Minor - 1
    Throw-InstallerError (
        "Python $Minimum-$((([version]$MaximumExclusive).Major)).$lastSupportedMinor " +
        "(64-bit) was not found.`n`n" +
        "Install a supported Python version and run this installer again:`n" +
        "https://www.python.org/downloads/windows/"
    )
}

function Get-NvidiaGpu {
    $nvidiaSmi = Get-CommandPath "nvidia-smi.exe"
    if ($null -eq $nvidiaSmi) {
        return $null
    }
    try {
        $output = Invoke-Native -FilePath $nvidiaSmi -Arguments @(
            "--query-gpu=name",
            "--format=csv,noheader"
        ) -Capture
        $name = ($output -split "`r?`n" | Select-Object -First 1).Trim()
        if (-not [string]::IsNullOrWhiteSpace($name)) {
            return $name
        }
    }
    catch {
        Write-Debug "nvidia-smi failed: $($_.Exception.Message)"
    }
    return $null
}

function Get-InstalledState {
    if (-not (Test-Path -LiteralPath $script:StatePath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $script:StatePath -Raw -Encoding UTF8 |
            ConvertFrom-Json
    }
    catch {
        Write-Warn "Existing installer state is unreadable; installation will be repaired."
        return $null
    }
}

function Assert-FFmpeg {
    $ffmpeg = Get-CommandPath "ffmpeg.exe"
    $ffprobe = Get-CommandPath "ffprobe.exe"
    $sharedDirectory = $null
    if ($null -ne $ffmpeg -and $null -ne $ffprobe) {
        $ffmpegDirectory = Split-Path -Parent $ffmpeg
        $ffprobeDirectory = Split-Path -Parent $ffprobe
        if (
            $ffmpegDirectory.Equals(
                $ffprobeDirectory,
                [StringComparison]::OrdinalIgnoreCase
            ) -and
            (Get-ChildItem -LiteralPath $ffmpegDirectory -Filter "avcodec-*.dll" -File |
                Select-Object -First 1)
        ) {
            $sharedDirectory = $ffmpegDirectory
        }
    }

    if ($null -eq $sharedDirectory) {
        $wingetPackages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        if (Test-Path -LiteralPath $wingetPackages -PathType Container) {
            $packageDirectories = Get-ChildItem `
                -LiteralPath $wingetPackages `
                -Directory `
                -Filter "Gyan.FFmpeg.Shared_*" `
                -ErrorAction SilentlyContinue
            foreach ($packageDirectory in $packageDirectories) {
                $executables = Get-ChildItem `
                    -LiteralPath $packageDirectory.FullName `
                    -Recurse `
                    -File `
                    -Filter "ffmpeg.exe" `
                    -ErrorAction SilentlyContinue
                foreach ($executable in $executables) {
                    $candidate = $executable.Directory.FullName
                    if (
                        (Test-Path -LiteralPath (Join-Path $candidate "ffprobe.exe")) -and
                        (Get-ChildItem -LiteralPath $candidate -Filter "avcodec-*.dll" -File |
                            Select-Object -First 1)
                    ) {
                        $sharedDirectory = $candidate
                        break
                    }
                }
                if ($null -ne $sharedDirectory) {
                    break
                }
            }
        }
    }

    if ($null -eq $sharedDirectory) {
        $detail = "FFmpeg and FFprobe were not found."
        if ($null -ne $ffmpeg -and $null -ne $ffprobe) {
            $detail = "FFmpeg executables were found, but the shared libraries required by TorchCodec were not."
        }
        Throw-InstallerError (
            "$detail`n`n" +
            "Recommended Windows installation:`n" +
            "winget install --id Gyan.FFmpeg.Shared`n`n" +
            "Reopen the terminal after installation and run this installer again."
        )
    }
    if (-not (($env:Path -split ";") -contains $sharedDirectory)) {
        $env:Path = "$sharedDirectory;$env:Path"
    }
    Write-Ok "FFmpeg"
    Write-Ok "FFprobe"
}

function New-IsolatedRuntime {
    param(
        [Parameter(Mandatory = $true)]$Python,
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$ProfileName,
        [Parameter(Mandatory = $true)][string]$WheelPath,
        [Parameter(Mandatory = $true)][string]$RuntimeId
    )

    $script:NewRuntimeRoot = Join-Path $script:RuntimeVersionsRoot $RuntimeId
    $venvPath = Join-Path $script:NewRuntimeRoot "venv"
    New-Item -ItemType Directory -Path $script:RuntimeVersionsRoot -Force | Out-Null
    Write-Host "Creating virtual environment..."
    $venvArguments = @($Python.Prefix) + @("-m", "venv", $venvPath)
    Invoke-Native -FilePath $Python.File -Arguments $venvArguments
    Write-Ok "Isolated environment ready"

    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    $llmvoiceExe = Join-Path $venvPath "Scripts\llmvoice.exe"
    Write-Host "Updating runtime package tools..."
    Invoke-Native -FilePath $venvPython -Arguments @(
        "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip"
    )

    $profile = $Manifest.runtimeProfiles.PSObject.Properties[$ProfileName].Value
    foreach ($group in @($profile.groups)) {
        $groupName = [string]$group.name
        $displayName = switch ($groupName) {
            "compute" { "CUDA compute runtime" }
            "codec" { "media codec runtime" }
            default { "$($ProfileName.ToUpperInvariant()) runtime" }
        }
        Write-Host "Installing $displayName..."
        $runtimeArguments = @(
            "-m", "pip", "install", "--disable-pip-version-check"
        )
        if ([bool]$group.noDependencies) {
            $runtimeArguments += "--no-deps"
        }
        $runtimeArguments += @("--index-url", [string]$group.indexUrl)
        $runtimeArguments += @(
            $group.packages | ForEach-Object { [string]$_ }
        )
        Invoke-Native -FilePath $venvPython -Arguments $runtimeArguments
        Write-Ok "$displayName installed"
    }

    Write-Host "Installing local TTS dependencies..."
    $applicationArguments = @(
        "-m", "pip", "install", "--disable-pip-version-check"
    ) + @($Manifest.application.dependencies | ForEach-Object { [string]$_ })
    Invoke-Native -FilePath $venvPython -Arguments $applicationArguments
    Write-Ok "TTS dependencies installed"

    $wheelSpec = "${WheelPath}[tts]"
    Write-Host "Installing LLMVoice..."
    Invoke-Native -FilePath $venvPython -Arguments @(
        "-m", "pip", "install", "--disable-pip-version-check", $wheelSpec
    )
    Write-Ok "LLMVoice installed"

    Write-Host "Checking installed dependencies..."
    Invoke-Native -FilePath $venvPython -Arguments @(
        "-m", "pip", "check"
    )
    Write-Ok "Dependencies verified"

    Write-Host "Validating runtime..."
    $runtimeProbePath = Join-Path $script:NewRuntimeRoot "validate-runtime.py"
    $runtimeProbeSource = @'
import importlib.metadata
import json
import math
import os
import platform
import struct
import subprocess
import sys
import traceback
import wave
from pathlib import Path

import torch
import llmvoice.audio.ffmpeg as ffmpeg_bootstrap

audio_path = Path(__file__).with_name("validate-runtime.wav")
sample_rate = 16000
diagnostics = {
    "python": platform.python_version(),
    "torch": importlib.metadata.version("torch"),
    "torchcodec": importlib.metadata.version("torchcodec"),
    "ffmpegDirectory": None,
    "ffmpegVersion": None,
    "avcodecDll": None,
    "dllDirectoryRegistered": False,
}
try:
    ffmpeg_path, _ = ffmpeg_bootstrap.require_ffmpeg()
    ffmpeg_directory = Path(ffmpeg_path).resolve().parent
    avcodec_dll = next(ffmpeg_directory.glob("avcodec-*.dll"), None)
    ffmpeg_version = subprocess.run(
        [ffmpeg_path, "-version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    diagnostics.update(
        {
            "ffmpegDirectory": str(ffmpeg_directory),
            "ffmpegVersion": (
                ffmpeg_version.stdout.splitlines()[0]
                if ffmpeg_version.stdout
                else None
            ),
            "avcodecDll": avcodec_dll.name if avcodec_dll else None,
            "dllDirectoryRegistered": (
                os.name != "nt"
                or (
                    ffmpeg_directory
                    in ffmpeg_bootstrap._REGISTERED_DLL_DIRECTORIES
                    and bool(ffmpeg_bootstrap._DLL_DIRECTORY_HANDLES)
                )
            ),
        }
    )

    import torchaudio
    import torchcodec
    from torchcodec.decoders import AudioDecoder

    samples = (
        int(12000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        for index in range(sample_rate)
    )
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

    waveform, torchaudio_rate = torchaudio.load(str(audio_path))
    decoded = AudioDecoder(str(audio_path)).get_all_samples()
    result = {
        "torch": importlib.metadata.version("torch"),
        "torchaudio": importlib.metadata.version("torchaudio"),
        "torchcodec": importlib.metadata.version("torchcodec"),
        "cuda": bool(torch.cuda.is_available()),
        "gpu": (
            torch.cuda.get_device_name(0)
            if torch.cuda.is_available()
            else None
        ),
        "audioDecode": (
            torchaudio_rate == sample_rate
            and tuple(waveform.shape) == (1, sample_rate)
            and decoded.sample_rate == sample_rate
            and tuple(decoded.data.shape) == (1, sample_rate)
        ),
        **diagnostics,
    }
    print(json.dumps(result))
except Exception:
    traceback.print_exc()
    print(
        "LLMVOICE_RUNTIME_DIAGNOSTICS=" + json.dumps(diagnostics),
        file=sys.stderr,
    )
    raise SystemExit(1)
finally:
    audio_path.unlink(missing_ok=True)
'@
    [IO.File]::WriteAllText(
        $runtimeProbePath,
        $runtimeProbeSource,
        [Text.UTF8Encoding]::new($false)
    )
    try {
        $probe = Invoke-Native `
            -FilePath $venvPython `
            -Arguments @($runtimeProbePath) `
            -Capture |
            ConvertFrom-Json
    }
    finally {
        Remove-Item `
            -LiteralPath $runtimeProbePath `
            -Force `
            -ErrorAction SilentlyContinue
    }
    Assert-RuntimeProbe `
        -ProfileName $ProfileName `
        -Profile $profile `
        -Probe $probe
    Write-Debug "Runtime Python: $($probe.python)"
    Write-Debug "Runtime torch: $($probe.torch)"
    Write-Debug "Runtime TorchCodec: $($probe.torchcodec)"
    Write-Debug "Runtime FFmpeg directory: $($probe.ffmpegDirectory)"
    Write-Debug "Runtime FFmpeg version: $($probe.ffmpegVersion)"
    Write-Debug "Runtime avcodec DLL: $($probe.avcodecDll)"
    Write-Debug (
        "Runtime DLL directory registered: " +
        [bool]$probe.dllDirectoryRegistered
    )
    if ($ProfileName -eq "cpu" -and [bool]$probe.cuda) {
        Write-Warn "CPU profile was requested; CUDA will not be used by this runtime."
    }
    Write-Ok "Runtime imports and audio decoding verified"

    if (-not (Test-Path -LiteralPath $llmvoiceExe -PathType Leaf)) {
        Throw-InstallerError "The LLMVoice console entry point was not installed."
    }
    $reportedVersion = Invoke-Native -FilePath $llmvoiceExe -Arguments @("--version") -Capture
    if ($reportedVersion.Trim() -ne "LLMVoice $($Manifest.version)") {
        Throw-InstallerError "Installed CLI version does not match the release manifest."
    }

    Write-Host ""
    Write-Host "Running diagnostics..."
    Invoke-Native -FilePath $llmvoiceExe -Arguments @("doctor")
    return [pscustomobject]@{
        Root = $script:NewRuntimeRoot
        Venv = $venvPath
        Executable = $llmvoiceExe
        Probe = $probe
    }
}

function Add-UserPath {
    param([string]$Directory)
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @()
    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
        $entries = @($userPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    $normalized = $Directory.TrimEnd("\")
    $present = $false
    foreach ($entry in $entries) {
        if ($entry.Trim().TrimEnd("\").Equals($normalized, [StringComparison]::OrdinalIgnoreCase)) {
            $present = $true
            break
        }
    }
    if (-not $present) {
        $updated = (@($entries) + @($Directory)) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $updated, "User")
    }
    $processEntries = @($env:Path -split ";")
    if (-not ($processEntries | Where-Object {
        $_.Trim().TrimEnd("\").Equals($normalized, [StringComparison]::OrdinalIgnoreCase)
    })) {
        $env:Path = "$Directory;$env:Path"
    }
}

function Publish-Installation {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$ProfileName,
        [Parameter(Mandatory = $true)][string]$RuntimeId,
        [Parameter(Mandatory = $true)]$RuntimeResult
    )

    New-Item -ItemType Directory -Path $script:BinDirectory -Force | Out-Null
    Add-UserPath -Directory $script:BinDirectory
    $launcherPath = Join-Path $script:BinDirectory "llmvoice.cmd"
    $launcherTemporary = "$launcherPath.new"
    $launcherContent = (
        "@echo off`r`n" +
        "`"%~dp0..\runtime\versions\$RuntimeId\venv\Scripts\llmvoice.exe`" %*`r`n"
    )
    [IO.File]::WriteAllText($launcherTemporary, $launcherContent, [Text.Encoding]::ASCII)
    Move-Item -LiteralPath $launcherTemporary -Destination $launcherPath -Force

    $stateDirectory = Split-Path -Parent $script:StatePath
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    $stateTemporary = "$($script:StatePath).new"
    $state = [ordered]@{
        schemaVersion = 1
        version = [string]$Manifest.version
        tag = [string]$Manifest.tag
        profile = $ProfileName
        runtimeId = $RuntimeId
        runtimePath = [string]$RuntimeResult.Venv
        installedAtUtc = [DateTime]::UtcNow.ToString("o")
    }
    [IO.File]::WriteAllText(
        $stateTemporary,
        ($state | ConvertTo-Json -Depth 4) + [Environment]::NewLine,
        (New-Object Text.UTF8Encoding($false))
    )

    $oldLauncher = $null
    $oldState = $null
    if (Test-Path -LiteralPath $launcherPath -PathType Leaf) {
        $oldLauncher = [IO.File]::ReadAllBytes($launcherPath)
    }
    if (Test-Path -LiteralPath $script:StatePath -PathType Leaf) {
        $oldState = [IO.File]::ReadAllBytes($script:StatePath)
    }
    try {
        Move-Item -LiteralPath $launcherTemporary -Destination $launcherPath -Force
        Move-Item -LiteralPath $stateTemporary -Destination $script:StatePath -Force
    }
    catch {
        if ($null -ne $oldLauncher) {
            [IO.File]::WriteAllBytes($launcherPath, $oldLauncher)
        }
        else {
            Remove-Item -LiteralPath $launcherPath -Force -ErrorAction SilentlyContinue
        }
        if ($null -ne $oldState) {
            [IO.File]::WriteAllBytes($script:StatePath, $oldState)
        }
        else {
            Remove-Item -LiteralPath $script:StatePath -Force -ErrorAction SilentlyContinue
        }
        throw
    }
    $script:InstallationCommitted = $true
}

function Remove-SafeRuntimeDirectory {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        return
    }
    $fullTarget = [IO.Path]::GetFullPath($Path).TrimEnd("\")
    $fullRoot = [IO.Path]::GetFullPath($script:RuntimeVersionsRoot).TrimEnd("\")
    if ([IO.Path]::GetDirectoryName($fullTarget) -ne $fullRoot) {
        Write-Warn "Refusing to remove unexpected runtime path: $fullTarget"
        return
    }
    Remove-Item -LiteralPath $fullTarget -Recurse -Force
}

try {
    Write-Host ""
    Write-Host "LLMVoice Installer" -ForegroundColor Cyan
    Assert-System

    $script:TemporaryDirectory = Join-Path (
        [IO.Path]::GetTempPath()
    ) ("LLMVoice-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $script:TemporaryDirectory | Out-Null

    Write-Section "Checking system"
    Write-Ok "$([Environment]::OSVersion.VersionString) x64"
    Assert-FFmpeg

    Write-Section "Release"
    $manifest = Get-ReleaseManifest -RequestedVersion $Version
    Assert-Manifest -Manifest $manifest -RequestedVersion $Version
    Write-Host ("Version     " + [string]$manifest.version)

    $installedState = Get-InstalledState
    if ($null -ne $installedState) {
        Write-Host ("Installed   " + [string]$installedState.version)
        if (
            [string]$installedState.version -eq [string]$manifest.version -and
            -not $Force -and
            (Test-Path -LiteralPath ([string]$installedState.runtimePath) -PathType Container)
        ) {
            Write-Host ""
            Write-Host "LLMVoice $($manifest.version) is already installed."
            Write-Host "Use -Force to reinstall it."
            exit 0
        }
    }

    $python = Get-PythonCandidate `
        -Minimum ([string]$manifest.python.minimum) `
        -MaximumExclusive ([string]$manifest.python.maximumExclusive)
    Write-Ok "Python $($python.Version) x64"

    $gpu = Get-NvidiaGpu
    if ($null -ne $gpu) {
        Write-Ok $gpu
    }
    else {
        Write-Warn "NVIDIA GPU not detected"
    }

    $selectedProfile = $Runtime
    if ($selectedProfile -eq "auto") {
        if ($null -ne $gpu) {
            $selectedProfile = "cuda"
        }
        else {
            $selectedProfile = "cpu"
        }
    }
    if ($selectedProfile -eq "cuda" -and $null -eq $gpu) {
        Throw-InstallerError "CUDA profile was requested, but no NVIDIA GPU was detected."
    }
    Write-Host ("Runtime     " + $selectedProfile.ToUpperInvariant())

    $wheelUri = (
        "https://github.com/$($script:Repository)/releases/download/" +
        "$($manifest.tag)/$($manifest.wheel.file)"
    )
    $wheelPath = Join-Path $script:TemporaryDirectory ([string]$manifest.wheel.file)
    Write-Section "Downloading package"
    Invoke-SecureDownload -Uri $wheelUri -Destination $wheelPath
    Write-Ok "Downloaded"

    Write-Host "Verifying SHA256..."
    $actualHash = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $expectedHash = ([string]$manifest.wheel.sha256).ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        Throw-InstallerError (
            "Package verification failed.`n`n" +
            "Expected:`n$expectedHash`n`n" +
            "Actual:`n$actualHash`n`n" +
            "Installation aborted."
        )
    }
    Write-Ok "Verified"

    $runtimeId = (
        "$($manifest.version)-$selectedProfile-" +
        [Guid]::NewGuid().ToString("N").Substring(0, 8)
    )
    Write-Section "Creating isolated runtime"
    $runtimeResult = New-IsolatedRuntime `
        -Python $python `
        -Manifest $manifest `
        -ProfileName $selectedProfile `
        -WheelPath $wheelPath `
        -RuntimeId $runtimeId
    Write-Ok "Runtime verified"

    Publish-Installation `
        -Manifest $manifest `
        -ProfileName $selectedProfile `
        -RuntimeId $runtimeId `
        -RuntimeResult $runtimeResult
    Write-Ok "User PATH configured"

    if ($null -ne $installedState -and $null -ne $installedState.runtimePath) {
        $previousRuntimeRoot = Split-Path -Parent ([string]$installedState.runtimePath)
        if ($previousRuntimeRoot -ne [string]$runtimeResult.Root) {
            try {
                Remove-SafeRuntimeDirectory -Path $previousRuntimeRoot
            }
            catch {
                Write-Warn "Previous runtime could not be removed; user data was not affected."
            }
        }
    }

    Write-Section "Installation complete."
    Write-Host "Open a new terminal and run:"
    Write-Host ""
    Write-Host "llmvoice doctor" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Then:"
    Write-Host ""
    Write-Host "llmvoice voice add myvoice reference.wav"
    Write-Host "llmvoice start transcript.txt --voice myvoice"
}
catch {
    Write-Host ""
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    if ($DebugPreference -eq "Continue" -or $DebugPreference -eq "Inquire") {
        Write-Host ""
        Write-Host ($_ | Format-List * -Force | Out-String)
    }
    exit 1
}
finally {
    if (-not $script:InstallationCommitted -and $null -ne $script:NewRuntimeRoot) {
        try {
            Remove-SafeRuntimeDirectory -Path $script:NewRuntimeRoot
        }
        catch {
            Write-Warn "Incomplete runtime cleanup failed: $($_.Exception.Message)"
        }
    }
    if (
        $null -ne $script:TemporaryDirectory -and
        (Test-Path -LiteralPath $script:TemporaryDirectory)
    ) {
        Remove-Item -LiteralPath $script:TemporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}
