#!/bin/bash
set -euxo pipefail

dnf update -y
dnf install -y docker
systemctl enable docker
systemctl start docker
usermod -a -G docker ec2-user

mkdir -p /opt/mediamtx
cat <<'EOF' >/opt/mediamtx/mediamtx.yml
${mediamtx_config}
EOF

chmod 640 /opt/mediamtx/mediamtx.yml

/usr/bin/docker pull bluenviron/mediamtx:${mediamtx_version}
if /usr/bin/docker ps -a --format '{{.Names}}' | grep -q '^mediamtx$'; then
  /usr/bin/docker rm -f mediamtx
fi

/usr/bin/docker run -d \
  --name mediamtx \
  --restart unless-stopped \
  -p 8554:8554/tcp \
  -p 1935:1935/tcp \
  -p 8888:8888/tcp \
  -p 8889:8889/tcp \
  -p 9998:9998/tcp \
  -p 9999:9999/tcp \
  -p 8200:8200/udp \
  -v /opt/mediamtx/mediamtx.yml:/mediamtx.yml:ro \
  bluenviron/mediamtx:${mediamtx_version}

%{ if domain_name != "" }
mkdir -p /opt/caddy /opt/caddy/data /opt/caddy/config
cat <<'EOF' >/opt/caddy/Caddyfile
${caddy_config}
EOF

/usr/bin/docker pull caddy:2
if /usr/bin/docker ps -a --format '{{.Names}}' | grep -q '^caddy$'; then
  /usr/bin/docker rm -f caddy
fi

/usr/bin/docker run -d \
  --name caddy \
  --restart unless-stopped \
  --network host \
  -v /opt/caddy/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v /opt/caddy/data:/data \
  -v /opt/caddy/config:/config \
  caddy:2
%{ endif }
