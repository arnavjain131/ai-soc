param(
    [Parameter(Mandatory)]
    [ValidateSet('Install', 'Remove')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$vbox = 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe'
$vm = 'AI-SOC-Ubuntu'
$target = 'aisoc@127.0.0.1'
$sshRule = 'SSH-local,tcp,127.0.0.1,2222,,22'
$rules = 18080..18087 | ForEach-Object {
    [pscustomobject]@{
        Name = "ai-soc-lab-$_"
        Port = $_
        Spec = "ai-soc-lab-$_,tcp,127.0.0.1,$_,10.0.2.15,$_"
    }
}

function Get-NatRules {
    $info = @(& $vbox showvminfo $vm --machinereadable)
    if ($LASTEXITCODE -ne 0) { throw 'Could not read VirtualBox VM settings.' }
    if ($info -notcontains 'VMState="running"' -or $info -notcontains 'nic1="nat"') {
        throw 'Start AI-SOC-Ubuntu with adapter 1 set to NAT before running this script.'
    }
    $info | ForEach-Object {
        if ($_ -match '^Forwarding\(\d+\)="(.*)"$') { $Matches[1] }
    }
}

function Assert-RuleNames {
    param([string[]]$Current)
    foreach ($rule in $rules) {
        $named = @($Current | Where-Object { $_.StartsWith($rule.Name + ',', [System.StringComparison]::OrdinalIgnoreCase) })
        if ($named.Count -gt 0 -and ($named.Count -ne 1 -or $named[0] -cne $rule.Spec)) {
            throw "Rule name $($rule.Name) is already used for a different mapping."
        }
    }
}

function Assert-WindowsPortsFree {
    foreach ($rule in $rules) {
        $socket = [System.Net.Sockets.Socket]::new('InterNetwork', 'Stream', 'Tcp')
        try {
            $socket.ExclusiveAddressUse = $true
            $socket.Bind([System.Net.IPEndPoint]::new([System.Net.IPAddress]::Loopback, $rule.Port))
        } catch {
            throw "Windows loopback port $($rule.Port) is unavailable."
        } finally {
            $socket.Dispose()
        }
    }
    Write-Host 'Windows bind check passed for TCP 18080–18087.'
}

function Remove-ExactRules {
    param([string[]]$Current)
    $failed = @()
    foreach ($rule in $rules) {
        if ($Current -ccontains $rule.Spec) {
            & $vbox controlvm $vm natpf1 delete $rule.Name
            if ($LASTEXITCODE -ne 0) { $failed += $rule.Name }
        }
    }
    if ($failed.Count) { throw "Could not remove: $($failed -join ', ')." }
}

$current = @(Get-NatRules)
if ($current -cnotcontains $sshRule) { throw 'Expected SSH-local mapping was not found. Review VirtualBox settings.' }
Assert-RuleNames -Current $current
if ($Action -eq 'Remove') {
    Remove-ExactRules -Current $current
    $after = @(Get-NatRules)
    if ($after -cnotcontains $sshRule) { throw 'Expected SSH-local mapping was not found after cleanup.' }
    foreach ($rule in $rules) {
        if ($after -ccontains $rule.Spec) { throw "Lab rule remains: $($rule.Name)" }
    }
    Assert-WindowsPortsFree
    Write-Host 'Lab NAT rules removed. SSH-local is present.'
    return
}

if (@($rules | Where-Object { $current -ccontains $_.Spec }).Count -eq $rules.Count) {
    Write-Host 'All eight lab NAT rules are already installed.'
    return
}
if (@($rules | Where-Object { $current -ccontains $_.Spec }).Count -gt 0) {
    throw 'A partial lab setup already exists. Run -Action Remove before installing.'
}
Assert-WindowsPortsFree

$listener = Join-Path $PSScriptRoot 'lab_tcp_listener.py'
Write-Host 'Enter the Ubuntu password locally if prompted for the copy and port check.'
& scp.exe -o StrictHostKeyChecking=yes -P 2222 $listener "${target}:~/"
if ($LASTEXITCODE -ne 0) { throw 'Listener file transfer failed.' }
& ssh.exe -o StrictHostKeyChecking=yes -p 2222 $target 'python3 ~/lab_tcp_listener.py --check'
if ($LASTEXITCODE -ne 0) { throw 'Ubuntu bind check failed. NAT rules were not added.' }
Assert-WindowsPortsFree

$attempted = $false
try {
    $before = @(Get-NatRules)
    if ($before -cnotcontains $sshRule -or @(Compare-Object $current $before -CaseSensitive).Count) {
        throw 'VirtualBox rules changed during preflight. Rerun setup after checking the current rules.'
    }
    $attempted = $true
    foreach ($rule in $rules) {
        & $vbox controlvm $vm natpf1 $rule.Spec
        if ($LASTEXITCODE -ne 0) { throw "Could not add $($rule.Name)." }
    }
    $after = @(Get-NatRules)
    if ($after -cnotcontains $sshRule) { throw 'SSH-local is missing after setup.' }
    foreach ($rule in $rules) {
        if ($after -cnotcontains $rule.Spec) { throw "Lab rule missing: $($rule.Name)" }
        Write-Host $rule.Spec
    }
    Write-Host 'Eight loopback-only NAT rules installed. SSH-local is present. Start the listener when ready.'
} catch {
    $failure = $_
    if ($attempted) {
        Remove-ExactRules -Current @(Get-NatRules)
    }
    throw $failure
}
