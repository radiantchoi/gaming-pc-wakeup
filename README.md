# gaming-pc-wakeup

A minimal FastAPI server that wakes one gaming PC on your LAN with
Wake-on-LAN and tells you whether it is up. Meant for a small always-on host
on the same network: a Raspberry Pi 1 Model B or an old Android phone running
Termux. Remote use goes over Tailscale; nothing is exposed to the internet.

| Endpoint      | What it does                                                    |
|---------------|-----------------------------------------------------------------|
| `GET /health` | `{"status": "ok"}`                                              |
| `POST /wake`  | Sends one magic packet. Needs `X-Token` if `WOL_TOKEN` is set.  |
| `GET /status` | `{"online": true/false, ...}` via a TCP connect to the PC.      |

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
| `WOL_TOKEN`          | unset               | If set, `POST /wake` requires `X-Token: <value>`     |

The server refuses to start if `WOL_MAC` or `WOL_HOST` is missing or invalid.

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
5. Install the Tailscale app from the Play Store and sign in.

## 5. Using it over the tailnet

Replace `HOST` with the host's Tailscale name or IP.

```sh
curl http://HOST:8000/health
curl -X POST http://HOST:8000/wake
curl -X POST -H "X-Token: your-token" http://HOST:8000/wake   # if WOL_TOKEN is set
curl http://HOST:8000/status
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
