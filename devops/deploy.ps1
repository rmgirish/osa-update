<#
.SYNOPSIS
    Deploys OpenSource Assist application to an AWS EC2 instance from Windows.

.DESCRIPTION
    This script connects to an AWS EC2 instance via SSH, copies project files or executes
    the remote build & deployment using Docker Compose.

.PARAMETER EC2Host
    The Public IP or Public DNS of the EC2 instance.

.PARAMETER KeyPath
    The path to your AWS EC2 .pem private key file.

.PARAMETER User
    The SSH username for the EC2 instance (Default: ubuntu).

.PARAMETER RemoteDir
    The target directory on the EC2 instance (Default: /home/ubuntu/open-source-assist).

.EXAMPLE
    .\devops\deploy.ps1 -EC2Host "54.210.12.34" -KeyPath "$HOME\.ssh\my-key.pem"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$EC2Host,

    [Parameter(Mandatory=$true)]
    [string]$KeyPath,

    [Parameter(Mandatory=$false)]
    [string]$User = "ubuntu",

    [Parameter(Mandatory=$false)]
    [string]$RemoteDir = "/home/ubuntu/open-source-assist"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $KeyPath)) {
    Write-Error "Private key file not found at: $KeyPath"
    exit 1
}

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Deploying to EC2 ($User@$EC2Host)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Test SSH connection
Write-Host "[1/4] Testing SSH connection to EC2..." -ForegroundColor Yellow
ssh -i $KeyPath -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$User@$EC2Host" "echo 'SSH Connection successful!'"

# 2. Ensure remote directory and setup scripts are ready
Write-Host "[2/4] Preparing remote directory..." -ForegroundColor Yellow
ssh -i $KeyPath -o StrictHostKeyChecking=no "$User@$EC2Host" "mkdir -p $RemoteDir"

# 3. Synchronize project files to EC2 (excluding local temp/venv files)
Write-Host "[3/4] Syncing project files to EC2..." -ForegroundColor Yellow
$tarArchive = "$env:TEMP\deploy_archive.tar.gz"
if (Test-Path $tarArchive) { Remove-Item $tarArchive -Force }

# Create tar archive using native tar (available in Windows 10/11)
Push-Location $RootDir
try {
    tar -czf $tarArchive `
        --exclude=".venv" `
        --exclude="node_modules" `
        --exclude=".git" `
        --exclude="__pycache__" `
        --exclude=".pytest_cache" `
        --exclude="dist" `
        alembic alembic.ini backend frontend data devops docker-compose.yml docker-compose.prod.yml pyproject.toml uv.lock README.md
} finally {
    Pop-Location
}

# Transfer archive and extract on EC2
scp -i $KeyPath -o StrictHostKeyChecking=no $tarArchive "$User@$EC2Host:$RemoteDir/deploy_archive.tar.gz"
Remove-Item $tarArchive -Force -ErrorAction SilentlyContinue

ssh -i $KeyPath -o StrictHostKeyChecking=no "$User@$EC2Host" "cd $RemoteDir && tar -xzf deploy_archive.tar.gz && rm deploy_archive.tar.gz && chmod +x devops/*.sh"

# 4. Trigger remote deployment
Write-Host "[4/4] Running remote build and deployment..." -ForegroundColor Yellow
ssh -i $KeyPath -o StrictHostKeyChecking=no -t "$User@$EC2Host" "cd $RemoteDir && bash devops/deploy.sh"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host " Deployment Completed Successfully!" -ForegroundColor Green
Write-Host " Open your browser at: http://$EC2Host" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
