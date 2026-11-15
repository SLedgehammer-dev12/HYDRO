param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..")
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "=== Windows Build Verification ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

# Step 1: Clean previous builds
Write-Host "`n[1/5] Cleaning previous builds..." -ForegroundColor Yellow
$releaseDir = Join-Path $ProjectRoot "release"
if (Test-Path $releaseDir) {
    Remove-Item -Path "$releaseDir\*" -Recurse -Force -ErrorAction SilentlyContinue
}

# Step 2: Run tests
Write-Host "`n[2/5] Running unit tests..." -ForegroundColor Yellow
python -m unittest discover -s tests -p "test_*.py" -v
if ($LASTEXITCODE -ne 0) {
    throw "Unit tests failed."
}

# Step 3: Run build script
Write-Host "`n[3/5] Running build_exe.ps1..." -ForegroundColor Yellow
& (Join-Path $ProjectRoot "build_exe.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Build script failed."
}

# Step 4: Verify artifacts
Write-Host "`n[4/5] Verifying build artifacts..." -ForegroundColor Yellow
$zipFiles = Get-ChildItem -Path $releaseDir -Filter "*.zip" | Sort-Object LastWriteTime -Descending
$exeFiles = Get-ChildItem -Path $releaseDir -Filter "*.exe" | Sort-Object LastWriteTime -Descending
if ($zipFiles) {
    $artifact = $zipFiles[0]
    Write-Host "Found release archive: $($artifact.Name)" -ForegroundColor Green
} elseif ($exeFiles) {
    $artifact = $exeFiles[0]
    Write-Host "Found executable: $($artifact.Name)" -ForegroundColor Green
} else {
    throw "No .zip or .exe file found in release directory."
}
Write-Host "Size: $('{0:N0}' -f ($artifact.Length / 1MB)) MB"

if ($artifact.Length -lt 10MB) {
    throw "Artifact too small ($($artifact.Length) bytes). Expected at least 10 MB."
}

# Step 5: Verify related artifacts
Write-Host "`n[5/5] Verifying release artifacts..." -ForegroundColor Yellow
$shaFiles = Get-ChildItem -Path $releaseDir -Filter "*.sha256.txt"
if (-not $shaFiles) {
    throw "No SHA-256 file found."
} else {
    # Prefer <artifact>.sha256.txt, fall back to the release-stem checksum.
    $preferred = Join-Path $releaseDir "$($artifact.Name).sha256.txt"
    $shaPath = if (Test-Path $preferred) { $preferred } else { $shaFiles[0].FullName }
    $expectedHash = ((Get-Content $shaPath -Raw) -split '\s+')[0].Trim().ToLower()
    $actualHash = (Get-FileHash -Path $artifact.FullName -Algorithm SHA256).Hash.ToLower()
    if ($expectedHash -ne $actualHash) {
        throw "SHA-256 mismatch! Expected $expectedHash, got $actualHash"
    }
    Write-Host "SHA-256 verified: $expectedHash" -ForegroundColor Green
}

Write-Host "`n=== Windows Build Verification PASSED ===" -ForegroundColor Green
