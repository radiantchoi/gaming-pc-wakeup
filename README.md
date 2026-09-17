# gaming-pc-wakeup

A minimal FastAPI server that wakes one gaming PC on your LAN with
Wake-on-LAN, tells you whether it is up, and can put it to sleep over SSH.
Meant for a small always-on host
on the same network: a Raspberry Pi 1 Model B or an old Android phone running
Termux. Remote use goes over Tailscale; nothing is exposed to the internet.

| Endpoint      | What it does                                                    |
|---------------|-----------------------------------------------------------------|
| `GET /health` | `{"status": "ok"}`                                              |
| `POST /wake`  | Sends one magic packet. Needs `X-Token` if `WOL_TOKEN` is set.  |
| `GET /status` | `{"online": true/false, ...}` via a TCP connect to the PC.      |
| `POST /sleep` | Puts the PC to sleep over SSH. Optional; see section 1. Same `X-Token` rule. |

Host status: Raspberry Pi 1 — untested. Galaxy Note 8 / Termux — untested.

## 1. PC prerequisites

- Enable Wake-on-LAN in BIOS/UEFI (often "Power On By PCI-E" or "Wake on
  LAN").
- Windows: Device Manager → the Ethernet adapter → Power Management → allow
  the device to wake the computer; also enable "Wake on Magic Packet" under
  Advanced.
- Windows: turn off Fast Startup (Control Panel → Power Options → "Choose
  what the power buttons do").
- Connect the PC by Ethernet. WoL over Wi-Fi is unreliable.
- Note the adapter's MAC address (`ipconfig /all` → Physical Address) and
  give the PC a fixed IP or DHCP reservation.

### Sleep over SSH (optional)

`POST /sleep` SSHes into the PC and runs a scheduled task that puts it to
sleep. Sleep, not shutdown: WoL from sleep is more reliable and resume is
fast. One-time setup, in an elevated PowerShell on the PC unless noted. Use
an administrator account as the SSH user.

1. Enable the OpenSSH server:

   ```powershell
   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
   Set-Service -Name sshd -StartupType Automatic
   Start-Service sshd
   ```

2. Install the sleep task. Copy `deploy/windows/sleep.ps1` to
   `C:\gaming-pc-wakeup\sleep.ps1`, then register a task with no trigger
   and run it once to confirm the PC sleeps:

   ```powershell
   $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\gaming-pc-wakeup\sleep.ps1'
   $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest
   Register-ScheduledTask -TaskName gaming-pc-sleep -Action $action -Principal $principal -Force
   schtasks /run /tn gaming-pc-sleep
   ```

3. On the host (Pi or phone), create a key and print its public half:

   ```sh
   ssh-keygen -t ed25519 -f ~/.ssh/gaming-pc -N "" -C gaming-pc-wakeup
   cat ~/.ssh/gaming-pc.pub
   ```

4. Register the public key on the PC, restricted so it can only run the
   sleep task. For an administrator account the file is
   `C:\ProgramData\ssh\administrators_authorized_keys`; for other accounts
   it is `C:\Users\<user>\.ssh\authorized_keys`. Add one line:

   ```
   command="schtasks /run /tn gaming-pc-sleep",no-port-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... gaming-pc-wakeup
   ```

   The administrators file must be readable only by SYSTEM and
   Administrators, so fix its permissions once:

   ```powershell
   icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
   ```

5. Test from the host, then put the user and key path in the env file as
   `WOL_SSH_USER` and `WOL_SSH_KEY` (on the Pi the service runs as `pi`, so
   the path is `/home/pi/.ssh/gaming-pc`):

   ```sh
   ssh -i ~/.ssh/gaming-pc <user>@<pc-ip> schtasks /run /tn gaming-pc-sleep
   ```

## 2. Environment file

Copy `deploy/common/gaming-pc-wakeup.env.example`, set `WOL_MAC` and
`WOL_HOST`, and put it where the host expects it (see below). All variables:

| Variable             | Default             | Meaning                                              |
|----------------------|---------------------|------------------------------------------------------|
| `WOL_MAC`            | required            | MAC of the PC's Ethernet NIC                         |
| `WOL_HOST`           | required            | IP or hostname of the PC, for `GET /status`          |
| `WOL_BROADCAST`      | `255.255.255.255`   | Where the magic packet goes; subnet broadcast is safer on Wi-Fi hosts |
| `WOL_PORT`           | `9`                 | UDP port for the magic packet                        |
| `WOL_STATUS_PORT`    | `3389`              | TCP port that is open when the PC is up (RDP)        |
| `WOL_STATUS_TIMEOUT` | `1.0`               | Seconds to wait in `GET /status`                     |
| `WOL_TOKEN`          | unset               | If set, `POST /wake` and `POST /sleep` require `X-Token: <value>` |
| `WOL_SSH_USER`       | unset               | Windows user for `POST /sleep`; set with `WOL_SSH_KEY` |
| `WOL_SSH_KEY`        | unset               | Private key path on the host for `POST /sleep`       |
| `WOL_SSH_PORT`       | `22`                | SSH port on the PC                                   |
| `WOL_SSH_TIMEOUT`    | `10.0`              | Seconds allowed for the ssh call                     |

The server refuses to start if `WOL_MAC` or `WOL_HOST` is missing or
invalid, if only one of `WOL_SSH_USER`/`WOL_SSH_KEY` is set, or if the key
file does not exist. With neither SSH value set, `POST /sleep` answers 503.

## 3. Host A: Raspberry Pi 1 Model B

1. Flash Raspberry Pi OS Lite (32-bit, trixie) with Raspberry Pi Imager.
   Use user `pi` or adjust the paths in the service file. Connect by
   Ethernet.
2. Install uv (it ships an ARMv6 build) and git:

   ```sh
   sudo apt install -y git
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. Clone and install. The script uses the OS Python and piwheels; it is the
   only Pi-specific part of the project.

   ```sh
   git clone https://github.com/radiantchoi/gaming-pc-wakeup.git ~/gaming-pc-wakeup
   ~/gaming-pc-wakeup/deploy/pi/install.sh
   ```

4. Install the environment file and the service:

   ```sh
   sudo cp ~/gaming-pc-wakeup/deploy/common/gaming-pc-wakeup.env.example /etc/gaming-pc-wakeup.env
   sudo nano /etc/gaming-pc-wakeup.env
   sudo cp ~/gaming-pc-wakeup/deploy/pi/gaming-pc-wakeup.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now gaming-pc-wakeup
   curl localhost:8000/health
   ```

5. Install Tailscale from its apt repository and join your tailnet:

   ```sh
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```

## 4. Host B: Samsung Galaxy Note 8 with Termux

1. Install Termux and Termux:Boot from F-Droid (not the Play Store build).
   Open Termux:Boot once so Android lets it run at boot.
2. In Termux, clone and install (installs python, uv, rust; the first run
   builds `pydantic-core`, which takes a while):

   ```sh
   pkg install -y git
   git clone https://github.com/radiantchoi/gaming-pc-wakeup.git ~/gaming-pc-wakeup
   ~/gaming-pc-wakeup/deploy/termux/install.sh
   ```

3. Environment file and boot script:

   ```sh
   cp ~/gaming-pc-wakeup/deploy/common/gaming-pc-wakeup.env.example ~/gaming-pc-wakeup.env
   nano ~/gaming-pc-wakeup.env
   mkdir -p ~/.termux/boot
   cp ~/gaming-pc-wakeup/deploy/termux/boot.sh ~/.termux/boot/gaming-pc-wakeup.sh
   chmod +x ~/.termux/boot/gaming-pc-wakeup.sh
   ~/.termux/boot/gaming-pc-wakeup.sh &
   curl localhost:8000/health
   ```

   Set `WOL_BROADCAST` to your subnet broadcast (for example
   `192.168.0.255`); phones on Wi-Fi handle that more reliably than
   `255.255.255.255`. Logs go to `~/gaming-pc-wakeup.log`.

4. Keep Android from killing it: Settings → Apps → Termux → Battery → not
   optimised (and remove Termux from "sleeping apps" on Samsung); disable
   Wi-Fi sleep / power saving for Wi-Fi; keep the phone on power. Reboot the
   phone once and check `curl localhost:8000/health` again.
5. Install the Tailscale app from the Play Store and sign in. Do not try to
   install tailscale inside Termux; the app is a device-wide VPN service, so
   the Termux server is reachable at the phone's tailnet address as-is.
   Then:
   - Android Settings → VPN → Tailscale → turn on "Always-on VPN" so it
     reconnects after a reboot without opening the app.
   - Exclude the Tailscale app from battery optimisation, like Termux.
   - Do not enable an exit node on this phone. With an exit node all
     traffic goes into the tunnel and the WoL broadcast never reaches the
     LAN. If you must, also enable "Allow LAN access".
   - Check `curl http://<phone tailnet name>:8000/health` from another
     tailnet device.

## 5. Using it over the tailnet

The device you call from (phone, laptop) needs the Tailscale client too and
must be signed in to the same account. In the Tailscale admin console,
open the host's device entry and choose "Disable key expiry"; otherwise the
host silently drops off the tailnet after 180 days.

Replace `HOST` with the host's Tailscale name or IP (Machines page in the
admin console, or `tailscale ip` on the Pi).

```sh
curl http://HOST:8000/health
curl -X POST http://HOST:8000/wake
curl -X POST -H "X-Token: your-token" http://HOST:8000/wake   # if WOL_TOKEN is set
curl http://HOST:8000/status
curl -X POST http://HOST:8000/sleep                            # if WOL_SSH_* is set
```

## Development

```sh
uv sync
uv run pytest -q
uv run ruff check .
WOL_MAC=aa:bb:cc:dd:ee:ff WOL_HOST=192.0.2.10 uv run uvicorn app.main:app --port 8000
```

`pyproject.toml` and `uv.lock` are host-neutral; everything host-specific
lives under `deploy/<host>/`.
