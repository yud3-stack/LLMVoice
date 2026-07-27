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
    throw "Installer could not be parsed for runtime profile tests."
}
$neededFunctions = @(
    "Throw-InstallerError",
    "Get-RuntimeRequirementVersion",
    "Assert-RuntimeProbe"
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

function Assert-Throws {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [Parameter(Mandatory = $true)][string]$MessagePattern
    )
    $threw = $false
    try {
        & $Action
    }
    catch {
        $threw = $true
        if ($_.Exception.Message -notmatch $MessagePattern) {
            throw "$Name produced an unexpected error: $($_.Exception.Message)"
        }
    }
    if (-not $threw) {
        throw "$Name did not abort runtime validation."
    }
    $script:Passed++
}

$profile = [pscustomobject]@{
    groups = @(
        [pscustomobject]@{
            packages = @(
                "torch==2.11.0+cu130",
                "torchaudio==2.11.0+cu130"
            )
        },
        [pscustomobject]@{
            packages = @("torchcodec==0.13.0+cpu")
        }
    )
}
$validProbe = [pscustomobject]@{
    torch = "2.11.0+cu130"
    torchaudio = "2.11.0+cu130"
    torchcodec = "0.13.0+cpu"
    cuda = $true
    gpu = "NVIDIA Test GPU"
    audioDecode = $true
    ffmpegDirectory = "C:\FFmpeg\bin"
    ffmpegVersion = "ffmpeg version 8.1"
    avcodecDll = "avcodec-62.dll"
    dllDirectoryRegistered = $true
}
$script:Passed = 0

Assert-RuntimeProbe -ProfileName "cuda" -Profile $profile -Probe $validProbe
$script:Passed++

$wrongCodec = $validProbe.PSObject.Copy()
$wrongCodec.torchcodec = "0.13.0+cu130"
Assert-Throws `
    -Name "TorchCodec version mismatch" `
    -Action {
        Assert-RuntimeProbe `
            -ProfileName "cuda" `
            -Profile $profile `
            -Probe $wrongCodec
    } `
    -MessagePattern "version mismatch for torchcodec"

$cudaUnavailable = $validProbe.PSObject.Copy()
$cudaUnavailable.cuda = $false
$cudaUnavailable.gpu = $null
Assert-Throws `
    -Name "CUDA unavailable" `
    -Action {
        Assert-RuntimeProbe `
            -ProfileName "cuda" `
            -Profile $profile `
            -Probe $cudaUnavailable
    } `
    -MessagePattern "cannot access the NVIDIA GPU"

$missingGpu = $validProbe.PSObject.Copy()
$missingGpu.gpu = ""
Assert-Throws `
    -Name "GPU name unavailable" `
    -Action {
        Assert-RuntimeProbe `
            -ProfileName "cuda" `
            -Profile $profile `
            -Probe $missingGpu
    } `
    -MessagePattern "no GPU name"

$decodeFailure = $validProbe.PSObject.Copy()
$decodeFailure.audioDecode = $false
Assert-Throws `
    -Name "TorchCodec decode failure" `
    -Action {
        Assert-RuntimeProbe `
            -ProfileName "cuda" `
            -Profile $profile `
            -Probe $decodeFailure
    } `
    -MessagePattern "could not decode audio"

$dllRegistrationFailure = $validProbe.PSObject.Copy()
$dllRegistrationFailure.dllDirectoryRegistered = $false
Assert-Throws `
    -Name "FFmpeg DLL registration failure" `
    -Action {
        Assert-RuntimeProbe `
            -ProfileName "cuda" `
            -Profile $profile `
            -Probe $dllRegistrationFailure
    } `
    -MessagePattern "DLL directory was not registered"

Write-Output "RUNTIME_PROFILE_CASES_PASSED=$script:Passed"
