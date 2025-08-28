import requests

url = "https://oauth2.googleapis.com/token"
print(f"接続テストを開始します: {url}")

try:
    # SSL証明書の検証を有効にしたまま接続を試みます
    response = requests.get(url, timeout=10)
    
    print("\n--- 結果 ---")
    print("✅ 接続に成功しました！")
    print(f"ステータスコード: {response.status_code}")
    print("---------------------------------")
    print("ネットワーク経路は正常です。もしgspreadでだけエラーが起きる場合、別の問題が考えられます。")


except requests.exceptions.SSLError as e:
    print("\n--- 結果 ---")
    print("❌ SSLErrorが発生しました。")
    print("---------------------------------")
    print("原因はやはりSSL証明書の問題のようです。大学ネットワークのセキュリティ機能が通信に介在しています。")
    print("次のステップでこの問題を回避します。")
    # print(f"詳細: {e}") # より詳細なエラーを見たい場合はこの行のコメントを外す

except requests.exceptions.ConnectionError as e:
    print("\n--- 結果 ---")
    print("❌ ConnectionErrorが発生しました。")
    print("---------------------------------")
    print("SSL以外の、より低レベルな接続問題がPython環境で発生しているようです。")
    # print(f"詳細: {e}")

except Exception as e:
    print(f"\n予期せぬエラーが発生しました: {e}")
