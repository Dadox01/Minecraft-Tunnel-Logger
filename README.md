# Minecraft TCP Proxy & Command Logger

A lightweight, zero-dependency TCP proxy written in Python that bridges connections between Minecraft clients and a target server. It intercepts and logs incoming connections, player join events, and in-game commands in real time by inspecting packets directly at the network layer.

Designed to work seamlessly with port-forwarding and tunneling services like **playit.gg** or **ngrok**, as well as local development environments.

---

## Features

* **Zero External Dependencies**: Built entirely using Python standard libraries (`socket`, `struct`, `threading`, `zlib`).
* **Real-Time Command Logging**: Intercepts and logs commands executed by players (authentication commands, teleports, moderation, game modes, etc.).
* **Modern & Legacy Protocol Support**:
  * Legacy commands prefixed with `/` (`Chat Message`).
  * Modern Minecraft 1.19+ native `Chat Command` packets (where the client strips the leading slash `/`).
* **On-the-Fly Zlib Decompression**: Automatically handles network compression when the target server has `network-compression-threshold` enabled (common on shared game hosts).
* **Terminal Output Sanitization**: Strips non-printable ASCII control characters (`\r`, `\n`, null bytes) to eliminate cursor glitches, blank gaps, and line overwriting in terminal consoles.
* **Typing & Tab-Complete Filtering**: Ignores incomplete command suggestions sent during active typing, logging only fully submitted commands (Enter key press).
* **Non-Blocking Multithreaded Relay**: Bi-directional asynchronous forwarding ensuring zero noticeable gameplay latency or tick drops.
* **Optional Persistent Logging**: Append all terminal activity to a `.log` or `.txt` file on disk.

---

## Architecture

```text
[ Minecraft Client ]
         │ (TCP Traffic)
         ▼
[ Tunnel Agent (e.g., playit.gg) ]
         │
         ▼
[ mc_tunnel_logger.py ] (Listens on 0.0.0.0:25565)
    ├── 1. Handshake & Login Start  ──> Extracts Username & Source IP
    ├── 2. Play Phase (Client -> Server) ──> Decompresses Zlib & Parses /commands
    └── 3. Transparent Passthrough  ──> Bi-directional relay to preserve traffic integrity
         │
         ▼
[ Target Minecraft Server ] (e.g., yourhost.com:25565)
```

---

## Technical Limitations & Prerequisites

* **Python Version**: Python 3.10 or higher.
* **Server `online-mode=false` Requirement**:
  * In standard Minecraft connections with official Microsoft accounts (`online-mode=true`), the client and server negotiate an AES-128 symmetric cipher during the login phase. Because a passive proxy does not hold the negotiated session keys, in-game packets cannot be decrypted in online mode.
  * To inspect and read commands via this proxy, the target server must have **`online-mode=false`** configured in its `server.properties`. Player joins are always visible regardless of this setting.

---

## Installation

Clone the repository or download the source file directly[cite: 1]:

```bash
git clone https://github.com/Dadox01/Minecraft-Tunnel-Logger
```

No external package installations (`pip`) are required.

---

## Usage

### Basic Command

```bash
python3 mc_tunnel_logger.py --target-ip <SERVER_IP> --target-port <SERVER_PORT> [OPTIONS]
```

### CLI Arguments

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--target-ip` | `str` | *Required* | IP address or domain name of the destination Minecraft server. |
| `--target-port` | `int` | `25565` | Port of the destination Minecraft server. |
| `--listen-host` | `str` | `0.0.0.0` | Host interface to bind the proxy to. Use `127.0.0.1` for local-only traffic. |
| `--listen-port` | `int` | `25566` | Local listening port for clients or tunnels to connect to. |
| `--log-file` | `str` | `None` | Optional file path to persist logged output. |
| `--verbose` | `flag` | `False` | Enables extra logs for server-list pings and connection drops. |

---

## Practical Examples

### Running with a Public Tunnel (e.g., playit.gg)

1. Launch your tunneling client (e.g., playit.gg) and map a TCP tunnel to point to:
   ```text
   127.0.0.1:25565
   ```
2. Start the logger script pointing to your remote game server:
   ```bash
   python3 mc_tunnel_logger.py \
     --target-ip yourserver.hostingprovider.com \
     --target-port 9120 \
     --listen-port 25565 \
     --log-file server_activity.log
   ```
3. Share the public host/port provided by the tunneling agent with your players.

### Localhost Debugging / Private Mode

To ensure only your local machine can connect (rejecting any external traffic from the local network):

```bash
python3 mc_tunnel_logger.py \
  --target-ip remote.server.net \
  --target-port 25565 \
  --listen-host 127.0.0.1 \
  --listen-port 25565
```

Connect your Minecraft client directly to `127.0.0.1:25565`.

---

## Example Console Output

```text
[2026-09-02 21:10:04] Listening on 0.0.0.0:25565 -> yourserver.hostingprovider.com:9120
[2026-09-02 21:10:15] JOIN  'PlayerOne' da 127.125.43.170:21342 (PlayerOne (127.125.43.170:21342) -> yourserver.hostingprovider.com:9120)
[2026-09-02 21:10:21] CMD   [PlayerOne]: /login mySecretPass123
[2026-09-02 21:10:28] CMD   [PlayerOne]: /spawn
[2026-09-02 21:11:05] CMD   [PlayerOne]: /gamemode creative
[2026-09-02 21:11:42] CMD   [PlayerOne]: /tp PlayerTwo
```

---

## Disclaimer

This project is intended strictly for educational, network debugging, and administrative monitoring on servers you own or are authorized to manage. It does not bypass official Mojang authentication or intercept credentials on servers running standard online authentication. Ensure compliance with relevant privacy regulations and platform terms of service before recording network traffic.
