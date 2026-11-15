# Separate Ubuntu telemetry lab

The owner completed VM setup, collector installation, and hosted SSH incident verification by 15 November 2026. The phases below document the setup for reference.

## Goal and topology

First prove that real SSH authentication logs reach the deployed SOC:

`Windows SSH client -> localhost-only NAT forwarding -> Ubuntu SSH server -> journal -> collector -> HTTPS API -> PostgreSQL -> incident evidence`

The backend accepts normalized `LOGIN_FAILED` and `LOGIN_SUCCEEDED` events. Phase 4 installs the journal collector and connects it to the deployed API. Suricata network telemetry and additional rules follow after this path works.

## Recommended first VM

| Setting | Value |
| --- | --- |
| Name | AI-SOC-Ubuntu |
| OS | Ubuntu Server 24.04 LTS, 64-bit PC/AMD64 |
| Memory | 3072 MB |
| CPUs | 2 virtual CPUs |
| Disk | 30 GB VDI, dynamically allocated |
| Suggested folder | E:\VMs\AI-SOC, if E: is a stable local drive |
| Network | One adapter, NAT |
| SSH entry | TCP host 127.0.0.1:2222 -> guest port 22 |
| Hostname | ai-soc-lab |
| Administrator username | aisoc, or another privately chosen username |

Read-only checks found 16 GB host RAM and VirtualBox 7.1.6. Free space was approximately C: 17.4 GB, D: 49.2 GB, E: 67.8 GB. Place the VM and installer on a data drive with enough space rather than C:. A dynamic disk grows as used; logs, snapshots, and updates still consume real storage. Resource values are starting allocations for SSH plus a collector, not a guaranteed Suricata load profile.

## Phase 1: obtain the installer

Use https://ubuntu.com/download/server and select the supported 24.04 LTS Server AMD64 image from previous releases/alternative downloads. The current latest Ubuntu release may differ; Server 24.04 LTS is the chosen lab baseline. Use a Server installer rather than Desktop to keep the VM small. Download only from Canonical's official release links.

The release directory https://releases.ubuntu.com/24.04/ supplies installer images and SHA256SUMS. Compare the ISO's `Get-FileHash -Algorithm SHA256` result with the entry for that exact filename. Point releases/filenames change; do not compare against a checksum for a different image.

## Phase 2: create and install in VirtualBox

1. Choose New and name the VM AI-SOC-Ubuntu. Select the storage folder on E: and the downloaded ISO.
2. Choose Linux / Ubuntu (64-bit). Skip unattended installation so you enter the guest account credentials yourself.
3. Allocate 3072 MB RAM, 2 CPUs, and a new dynamically allocated 30 GB VDI.
4. Keep Adapter 1 on NAT. Do not modify the existing VMs or create a bridged connection for this first milestone.
5. Start the new VM and install Ubuntu Server. Use normal DHCP and default package mirror settings. Select the VM's virtual disk for installation; never select a host physical disk/passthrough device.
6. Set hostname ai-soc-lab and create your administrator account. Keep its password private. Select Install OpenSSH server when offered. Ubuntu Pro and optional server snaps are not required for this milestone.
7. Finish installation, detach the installer ISO if prompted, and reboot into the installed guest.

No Kali VM or second Linux VM is needed for the first authentication milestone; the existing Windows SSH client can provide controlled test connections.

## Phase 3: prepare SSH and verify logs

Inside the new Ubuntu guest:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y openssh-server python3 python3-venv git ca-certificates
sudo systemctl enable --now ssh
systemctl is-active ssh
timedatectl status
```

Confirm SSH is active and the clock is synchronized. The SOC rejects event timestamps more than five minutes in the future. If Ubuntu requests a reboot after updates, reboot this new VM before continuing.

Power off this VM before changing VirtualBox networking settings. In Settings -> Network -> Adapter 1 -> Advanced -> Port Forwarding, add:

| Name | Protocol | Host IP | Host port | Guest IP | Guest port |
| --- | --- | --- | --- | --- | --- |
| SSH-local | TCP | 127.0.0.1 | 2222 | leave blank for default NAT DHCP | 22 |

Boot the VM again. From Windows PowerShell:

```powershell
ssh -p 2222 aisoc@127.0.0.1
```

Replace aisoc if you chose another username. On the first connection, compare the displayed host fingerprint with the guest's host public-key fingerprint, for example `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` for ED25519. Enter your guest password only in the SSH prompt.

In the guest, confirm actual SSH records exist:

```bash
sudo journalctl -t sshd -n 20 --no-pager
```

If no records appear, check `sudo journalctl -u ssh.service -n 30 --no-pager` and the actual identifier/unit before choosing the collector filter. Do not assume `/var/log/auth.log` exists on every install.

Binding the forwarded host port to 127.0.0.1 keeps this inbound SSH entry local to the Windows host. NAT still permits outbound connectivity for updates and the HTTPS collector; it is not complete egress isolation. No router port forwarding is needed.

## Phase 4: install and connect the collector

The owner installed and verified the collector on Ubuntu Server 24.04.5 LTS. The journal records accepted and failed authentication from peer address `10.0.2.2`. The collector uses guest destination `10.0.2.15` and the deployed Render API.

Create an `Ubuntu SSH journal` source in the private dashboard under **Telemetry sources**. Keep the one-time token for the guest's credential prompt. Copy the two collector files from Windows PowerShell with the repository as your current directory:

```powershell
scp -P 2222 collector/ssh_journal.py collector/ai-soc-ssh.service aisoc@127.0.0.1:~
```

In Ubuntu, use `ip -4 -brief address` to find the guest's NAT interface address. Use the guest address for `SOC_SSH_DESTINATION_IP`. The observed `10.0.2.2` is the peer address in the journal.

```bash
sudo install -d -m 0755 /opt/ai-soc
sudo install -d -m 0700 /etc/ai-soc
sudo install -m 0644 ~/ssh_journal.py /opt/ai-soc/ssh_journal.py
sudo install -m 0644 ~/ai-soc-ssh.service /etc/systemd/system/ai-soc-ssh.service
sudoedit /etc/ai-soc/ssh-collector.conf
```

Enter the following settings. Replace `GUEST_IPV4` with the actual address. Set lookback to a value from 1 to 60 if you want to send recent lab records on first start. The default of 0 starts from the time the queue is created. Changing lookback after first start leaves the saved checkpoint in effect.

```dotenv
SOC_API_URL=https://ai-soc-api.onrender.com
SOC_SSH_DESTINATION_IP=GUEST_IPV4
SOC_SSH_LOOKBACK_MINUTES=0
```

Enter the source token at the hidden prompt, then start the service:

```bash
sudo bash -c '
umask 077
read -rsp "Source token: " token
printf "\n"
test -n "$token" || exit 1
printf "%s\n" "$token" > /etc/ai-soc/source-token
'
sudo systemctl daemon-reload
sudo systemctl enable --now ai-soc-ssh.service
sudo journalctl -u ai-soc-ssh.service -f
```

Open a normal SSH session and look for `API acknowledged 1 SSH events` (or a larger batch count). Refresh the private dashboard and check that the source has a last-received time and the event count increased. A successful login alone does not create an incident.

The collector runs under a dynamic service user with journal read access and a private SQLite state directory. It sends the actual peer IP and timestamp and only the normalized authentication fields. An `Invalid user` prelude does not count as a second failure when OpenSSH also writes `Failed password`. Journal cursor and pending events commit together. A batch stays queued until the API acknowledges it, including duplicate acknowledgements after retry. When the 5,000-event queue fills, collection waits for space. If journal retention removes unread entries during a long outage, those entries cannot be recovered by the collector. The source token is loaded as a systemd credential. See https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html.

## Phase 5: real detection demonstration (after collector delivery works)

Create a dedicated non-admin lab test account in this guest. First verify a successful SSH connection and record collection. Then manually perform five incorrect-password logins against that same test account within 120 seconds, using the localhost-forwarded lab SSH endpoint. Verify actual failure records are emitted before expecting the rule to fire. Do not alter the existing VMs' authentication or attempt external systems.

Expected evidence: real LOGIN_FAILED records, one brute_force_v1 alert/incident at the first five unlinked matching failures, journal-backed IDs/timestamps, and the correct guest destination port 22. NAT may make the guest see a translated source IP; record the observed address rather than substituting a fabricated one.

Also test API unavailability/retry, collector restart, and duplicate delivery. Keep this real lab source separate from the earlier synthetic Authentication test source.

## Verified outcome

The owner verified API acknowledgements after installing the journal cursor fix. Five real failed-login events were linked to **Possible brute force against soc-lab-test**, with source `10.0.2.2` and destination `10.0.2.15:22`. The synthetic `demo-admin` incident remained separate.

## References

- Ubuntu Server downloads: https://ubuntu.com/download/server
- Ubuntu 24.04 images/checksums: https://releases.ubuntu.com/24.04/
- Ubuntu OpenSSH setup: https://ubuntu.com/server/docs/how-to/security/openssh-server/
- VirtualBox 7.1 NAT/port forwarding: https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/networkingdetails.html

## Phase 6: verify a Suricata flow

Suricata 7.0.3 is configured on `enp0s3`. The owner completed this phase with `tmp/import-ubuntu-flow.ps1`. The Render API accepted one flow, and the private dashboard displayed TCP from `10.0.2.2:64620` to `10.0.2.15:22` at `2026-11-14 21:34:43.547Z` under `Ubuntu Suricata`. The manual import steps remain below for reference.

The API and private dashboard support TCP/UDP flow metadata. This first check imports a single matching flow. Suricata EVE flow records include the timestamp, protocol, and both endpoints. See https://docs.suricata.io/en/suricata-7.0.14/output/eve/eve-json-format.html#event-type-flow.

In Ubuntu, install Suricata if needed and confirm that it captures the NAT interface shown by `ip -4 -brief address`. Check that EVE flow output is enabled in its configuration, then validate and start the sensor.

```bash
sudo apt update
sudo apt install suricata
sudo suricata -T -c /etc/suricata/suricata.yaml
sudo systemctl enable --now suricata
sudo systemctl status suricata --no-pager
```

From Windows PowerShell, copy the importer and its companion module to the guest account directory.

```powershell
scp -P 2222 collector/suricata_eve.py collector/ssh_journal.py aisoc@127.0.0.1:~/
```

Open and close a normal SSH connection. Allow Suricata time to write the completed flow. Preview the newest matching record from the lab addresses.

```bash
sudo python3 ~/suricata_eve.py /var/log/suricata/eve.json \
  --source-ip 10.0.2.2 --destination-ip 10.0.2.15 --destination-port 22
```

After the API supports `NETWORK_FLOW`, create a separate `Ubuntu Suricata` source in the private dashboard. Repeat the preview command with `--api-url https://ai-soc-api.onrender.com` and enter the source token at the hidden prompt. Acknowledge success with `{"accepted": 1, "duplicates": 0}`. Reimporting the same flow with the same source returns a duplicate acknowledgement.

In **Network events**, compare the row's UTC timestamp, source IP and port, destination IP and port, and protocol against the preview. The existing brute-force rule operates on failed authentication records. A regular network flow is displayed as telemetry.

## Phase 7: enable automatic Suricata forwarding

The forwarder tails `/var/log/suricata/eve.json` and sends TCP flows from `10.0.2.2` to `10.0.2.15:22`. On its first run it starts at the current end of the file. Later starts resume the saved position. This filter limits the first rollout to the established lab traffic and excludes HTTPS delivery traffic.

From Windows PowerShell in the project folder, copy the files and start an interactive SSH session.

```powershell
scp -P 2222 collector/suricata_forwarder.py collector/suricata_eve.py collector/ssh_journal.py collector/ai-soc-suricata.service collector/install-suricata-forwarder.sh aisoc@127.0.0.1:~/
ssh -p 2222 aisoc@127.0.0.1
```

In Ubuntu, run the installer. If it reports that `setfacl` is missing, run `sudo apt install acl` and retry.

```bash
sudo bash ~/install-suricata-forwarder.sh
sudo journalctl -u ai-soc-suricata.service -n 30 --no-pager
```

At the hidden prompt, enter the existing **Ubuntu Suricata** telemetry source token. If it is unavailable, create a fresh Suricata source in the private dashboard and enter that token. The installer stores it separately from the SSH journal collector's credential. It grants the dedicated service group read access to the active EVE file and inherited access to newly created Suricata log files. The unit loads the token using systemd credentials. https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#LoadCredential=

After the service is active, open and close a new ordinary SSH session. Wait for Suricata to emit its flow record. Check for `API acknowledged … Suricata events` (older builds say `Suricata flows`), then find the new timestamp and source port in **Network events**. Restart `ai-soc-suricata.service` and repeat with a fresh session to verify that collection resumes. Keep the existing source and SQLite state for restart testing. Reusing the source also lets the API deduplicate a flow previously sent by the manual importer.

The forwarder holds up to 5,000 pending flows on disk and retries unacknowledged batches. For rename-based rotation, retain the previous uncompressed EVE file in the same directory until the collector reads it. The collector drains that file and then reads the current EVE file. Multiple rotations while stopped can leave intervening files unprocessed. If the checkpointed file is missing or was truncated, the service logs the problem and keeps queued deliveries and the checkpoint. Check the EVE file and rotation configuration before changing the checkpoint.

## Phase 8: forward alerts and inspect incident context

Update the guest after the hosted API accepts `SURICATA_ALERT`. From Windows, repeat the file copy in phase 7. In Ubuntu, rerun `sudo bash ~/install-suricata-forwarder.sh`. The installer reuses the source credential and configuration and restarts the service with its existing SQLite state.

Check that Suricata's EVE output includes the `alert` type. Look for a matching alert already observed by the lab sensor or let the service run until one occurs. The forwarder uses the existing lab TCP endpoint filter for both flows and alerts. **Network events** shows the signature name, ID, and sensor severity when a matching alert arrives.

Open a failed-login incident and refresh it. The timeline shows up to 50 related TCP flows and Suricata alerts from the same workspace that match the source IP, destination IP and port. The search starts two minutes before the first linked failure and ends two minutes after the last. The match provides context because several sessions can share a NAT address. Existing stored flows can appear immediately when they match. Alerts written before the guest update and already passed by the saved checkpoint require a separate backfill if needed.
