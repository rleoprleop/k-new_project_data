[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $ConnectionString,
    [string] $ContentRoot,
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')] [string] $ProcessingDate,
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')] [string] $CorrectionDate,
    [string] $CorrectionVersion,
    [ValidateRange(1, 31)] [int] $MaxDatesPerBatch = 7,
    [string] $PseudonymizationKey = $env:KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY,
    [switch] $AllowSyntheticDefaultKey
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ContentRoot)) {
    $ContentRoot = Join-Path $PSScriptRoot '..\..\generator\data\generated\raw\content_usage'
}
$ContentRoot = [IO.Path]::GetFullPath($ContentRoot)
if (-not (Test-Path -LiteralPath $ContentRoot -PathType Container)) {
    throw "Content partition root not found: $ContentRoot"
}
$psql = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psql) { throw 'psql was not found. Install PostgreSQL client tools and add psql to PATH.' }
if ([string]::IsNullOrWhiteSpace($PseudonymizationKey)) {
    if (-not $AllowSyntheticDefaultKey) {
        throw 'Set KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY. For synthetic data only, use -AllowSyntheticDefaultKey.'
    }
    $PseudonymizationKey = 'kt-nd-synthetic-analysis-v1'
    Write-Warning 'Using the synthetic HMAC key. Do not use this option with real data.'
}

$dateFormat = 'yyyy-MM-dd'
if ([string]::IsNullOrWhiteSpace($ProcessingDate)) {
    try {
        $koreaTimeZone = [TimeZoneInfo]::FindSystemTimeZoneById('Korea Standard Time')
    } catch {
        $koreaTimeZone = [TimeZoneInfo]::FindSystemTimeZoneById('Asia/Seoul')
    }
    $processingDay = [TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow, $koreaTimeZone).Date
} else {
    $processingDay = [DateTime]::ParseExact($ProcessingDate, $dateFormat,
        [Globalization.CultureInfo]::InvariantCulture)
}
$cutoffDay = $processingDay.AddDays(-1)
if ([string]::IsNullOrWhiteSpace($CorrectionDate) -ne
    [string]::IsNullOrWhiteSpace($CorrectionVersion)) {
    throw 'CorrectionDate and CorrectionVersion must be provided together.'
}

function Invoke-PsqlScalar([string] $Sql) {
    $result = & $psql.Source -X -A -t -v ON_ERROR_STOP=1 $ConnectionString -c $Sql
    if ($LASTEXITCODE -ne 0) { throw "psql query failed with code $LASTEXITCODE" }
    return ($result | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -First 1)
}

function Get-PartitionDirectory([DateTime] $EventDay, [string] $Version) {
    $partition = Join-Path $ContentRoot ("event_date=" + $EventDay.ToString($dateFormat))
    if (-not (Test-Path -LiteralPath $partition -PathType Container)) {
        throw "Required content partition is missing: $partition"
    }
    if (-not [string]::IsNullOrWhiteSpace($Version)) {
        $versionDirectory = Join-Path $partition ("run_id=" + $Version)
        if (-not (Test-Path -LiteralPath $versionDirectory -PathType Container)) {
            throw "Requested correction version is missing: $versionDirectory"
        }
        return $versionDirectory
    }
    $directFiles = @(Get-ChildItem -LiteralPath $partition -File -Filter 'part-*.csv')
    if ($directFiles.Count -gt 0) { return $partition }
    $versions = @(Get-ChildItem -LiteralPath $partition -Directory -Filter 'run_id=*')
    if ($versions.Count -ne 1) {
        throw "Partition must contain direct part files or exactly one run_id directory: $partition"
    }
    return $versions[0].FullName
}

function Get-PartitionFiles([DateTime] $EventDay, [string] $Version) {
    $directory = Get-PartitionDirectory $EventDay $Version
    $files = @(Get-ChildItem -LiteralPath $directory -File -Filter 'part-*.csv' | Sort-Object Name)
    if ($files.Count -eq 0) { throw "No part CSV exists in partition directory: $directory" }
    return $files
}

function Get-Sha256Text([string] $Value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return -join ($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)) |
            ForEach-Object { $_.ToString('x2') })
    } finally {
        $algorithm.Dispose()
    }
}

function New-CombinedInput([DateTime[]] $EventDays, [string] $Version,
    [string] $TemporaryRoot, [string] $CurrentRunType) {
    $combinedPath = Join-Path $TemporaryRoot 'content_usage.csv'
    $manifestPath = Join-Path $TemporaryRoot 'source_manifest.csv'
    $utf8 = [Text.UTF8Encoding]::new($false)
    $writer = [IO.StreamWriter]::new($combinedPath, $false, $utf8)
    $manifest = [Collections.Generic.List[object]]::new()
    $expectedHeader = 'content_usage_id,user_id,usage_date,content_category,content_detail,data_usage_mb'
    try {
        $writer.WriteLine("partition_event_date,$expectedHeader")
        foreach ($eventDay in $EventDays) {
            $eventDate = $eventDay.ToString($dateFormat)
            foreach ($file in (Get-PartitionFiles $eventDay $Version)) {
                $reader = [IO.StreamReader]::new($file.FullName, $true)
                $rowCount = 0L
                try {
                    $header = $reader.ReadLine()
                    if ($header.TrimStart([char]0xFEFF) -ne $expectedHeader) {
                        throw "Unexpected content_usage header: $($file.FullName)"
                    }
                    while (-not $reader.EndOfStream) {
                        $line = $reader.ReadLine()
                        if ([string]::IsNullOrWhiteSpace($line)) { continue }
                        if ($line -notmatch '^[^,]*,[^,]*,(\d{4}-\d{2}-\d{2}),') {
                            throw "Cannot parse usage_date in $($file.FullName) at data row $($rowCount + 1)"
                        }
                        if ($Matches[1] -ne $eventDate) {
                            throw "Partition $eventDate contains usage_date $($Matches[1]): $($file.FullName)"
                        }
                        $writer.WriteLine("$eventDate,$line")
                        $rowCount++
                    }
                } finally {
                    $reader.Dispose()
                }
                if ($rowCount -eq 0) { throw "Content partition file is empty: $($file.FullName)" }
                $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
                $relativePath = [IO.Path]::GetRelativePath($ContentRoot, $file.FullName).Replace('\', '/')
                $objectVersion = if ([string]::IsNullOrWhiteSpace($Version)) { '' } else { $Version }
                $manifest.Add([pscustomobject]@{
                    source_path = $relativePath
                    event_date = $eventDate
                    object_version = $objectVersion
                    sha256 = $hash
                    row_count = $rowCount
                })
            }
        }
    } finally {
        $writer.Dispose()
    }
    $manifest | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding utf8
    $checksumMaterial = $CurrentRunType + "`n" + (($manifest |
      Sort-Object event_date, source_path | ForEach-Object {
        "$($_.event_date)|$($_.source_path)|$($_.object_version)|$($_.sha256)"
    }) -join "`n")
    return [pscustomobject]@{
        CombinedPath = $combinedPath
        ManifestPath = $manifestPath
        SourceSetChecksum = Get-Sha256Text $checksumMaterial
    }
}

$watermarkText = Invoke-PsqlScalar @"
select to_char(last_successful_event_date,'YYYY-MM-DD')
from audit.ingestion_watermark
where pipeline_name='content_usage_daily';
"@
$watermarkDay = if ([string]::IsNullOrWhiteSpace($watermarkText)) {
    $null
} else {
    [DateTime]::ParseExact($watermarkText, $dateFormat, [Globalization.CultureInfo]::InvariantCulture)
}

$runType = 'INCREMENTAL'
if (-not [string]::IsNullOrWhiteSpace($CorrectionDate)) {
    $runType = 'CORRECTION'
    $correctionDay = [DateTime]::ParseExact($CorrectionDate, $dateFormat,
        [Globalization.CultureInfo]::InvariantCulture)
    if ($null -eq $watermarkDay -or $correctionDay -gt $watermarkDay) {
        throw 'CorrectionDate must be on or before the successful watermark.'
    }
    if ($correctionDay -gt $cutoffDay) { throw 'CorrectionDate exceeds the allowed cutoff.' }
    $datesToProcess = @($correctionDay)
} else {
    $partitionDays = @(Get-ChildItem -LiteralPath $ContentRoot -Directory -Filter 'event_date=*' |
        ForEach-Object {
            if ($_.Name -match '^event_date=(\d{4}-\d{2}-\d{2})$') {
                [DateTime]::ParseExact($Matches[1], $dateFormat,
                    [Globalization.CultureInfo]::InvariantCulture)
            }
        } | Where-Object { $_ -le $cutoffDay } | Sort-Object -Unique)
    if ($null -eq $watermarkDay) {
        $datesToProcess = @($partitionDays)
    } else {
        $datesToProcess = @($partitionDays | Where-Object { $_ -gt $watermarkDay })
    }
    if ($datesToProcess.Count -eq 0) {
        if ($null -ne $watermarkDay -and $watermarkDay -ge $cutoffDay) {
            Write-Host "No new eligible content partitions. watermark=$($watermarkDay.ToString($dateFormat)) cutoff=$($cutoffDay.ToString($dateFormat))"
            return
        }
        throw "No eligible content partition was found through cutoff $($cutoffDay.ToString($dateFormat))."
    }
    $expectedFirst = if ($null -eq $watermarkDay) { $datesToProcess[0] } else { $watermarkDay.AddDays(1) }
    $expectedDays = @()
    for ($day = $expectedFirst; $day -le $cutoffDay; $day = $day.AddDays(1)) {
        $expectedDays += $day
    }
    $actualSet = @{}; foreach ($day in $datesToProcess) { $actualSet[$day.ToString($dateFormat)] = $true }
    $missing = @($expectedDays | Where-Object { -not $actualSet.ContainsKey($_.ToString($dateFormat)) })
    if ($missing.Count -gt 0) {
        throw "Content partition gap detected at $($missing[0].ToString($dateFormat))."
    }
}

$runFile = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\sql\020_run_incremental_pipeline.psql'))
for ($offset = 0; $offset -lt $datesToProcess.Count; $offset += $MaxDatesPerBatch) {
    $lastIndex = [Math]::Min($offset + $MaxDatesPerBatch - 1, $datesToProcess.Count - 1)
    $chunk = @($datesToProcess[$offset..$lastIndex])
    $eventDateFrom = $chunk[0].ToString($dateFormat)
    $eventDateTo = $chunk[-1].ToString($dateFormat)
    $temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("kt-nd-incremental-" + [Guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $temporaryRoot)
    $sourceSetChecksum = $null
    try {
        $input = New-CombinedInput $chunk $CorrectionVersion $temporaryRoot $runType
        $sourceSetChecksum = $input.SourceSetChecksum
        $args = @(
            '-X', '-v', 'ON_ERROR_STOP=1',
            '-v', "source_set_checksum=$sourceSetChecksum",
            '-v', "reference_date=$($processingDay.ToString($dateFormat))",
            '-v', "run_type=$runType",
            '-v', "event_date_from=$eventDateFrom",
            '-v', "event_date_to=$eventDateTo",
            '-v', "cutoff_date=$($cutoffDay.ToString($dateFormat))",
            '-v', "pseudonymization_key=$PseudonymizationKey",
            '-v', "content_usage_csv=$($input.CombinedPath)",
            '-v', "source_manifest_csv=$($input.ManifestPath)",
            '-f', $runFile
        )
        & $psql.Source $ConnectionString @args
        if ($LASTEXITCODE -ne 0) { throw "psql exited with code $LASTEXITCODE" }
        Write-Host "$runType succeeded for $eventDateFrom through $eventDateTo."
    } catch {
        if (-not [string]::IsNullOrWhiteSpace($sourceSetChecksum)) {
            $message = $_.Exception.Message.Replace("'", "''")
            $sql = "update audit.pipeline_run set status='FAILED', ended_at=clock_timestamp(), error_message='$message' where pipeline_name='content_usage_daily' and source_set_checksum='$sourceSetChecksum';"
            & $psql.Source -X $ConnectionString -c $sql | Out-Host
        }
        throw
    } finally {
        $resolvedTemporaryRoot = [IO.Path]::GetFullPath($temporaryRoot)
        $systemTemporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if ($resolvedTemporaryRoot.StartsWith($systemTemporaryRoot,
            [StringComparison]::OrdinalIgnoreCase) -and
            (Split-Path -Leaf $resolvedTemporaryRoot).StartsWith('kt-nd-incremental-')) {
            Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force
        }
    }
}
