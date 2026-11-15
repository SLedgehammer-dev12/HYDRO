param(
    [string]$PythonExe = "python",
    [switch]$SkipTests,
    [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$metadataPath = Join-Path $projectRoot "hidrostatik_test\app_metadata.py"
$entryPoint = Join-Path $projectRoot "Hidrostatik_Test_Chat.py"
$manifestSourcePath = Join-Path $projectRoot "windows_manifest.xml"
$runtimeHookPath = Join-Path $projectRoot "hidrostatik_test\_pyinstaller_hook.py"
$releasePath = Join-Path $projectRoot "release"
$abControlTableCsvPath = Join-Path $projectRoot "hidrostatik_test\data\ab_control_table_v1.csv"
$abControlTableMetadataPath = Join-Path $projectRoot "hidrostatik_test\data\ab_control_table_v1.meta.json"
$gailReferenceTableCsvPath = Join-Path $projectRoot "hidrostatik_test\data\gail_reference_table_v1.csv"
$gailReferenceTableMetadataPath = Join-Path $projectRoot "hidrostatik_test\data\gail_reference_table_v1.meta.json"
$waterPropertyCsvPath = Join-Path $projectRoot "hidrostatik_test\data\water_property_table_v1.csv"
$waterPropertyMetadataPath = Join-Path $projectRoot "hidrostatik_test\data\water_property_table_v1.meta.json"

function Get-MetadataValue {
    param([string]$Name)

    $pattern = '^{0}\s*=\s*"(?<value>.+)"$' -f [regex]::Escape($Name)
    $match = Select-String -Path $metadataPath -Pattern $pattern | Select-Object -First 1
    if (-not $match) {
        throw "Metadata alani okunamadi: $Name"
    }
    return $match.Matches[0].Groups["value"].Value
}

function Get-VersionQuad {
    param([string]$AppVersion)

    $segments = @($AppVersion.Split("."))
    while ($segments.Count -lt 4) {
        $segments += "0"
    }
    return (($segments[0..3]) -join ".")
}

# Windows manifest surumu statik tutulmaz: her build'de app_metadata APP_VERSION
# degerinden turetilen gecici bir manifest kullanilir.
function Write-VersionedManifest {
    param(
        [string]$SourcePath,
        [string]$OutputPath,
        [string]$AppVersion
    )

    $versionQuad = Get-VersionQuad -AppVersion $AppVersion
    $content = Get-Content -LiteralPath $SourcePath -Raw
    # Sadece assembly'nin kendi kimligi hedeflenir; Common-Controls bagimliligi
    # blogundaki version="6.0.0.0" degistirilmemelidir.
    $updated = [regex]::Replace(
        $content,
        '(<assemblyIdentity\s+version=")[^"]+(")',
        { param($match) $match.Groups[1].Value + $versionQuad + $match.Groups[2].Value }
    )
    if ($updated -notmatch [regex]::Escape('version="' + $versionQuad + '"')) {
        throw "Manifest surum alani guncellenemedi: $SourcePath"
    }
    Set-Content -LiteralPath $OutputPath -Value $updated -Encoding UTF8
}

function Write-VersionInfoFile {
    param(
        [string]$OutputPath,
        [string]$AppVersion,
        [string]$AppName,
        [string]$PublisherName,
        [string]$CopyrightNotice
    )

    $versionTuple = ((Get-VersionQuad -AppVersion $AppVersion).Split(".") -join ", ")

    $content = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($versionTuple),
    prodvers=($versionTuple),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', '$PublisherName'),
          StringStruct('FileDescription', '$AppName'),
          StringStruct('FileVersion', '$AppVersion'),
          StringStruct('InternalName', '$AppName'),
          StringStruct('OriginalFilename', '$AppName.exe'),
          StringStruct('ProductName', '$AppName'),
          StringStruct('ProductVersion', '$AppVersion'),
          StringStruct('LegalCopyright', '$CopyrightNotice')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@

    Set-Content -LiteralPath $OutputPath -Value $content -Encoding UTF8
}

function Write-ReleaseNotes {
    param(
        [string]$OutputPath,
        [string]$AppName,
        [string]$AppVersion,
        [string]$ArtifactName,
        [string]$HashFileName,
        [string]$ArchiveHashFileName,
        [string]$ReleaseTag
    )

    $notes = @"
# $AppName v$AppVersion (Windows x64)

## Included Artifacts
- $ArtifactName
- $HashFileName
- $ArchiveHashFileName

## Validation Summary
- python -m unittest discover -s tests -p "test_*.py"
- import smoke check
- zip icerigi ve SHA-256 dogrulamasi

## Build Notes
- Windows standalone executable (.exe) generated with PyInstaller
- Runtime hook (hidrostatik_test/_pyinstaller_hook.py) packaged in both build paths
- UPX disabled to reduce antivirus false positives
- Version resource and Windows manifest embedded (manifest version = ${AppVersion}.0)
- CoolProp dependency and CSV/JSON data tables bundled directly into the executable
- Startup update check and manual update control are enabled
- Auto-updater bu paketi HidrostatikTest\HidrostatikTest.exe yapisiyla bekler

## Install
1. Zip arsivini bos bir klasore acin.
2. HidrostatikTest\HidrostatikTest.exe dosyasini calistirin.

## Verification
Get-FileHash .\$ArtifactName -Algorithm SHA256 ciktisi $HashFileName ile ayni olmalidir.

## Suggested Tag
- $ReleaseTag

## Antivirus Note
Code signing was not applied in this package. False-positive risk is reduced but cannot be
zero without Authenticode code signing and publisher reputation.
"@

    Set-Content -LiteralPath $OutputPath -Value $notes -Encoding UTF8
}

function New-ReleaseArchive {
    param(
        [string]$SourcePath,
        [string]$DestinationPath,
        [bool]$IncludeBaseDirectory = $false
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $resolvedSource = (Resolve-Path -LiteralPath $SourcePath).Path
    $maxAttempts = 8

    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            if (Test-Path -LiteralPath $DestinationPath) {
                Remove-Item -LiteralPath $DestinationPath -Force -ErrorAction SilentlyContinue
            }

            [System.IO.Compression.ZipFile]::CreateFromDirectory(
                $resolvedSource,
                $DestinationPath,
                [System.IO.Compression.CompressionLevel]::Optimal,
                $IncludeBaseDirectory
            )
            return
        } catch {
            if ($attempt -eq $maxAttempts) {
                throw
            }

            $delaySeconds = [Math]::Min($attempt * 2, 12)
            Write-Warning "Release arsivleme adimi dosya kilidi nedeniyle tekrar denenecek ($attempt/$maxAttempts)."
            Start-Sleep -Seconds $delaySeconds
        }
    }
}

function Assert-ArchiveLayout {
    param(
        [string]$ArchivePath,
        [string]$BinaryName
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $expectedEntry = "$BinaryName/$BinaryName.exe"
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        $entry = $archive.Entries | Where-Object { $_.FullName -eq $expectedEntry } | Select-Object -First 1
        if (-not $entry) {
            throw "Zip icinde beklenen giris bulunamadi: $expectedEntry (updater bu yapiyi bekler)."
        }
        if ($entry.Length -lt 10MB) {
            throw "Zip icindeki exe cok kucuk: $($entry.Length) bytes."
        }
    } finally {
        $archive.Dispose()
    }
}

function Invoke-PyInstallerBuild {
    param(
        [string]$RunId,
        [string]$AppVersion,
        [string]$AppName,
        [string]$PublisherName,
        [string]$CopyrightNotice
    )

    $attemptDistPath = Join-Path $releasePath "raw-dist-$RunId"
    $attemptBuildPath = Join-Path $releasePath "build-temp-$RunId"
    $attemptVersionInfoPath = Join-Path $attemptBuildPath "version_info.txt"
    $attemptManifestPath = Join-Path $attemptBuildPath "windows_manifest.xml"

    New-Item -ItemType Directory -Path $attemptBuildPath -Force | Out-Null
    $env:PYTHONPYCACHEPREFIX = Join-Path $attemptBuildPath "pycache"

    Write-VersionInfoFile `
        -OutputPath $attemptVersionInfoPath `
        -AppVersion $AppVersion `
        -AppName $AppName `
        -PublisherName $PublisherName `
        -CopyrightNotice $CopyrightNotice

    Write-VersionedManifest `
        -SourcePath $manifestSourcePath `
        -OutputPath $attemptManifestPath `
        -AppVersion $AppVersion

    $pyinstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--noupx",
        "--name", $binaryName,
        "--distpath", $attemptDistPath,
        "--workpath", $attemptBuildPath,
        "--specpath", $attemptBuildPath,
        "--version-file", $attemptVersionInfoPath,
        "--manifest", $attemptManifestPath,
        "--runtime-hook", $runtimeHookPath,
        "--add-data", "$abControlTableCsvPath;hidrostatik_test\data",
        "--add-data", "$abControlTableMetadataPath;hidrostatik_test\data",
        "--add-data", "$gailReferenceTableCsvPath;hidrostatik_test\data",
        "--add-data", "$gailReferenceTableMetadataPath;hidrostatik_test\data",
        "--add-data", "$waterPropertyCsvPath;hidrostatik_test\data",
        "--add-data", "$waterPropertyMetadataPath;hidrostatik_test\data",
        "--collect-all", "numpy",
        "--collect-all", "scipy",
        "--hidden-import", "CoolProp.CoolProp",
        "--hidden-import", "numpy.core._multiarray_umath",
        "--hidden-import", "numpy.core._multiarray_tests",
        "--hidden-import", "numpy.core._umath_tests",
        "--hidden-import", "numpy.lib.utils",
        "--hidden-import", "numpy.lib.format",
        "--hidden-import", "numpy.compat.py3k",
        "--hidden-import", "scipy.interpolate",
        "--hidden-import", "scipy.linalg",
        "--hidden-import", "pint",
        "--exclude-module", "CoolProp.GUI",
        "--exclude-module", "CoolProp.Plots",
        "--exclude-module", "CoolProp.tests",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pandas",
        "--exclude-module", "pytest",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PySide6",
        "--exclude-module", "lxml",
        "--exclude-module", "pyarrow",
        "--exclude-module", "iapws",
        $entryPoint
    )

    & $PythonExe @pyinstallerArgs

    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        DistPath = $attemptDistPath
        BuildPath = $attemptBuildPath
        ExePath = Join-Path $attemptDistPath "$binaryName.exe"
    }
}

$appName = Get-MetadataValue "APP_NAME"
$appVersion = Get-MetadataValue "APP_VERSION"
$binaryName = Get-MetadataValue "BINARY_NAME"
$publisherName = Get-MetadataValue "PUBLISHER_NAME"
$copyrightNotice = Get-MetadataValue "COPYRIGHT_NOTICE"
$releaseTagPrefix = Get-MetadataValue "RELEASE_TAG_PREFIX"
$artifactBaseName = "$binaryName-v$appVersion-windows-x64"
# Artefakt sozlesmesi:
#   HidrostatikTest-v<surum>-windows-x64.zip
#   HidrostatikTest-v<surum>-windows-x64.sha256.txt
#   HidrostatikTest-v<surum>-windows-x64.zip.sha256.txt  (updater <.zip>.sha256.txt bekler)
#   HidrostatikTest-v<surum>-windows-x64-RELEASE-NOTES.md
$archivePath = Join-Path $releasePath "$artifactBaseName.zip"
$hashPath = Join-Path $releasePath "$artifactBaseName.sha256.txt"
$archiveHashPath = Join-Path $releasePath "$artifactBaseName.zip.sha256.txt"
$notesPath = Join-Path $releasePath "$artifactBaseName-RELEASE-NOTES.md"
$releaseTag = "$releaseTagPrefix$appVersion"
$runId = "{0}-{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss_fff"), ([System.Guid]::NewGuid().ToString("N").Substring(0, 8))
$compileScratchPath = Join-Path $releasePath "compile-check-$runId"

Write-Host "Release build hazirlaniyor..."
Write-Host "Project root: $projectRoot"
Write-Host "Version: $appVersion"
Write-Host "Run id: $runId"

New-Item -ItemType Directory -Path $releasePath -Force | Out-Null
New-Item -ItemType Directory -Path $compileScratchPath -Force | Out-Null
$env:PYTHONPYCACHEPREFIX = $compileScratchPath

if (-not (Test-Path -LiteralPath $manifestSourcePath)) {
    throw "Windows manifest bulunamadi: $manifestSourcePath"
}
if (-not (Test-Path -LiteralPath $runtimeHookPath)) {
    throw "PyInstaller runtime hook bulunamadi: $runtimeHookPath"
}
if (-not (Test-Path -LiteralPath $abControlTableCsvPath)) {
    throw "Kurum ici A/B kontrol tablosu CSV dosyasi bulunamadi: $abControlTableCsvPath"
}
if (-not (Test-Path -LiteralPath $abControlTableMetadataPath)) {
    throw "Kurum ici A/B kontrol tablosu metadata dosyasi bulunamadi: $abControlTableMetadataPath"
}
if (-not (Test-Path -LiteralPath $gailReferenceTableCsvPath)) {
    throw "GAIL referans tablosu CSV dosyasi bulunamadi: $gailReferenceTableCsvPath"
}
if (-not (Test-Path -LiteralPath $gailReferenceTableMetadataPath)) {
    throw "GAIL referans tablosu metadata dosyasi bulunamadi: $gailReferenceTableMetadataPath"
}
if (-not (Test-Path -LiteralPath $waterPropertyCsvPath)) {
    throw "Su ozelligi CSV dosyasi bulunamadi: $waterPropertyCsvPath"
}
if (-not (Test-Path -LiteralPath $waterPropertyMetadataPath)) {
    throw "Su ozelligi metadata dosyasi bulunamadi: $waterPropertyMetadataPath"
}

if (-not $SkipTests) {
    Write-Host "Otomatik testler calistiriliyor..."
    & $PythonExe -m unittest discover -s (Join-Path $projectRoot "tests") -p "test_*.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Unit testler basarisiz oldu."
    }

    $compileTargets = @(
        "Hidrostatik_Test_Chat.py",
        "hidrostatik_test\__init__.py",
        "hidrostatik_test\app_metadata.py",
        "hidrostatik_test\_pyinstaller_hook.py",
        "hidrostatik_test\data\__init__.py",
        "hidrostatik_test\data\ab_control_table.py",
        "hidrostatik_test\data\botas_reference_table.py",
        "hidrostatik_test\data\coefficient_reference.py",
        "hidrostatik_test\data\gail_reference_table.py",
        "hidrostatik_test\data\pipe_catalog.py",
        "hidrostatik_test\data\water_property_table.py",
        "hidrostatik_test\domain\__init__.py",
        "hidrostatik_test\domain\coefficient_manager.py",
        "hidrostatik_test\domain\hydrotest_core.py",
        "hidrostatik_test\domain\operations.py",
        "hidrostatik_test\domain\pressure_profile.py",
        "hidrostatik_test\domain\pressurization.py",
        "hidrostatik_test\domain\session_manager.py",
        "hidrostatik_test\domain\time_series.py",
        "hidrostatik_test\domain\units.py",
        "hidrostatik_test\domain\water_properties.py",
        "hidrostatik_test\services\__init__.py",
        "hidrostatik_test\services\database.py",
        "hidrostatik_test\services\download_manager.py",
        "hidrostatik_test\services\report_export.py",
        "hidrostatik_test\services\updater.py",
        "hidrostatik_test\services\water_property_table_builder.py",
        "hidrostatik_test\ui\__init__.py",
        "hidrostatik_test\ui\app.py",
        "hidrostatik_test\ui\constants.py",
        "hidrostatik_test\ui\download_dialog.py",
        "hidrostatik_test\ui\helpers.py",
        "hidrostatik_test\ui\validators.py",
        "hidrostatik_test\ui\wizard.py",
        "tools\generate_water_property_table.py",
        "tests\test_ab_control_table.py",
        "tests\test_botas_reference_table.py",
        "tests\test_coefficient_manager.py",
        "tests\test_database.py",
        "tests\test_gail_reference_table.py",
        "tests\test_hydrotest_core.py",
        "tests\test_operations.py",
        "tests\test_pipe_catalog.py",
        "tests\test_pressure_profile.py",
        "tests\test_pressurization.py",
        "tests\test_report_export.py",
        "tests\test_session_manager.py",
        "tests\test_time_series.py",
        "tests\test_ui_workflow.py",
        "tests\test_units.py",
        "tests\test_updater.py",
        "tests\test_validators.py",
        "tests\test_water_properties.py",
        "tests\test_water_property_table.py"
    )

    $compilePaths = $compileTargets | ForEach-Object { Join-Path $projectRoot $_ }
    & $PythonExe -m py_compile @compilePaths
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "py_compile adimi Windows dosya kilidi nedeniyle atlandi. Unit test ve import smoke check devam ediyor."
    }

    & $PythonExe -c "import sys; sys.path.insert(0, r'$projectRoot'); import Hidrostatik_Test_Chat; import hidrostatik_test.app_metadata; import hidrostatik_test.data.ab_control_table; import hidrostatik_test.data.botas_reference_table; import hidrostatik_test.data.gail_reference_table; import hidrostatik_test.data.pipe_catalog; import hidrostatik_test.data.water_property_table; import hidrostatik_test.domain.coefficient_manager; import hidrostatik_test.domain.hydrotest_core; import hidrostatik_test.domain.pressurization; import hidrostatik_test.domain.pressure_profile; import hidrostatik_test.domain.session_manager; import hidrostatik_test.domain.time_series; import hidrostatik_test.domain.water_properties; import hidrostatik_test.services.database; import hidrostatik_test.services.download_manager; import hidrostatik_test.services.report_export; import hidrostatik_test.services.updater; import hidrostatik_test.services.water_property_table_builder; print('import-ok')"
    if ($LASTEXITCODE -ne 0) {
        throw "Import smoke check basarisiz oldu."
    }
}

Write-Host "PyInstaller build basliyor..."
$buildResult = Invoke-PyInstallerBuild `
    -RunId $runId `
    -AppVersion $appVersion `
    -AppName $appName `
    -PublisherName $publisherName `
    -CopyrightNotice $copyrightNotice

# Sessiz "plain fallback" yok: build basarisizsa release artefakti uretilmez.
if ($buildResult.ExitCode -ne 0) {
    throw "PyInstaller build basarisiz oldu (exit code $($buildResult.ExitCode)). Release artefakti uretilmedi."
}

$exePath = $buildResult.ExePath
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Beklenen exe olusmadi: $exePath"
}

if (-not $SkipArchive) {
    Write-Host "Release zip artefakti uretiliyor..."
    $stageRoot = Join-Path $releasePath "stage-$runId"
    $stageAppDir = Join-Path $stageRoot $binaryName
    New-Item -ItemType Directory -Path $stageAppDir -Force | Out-Null
    Copy-Item -LiteralPath $exePath -Destination (Join-Path $stageAppDir "$binaryName.exe") -Force

    New-ReleaseArchive -SourcePath $stageRoot -DestinationPath $archivePath -IncludeBaseDirectory $false
    Assert-ArchiveLayout -ArchivePath $archivePath -BinaryName $binaryName

    # Iki checksum adi da ayni icerigi tasir: <zip>.<...>.sha256.txt updater icin,
    # <...>.sha256.txt dokumante edilen artefakt sozlesmesi icin.
    $hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $hashRecord = "$hash  $([System.IO.Path]::GetFileName($archivePath))"
    Set-Content -LiteralPath $hashPath -Value $hashRecord -Encoding ASCII
    Set-Content -LiteralPath $archiveHashPath -Value $hashRecord -Encoding ASCII

    Write-ReleaseNotes `
        -OutputPath $notesPath `
        -AppName $appName `
        -AppVersion $appVersion `
        -ArtifactName ([System.IO.Path]::GetFileName($archivePath)) `
        -HashFileName ([System.IO.Path]::GetFileName($hashPath)) `
        -ArchiveHashFileName ([System.IO.Path]::GetFileName($archiveHashPath)) `
        -ReleaseTag $releaseTag

    Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Build tamamlandi."
Write-Host "Exe yolu: $exePath"
Write-Host "Windows manifest ve version resource eklendi (manifest surumu $(Get-VersionQuad -AppVersion $appVersion))."
if (-not $SkipArchive) {
    Write-Host "Release zip: $archivePath"
    Write-Host "SHA256: $hashPath"
    Write-Host "SHA256 (updater): $archiveHashPath"
    Write-Host "Release notes: $notesPath"
    Write-Host "Git tag onerisi: $releaseTag"
}
Write-Host "Not: False-positive riski azaltildi ancak kod imzalama olmadan sifir garanti verilemez."
