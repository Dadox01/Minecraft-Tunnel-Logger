#!/usr/bin/env python3

import argparse
import socket
import struct
import sys
import threading
import zlib
from datetime import datetime

COMMON_COMMANDS = {
    "help", "gamemode", "gm", "gmc", "gms", "gma", "gmsp", "tp", "teleport",
    "tpa", "tpaccept", "tpdeny", "tpcancel", "spawn", "setspawn", "home",
    "sethome", "delhome", "warp", "setwarp", "delwarp", "back", "rt", "rtp",
    "wild", "kit", "kits", "msg", "tell", "w", "r", "reply", "mail", "m",
    "pay", "bal", "balance", "money", "eco", "shop", "sell", "buy", "login",
    "l", "register", "reg", "changepassword", "cp", "unregister", "op", "deop",
    "ban", "kick", "pardon", "unban", "tempban", "mute", "tempmute", "unmute",
    "stop", "reload", "rl", "restart", "whitelist", "give", "clear", "effect",
    "enchant", "xp", "experience", "time", "weather", "difficulty", "seed",
    "kill", "suicide", "afk", "fly", "god", "heal", "feed", "hat", "craft",
    "workbench", "echest", "enderchest", "anvil", "repair", "trash", "rules",
    "discord", "link", "vote", "rank", "ranks", "lp", "luckperms", "co",
    "coreprotect", "claim", "claims", "trust", "untrust", "lands", "land",
    "clan", "clans", "quest", "quests", "trade", "ah", "ping", "tps", "pl",
    "plugins", "ver", "version", "vanish", "v"
}


class ProtocolError(Exception):
    pass


def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed while reading")
        buf.extend(chunk)
    return bytes(buf)


def read_varint_from_socket(sock: socket.socket):
    value = 0
    raw = bytearray()
    for i in range(5):
        b = recv_exact(sock, 1)
        raw += b
        byte_val = b[0]
        value |= (byte_val & 0x7F) << (7 * i)
        if not (byte_val & 0x80):
            return value, bytes(raw)
    raise ProtocolError("VarInt too long")


def read_varint_from_bytes(data: bytes, offset: int = 0):
    value = 0
    for i in range(5):
        if offset >= len(data):
            raise ProtocolError("Buffer too short for VarInt")
        byte_val = data[offset]
        offset += 1
        value |= (byte_val & 0x7F) << (7 * i)
        if not (byte_val & 0x80):
            return value, offset
    raise ProtocolError("VarInt too long")


def read_string_from_bytes(data: bytes, offset: int = 0):
    length, offset = read_varint_from_bytes(data, offset)
    if offset + length > len(data):
        raise ProtocolError("Buffer too short for string")
    s = data[offset:offset + length].decode("utf-8", errors="replace")
    return s, offset + length


def read_full_packet(sock: socket.socket):
    length, length_raw = read_varint_from_socket(sock)
    payload = recv_exact(sock, length)
    return length_raw + payload, payload


class Handshake:
    def __init__(self, protocol_version, server_address, server_port, next_state):
        self.protocol_version = protocol_version
        self.server_address = server_address
        self.server_port = server_port
        self.next_state = next_state


def parse_handshake(payload: bytes) -> Handshake:
    offset = 0
    packet_id, offset = read_varint_from_bytes(payload, offset)
    if packet_id != 0x00:
        raise ProtocolError(f"Expected 0x00 for handshake, got {packet_id:#x}")
    protocol_version, offset = read_varint_from_bytes(payload, offset)
    server_address, offset = read_string_from_bytes(payload, offset)
    server_port = struct.unpack(">H", payload[offset:offset + 2])[0]
    offset += 2
    next_state, offset = read_varint_from_bytes(payload, offset)
    return Handshake(protocol_version, server_address, server_port, next_state)


def parse_login_start_username(payload: bytes) -> str:
    offset = 0
    packet_id, offset = read_varint_from_bytes(payload, offset)
    if packet_id != 0x00:
        raise ProtocolError(f"Expected 0x00 for login start, got {packet_id:#x}")
    username, offset = read_string_from_bytes(payload, offset)
    return username


def get_candidate_payloads(raw_body: bytes) -> list[bytes]:
    candidates = []

    try:
        data_len, offset = read_varint_from_bytes(raw_body, 0)
        if data_len == 0 and offset < len(raw_body):
            candidates.append(raw_body[offset:])
        elif data_len > 0 and offset < len(raw_body):
            decompressed = zlib.decompress(raw_body[offset:])
            candidates.append(decompressed)
    except Exception:
        pass

    try:
        candidates.append(zlib.decompress(raw_body))
    except Exception:
        pass

    candidates.append(raw_body)
    return candidates


def extract_command_or_chat(payload: bytes) -> tuple[str, str] | None:
    if not payload or len(payload) < 2:
        return None
    try:
        packet_id, offset = read_varint_from_bytes(payload, 0)
        text, _ = read_string_from_bytes(payload, offset)
        if not text:
            return None

        clean_text = "".join(c for c in text if c.isprintable())
        clean_text = " ".join(clean_text.split()).strip()
        if not clean_text:
            return None

        if ":" in clean_text or (len(clean_text) == 5 and clean_text[2] == "_" and clean_text[:2].isalpha()):
            return None

        if clean_text.startswith("/"):
            if clean_text == "/":
                return None
            return ("CMD", clean_text)

        first_token = clean_text.split()[0].lower()
        if first_token in COMMON_COMMANDS:
            return ("CMD", f"/{clean_text}")

        if first_token.isalnum() or "_" in first_token:
            return ("CHAT/CMD", clean_text)

    except Exception:
        pass
    return None


_log_lock = threading.Lock()
_log_file_handle = None


def setup_log_file(path: str):
    global _log_file_handle
    if path:
        _log_file_handle = open(path, "a", encoding="utf-8")


def log_event(message: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    with _log_lock:
        print(line, flush=True)
        if _log_file_handle:
            _log_file_handle.write(line + "\n")
            _log_file_handle.flush()


def pipe_target_to_client(target_sock: socket.socket, client_sock: socket.socket):
    try:
        while True:
            data = target_sock.recv(4096)
            if not data:
                break
            client_sock.sendall(data)
    except OSError:
        pass
    finally:
        try:
            client_sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def pipe_client_to_target(client_sock: socket.socket, target_sock: socket.socket, username: str):
    try:
        while True:
            length, length_raw = read_varint_from_socket(client_sock)
            raw_body = recv_exact(client_sock, length)

            target_sock.sendall(length_raw + raw_body)

            for candidate in get_candidate_payloads(raw_body):
                res = extract_command_or_chat(candidate)
                if res:
                    tag, content = res
                    if tag == "CMD":
                        log_event(f"CMD   [{username}]: {content}")
                    elif tag == "CHAT/CMD":
                        log_event(f"LOG   [{username}]: {content}")
                    break
    except (ProtocolError, ConnectionError, OSError):
        pass
    finally:
        try:
            target_sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def relay(client_sock: socket.socket, target_sock: socket.socket, username: str, label: str, verbose: bool):
    t_c2s = threading.Thread(
        target=pipe_client_to_target,
        args=(client_sock, target_sock, username),
        daemon=True,
    )
    t_s2c = threading.Thread(
        target=pipe_target_to_client,
        args=(target_sock, client_sock),
        daemon=True,
    )
    t_c2s.start()
    t_s2c.start()
    t_c2s.join()
    t_s2c.join()
    if verbose:
        log_event(f"Connection closed: {label}")
    client_sock.close()
    target_sock.close()


def handle_client(client_sock: socket.socket, client_addr, target_ip: str, target_port: int, verbose: bool):
    client_ip, client_port = client_addr[0], client_addr[1]
    label = f"{client_ip}:{client_port} -> {target_ip}:{target_port}"
    username = f"Player_{client_ip}"

    try:
        target_sock = socket.create_connection((target_ip, target_port), timeout=10)
    except OSError as e:
        log_event(f"ERROR: unable to reach {target_ip}:{target_port} ({e})")
        client_sock.close()
        return

    try:
        raw1, payload1 = read_full_packet(client_sock)
        pending_raw = raw1

        try:
            hs = parse_handshake(payload1)
        except ProtocolError:
            hs = None

        if hs is not None and hs.next_state == 2:
            raw2, payload2 = read_full_packet(client_sock)
            pending_raw += raw2
            try:
                username = parse_login_start_username(payload2)
                log_event(f"JOIN  '{username}' from {client_ip}:{client_port} ({label})")
                label = f"{username} ({client_ip}:{client_port}) -> {target_ip}:{target_port}"
            except ProtocolError:
                log_event(f"Unrecognized LOGIN from {client_ip}:{client_port}")
        elif hs is not None and hs.next_state == 1:
            if verbose:
                log_event(f"Server-list PING from {client_ip}:{client_port}")

        target_sock.sendall(pending_raw)

    except (ProtocolError, ConnectionError, OSError) as e:
        if verbose:
            log_event(f"Handshake error ({e}), closing.")
        client_sock.close()
        target_sock.close()
        return

    relay(client_sock, target_sock, username, label, verbose)


def main():
    parser = argparse.ArgumentParser(description="Transparent Minecraft TCP proxy with join and command logging.")
    parser.add_argument("--target-ip", required=True, help="Target Minecraft server IP or hostname")
    parser.add_argument("--target-port", type=int, default=25565, help="Target server port (default: 25565)")
    parser.add_argument("--listen-host", default="0.0.0.0", help="Local listen host (default: 0.0.0.0)")
    parser.add_argument("--listen-port", type=int, default=25566, help="Local proxy listen port (default: 25566)")
    parser.add_argument("--log-file", default=None, help="Optional log file path")
    parser.add_argument("--verbose", action="store_true", help="Show verbose ping and disconnect logs")
    args = parser.parse_args()

    setup_log_file(args.log_file)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((args.listen_host, args.listen_port))
    server_sock.listen(50)

    log_event(f"Listening on {args.listen_host}:{args.listen_port} -> {args.target_ip}:{args.target_port}")

    try:
        while True:
            client_sock, client_addr = server_sock.accept()
            threading.Thread(
                target=handle_client,
                args=(client_sock, client_addr, args.target_ip, args.target_port, args.verbose),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        log_event("Stopping proxy.")
    finally:
        server_sock.close()
        if _log_file_handle:
            _log_file_handle.close()


if __name__ == "__main__":
    main()