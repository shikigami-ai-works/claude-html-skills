# render.ps1 - build/verify pipeline for the a4-booklet skill (ASCII only, Windows PowerShell 5.1+)
#
# Usage examples (run from anywhere):
#   powershell -File render.ps1 -Html D:\work\foo\foo.html -MakeNoise
#   powershell -File render.ps1 -Html D:\work\foo\foo.html -Screenshot -PageCount 14
#   powershell -File render.ps1 -Html D:\work\foo\foo.html -Screenshot -PageCount 14 -Scale 2
#   powershell -File render.ps1 -Html D:\work\foo\foo.html -Pdf
#   powershell -File render.ps1 -Html D:\work\foo\foo.html -Zip
#
# -MakeNoise   : generate img/noise.png (96x96 gray tile, seed 42) next to the HTML
# -Screenshot  : capture full page as one tall PNG (preview.png) and slice into pages/<base>-pNN.png
# -Pdf         : print to <base>.pdf via headless Chrome, report size and page count
# -Zip         : zip pages/*.png and a JPEG(q88) copy into <base>-pages.zip / <base>-pages-jpg.zip
# -Scale       : 1 for quick visual check, 2 for deliverable page images
# -PageH       : CSS px per A4 page. 296mm at 96dpi = 1118.74 (verified 2026-08-26).
#                If slices drift (page tops cut off on later pages), remeasure here.

param(
    [Parameter(Mandatory=$true)][string]$Html,
    [switch]$MakeNoise,
    [switch]$Screenshot,
    [switch]$Pdf,
    [switch]$Zip,
    [int]$PageCount = 0,
    [int]$Scale = 1,
    [double]$PageH = 1118.74,
    [string]$Chrome = ""
)

$ErrorActionPreference = "Stop"

# Chrome: -Chrome > $env:CHROME_PATH > Chrome in Program Files / LocalAppData > Edge
if (-not $Chrome) { $Chrome = $env:CHROME_PATH }
if (-not $Chrome) {
    $cands = @()
    foreach ($b in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if ($b) { $cands += (Join-Path $b "Google\Chrome\Application\chrome.exe") }
    }
    foreach ($b in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if ($b) { $cands += (Join-Path $b "Microsoft\Edge\Application\msedge.exe") }
    }
    $Chrome = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Chrome) { throw "Chrome/Edge not found. Pass -Chrome <path> or set CHROME_PATH." }
}
# A separate profile: with the user's everyday Chrome running, headless Chrome may exit without writing anything.
$ChromeProfile = Join-Path $env:TEMP "a4-booklet-chrome-profile"
$HtmlPath = (Resolve-Path $Html).Path
$Dir  = Split-Path -Parent $HtmlPath
$Base = [IO.Path]::GetFileNameWithoutExtension($HtmlPath)
$Uri  = "file:///" + $HtmlPath.Replace('\', '/')

Add-Type -AssemblyName System.Drawing

if ($MakeNoise) {
    $imgDir = Join-Path $Dir "img"
    if (-not (Test-Path $imgDir)) { New-Item -ItemType Directory -Path $imgDir | Out-Null }
    $bmp = New-Object System.Drawing.Bitmap 96, 96
    $rnd = New-Object System.Random 42
    for ($y = 0; $y -lt 96; $y++) {
        for ($x = 0; $x -lt 96; $x++) {
            $v = $rnd.Next(0, 256)
            $bmp.SetPixel($x, $y, [System.Drawing.Color]::FromArgb(255, $v, $v, $v))
        }
    }
    $noisePath = Join-Path $imgDir "noise.png"
    $bmp.Save($noisePath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    "noise: $noisePath ($((Get-Item $noisePath).Length) bytes)"
}

if ($Screenshot) {
    if ($PageCount -lt 1) { throw "-Screenshot requires -PageCount" }
    $h = [int][Math]::Ceiling($PageCount * $PageH)
    $shot = Join-Path $Dir "preview.png"
    & $Chrome --headless=new --disable-gpu --no-first-run --hide-scrollbars --user-data-dir="$ChromeProfile" `
        --virtual-time-budget=25000 --force-device-scale-factor=$Scale `
        --window-size="794,$h" --screenshot="$shot" $Uri | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "chrome screenshot exit $LASTEXITCODE" }
    $img = [System.Drawing.Image]::FromFile($shot)
    "shot: $($img.Width)x$($img.Height)"
    $pagesDir = Join-Path $Dir "pages"
    if (-not (Test-Path $pagesDir)) { New-Item -ItemType Directory -Path $pagesDir | Out-Null }
    $ph = $img.Height / $PageCount
    for ($i = 0; $i -lt $PageCount; $i++) {
        $top = [int][Math]::Ceiling($i * $ph) + 2
        $bot = [int][Math]::Floor(($i + 1) * $ph) - 2
        $hgt = $bot - $top
        $page = New-Object System.Drawing.Bitmap $img.Width, $hgt
        $g = [System.Drawing.Graphics]::FromImage($page)
        $src = New-Object System.Drawing.Rectangle 0, $top, $img.Width, $hgt
        $dst = New-Object System.Drawing.Rectangle 0, 0, $img.Width, $hgt
        $g.DrawImage($img, $dst, $src, [System.Drawing.GraphicsUnit]::Pixel)
        $g.Dispose()
        $out = Join-Path $pagesDir ("{0}-p{1:00}.png" -f $Base, ($i + 1))
        $page.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
        $page.Dispose()
    }
    $img.Dispose()
    "pages: $PageCount sliced into $pagesDir"
}

if ($Pdf) {
    # NOTE: do not name locals like a param ($pdf vs [switch]$Pdf collides; PS is case-insensitive)
    $pdfPath = Join-Path $Dir "$Base.pdf"
    $before = if (Test-Path $pdfPath) { (Get-Item $pdfPath).LastWriteTime } else { [datetime]::MinValue }
    & $Chrome --headless=new --disable-gpu --no-first-run --user-data-dir="$ChromeProfile" `
        --virtual-time-budget=25000 --no-pdf-header-footer `
        --print-to-pdf="$pdfPath" $Uri | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "chrome pdf exit $LASTEXITCODE" }
    if (-not (Test-Path $pdfPath) -or (Get-Item $pdfPath).LastWriteTime -le $before) { throw "pdf was not written: $pdfPath" }
    "pdf: $pdfPath ($((Get-Item $pdfPath).Length) bytes)"
    # Count "/Type /Page" objects (not /Pages). No external library needed.
    $raw = [System.Text.Encoding]::GetEncoding(28591).GetString([System.IO.File]::ReadAllBytes($pdfPath))
    $count = ([regex]::Matches($raw, '/Type\s*/Page[^s]')).Count
    "pdf pages: $count"
}

if ($Zip) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $pagesDir = Join-Path $Dir "pages"
    if (-not (Test-Path $pagesDir)) { throw "-Zip requires pages/ (run -Screenshot first)" }
    $jpgDir = Join-Path $Dir "pages-jpg"
    if (-not (Test-Path $jpgDir)) { New-Item -ItemType Directory -Path $jpgDir | Out-Null }
    $enc = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/jpeg" }
    $prm = New-Object System.Drawing.Imaging.EncoderParameters 1
    $prm.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, [long]88)
    Get-ChildItem $pagesDir -Filter "*.png" | ForEach-Object {
        $src = [System.Drawing.Image]::FromFile($_.FullName)
        $jpg = Join-Path $jpgDir ($_.BaseName + ".jpg")
        $src.Save($jpg, $enc, $prm)
        $src.Dispose()
    }
    foreach ($pair in @(@($pagesDir, "$Base-pages.zip"), @($jpgDir, "$Base-pages-jpg.zip"))) {
        $zipPath = Join-Path $Dir $pair[1]
        $tmp = "$zipPath.tmp"
        if (Test-Path $tmp) { [System.IO.File]::Delete($tmp) }
        [System.IO.Compression.ZipFile]::CreateFromDirectory($pair[0], $tmp)
        [System.IO.File]::Copy($tmp, $zipPath, $true)
        [System.IO.File]::Delete($tmp)
        "zip: $zipPath ($((Get-Item $zipPath).Length) bytes)"
    }
}
