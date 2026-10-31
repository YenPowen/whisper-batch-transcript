# 一键打包：生成 dist\批量提取视频文案工具v6\
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

Push-Location $root
try {
    python -m PyInstaller --noconfirm --clean `
        --distpath "$root\dist" `
        --workpath "$root\build" `
        "$here\v6.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败，退出码 $LASTEXITCODE" }

    $dist = Join-Path $root "dist\批量提取视频文案工具v6"
    foreach ($f in @("ffmpeg.exe", "ffprobe.exe", "config_v6.json")) {
        $p = Join-Path $root $f
        if (Test-Path $p) { Copy-Item $p $dist -Force }
    }
    Write-Host "打包完成: $dist"
} finally {
    Pop-Location
}
