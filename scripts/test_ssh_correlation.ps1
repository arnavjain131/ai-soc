# Five controlled, real authentication attempts against the existing local lab.
# This script never reads a source token, changes SSH settings, or ingests events.
$ErrorActionPreference = 'Stop'

Write-Host 'Checking hosted API readiness (no credentials are sent)...'
$ready = Invoke-RestMethod -Uri 'https://ai-soc-api.onrender.com/health/ready' -TimeoutSec 60
if ($ready.status -ne 'ready') { throw 'API is not ready. No test attempts were made.' }

$inspection = @'
import grp
import json
from pathlib import Path
import os
import pwd
import re
import subprocess
import sys

def stop(message):
    print('Preflight stopped:', message)
    sys.exit(1)

try:
    account = pwd.getpwnam('soc-lab-test')
except KeyError:
    stop('The existing soc-lab-test account was not found. No account was created.')
groups = {grp.getgrgid(gid).gr_name for gid in os.getgrouplist(account.pw_name, account.pw_gid)}
if account.pw_uid < 1000 or groups & {'root', 'sudo', 'admin', 'wheel'}:
    stop('The test account has an administrative identity or group membership.')
status = subprocess.run(['passwd', '-S', account.pw_name], capture_output=True, text=True)
parts = status.stdout.split()
if status.returncode or len(parts) < 2 or parts[1] != 'P':
    stop('The test account is locked or has no usable password. No account changes were made.')
for service in ('suricata.service', 'ai-soc-ssh.service', 'ai-soc-suricata.service'):
    result = subprocess.run(['systemctl', 'is-active', '--quiet', service])
    if result.returncode:
        stop(service + ' is not active.')
    print(service + ': active')
clock = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'],
                       capture_output=True, text=True)
if clock.returncode or clock.stdout.strip() != 'yes':
    stop('Clock synchronization is not confirmed.')
network = subprocess.run(['ip', '-j', 'address', 'show', 'dev', 'enp0s3'], capture_output=True, text=True)
if network.returncode:
    stop('Could not inspect the existing lab interface.')
addresses = {item.get('local') for interface in json.loads(network.stdout) for item in interface.get('addr_info', [])}
if '10.0.2.15' not in addresses:
    stop('The lab interface does not have the expected 10.0.2.15 address.')
for service in ('fail2ban.service', 'sshguard.service'):
    if subprocess.run(['systemctl', 'is-active', '--quiet', service]).returncode == 0:
        stop('An active lockout service needs review before this test: ' + service)
for policy in Path('/etc/pam.d').iterdir():
    if policy.is_file():
        lines = [line.partition('#')[0] for line in policy.read_text(errors='replace').splitlines()]
        if any(re.search(r'pam_(?:faillock|tally2?)\.so', line) for line in lines):
            stop('A PAM lockout module needs review. Its configuration was not changed.')
result = subprocess.run(['/usr/sbin/sshd', '-T', '-C',
                         'user=soc-lab-test,host=localhost,addr=10.0.2.2'],
                        capture_output=True, text=True)
if result.returncode:
    stop('Could not inspect effective SSH settings.')
settings = dict(line.split(' ', 1) for line in result.stdout.splitlines() if ' ' in line)
if settings.get('passwordauthentication') != 'yes':
    stop('Password authentication is not enabled for this test; SSH was not changed.')
if settings.get('authenticationmethods') not in ('any', 'password'):
    stop('Authentication requires additional methods; SSH was not changed.')
if any(key in settings for key in ('allowusers', 'denyusers', 'allowgroups', 'denygroups')):
    stop('SSH access restrictions need review before attempting this test.')
print('Existing test account and SSH settings passed the lab checks.')
print('No active fail2ban/sshguard service or configured PAM lockout module was found.')
print('No services, accounts, credentials, logs or collector state were modified.')
'@
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($inspection))
$remote = "printf %s $encoded | base64 -d | sudo python3 -"
Write-Host 'Preflight: enter the aisoc administrator password and sudo password correctly at the local prompts.'
& ssh.exe -t -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -p 2222 aisoc@127.0.0.1 $remote
if ($LASTEXITCODE -ne 0) { throw 'Lab preflight did not pass. No failed-login test was started.' }

Write-Host ''
Write-Host 'Next: five separate connections for soc-lab-test, with ONE password prompt per connection.'
Write-Host 'Enter an intentionally incorrect password at each test prompt. Never enter the aisoc password here.'
Write-Host 'Complete all five promptly, within 120 seconds. Input stays hidden; this script never captures it.'
Write-Host 'If a prompt is missing, a connection succeeds, or an unexpected error appears, stop and share the non-secret output.'
[void](Read-Host 'Press Enter when ready to start the five authorized test attempts, or Ctrl+C to cancel')
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$started = [DateTime]::UtcNow
Write-Host ('Test started UTC: ' + $started.ToString('o'))
for ($attempt = 1; $attempt -le 5; $attempt++) {
    if ($timer.Elapsed.TotalSeconds -ge 110) {
        Write-Warning 'Stopping: close to the 120-second rule window. Do not repeat until existing evidence is checked.'
        break
    }
    Write-Host "Attempt $attempt of 5 - deliberately WRONG password for soc-lab-test only."
    & ssh.exe -p 2222 -o StrictHostKeyChecking=yes -o ConnectTimeout=5 -o ConnectionAttempts=1 `
        -o PreferredAuthentications=password -o PubkeyAuthentication=no -o KbdInteractiveAuthentication=no `
        -o NumberOfPasswordPrompts=1 -o ControlMaster=no -o ControlPath=none soc-lab-test@127.0.0.1 exit
    if ($LASTEXITCODE -eq 0) {
        Write-Warning 'A connection succeeded. The test has stopped; do not repeat it.'
        break
    }
    if ($LASTEXITCODE -ne 255) {
        Write-Warning 'Unexpected SSH exit code. The test has stopped; inspect the output before continuing.'
        break
    }
}
$timer.Stop()
Write-Host ('Test ended UTC: ' + [DateTime]::UtcNow.ToString('o'))
Write-Host ('Elapsed seconds: ' + [Math]::Round($timer.Elapsed.TotalSeconds, 1))
Write-Host 'SSH exit code 255 alone does not prove an authentication failure; journal/API evidence must confirm it.'
Write-Host 'Keep both collectors running. Allow time for flow export and API delivery, then inspect the new incident.'
Write-Host 'Do not manually import events or repeat the test if the incident is not immediately visible.'
