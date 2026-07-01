#!/bin/sh
set -e

cat > /etc/alertmanager/alertmanager.yml <<EOF
route:
  receiver: "telegram"
  group_by: ["alertname"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: "telegram"
    telegram_configs:
      - bot_token: "${TELEGRAM_BOT_TOKEN}"
        chat_id: ${TELEGRAM_CHAT_ID}
        parse_mode: "HTML"
EOF

exec /bin/alertmanager --config.file=/etc/alertmanager/alertmanager.yml --storage.path=/alertmanager
