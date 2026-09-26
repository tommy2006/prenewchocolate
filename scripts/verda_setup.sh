#!/usr/bin/env bash
# Scout's AI on your own GPU server (for example a Verda instance), instead of a paid AI API.
#
# Runs an open model with vLLM behind an OpenAI-compatible address, as a service that restarts by itself
# (also after a spot instance comes back). Run it once on the server, as root:
#
#     scp scripts/verda_setup.sh root@SERVER-IP:  &&  ssh root@SERVER-IP 'bash verda_setup.sh'
#
# At the end it prints the address and API key to paste into Scout: Settings -> Your GPU server.
#
# Options (environment variables):
#   MODEL=org/name   Hugging Face model. Default: picked from the GPU memory (see below).
#   PORT=8000        Port of the OpenAI-compatible API.
#   PUBLIC=1         1 (default): reachable on the server's IP, protected by the API key.
#                    0: only on the server itself; reach it from your computer with an SSH tunnel:
#                       ssh -N -L 8000:localhost:8000 root@SERVER-IP   (then use http://localhost:8000/v1)
#   HF_TOKEN=...     Hugging Face token, only for gated models.
set -euo pipefail

PORT="${PORT:-8000}"
PUBLIC="${PUBLIC:-1}"
DIR=/opt/scout-ai
MAX_LEN="${MAX_LEN:-32768}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "Run this as root."; exit 1; }
command -v nvidia-smi >/dev/null || { echo "No NVIDIA driver (nvidia-smi) found. Pick a GPU image for the server."; exit 1; }

GPUS=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
MEM_GB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk '{s+=$1} END {print int(s/1024)}')
mkdir -p "$DIR"
FREE_GB=$(df -BG --output=avail "$DIR" | tail -1 | tr -dc '0-9')
say "Server: ${GPUS}x ${GPU_NAME}, ${MEM_GB} GB GPU memory, ${FREE_GB} GB free disk"

# The model. Scout needs good Finnish/German/Swedish, reliable JSON and sound judgement.
#   >= 250 GB GPU memory and ~260 GB disk (e.g. 2x H200): Qwen3-235B-A22B-Instruct-2507 in FP8 (MoE, 22B active: fast).
#   otherwise (>= 70 GB):                                 Qwen3-30B-A3B-Instruct-2507.
if [ -z "${MODEL:-}" ]; then
  if [ "$MEM_GB" -ge 250 ] && [ "$FREE_GB" -ge 260 ]; then
    MODEL=Qwen/Qwen3-235B-A22B-Instruct-2507-FP8
  elif [ "$MEM_GB" -ge 70 ] && [ "$FREE_GB" -ge 75 ]; then
    MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
    [ "$MEM_GB" -ge 250 ] && echo "Not enough disk for the large model (${FREE_GB} GB free, ~260 GB needed): using the smaller one."
  else
    echo "Need at least ~70 GB of GPU memory and ~75 GB of free disk. Set MODEL=... to choose a smaller model."
    exit 1
  fi
fi
TP="${TP:-$GPUS}"
say "Model: $MODEL (tensor parallel over $TP GPUs)"

say "Installing vLLM (a few minutes the first time)"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
[ -x "$DIR/venv/bin/python" ] || uv venv "$DIR/venv" --python 3.12
uv pip install --python "$DIR/venv/bin/python" --upgrade vllm huggingface_hub

say "Downloading the model (can take 10-30 minutes for the large one; it's kept for next time)"
export HF_HOME="$DIR/hf"
[ -n "${HF_TOKEN:-}" ] && export HF_TOKEN
"$DIR/venv/bin/python" -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1])" "$MODEL"

# The API key Scout sends. Kept on the server, so re-running this script keeps the same key.
[ -s "$DIR/api_key" ] || "$DIR/venv/bin/python" -c "import secrets; print(secrets.token_hex(24))" > "$DIR/api_key"
chmod 600 "$DIR/api_key"
KEY=$(cat "$DIR/api_key")
HOST=127.0.0.1
[ "$PUBLIC" = "1" ] && HOST=0.0.0.0

say "Starting the service (scout-ai)"
cat > /etc/systemd/system/scout-ai.service <<EOF
[Unit]
Description=Scout AI: $MODEL via vLLM (OpenAI-compatible API)
After=network-online.target
Wants=network-online.target

[Service]
Environment=HF_HOME=$DIR/hf
Environment=HF_HUB_OFFLINE=1
Environment=VLLM_API_KEY=$KEY
ExecStart=$DIR/venv/bin/vllm serve $MODEL --served-model-name scout --host $HOST --port $PORT --tensor-parallel-size $TP --max-model-len $MAX_LEN --gpu-memory-utilization 0.92
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
chmod 600 /etc/systemd/system/scout-ai.service
systemctl daemon-reload
systemctl enable scout-ai >/dev/null
systemctl restart scout-ai
if [ "$PUBLIC" = "1" ] && command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow "$PORT/tcp" >/dev/null
fi

say "Loading the model onto the GPUs (usually 3-10 minutes)"
for _ in $(seq 1 180); do
  if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  if ! systemctl is-active --quiet scout-ai; then
    echo "The service stopped. Last log lines:"; journalctl -u scout-ai -n 40 --no-pager; exit 1
  fi
  sleep 10
done
curl -fs "http://127.0.0.1:$PORT/health" >/dev/null || { echo "Not ready after 30 minutes. Check: journalctl -u scout-ai -f"; exit 1; }

REPLY=$(curl -fs "http://127.0.0.1:$PORT/v1/chat/completions" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"scout","messages":[{"role":"user","content":"Say hei in Finnish, one word."}],"max_tokens":10}' \
  | "$DIR/venv/bin/python" -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'].strip())" \
  || echo "(no answer: check journalctl -u scout-ai)")
say "Ready. Test answer: $REPLY"

IP=$(curl -fs --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')
ADDRESS="http://$IP:$PORT/v1"
[ "$PUBLIC" = "1" ] || ADDRESS="http://localhost:$PORT/v1   (after: ssh -N -L $PORT:localhost:$PORT root@$IP)"
cat <<EOF

In Scout: Settings -> Search AI -> "Your GPU server"
  Address:  $ADDRESS
  API key:  $KEY
  Model:    scout
Then choose "Your GPU server" as the Writing AI too, and press Save.

Useful: journalctl -u scout-ai -f (logs) · systemctl restart scout-ai · nvidia-smi
EOF
if [ "$PUBLIC" = "1" ]; then
  echo "Note: the address is plain HTTP; the API key is what protects it. For an encrypted connection,"
  echo "run with PUBLIC=0 and use an SSH tunnel. If the address doesn't answer from your computer, open"
  echo "TCP port $PORT in the server's firewall settings (Verda console)."
fi
