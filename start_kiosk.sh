#!/bin/bash

# --- より安定したネットワーク接続待機 ---
# 4回pingを試し、2回以上成功するまで待つ
echo "ネットワーク接続を確立しています..."
RECEIVED_COUNT=0
while [ "$RECEIVED_COUNT" -lt 2 ]; do
    echo "接続を試行中..."
    # 4回pingを送信し、成功した(received)回数を取得する
    RECEIVED_COUNT=$(ping -c 4 -W 1 8.8.8.8 | grep 'packets transmitted' | awk '{print $4}')

    # pingコマンド自体が失敗した場合、結果が空になるのを防ぐ
    if [ -z "$RECEIVED_COUNT" ]; then
        RECEIVED_COUNT=0
    fi

    # もし接続に失敗していたら、少し待ってから再試行する
    if [ "$RECEIVED_COUNT" -lt 2 ]; then
        sleep 3
    fi
done

echo "ネットワーク接続完了。アプリケーションを起動します。"

# --- 環境変数の設定 ---
# 【重要】このパスは、あなたの環境に合わせて必ず書き換えてください
export KASHI_KIOSK_CREDS_PATH="/home/andolab/okashi-system/useful-figure-462606-f3-d5bf8344ee64.json"

# --- アプリケーションの起動 ---
cd /home/andolab/okashi-system/
python3 main.py
