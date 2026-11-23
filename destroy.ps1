<#
.SYNOPSIS
    Removes everything deploy.ps1 created in Azure.

.DESCRIPTION
    Runs terraform destroy, then confirms the resource group is gone. If the local Terraform state
    is missing, falls back to deleting the resource group by name (-ResourceGroup) or by its
    project=vigil tag.

.EXAMPLE
    .\destroy.ps1
.EXAMPLE
    .\destroy.ps1 -Force
.EXAMPLE
    .\destroy.ps1 -ResourceGroup rg-vigil-ab12c -Force
#>
[CmdletBinding()]
param (
    [string]$ResourceGroup,
    [string]$Subscription,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$TfDir = Join-Path $PSScriptRoot "terraform"

# Success is judged by the exit code only (native stderr is progress, not failure; see deploy.ps1).
function Invoke-Checked {
    param([string]$What, [scriptblock]$Command)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

function Invoke-Quiet {
    param([scriptblock]$Command)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $output = & $Command 2>$null } finally { $ErrorActionPreference = $previous }
    return [pscustomobject]@{ Output = $output; Ok = ($LASTEXITCODE -eq 0) }
}

function Confirm-Teardown($target) {
    if ($Force) { return }
    Write-Host "`nThis permanently deletes $target and everything in it (app, registry, images, logs)." -ForegroundColor Yellow
    $answer = Read-Host "Type 'yes' to continue"
    if ($answer -ne "yes") {
        Write-Host "Cancelled. Nothing was deleted." -ForegroundColor Green
        exit 0
    }
}

function Test-GroupExists($name) {
    $result = Invoke-Quiet { az group exists --name $name }
    return (($result.Output -join "").Trim() -eq "true")
}

Write-Host "==========================================================" -ForegroundColor Red
Write-Host "               Vigil Azure teardown                        " -ForegroundColor Red
Write-Host "==========================================================" -ForegroundColor Red

foreach ($tool in @("az", "terraform")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "'$tool' is not installed or not on PATH." }
}
if ($Subscription) { Invoke-Checked "az account set" { az account set --subscription $Subscription } }

$account = Invoke-Quiet { az account show -o json }
if (-not $account.Ok) {
    Invoke-Checked "az login" { az login --output none }
    $account = Invoke-Quiet { az account show -o json }
}
$account = ($account.Output -join "") | ConvertFrom-Json
$env:ARM_SUBSCRIPTION_ID = $account.id
Write-Host "Subscription: $($account.name) ($($account.id))" -ForegroundColor Gray

# Resources Terraform is tracking, if any.
$tracked = @()
if (Test-Path (Join-Path $TfDir "terraform.tfstate")) {
    Invoke-Checked "terraform init" { terraform "-chdir=$TfDir" init -input=false | Out-Null }
    $state = Invoke-Quiet { terraform "-chdir=$TfDir" state list }
    if ($state.Ok -and $state.Output) { $tracked = @($state.Output) }
}

if ($tracked.Count -gt 0) {
    if (-not $ResourceGroup) {
        $rgOutput = Invoke-Quiet { terraform "-chdir=$TfDir" output -raw resource_group }
        if ($rgOutput.Ok) { $ResourceGroup = ($rgOutput.Output -join "").Trim() }
    }
    $label = "resource group '$ResourceGroup'"
    if (-not $ResourceGroup) { $label = "the $($tracked.Count) resources in Terraform state" }
    Confirm-Teardown $label

    Write-Host "`nRunning terraform destroy (takes a few minutes)..." -ForegroundColor Yellow
    # image_tag only satisfies the app's precondition; nothing is built.
    Invoke-Checked "terraform destroy" {
        terraform "-chdir=$TfDir" destroy -input=false -auto-approve "-var=image_tag=destroy"
    }
} else {
    Write-Host "`nNo resources in local Terraform state." -ForegroundColor Yellow
    if (-not $ResourceGroup) {
        $found = Invoke-Quiet { az group list --tag project=vigil --query "[?tags.managed_by=='terraform'].name" -o tsv }
        $groups = @($found.Output | Where-Object { $_ })
        if ($groups.Count -eq 1) {
            $ResourceGroup = $groups[0].Trim()
            Write-Host "Found resource group by tag: $ResourceGroup" -ForegroundColor Gray
        } elseif ($groups.Count -gt 1) {
            throw "Several Vigil resource groups found ($($groups -join ', ')). Pick one with -ResourceGroup."
        } else {
            Write-Host "Nothing to delete." -ForegroundColor Green
            exit 0
        }
    }
}

# Make sure nothing is left behind (also covers the no-state fallback).
if ($ResourceGroup -and (Test-GroupExists $ResourceGroup)) {
    if ($tracked.Count -eq 0) { Confirm-Teardown "resource group '$ResourceGroup'" }
    Write-Host "`nDeleting resource group '$ResourceGroup'..." -ForegroundColor Yellow
    Invoke-Checked "az group delete" { az group delete --name $ResourceGroup --yes }
}

if ($ResourceGroup -and (Test-GroupExists $ResourceGroup)) {
    throw "Resource group '$ResourceGroup' still exists. Check the Azure portal."
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  Teardown complete. All Vigil resources are deleted." -ForegroundColor Green
Write-Host "  Deploy again any time with .\deploy.ps1" -ForegroundColor Green
Write-Host "==========================================================`n" -ForegroundColor Green
