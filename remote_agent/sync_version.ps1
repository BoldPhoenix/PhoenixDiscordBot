# sync_version.ps1
# Reads AgentVersion from main.go and updates versioninfo.json to match.
# Called automatically by build.bat before goversioninfo runs.

$ErrorActionPreference = "Stop"

# Extract version string from main.go
$src = Get-Content "$PSScriptRoot\main.go" -Raw
$match = [regex]::Match($src, 'AgentVersion\s*=\s*"([^"]+)"')
if (-not $match.Success) {
    Write-Error "AgentVersion constant not found in main.go"
    exit 1
}

$ver = $match.Groups[1].Value
$parts = $ver.Split('.')
if ($parts.Count -lt 3) {
    Write-Error "AgentVersion must be in Major.Minor.Patch format, got: $ver"
    exit 1
}

$major = [int]$parts[0]
$minor = [int]$parts[1]
$patch = [int]$parts[2]

# Update versioninfo.json
$jsonPath = "$PSScriptRoot\versioninfo.json"
$json = Get-Content $jsonPath -Raw | ConvertFrom-Json

$json.FixedFileInfo.FileVersion.Major = $major
$json.FixedFileInfo.FileVersion.Minor = $minor
$json.FixedFileInfo.FileVersion.Patch = $patch
$json.FixedFileInfo.FileVersion.Build = 0

$json.FixedFileInfo.ProductVersion.Major = $major
$json.FixedFileInfo.ProductVersion.Minor = $minor
$json.FixedFileInfo.ProductVersion.Patch = $patch
$json.FixedFileInfo.ProductVersion.Build = 0

$json.StringFileInfo.FileVersion    = "$ver.0"
$json.StringFileInfo.ProductVersion = "$ver.0"

# Write without BOM — goversioninfo rejects UTF-8 BOM
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$content = $json | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($jsonPath, $content, $utf8NoBom)
Write-Host "  Version synced: $ver" -ForegroundColor Cyan
