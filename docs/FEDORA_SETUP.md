# Fedora Setup

Tested on Fedora 44 (Workstation and Server). All commands are exact; run them as a normal user
with `sudo` rights. SELinux stays **enforcing**.

## 1. Base tools

```bash
sudo dnf upgrade --refresh -y
sudo dnf install -y git curl make gcc python3 python3-devel nodejs npm
```

Install `uv` (Python package/venv manager used by the backend and bot):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new shell, then check: `uv --version`, `node --version` (22+).

## 2. Containers — choose one

### Option A: Docker Engine (documented default for servers)

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf-3 config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # log out and back in afterwards
docker compose version
```

### Option B: Podman (preinstalled on Fedora, rootless — what this repo was verified with)

```bash
sudo dnf install -y podman podman-compose
podman --version
```

With Podman use `podman-compose` wherever the docs say `docker compose`. Rootless Podman cannot
bind ports below 1024 by default; either set `HTTP_PORT=8080` for local runs, or on a server:

```bash
echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee /etc/sysctl.d/90-unprivileged-ports.conf
sudo sysctl --system
```

## 3. Firewall (servers)

```bash
sudo firewall-cmd --permanent --add-service=http --add-service=https
sudo firewall-cmd --reload
```

Only 80/443 (and SSH) should be open. PostgreSQL and Redis are never published.

## 4. SELinux notes

Bind mounts in development need relabeling; the dev commands in DEVELOPMENT.md already use named
volumes or `:Z` where required. Never disable SELinux to "fix" a permission error — relabel with
`:Z` (private) or `:z` (shared) instead.

## 5. Next steps

- Local development → [DEVELOPMENT.md](DEVELOPMENT.md)
- Production server → [DEPLOYMENT.md](DEPLOYMENT.md)
