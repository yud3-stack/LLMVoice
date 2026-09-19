[CmdletBinding()]
param(
    [ValidateSet("auto", "cuda", "cpu")]
    [string]$Runtime = "auto",

    [string]$Version = "latest",

    [switch]$Force
)

$canonicalInstaller = Join-Path $PSScriptRoot "installer\install.ps1"
if (-not (Test-Path -LiteralPath $canonicalInstaller -PathType Leaf)) {
    throw "Canonical installer was not found: $canonicalInstaller"
}

$debugArguments = @()
if ($DebugPreference -eq "Continue" -or $DebugPreference -eq "Inquire") {
    $debugArguments = @("-Debug")
}
& $canonicalInstaller -Runtime $Runtime -Version $Version -Force:$Force @debugArguments
exit $LASTEXITCODE
