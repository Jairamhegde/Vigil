<#
.SYNOPSIS
    Deploys Vigil to Azure with Terraform. Safe to re-run (redeploys).

.DESCRIPTION
    Azure services (see DEPLOYMENT.md):
        Azure Static Web Apps                    React dashboard
        Azure Container Apps                     FastAPI backend
        Azure Database for PostgreSQL            data
        Azure Key Vault                          database URL, admin password, signing key
        + Container Registry, Managed Identity, Log Analytics

    1. Checks tools, Azure login, the PC clock, and registers resource providers.
    2. terraform apply (base): resource group, container registry, managed identity + AcrPull.
    3. Builds the API image with Docker Desktop (started automatically) and pushes it to the registry.
       Without Docker it tries a cloud build (az acr build), which student subscriptions block.
    4. terraform apply (all): PostgreSQL, Key Vault, Container Apps, Static Web App, Log Analytics.
    5. Waits for the API: its first start loads data/ into PostgreSQL.
    6. Builds the dashboard with the API URL and uploads it to Static Web Apps.

    Tear everything down with .\destroy.ps1.

.EXAMPLE
    .\deploy.ps1
.EXAMPLE
    .\deploy.ps1 -Location centralindia -MinReplicas 1
#>
[CmdletBinding()]
param (
    [string]$Location,
    # PostgreSQL region, when the subscription cannot create it in -Location (SkuNotAvailable)
    [string]$DatabaseLocation,
    [string]$Prefix,
    [ValidateSet(0, 1)][int]$MinReplicas,
    [string]$AdminPassword,
    [string]$Subscription,
    # Auto: local Docker (started if needed), else build in Azure (az acr build). Cloud / Local: force one.
    [ValidateSet("Auto", "Cloud", "Local")][string]$Build = "Auto"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$TfDir = Join-Path $Root "terraform"
$FrontendDir = Join-Path $Root "frontend"
$SettingsFile = Join-Path $TfDir "deploy.auto.tfvars.json"   # git-ignored; remembers options between runs
$SwaCli = "@azure/static-web-apps-cli@2.0.10"

function Write-Step($number, $text) { Write-Host "`n[$number/6] $text" -ForegroundColor Yellow }
function Write-Ok($text) { Write-Host "      $text" -ForegroundColor Green }
function Write-Info($text) { Write-Host "      $text" -ForegroundColor Gray }
function Write-Warn($text) { Write-Host "      $text" -ForegroundColor Yellow }

# Runs a native command and stops the script if it fails. Success is judged by the exit code only:
# docker, terraform and npm write normal progress to stderr, which Windows PowerShell 5.1 would
# otherwise turn into a fatal error whenever the script's output is redirected (logs, CI).
function Invoke-Checked {
    param([string]$What, [scriptblock]$Command)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

# Runs a native command for its output only; never throws on stderr.
function Invoke-Quiet {
    param([scriptblock]$Command)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $output = & $Command 2>$null } finally { $ErrorActionPreference = $previous }
    return [pscustomobject]@{ Output = $output; Ok = ($LASTEXITCODE -eq 0) }
}

function Get-TfOutput($name) {
    $result = Invoke-Quiet { terraform "-chdir=$TfDir" output -raw $name }
    if (-not $result.Ok) { throw "Could not read Terraform output '$name'." }
    return ($result.Output -join "").Trim()
}

function Wait-Url($url, $minutes, $what) {
    $deadline = (Get-Date).AddMinutes($minutes)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
        Write-Info "waiting for $what..."
        Start-Sleep -Seconds 10
    }
    return $false
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "     Vigil -> Azure (Static Web Apps + Container Apps +     " -ForegroundColor Cyan
Write-Host "            PostgreSQL + Key Vault), via Terraform           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# ---------------------------------------------------------------- 1. tools, login, clock, providers
Write-Step 1 "Checking tools, Azure login and clock..."

foreach ($tool in @("az", "terraform", "node", "npm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "'$tool' is not installed or not on PATH. See DEPLOYMENT.md (Deploy section)."
    }
}

if ($Subscription) { Invoke-Checked "az account set" { az account set --subscription $Subscription } }

$account = Invoke-Quiet { az account show -o json }
if (-not $account.Ok) {
    Write-Info "Not signed in, opening Azure login..."
    Invoke-Checked "az login" { az login --output none }
    $account = Invoke-Quiet { az account show -o json }
}
$account = ($account.Output -join "") | ConvertFrom-Json
$env:ARM_SUBSCRIPTION_ID = $account.id
Write-Ok "Signed in as $($account.user.name)"
Write-Ok "Subscription: $($account.name) ($($account.id))"

# Some Azure calls are signed with the PC's clock and are rejected when it is more than 15 minutes off
try {
    $azureNow = [DateTime]::Parse((Invoke-WebRequest -Uri "https://management.azure.com/" -Method Head -UseBasicParsing -TimeoutSec 20 -ErrorAction Stop).Headers["Date"]).ToUniversalTime()
} catch {
    $azureNow = if ($_.Exception.Response) { [DateTime]::Parse($_.Exception.Response.Headers["Date"]).ToUniversalTime() } else { $null }
}
if ($azureNow) {
    $skew = [Math]::Abs(((Get-Date).ToUniversalTime() - $azureNow).TotalMinutes)
    if ($skew -gt 5) {
        Write-Warn "Your PC clock is $([Math]::Round($skew)) minutes off Azure's time. Fix it in Settings > Time & language >"
        Write-Warn "Date & time (Set time automatically + Sync now) if a step below fails with 'AuthenticationFailed'."
    } else {
        Write-Ok "Clock is in sync with Azure."
    }
}

# Providers only need registering once per subscription. Skip the ones already done, start the rest
# without --wait (its fixed 5-minute HTTP timeout fails when Azure is slow) and poll for up to 10 minutes.
Write-Info "Checking resource providers..."
$providers = @("Microsoft.App", "Microsoft.ContainerRegistry", "Microsoft.OperationalInsights", "Microsoft.ManagedIdentity",
               "Microsoft.DBforPostgreSQL", "Microsoft.KeyVault", "Microsoft.Web")
$pending = @()
foreach ($ns in $providers) {
    $state = ((Invoke-Quiet { az provider show --namespace $ns --query registrationState -o tsv }).Output -join "").Trim()
    if ($state -ne "Registered") {
        Write-Info "Registering $ns (was: $(if ($state) { $state } else { 'unknown' }))..."
        $null = Invoke-Quiet { az provider register --namespace $ns --output none }
        $pending += $ns
    }
}
$deadline = (Get-Date).AddMinutes(10)
while ($pending.Count -gt 0 -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 10
    $still = @()
    foreach ($ns in $pending) {
        $state = ((Invoke-Quiet { az provider show --namespace $ns --query registrationState -o tsv }).Output -join "").Trim()
        if ($state -ne "Registered") { $still += $ns }
    }
    $pending = $still
}
if ($pending.Count -gt 0) {
    Write-Warn "Still registering after 10 minutes: $($pending -join ', '). Continuing; Terraform waits for them too."
} else {
    Write-Ok "Providers registered."
}

# Remember options between runs, so a plain .\deploy.ps1 redeploys the same way
# (and a custom admin password is not replaced by a generated one).
$settings = @{}
if (Test-Path $SettingsFile) {
    (Get-Content $SettingsFile -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $settings[$_.Name] = $_.Value }
}
if ($PSBoundParameters.ContainsKey("Location"))      { $settings["location"] = $Location }
if ($PSBoundParameters.ContainsKey("DatabaseLocation")) { $settings["postgres_location"] = $DatabaseLocation }
if ($PSBoundParameters.ContainsKey("Prefix"))        { $settings["prefix"] = $Prefix }
if ($PSBoundParameters.ContainsKey("MinReplicas"))   { $settings["min_replicas"] = $MinReplicas }
if ($PSBoundParameters.ContainsKey("AdminPassword")) { $settings["admin_password"] = $AdminPassword }
$settings | ConvertTo-Json | Set-Content -Path $SettingsFile -Encoding ascii

# ---------------------------------------------------------------- 2. base infrastructure
Write-Step 2 "Creating base infrastructure (resource group, registry, identity)..."
Invoke-Checked "terraform init" { terraform "-chdir=$TfDir" init -input=false -upgrade }

# Earlier single-container layout kept a revocation log on an Azure Files share. PostgreSQL replaces
# it; Terraform cannot even read the share when the PC clock is off, so remove it via Azure directly.
$tracked = @((Invoke-Quiet { terraform "-chdir=$TfDir" state list }).Output)
if ($tracked -contains "azurerm_storage_account.state") {
    $oldRg = Get-TfOutput "resource_group"
    $oldAccount = ((Invoke-Quiet { az storage account list -g $oldRg --query "[?tags.project=='vigil'].name | [0]" -o tsv }).Output -join "").Trim()
    Write-Info "Removing the old revocation-log storage ($oldAccount), now replaced by PostgreSQL..."
    foreach ($address in @("azurerm_container_app_environment_storage.state", "azurerm_storage_share.state", "azurerm_storage_account.state")) {
        if ($tracked -contains $address) { Invoke-Checked "terraform state rm" { terraform "-chdir=$TfDir" state rm $address } }
    }
    if ($oldAccount) { Invoke-Checked "az storage account delete" { az storage account delete -n $oldAccount -g $oldRg --yes } }
}

Invoke-Checked "terraform apply (base)" {
    terraform "-chdir=$TfDir" apply -input=false -auto-approve `
        "-target=azurerm_resource_group.main" `
        "-target=azurerm_container_registry.main" `
        "-target=azurerm_role_assignment.acr_pull"
}
$resourceGroup = Get-TfOutput "resource_group"
$acrName = Get-TfOutput "acr_name"
Write-Ok "Resource group: $resourceGroup"
Write-Ok "Registry:       $acrName"

# ---------------------------------------------------------------- 3. API image
$commit = Invoke-Quiet { git -C $Root rev-parse --short HEAD }
$tag = (Get-Date -Format "yyyyMMdd-HHmmss")
if ($commit.Ok -and $commit.Output) { $tag = "$tag-$(($commit.Output -join '').Trim())" }

$image = "$acrName.azurecr.io/vigil:$tag"
Write-Step 3 "Building API image vigil:$tag ..."
$built = $false

# Docker Desktop is the reliable path (Azure for Students blocks cloud builds), so start it if needed
function Start-DockerIfNeeded {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { return $false }
    if ((Invoke-Quiet { docker info }).Ok) { return $true }

    $desktop = @(
        (Join-Path (Split-Path (Split-Path (Split-Path $docker.Source))) "Docker Desktop.exe"),
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\Docker Desktop.exe")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $desktop) { return $false }

    Write-Info "Starting Docker Desktop..."
    Start-Process -FilePath $desktop | Out-Null
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        if ((Invoke-Quiet { docker info }).Ok) { Write-Ok "Docker is running."; return $true }
    }
    return $false
}

$useDocker = $Build -eq "Local" -or ($Build -eq "Auto" -and (Start-DockerIfNeeded))
if ($Build -eq "Local" -and -not (Start-DockerIfNeeded)) {
    throw "Docker is not available. Install or start Docker Desktop and run .\deploy.ps1 again."
}

if (-not $useDocker) {
    Write-Info "Building in Azure Container Registry (uploads the repo, filtered by .dockerignore)..."
    # az streams the build log; force UTF-8 so pip output cannot crash it on Windows consoles.
    $env:PYTHONIOENCODING = "utf-8"
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    az acr build --registry $acrName --image "vigil:$tag" --file (Join-Path $Root "Dockerfile") $Root
    $built = ($LASTEXITCODE -eq 0)
    if (-not $built) {
        throw "The cloud build failed (ACR Tasks are disabled on free/student subscriptions). Install Docker Desktop and run .\deploy.ps1 again."
    }
}

if (-not $built) {
    Invoke-Checked "docker build" { docker build --platform linux/amd64 -t $image $Root }
    Invoke-Checked "az acr login" { az acr login --name $acrName }
    Invoke-Checked "docker push" { docker push $image }
}
Write-Ok "Image pushed: $image"

# ---------------------------------------------------------------- 4. everything else
Write-Step 4 "Deploying PostgreSQL, Key Vault, Container Apps and Static Web App (PostgreSQL takes 5-10 minutes)..."
Invoke-Checked "terraform apply" {
    terraform "-chdir=$TfDir" apply -input=false -auto-approve "-var=image_tag=$tag"
}
$apiUrl = Get-TfOutput "api_url"
$appUrl = Get-TfOutput "app_url"
$swaToken = Get-TfOutput "static_web_app_deployment_token"
$adminUser = Get-TfOutput "admin_username"
$adminPassword = Get-TfOutput "admin_password"

# ---------------------------------------------------------------- 5. API health
Write-Step 5 "Waiting for the API at $apiUrl (the first start loads data/ into PostgreSQL)..."
$apiHealthy = Wait-Url "$apiUrl/api/health" 8 "the API"
if ($apiHealthy) {
    Write-Ok "API is healthy."
} else {
    Write-Host "      API not healthy after 8 minutes. Check the logs:" -ForegroundColor Red
    Write-Host "      az containerapp logs show -n $(Get-TfOutput 'container_app_name') -g $resourceGroup --tail 100" -ForegroundColor Red
}

# ---------------------------------------------------------------- 6. dashboard
Write-Step 6 "Building the dashboard for $apiUrl and uploading it to Static Web Apps..."
Push-Location $FrontendDir
try {
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Invoke-Checked "npm ci" { npm ci --no-audit --no-fund }
    }
    $env:VITE_API_URL = $apiUrl
    Invoke-Checked "npm run build" { npm run build }
} finally {
    Remove-Item Env:VITE_API_URL -ErrorAction SilentlyContinue
    Pop-Location
}

$env:SWA_CLI_DEPLOYMENT_TOKEN = $swaToken   # read by the SWA CLI; kept off the command line
try {
    Invoke-Checked "Static Web Apps upload" {
        npx --yes $SwaCli deploy (Join-Path $FrontendDir "dist") --env production
    }
} finally {
    Remove-Item Env:SWA_CLI_DEPLOYMENT_TOKEN -ErrorAction SilentlyContinue
}
$appHealthy = Wait-Url $appUrl 5 "the dashboard"
if ($appHealthy) { Write-Ok "Dashboard is live." } else { Write-Warn "The dashboard did not answer yet; it can take a few minutes after the first upload." }

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  Vigil is deployed on Azure" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  Dashboard (Static Web Apps) : $appUrl" -ForegroundColor Cyan
Write-Host "  API (Container Apps)        : $apiUrl" -ForegroundColor Cyan
Write-Host "  API docs                    : $apiUrl/docs" -ForegroundColor Cyan
Write-Host "  Database (PostgreSQL)       : $(Get-TfOutput 'postgres_server')" -ForegroundColor Gray
Write-Host "  Secrets (Key Vault)         : $(Get-TfOutput 'key_vault_name')" -ForegroundColor Gray
Write-Host "  Resource group              : $resourceGroup" -ForegroundColor Gray
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Username : $adminUser" -ForegroundColor Yellow
Write-Host "  Password : $adminPassword" -ForegroundColor Yellow
Write-Host "  (again later: terraform -chdir=terraform output -raw admin_password)" -ForegroundColor DarkGray
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Remove everything: .\destroy.ps1" -ForegroundColor Gray
Write-Host "==========================================================`n" -ForegroundColor Green

if (-not ($apiHealthy -and $appHealthy)) { exit 1 }
