param(
    [string]$PythonExe = "python",
    [switch]$SkipFrontendBuild,
    [switch]$SkipSigning
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$metadataPath = Join-Path $projectRoot "hidrostatik_test\app_metadata.py"
$specPath = Join-Path $projectRoot "HydroWeb.spec"
$issPath = Join-Path $projectRoot "installer\hydro_web.iss"
$manifestSourcePath = Join-Path $projectRoot "windows_manifest.xml"
$releasePath = Join-Path $projectRoot "release"
$signingScriptPath = Join-Path $projectRoot "tools\update_signing.py"
$userProfilePath = [Environment]::GetFolderPath("UserProfile")
$signingKeyPath = if ($env:HYDRO_UPDATE_SIGNING_KEY) {
    $env:HYDRO_UPDATE_SIGNING_KEY
} else {
    Join-Path $userProfilePath ".config\hydro\update_signing_key.pem"
}

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

function Assert-UpdateSigningReady {
    if ($SkipSigning) {
        Write-Warning "UYARI: -SkipSigning etkin. Paketler IMZASIZ uretilecek."
        return
    }
    if (-not (Test-Path -LiteralPath $signingScriptPath)) {
        throw "Imzalama araci bulunamadi: $signingScriptPath"
    }
    if (-not (Test-Path -LiteralPath $signingKeyPath)) {
        throw "Guncelleme imzalama anahtari bulunamadi: $signingKeyPath"
    }
    $keyInfo = & $PythonExe $signingScriptPath fingerprint --key $signingKeyPath
    if ($LASTEXITCODE -ne 0) {
        throw "Ozel anahtar okunamadi: $signingKeyPath"
    }
    $publicLine = @($keyInfo) | Where-Object { $_ -like "Public key (base64): *" } | Select-Object -First 1
    if (-not $publicLine) {
        throw "Anahtar parmak izi ciktisi okunamadi: $keyInfo"
    }
    $signingPublicKey = ($publicLine -replace "^Public key \(base64\):\s*", "").Trim()
    $embeddedPublicKey = Get-MetadataValue "UPDATE_SIGNING_PUBLIC_KEY"
    if ($signingPublicKey -ne $embeddedPublicKey) {
        throw "Ozel anahtar app_metadata.UPDATE_SIGNING_PUBLIC_KEY ile eslesmiyor."
    }
    Write-Host "Imzalama anahtari hazir: $signingKeyPath"
}

function Write-Sha256File {
    param(
        [string]$ArtifactPath,
        [string]$HashFilePath
    )

    $hash = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $name = [System.IO.Path]::GetFileName($ArtifactPath)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($HashFilePath, "$hash  $name`n", $utf8NoBom)
    return $hash
}

function Invoke-ArtifactSigning {
    param([string]$ArtifactPath)

    if ($SkipSigning) {
        return $null
    }
    $signaturePath = "$ArtifactPath.sig"
    & $PythonExe $signingScriptPath sign $ArtifactPath --key $signingKeyPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Artefakt imzalanamadi: $ArtifactPath"
    }
    & $PythonExe $signingScriptPath verify $ArtifactPath $signaturePath --key $signingKeyPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Imza dogrulanamadi: $ArtifactPath"
    }
    return $signaturePath
}

function Write-VersionedManifest {
    param(
        [string]$SourcePath,
        [string]$OutputPath,
        [string]$AppVersion
    )

    $versionQuad = Get-VersionQuad -AppVersion $AppVersion
    $content = Get-Content -LiteralPath $SourcePath -Raw
    $updated = [regex]::Replace(
        $content,
        '(<assemblyIdentity\s+version=")[^"]+(")',
        { param($match) $match.Groups[1].Value + $versionQuad + $match.Groups[2].Value }
    )
    $updated = $updated -replace 'name="HidrostatikTest"', 'name="HydroWeb"'
    $updated = $updated -replace '<description>[^<]*</description>', '<description>HYDRO Web</description>'
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($OutputPath, $updated, $utf8NoBom)
}

function Write-VersionInfoFile {
    param(
        [string]$OutputPath,
        [string]$AppVersion,
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
          StringStruct('FileDescription', 'HYDRO Web'),
          StringStruct('FileVersion', '$AppVersion'),
          StringStruct('InternalName', 'HydroWeb'),
          StringStruct('OriginalFilename', 'HydroWeb.exe'),
          StringStruct('ProductName', 'HYDRO Web'),
          StringStruct('ProductVersion', '$AppVersion'),
          StringStruct('LegalCopyright', '$CopyrightNotice')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($OutputPath, $content, $utf8NoBom)
}

function Resolve-IsccPath {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $choco = Get-Command choco -ErrorAction SilentlyContinue
    if ($choco) {
        Write-Host "Inno Setup 6 bulunamadi; Chocolatey ile kuruluyor..."
        & $choco.Source install innosetup -y --no-progress | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Chocolatey ile Inno Setup kurulumu basarisiz oldu."
        }
        foreach ($candidate in $candidates) {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                return $candidate
            }
        }
        $cmdAfter = Get-Command iscc -ErrorAction SilentlyContinue
        if ($cmdAfter) {
            return $cmdAfter.Source
        }
    }
    throw "Inno Setup 6 (ISCC.exe) bulunamadi."
}

$appVersion = Get-MetadataValue "APP_VERSION"
$publisherName = Get-MetadataValue "PUBLISHER_NAME"
$copyrightNotice = Get-MetadataValue "COPYRIGHT_NOTICE"
$runId = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmss")

Write-Host "HYDRO Web Windows build hazirlaniyor (v$appVersion)..."
Assert-UpdateSigningReady

New-Item -ItemType Directory -Path $releasePath -Force | Out-Null

$frontendDistIndex = Join-Path $projectRoot "webapp\frontend\dist\index.html"
if ($SkipFrontendBuild -and (Test-Path -LiteralPath $frontendDistIndex)) {
    Write-Host "Frontend derlemesi atlandi (-SkipFrontendBuild)."
} else {
    Write-Host "Frontend derleniyor (webapp\frontend)..."
    Push-Location (Join-Path $projectRoot "webapp\frontend")
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci basarisiz oldu." }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build basarisiz oldu." }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $frontendDistIndex)) {
    throw "Frontend dist/index.html olusmadi: $frontendDistIndex"
}

$tempBuildDir = Join-Path $releasePath "web-build-meta-$runId"
New-Item -ItemType Directory -Path $tempBuildDir -Force | Out-Null
$manifestOut = Join-Path $tempBuildDir "windows_manifest.xml"
$versionOut = Join-Path $tempBuildDir "version_info.txt"
Write-VersionedManifest -SourcePath $manifestSourcePath -OutputPath $manifestOut -AppVersion $appVersion
Write-VersionInfoFile -OutputPath $versionOut -AppVersion $appVersion -PublisherName $publisherName -CopyrightNotice $copyrightNotice

$env:HYDROWEB_WINDOWS_MANIFEST = $manifestOut
$env:HYDROWEB_WINDOWS_VERSION_FILE = $versionOut

$distDir = Join-Path $projectRoot "dist\HydroWeb"
$buildWorkDir = Join-Path $projectRoot "build\HydroWeb"
if (Test-Path -LiteralPath $distDir) { Remove-Item -LiteralPath $distDir -Recurse -Force }
if (Test-Path -LiteralPath $buildWorkDir) { Remove-Item -LiteralPath $buildWorkDir -Recurse -Force }

try {
    Push-Location $projectRoot
    Write-Host "PyInstaller derlemesi baslatiliyor (HydroWeb.spec)..."
    & $PythonExe -m PyInstaller --noconfirm --clean $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller HydroWeb.spec derlemesi basarisiz (exit code $LASTEXITCODE)."
    }
} finally {
    Pop-Location
    Remove-Item -LiteralPath $tempBuildDir -Recurse -Force -ErrorAction SilentlyContinue
}

$exePath = Join-Path $distDir "HydroWeb.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Beklenen HydroWeb.exe olusmadi: $exePath"
}

Write-Host "Paketli HydroWeb.exe --self-test calistiriliyor..."
$selfTestProc = Start-Process -FilePath $exePath -ArgumentList "--self-test" -Wait -PassThru
if ($selfTestProc.ExitCode -ne 0) {
    throw "HydroWeb.exe --self-test basarisiz (exit code $($selfTestProc.ExitCode))."
}
Write-Host "HydroWeb.exe --self-test basarili."

# --- Tasinabilir ZIP --------------------------------------------------------
$baseName = "HydroWeb-v$appVersion-windows-x64"
$portableZipPath = Join-Path $releasePath "$baseName-portable.zip"
$stageZipRoot = Join-Path $releasePath "stage-web-$runId"
$stageHydroWebDir = Join-Path $stageZipRoot "HydroWeb"
New-Item -ItemType Directory -Path $stageHydroWebDir -Force | Out-Null
Copy-Item -Path (Join-Path $distDir "*") -Destination $stageHydroWebDir -Recurse -Force

if (Test-Path -LiteralPath $portableZipPath) {
    Remove-Item -LiteralPath $portableZipPath -Force
}
$zipScript = @"
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1]).resolve()
out = pathlib.Path(sys.argv[2]).resolve()
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for p in sorted(root.rglob('*')):
        if p.is_file():
            zf.write(p, p.relative_to(root).as_posix())
"@
& $PythonExe -c $zipScript $stageZipRoot $portableZipPath
if ($LASTEXITCODE -ne 0) {
    throw "Portable ZIP olusturulamadi (exit code $LASTEXITCODE)."
}
Remove-Item -LiteralPath $stageZipRoot -Recurse -Force -ErrorAction SilentlyContinue

# --- Inno Setup Kurulum EXE -------------------------------------------------
$isccExe = Resolve-IsccPath
$setupExePath = Join-Path $releasePath "$baseName-setup.exe"
if (Test-Path -LiteralPath $setupExePath) {
    Remove-Item -LiteralPath $setupExePath -Force
}
Write-Host "Inno Setup ile kurulum dosyasi derleniyor ($isccExe)..."
& $isccExe "/DMyAppVersion=$appVersion" $issPath
if ($LASTEXITCODE -ne 0) {
    throw "ISCC.exe basarisiz oldu (exit code $LASTEXITCODE)."
}
if (-not (Test-Path -LiteralPath $setupExePath)) {
    throw "Setup EXE olusmadi: $setupExePath"
}

# --- Setup EXE sessiz kurulum + --self-test dogrulamasi ---------------------
$smokeInstallDir = Join-Path $releasePath "smoke-install-$runId"
Write-Host "Kurulum EXE sessiz kurulum testi yapiliyor..."
$installProc = Start-Process `
    -FilePath $setupExePath `
    -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /SP- `"/DIR=$smokeInstallDir`"" `
    -Wait `
    -PassThru
if ($installProc.ExitCode -ne 0) {
    throw "Setup EXE sessiz kurulumu basarisiz (exit code $($installProc.ExitCode))."
}
$installedExe = Join-Path $smokeInstallDir "HydroWeb.exe"
if (-not (Test-Path -LiteralPath $installedExe)) {
    throw "Kurulan dizinde HydroWeb.exe bulunamadi: $installedExe"
}
$installedTestProc = Start-Process -FilePath $installedExe -ArgumentList "--self-test" -Wait -PassThru
if ($installedTestProc.ExitCode -ne 0) {
    throw "Kurulan HydroWeb.exe --self-test basarisiz (exit code $($installedTestProc.ExitCode))."
}
Remove-Item -LiteralPath $smokeInstallDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Setup EXE sessiz kurulum ve --self-test dogrulandi."

# --- SHA-256 & Ed25519 Imzalar ----------------------------------------------
$setupShaPath = "$setupExePath.sha256.txt"
$portableShaPath = "$portableZipPath.sha256.txt"
$setupHash = Write-Sha256File -ArtifactPath $setupExePath -HashFilePath $setupShaPath
$portableHash = Write-Sha256File -ArtifactPath $portableZipPath -HashFilePath $portableShaPath

$setupSigPath = Invoke-ArtifactSigning -ArtifactPath $setupExePath
$portableSigPath = Invoke-ArtifactSigning -ArtifactPath $portableZipPath

$notesPath = Join-Path $releasePath "$baseName-RELEASE-NOTES.md"
$setupSigName = if ($setupSigPath) { [System.IO.Path]::GetFileName($setupSigPath) } else { "(imza yok)" }
$portableSigName = if ($portableSigPath) { [System.IO.Path]::GetFileName($portableSigPath) } else { "(imza yok)" }

$notes = @"
# HYDRO Web v$appVersion (Windows x64)

## Included Artifacts
- $([System.IO.Path]::GetFileName($setupExePath)) (Kurulum EXE / Installer)
- $setupSigName
- $([System.IO.Path]::GetFileName($setupShaPath))
- $([System.IO.Path]::GetFileName($portableZipPath)) (Tasinabilir / Portable ZIP)
- $portableSigName
- $([System.IO.Path]::GetFileName($portableShaPath))

## Verification Summary
- Setup EXE SHA256: $setupHash
- Portable ZIP SHA256: $portableHash
- PyInstaller bundle --self-test: PASS
- Silent Inno Setup install + installed HydroWeb.exe --self-test: PASS
- Ed25519 Signatures: $setupSigName, $portableSigName

## Installation (Windows 10/11 x64)
1. ``$([System.IO.Path]::GetFileName($setupExePath))`` kurulum dosyasini calistirin (veya portable zip'i acip ``HydroWeb\HydroWeb.exe`` calistirin).
2. SmartScreen uyarisi cikarsa "Daha fazla bilgi" -> "Yine de calistir" secin.
3. Uygulama yerel sunucuyu baslatip varsayilan tarayicinizda HYDRO Web arayuzunu otomatik acar.
"@

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($notesPath, ($notes -replace "`r`n", "`n"), $utf8NoBom)

Write-Host ""
Write-Host "HYDRO Web Windows build tamamlandi:"
Write-Host "  Setup EXE   : $setupExePath"
Write-Host "  Portable ZIP: $portableZipPath"
Write-Host "  Notes       : $notesPath"
