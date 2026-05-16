"""
Auto-deploy REYOG CAPITAL to IDCloudHost VPS via paramiko.

Runs the full deploy:
  1. SCP project tarball
  2. Extract on VPS
  3. Install Docker + Compose
  4. Generate .env with auto-detected IP and random DB password
  5. Build all 6 containers
  6. Start stack + healthcheck wait
  7. Print public URL

Usage:
  python scripts/auto_deploy.py <ip> <password> [user]
"""
import io
import os
import sys
import time
import paramiko
import secrets

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str, kind: str = "info"):
    prefix = {"info": "[i]", "ok": "[+]", "warn": "[!]", "err": "[X]"}.get(kind, "[*]")
    print(f"  {prefix}  {msg}", flush=True)


def section(title: str):
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}", flush=True)


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 600, show: bool = True) -> tuple[int, str, str]:
    """Run a command, stream output, return (exit_code, stdout, stderr)."""
    if show:
        log(f"$ {cmd[:120]}{'…' if len(cmd) > 120 else ''}", "info")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout, get_pty=True)
    out_lines = []
    for line in iter(stdout.readline, ""):
        if not line:
            break
        line = line.rstrip()
        if show and line:
            print(f"    {line}", flush=True)
        out_lines.append(line)
    exit_code = stdout.channel.recv_exit_status()
    err = stderr.read().decode("utf-8", errors="replace")
    return exit_code, "\n".join(out_lines), err


def main():
    if len(sys.argv) < 3:
        print("Usage: python auto_deploy.py <ip> <password> [user]")
        print("       python auto_deploy.py <ip> --key /path/to/key [user]")
        sys.exit(1)

    ip = sys.argv[1]
    password = sys.argv[2]
    user = sys.argv[3] if len(sys.argv) >= 4 else "root"
    key_file = None
    if password == "--key" and len(sys.argv) >= 4:
        key_file = sys.argv[3]
        user = sys.argv[4] if len(sys.argv) >= 5 else "root"
        password = None

    # Try multiple paths
    candidates = [
        "reyog-capital.tar.gz",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reyog-capital.tar.gz"),
        "/tmp/reyog-capital.tar.gz",
        "C:\\tmp\\reyog-capital.tar.gz",
    ]
    tarball = next((p for p in candidates if os.path.exists(p)), None)
    if not tarball:
        log(f"Tarball missing. Looked in: {candidates}", "err")
        sys.exit(1)

    section(f"REYOG CAPITAL auto-deploy → {user}@{ip}")
    log(f"Tarball size: {os.path.getsize(tarball) / 1024:.1f} KB", "info")

    # ─── Connect ───
    section("Step 1/6: SSH connect")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if key_file:
            pkey = paramiko.Ed25519Key.from_private_key_file(key_file)
            ssh.connect(ip, username=user, pkey=pkey,
                        timeout=15, banner_timeout=15, auth_timeout=15)
        else:
            ssh.connect(ip, username=user, password=password,
                        timeout=15, banner_timeout=15, auth_timeout=15)
        log("SSH connected", "ok")
    except Exception as e:
        log(f"SSH failed: {e}", "err")
        log("Check: correct password? Correct username? VPS firewall open on port 22?", "warn")
        sys.exit(2)

    # OS detect
    rc, out, _ = run(ssh, "cat /etc/os-release | head -3", show=False)
    log(f"OS: {out.splitlines()[0] if out else 'unknown'}", "info")
    rc, out, _ = run(ssh, "free -h | head -2", show=False)
    log(f"Memory:\n{out}", "info")

    # ─── Upload tarball ───
    section("Step 2/6: Upload project")
    sftp = ssh.open_sftp()
    # Determine home dir
    rc, home_dir, _ = run(ssh, "echo $HOME", show=False)
    home_dir = home_dir.strip() or f"/home/{user}"
    remote_tar = f"{home_dir}/reyog-capital.tar.gz"
    log(f"SCP → {remote_tar}", "info")
    t0 = time.time()

    def progress(transferred, total):
        pct = 100 * transferred / total if total else 0
        print(f"\r    {pct:.1f}% ({transferred/1024:.1f} KB / {total/1024:.1f} KB)", end="", flush=True)

    sftp.put(tarball, remote_tar, callback=progress)
    print()
    log(f"Upload done in {time.time()-t0:.1f}s", "ok")
    sftp.close()

    # ─── Extract ───
    section("Step 3/6: Extract project")
    # Use home directory (works for non-root user too)
    run(ssh, "mkdir -p ~/reyog-capital && tar -xzf ~/reyog-capital.tar.gz -C ~/reyog-capital")
    rc, out, _ = run(ssh, "ls ~/reyog-capital | head -20", show=False)
    log(f"Extracted files:\n{out}", "info")

    # ─── Detect OS family ───
    rc, os_id, _ = run(ssh, "cat /etc/os-release | grep ^ID= | head -1 | cut -d= -f2 | tr -d '\"'", show=False)
    os_id = os_id.strip().lower()
    is_rhel = os_id in ("almalinux", "rocky", "centos", "rhel", "fedora")
    pkg_install = "sudo dnf install -y" if is_rhel else "sudo apt install -y"
    pkg_update = "sudo dnf check-update -y || true" if is_rhel else "sudo apt update -y"
    log(f"OS family: {os_id} ({'RHEL-based' if is_rhel else 'Debian-based'})", "info")

    # ─── Install Docker ───
    section("Step 4/6: Install Docker + Compose")
    rc, out, _ = run(ssh, "command -v docker && docker --version || echo NOT_INSTALLED", show=False)
    if "NOT_INSTALLED" in out:
        log("Installing Docker…", "info")
        run(ssh, f"{pkg_update} 2>&1 | tail -3", timeout=300)
        run(ssh, f"{pkg_install} curl ca-certificates 2>&1 | tail -3", timeout=300)
        run(ssh, "curl -fsSL https://get.docker.com | sudo sh", timeout=600)
        # Add current user to docker group + enable service
        run(ssh, "sudo systemctl enable --now docker", show=False)
        run(ssh, "sudo usermod -aG docker $(whoami)", show=False)
        rc, out, _ = run(ssh, "sudo docker --version", show=False)
        log(f"Docker installed: {out}", "ok")
    else:
        log(f"Docker already present: {out}", "ok")
        run(ssh, "sudo systemctl enable --now docker 2>/dev/null || true", show=False)

    # Firewall (firewalld on RHEL, ufw on Debian)
    if is_rhel:
        run(ssh, "sudo dnf install -y firewalld 2>&1 | tail -2 || true", timeout=120, show=False)
        run(ssh, "sudo systemctl enable --now firewalld 2>/dev/null || true", show=False)
        run(ssh, "sudo firewall-cmd --permanent --add-port=22/tcp 2>/dev/null || true", show=False)
        run(ssh, "sudo firewall-cmd --permanent --add-port=80/tcp 2>/dev/null || true", show=False)
        run(ssh, "sudo firewall-cmd --permanent --add-port=443/tcp 2>/dev/null || true", show=False)
        run(ssh, "sudo firewall-cmd --reload 2>/dev/null || true", show=False)
    else:
        run(ssh, "sudo ufw allow OpenSSH 2>/dev/null || sudo ufw allow 22/tcp", show=False)
        run(ssh, "sudo ufw allow 80/tcp", show=False)
        run(ssh, "sudo ufw allow 443/tcp", show=False)
        run(ssh, "echo 'y' | sudo ufw enable 2>&1 | tail -3 || true", show=False)
    log("Firewall: 22/80/443 open", "ok")

    # ─── Generate .env ───
    section("Step 5/6: Generate .env")
    db_pw = secrets.token_hex(16)
    env_content = f"""# Auto-generated by auto_deploy.py on {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
REYOG_DOMAIN={ip}
NEXT_PUBLIC_API_URL=http://{ip}
NEXT_PUBLIC_WS_URL=ws://{ip}
CORS_ORIGINS=*

DB_USER=arb
DB_PASSWORD={db_pw}
DB_NAME=ultra_arb
DB_HOST=postgres
DB_PORT=5432
DATABASE_URL=postgresql+asyncpg://arb:{db_pw}@postgres:5432/ultra_arb

REDIS_PASSWORD=reyog_redis_secret
REDIS_URL=redis://:reyog_redis_secret@redis:6379/0

PAPER_TRADE=true
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true
BYBIT_API_KEY=
BYBIT_API_SECRET=
BYBIT_TESTNET=true
POLYMARKET_PRIVATE_KEY=
POLYMARKET_SANDBOX=true
FINANCIAL_DATASETS_API_KEY=

MAX_DRAWDOWN_PCT=2.0
MAX_POSITION_PCT=2.5
MAX_CONCURRENT_POSITIONS=5
VOL_BREAKER_MULTIPLIER=3.0
"""
    sftp = ssh.open_sftp()
    env_path = f"{home_dir}/reyog-capital/.env"
    with sftp.open(env_path, "w") as f:
        f.write(env_content)
    sftp.chmod(env_path, 0o600)
    sftp.close()
    log("Created .env with random 32-char DB password", "ok")

    # ─── Build + start ───
    section("Step 6/6: Build & start containers")
    project_dir = f"{home_dir}/reyog-capital"
    # Non-root user needs sudo for docker (until newgrp picks up group membership)
    docker_cmd = "sudo docker"
    compose_cmd = "sudo docker compose"

    log("Pulling base images (redis, postgres, nginx)…", "info")
    rc, _, _ = run(ssh,
        f"cd {project_dir} && {compose_cmd} pull redis postgres nginx 2>&1 | tail -10",
        timeout=600)

    log("Building app containers (~5-10 min)…", "info")
    rc, _, _ = run(ssh,
        f"cd {project_dir} && {compose_cmd} build 2>&1 | tail -40",
        timeout=1800)
    if rc != 0:
        log(f"Build returned {rc} — try starting anyway", "warn")

    log("Starting stack…", "info")
    run(ssh, f"cd {project_dir} && {compose_cmd} up -d", timeout=180)

    # Wait for healthy
    log("Waiting for services to become healthy…", "info")
    for i in range(60):
        rc, out, _ = run(ssh,
            f"cd {project_dir} && {compose_cmd} ps --format '{{{{.Name}}}} {{{{.State}}}} {{{{.Health}}}}'",
            show=False)
        healthy = out.count("healthy")
        if healthy >= 2:
            log(f"{healthy} healthy containers", "ok")
            break
        time.sleep(3)

    rc, out, _ = run(ssh, f"cd {project_dir} && {compose_cmd} ps", show=False)
    log(f"Final container status:\n{out}", "info")

    # Test endpoints
    section("Verifying public access")
    rc, out, _ = run(ssh, "curl -s -m 5 http://localhost/health", show=False)
    if out:
        log(f"Internal /health: {out}", "ok")
    rc, out, _ = run(ssh, "curl -s -m 5 -o /dev/null -w '%{http_code}' http://localhost/", show=False)
    log(f"Internal / status: HTTP {out}", "ok")

    section("✅ DEPLOY COMPLETE")
    print(f"""
  Dashboard:   http://{ip}/
  API health:  http://{ip}/api/health
  Edge radar:  http://{ip}/api/edges/summary
  WebSocket:   ws://{ip}/ws/firehose

  SSH again:   ssh {user}@{ip}
  Logs:        ssh {user}@{ip} 'cd /root/reyog-capital && docker compose logs -f --tail=100'
  Update:      ssh {user}@{ip} 'cd /root/reyog-capital && git pull && docker compose up -d --build'

  Engine starts placing Polymarket bets automatically every 60s.
  Edge scanners run in background (yes/no arb, smart money, basis carry).
  Real prices from Gate.io + HTX update every second.
""")
    ssh.close()


if __name__ == "__main__":
    main()
