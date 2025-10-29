$hash = -join ((48..57) + (97..102) | Get-Random -Count 6 | ForEach-Object {[char]$_})
Remove-Item control-broker-*.zip, visual-controller-*.zip, stream-cleaner-*.zip -ErrorAction SilentlyContinue

$services = @(
    @{ Name = 'control_broker'; Path = 'control_broker'; Output = "control-broker-$hash.zip" },
    @{ Name = 'visual_controller'; Path = 'visual_controller'; Output = "visual-controller-$hash.zip" },
    @{ Name = 'stream_cleaner'; Path = 'stream_cleaner'; Output = "stream-cleaner-$hash.zip" }
)

$pythonScript = @"
import os
import sys
import zipfile

service_path = sys.argv[1]
zip_name = sys.argv[2]

with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, _, files in os.walk(service_path):
        for file in files:
            filepath = os.path.join(root, file)
            if os.path.isdir(filepath):
                continue
            arcname = os.path.relpath(filepath, service_path).replace('\\', '/')
            zipf.write(filepath, arcname)
print(f"Created {zip_name}")
"@

foreach ($service in $services) {
    $output = $service.Output
    $path = $service.Path
    if (!(Test-Path $path)) {
        Write-Host "Skipping $path (not found)." -ForegroundColor Yellow
        continue
    }
    $pythonScript | python - $path $output
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Created $output" -ForegroundColor Green
    } else {
        Write-Host "Failed to create $output" -ForegroundColor Red
        break
    }
}
