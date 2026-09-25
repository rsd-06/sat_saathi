$pages = @(
    "http://localhost:3100/en",
    "http://localhost:3100/en/dashboard",
    "http://localhost:3100/en/workspace",
    "http://localhost:3100/en/history",
    "http://localhost:3100/en/review",
    "http://localhost:3100/en/settings"
)

Write-Host "Warming up Next.js pages..."
foreach ($page in $pages) {
    Write-Host "Fetching $page"
    try {
        Invoke-WebRequest -Uri $page -UseBasicParsing -TimeoutSec 10 | Out-Null
        Write-Host "OK: $page" -ForegroundColor Green
    } catch {
        Write-Host "Failed: $page" -ForegroundColor Red
    }
}
Write-Host "Warm-up complete!"
