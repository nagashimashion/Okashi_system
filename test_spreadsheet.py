import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import sys

# --- 設定 ---
SERVICE_ACCOUNT_FILE = './deft-scope-462604-p2-9f796b1cb1f6.json'
SPREADSHEET_NAME = '在庫管理ログ'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

# ★★★重要★★★
# あなたの「在庫マスター」シートに実際に存在するJANコードを一つ、ここに設定してください。
# このコードを使って検索・更新テストを行います。
TEST_JAN_CODE = '4902777008592' # 例：きのこの山のJANコード

def run_test():
    print("--- スプレッドシート接続テストを開始します ---")
    
    # --- 1. 認証と接続 ---
    try:
        print("1. サービスアカウントの認証情報を読み込んでいます...")
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        gc = gspread.authorize(creds)
        
        print("2. スプレッドシートを開いています...")
        spreadsheet = gc.open(SPREADSHEET_NAME)
        
        print("3. 「在庫マスター」と「消費ログ」シートを取得しています...")
        master_sheet = spreadsheet.worksheet('在庫マスター')
        log_sheet = spreadsheet.worksheet('消費ログ')
        
        print("\n✅ 接続成功！ スプレッドシートとシートの読み込みが完了しました。\n")

    except gspread.exceptions.SpreadsheetNotFound:
        print("\n❌ エラー: スプレッドシートが見つかりません。")
        print(f"ファイル名が「{SPREADSHEET_NAME}」で正しいか、Googleドライブで確認してください。")
        sys.exit() # プログラムを終了
    except gspread.exceptions.WorksheetNotFound:
        print("\n❌ エラー: 必要なシートが見つかりません。")
        print("「在庫マスター」と「消費ログ」という名前のシートが存在するか確認してください。")
        sys.exit()
    except Exception as e:
        print("\n❌ エラー: 認証または接続中に問題が発生しました。")
        print(" - service_account.jsonファイルは正しい場所にありますか？")
        print(" - スプレッドシートの「共有」設定で、サービスアカウントのメールアドレスを編集者として追加しましたか？")
        print(f"詳細エラー: {e}")
        sys.exit()

    # --- 2. 読み取りと書き込みテスト ---
    try:
        # 在庫マスターから商品を検索
        print(f"4. 在庫マスターからテスト商品（JAN: {TEST_JAN_CODE}）を検索します...")
        cell = master_sheet.find(TEST_JAN_CODE, in_column=1)
        
        if cell:
            product_name = master_sheet.cell(cell.row, 2).value
            print(f"   -> ✅ 「{product_name}」が見つかりました。")
            
            # 「備考」列（F列=6列目）をテスト用に更新
            print("5. 備考欄にテスト書き込みをします...")
            master_sheet.update_cell(cell.row, 6, f"接続テストOK @ {datetime.now().strftime('%H:%M')}")
            print("   -> ✅ 備考欄の更新に成功しました。")
        else:
            print(f"\n❌ エラー: 在庫マスターにテスト用JANコード「{TEST_JAN_CODE}」が見つかりませんでした。")
            print("   -> `test_spreadsheet.py`のTEST_JAN_CODEを、あなたのシートに存在するコードに変更してください。")
            sys.exit()

        # 消費ログにテストデータを追記
        print("6. 消費ログにテスト書き込みをします...")
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_sheet.append_row([timestamp, TEST_JAN_CODE, "接続テスト用アイテム"])
        print("   -> ✅ ログの書き込みに成功しました。")

    except Exception as e:
        print("\n❌ エラー: データの読み書き中に問題が発生しました。")
        print(f"詳細エラー: {e}")
        sys.exit()
        
    print("\n--- ✅ 全てのテストが正常に完了しました！ ---")

# スクリプトを実行
if __name__ == '__main__':
    run_test()
