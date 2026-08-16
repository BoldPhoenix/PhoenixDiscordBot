# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Requesting administrator privileges..."
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Stop the agent service
Write-Host "Stopping PhoenixArkAgent service..."
try {
    Stop-Service -Name 'PhoenixArkAgent' -Force -ErrorAction Stop
    Write-Host "Service stopped successfully"
} catch {
    Write-Host "Warning: Could not stop service: $_"
}

# Wait a moment for service to fully stop
Start-Sleep -Seconds 3

# Copy new executables
Write-Host "Copying new executables..."
Copy-Item 'C:/PhoenixBot\remote_agent\dist\PhoenixArkAgent.exe' 'C:\Program Files\Phoenix Ark Agent\PhoenixArkAgent.exe' -Force
Copy-Item 'C:/PhoenixBot\remote_agent\dist\PhoenixARKServerService.exe' 'C:\Program Files\Phoenix Ark Agent\PhoenixARKServerService.exe' -Force

Write-Host "Executables copied successfully"

# Start the service
Write-Host "Starting PhoenixArkAgent service..."
try {
    Start-Service -Name 'PhoenixArkAgent' -ErrorAction Stop
    Write-Host "Service started successfully"
} catch {
    Write-Host "Error starting service: $_"
    Read-Host "Press Enter to exit"
    exit 1
}

# Verify service is running
Start-Sleep -Seconds 2
$service = Get-Service -Name 'PhoenixArkAgent' -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq 'Running') {
    Write-Host "Deployment complete! Service is running."
} else {
    Write-Host "Warning: Service status: $($service.Status)"
}

Read-Host "Press Enter to exit"
