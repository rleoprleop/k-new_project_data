[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $ConnectionString,
    [string] $RawDirectory,
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')] [string] $ReferenceDate = '2026-09-15',
    [string] $PseudonymizationKey = $env:KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY,
    [switch] $AllowSyntheticDefaultKey
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RawDirectory)) {
    $RawDirectory = Join-Path $PSScriptRoot '..\..\generator\data\generated'
}
$psql = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psql) { throw 'psql was not found. Install PostgreSQL client tools and add psql to PATH.' }
if (-not (Test-Path -LiteralPath $RawDirectory -PathType Container)) {
    throw "Raw directory not found: $RawDirectory"
}
if ([string]::IsNullOrWhiteSpace($PseudonymizationKey)) {
    if (-not $AllowSyntheticDefaultKey) {
        throw 'Set KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY. For synthetic data only, use -AllowSyntheticDefaultKey.'
    }
    $PseudonymizationKey = 'kt-nd-synthetic-analysis-v1'
    Write-Warning 'Using the synthetic HMAC key. Do not use this option with real data.'
}

$sourceFiles = [ordered]@{
    users = 'users.csv'; families = 'families.csv'; bundle_discount_compositions = 'bundle_discount_compositions.csv'
    plans = 'plans.csv'; age_benefits = 'age_benefits.csv'; plan_age_benefits = 'plan_age_benefits.csv'
    additional_services = 'additional_services.csv'; plan_benefits = 'plan_benefits.csv'; discounts = 'discounts.csv'
    internet_bundle_discount_rules = 'internet_bundle_discount_rules.csv'; premium_family_discount_rules = 'premium_family_discount_rules.csv'
    user_discounts = 'user_discounts.csv'; user_services = 'user_services.csv'
}

$fileState = @{}
foreach ($entry in $sourceFiles.GetEnumerator()) {
    $path = [IO.Path]::GetFullPath((Join-Path $RawDirectory $entry.Value))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required source file is missing: $path"
    }
    $fileState[$entry.Key] = @{
        Path = $path
        Sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    }
}

$checksumMaterial = ($sourceFiles.Keys | ForEach-Object {
    "$($_):$($fileState[$_].Sha256)"
}) -join "`n"
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $sourceSetChecksum = -join ($sha256.ComputeHash(
        [Text.Encoding]::UTF8.GetBytes($checksumMaterial)
    ) | ForEach-Object { $_.ToString('x2') })
} finally {
    $sha256.Dispose()
}

$runFile = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\sql\015_initialize_incremental_pipeline.psql'))
$psqlArguments = @(
    '-X', '-v', 'ON_ERROR_STOP=1',
    '-v', "source_set_checksum=$sourceSetChecksum",
    '-v', "reference_date=$ReferenceDate",
    '-v', "pseudonymization_key=$PseudonymizationKey"
)
foreach ($name in $sourceFiles.Keys) {
    $psqlArguments += @(
        '-v', "${name}_csv=$($fileState[$name].Path)",
        '-v', "${name}_sha256=$($fileState[$name].Sha256)"
    )
}
$psqlArguments += @('-f', $runFile)

try {
    & $psql.Source $ConnectionString @psqlArguments
    if ($LASTEXITCODE -ne 0) { throw "psql exited with code $LASTEXITCODE" }
    Write-Host "Incremental dataset initialized. source_set_checksum=$sourceSetChecksum"
} catch {
    $message = $_.Exception.Message.Replace("'", "''")
    $sql = "update audit.pipeline_run set status='FAILED', ended_at=clock_timestamp(), error_message='$message' where pipeline_name='content_usage_daily' and source_set_checksum='$sourceSetChecksum';"
    & $psql.Source -X $ConnectionString -c $sql | Out-Host
    throw
}
