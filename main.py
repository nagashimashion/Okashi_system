# ==============================================================================
# ライブラリのインポート
# ==============================================================================
# Tkinter: Python標準のGUIライブラリ。画面の作成やボタンの配置などに使用。
import tkinter as tk
from tkinter import font, messagebox

# gspread: Googleスプレッドシートを操作するためのライブラリ。
import gspread
from google.oauth2.service_account import Credentials

# その他、日付や時間、システム関連の標準ライブラリ
from datetime import datetime
import time
import sys
import os
import threading
import queue
# sslライブラリのインポートを削除


# ==============================================================================
# 全体設定
# ==============================================================================
# 認証キー（JSONファイル）のパスが設定されている環境変数の名前
CREDENTIALS_ENV_VAR = 'KASHI_KIOSK_CREDS_PATH'
# 操作対象のGoogleスプレッドシートのファイル名
SPREADSHEET_NAME = '購買部在庫管理システム'
# APIの操作範囲（スコープ）。この設定でOK。
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
# キャッシュを自動更新する間隔をミリ秒で指定（1時間 = 3,600,000ミリ秒）
REFRESH_INTERVAL_MS = 3600000

# スプレッドシートの列構成を一括管理。列の順番が変わったらここだけ修正する。
# A列=1, B列=2, ...
COLUMN_MAP = {
    'name': 1,      # 商品名
    'price': 3,     # 価格
    'stock': 4,     # 在庫
    'jan': 6        # JANコード
}


# ==============================================================================
# アプリケーション本体のクラス定義
# ==============================================================================
class App(tk.Tk):
    """
    在庫管理システムのGUIアプリケーション全体を管理するクラス。
    tk.Tkを継承して、ウィンドウそのものとして振る舞う。
    """
    def __init__(self):
        # 親クラス(tk.Tk)の初期化処理を呼び出す
        super().__init__()

        # --- インスタンス変数の初期化 ---
        self.last_transaction = None
        self.product_cache = {}
        self.update_queue = queue.Queue()

        # --- ウィンドウの基本設定 ---
        self.title("在庫管理システム")
        self.attributes('-fullscreen', True)
        self.configure(bg='#D0F0C0')

        # --- フォントの定義 ---
        self.info_font = font.Font(family="Helvetica", size=16)
        self.result_font = font.Font(family="Helvetica", size=22, weight="bold")
        self.button_font = font.Font(family="Helvetica", size=12)

        # --- 動的にテキストを変更するための専用変数 ---
        self.info_text = tk.StringVar(value="スプレッドシートに接続中...")
        self.result_text = tk.StringVar(value="")
        self.entry_text = tk.StringVar()

        # --- GUI部品（ウィジェット）の作成 ---
        info_label = tk.Label(self, textvariable=self.info_text, font=self.info_font, bg=self.cget('bg'))
        result_label = tk.Label(self, textvariable=self.result_text, font=self.result_font, bg=self.cget('bg'), wraplength=460, justify=tk.CENTER)
        self.cancel_button = tk.Button(self, text="直前の操作を取り消す", font=self.button_font, command=self.undo_last_transaction, width=18, height=2, state=tk.DISABLED)
        self.hidden_entry = tk.Entry(self, textvariable=self.entry_text)

        # --- ウィジェットの画面への配置 ---
        # .place()を使い、各部品を精密に配置する
        info_label.place(relx=0.5, y=35, anchor='center')
        result_label.place(relx=0.5, rely=0.5, anchor='center')
        self.cancel_button.place(relx=0.5, rely=1.0, y=-30, anchor='s')
        self.hidden_entry.place(x=-1000, y=-1000)

        # --- キーボードイベントの紐付け ---
        self.bind('<Return>', self.handle_scan)
        self.bind('<Escape>', self.quit_app)
        self.hidden_entry.focus_set()

        # --- 起動時の初期処理 ---
        self.connect_and_build_cache()
        self.process_queue()

    def connect_and_build_cache(self):
        """アプリ起動時に一度だけ実行。スプレッドシートへの接続と、初回のキャッシュ構築を行う"""
        try:
            credential_path = os.environ.get(CREDENTIALS_ENV_VAR)
            if not credential_path:
                raise ValueError(f"エラー: 環境変数 '{CREDENTIALS_ENV_VAR}' が設定されていません。")
            creds = Credentials.from_service_account_file(credential_path, scopes=SCOPES)
            self.gc = gspread.authorize(creds)
            self.spreadsheet = self.gc.open(SPREADSHEET_NAME)
            self.master_sheet = self.spreadsheet.worksheet('商品マスタ')
            self.log_sheet = self.spreadsheet.worksheet('購入履歴')
            self.rebuild_cache()
            self.after(REFRESH_INTERVAL_MS, self.refresh_cache_periodically)
        except Exception as e:
            self.info_text.set("エラー：起動に失敗しました")
            messagebox.showerror("起動エラー", f"スプレッドシートの読み込みに失敗しました。\n詳細: {e}")
            self.destroy()

    def rebuild_cache(self):
        """商品マスタを読み込み直し、メモリ上のキャッシュを再構築する"""
        self.info_text.set("商品マスタを読み込み中...")
        self.update_idletasks()
        all_products = self.master_sheet.get_all_records()
        temp_cache = {}
        for i, product in enumerate(all_products):
            jan_code = str(product.get('JAN', ''))
            if jan_code:
                temp_cache[jan_code] = {
                    'name': product.get('商品名'),
                    'price': int(product.get('価格')),
                    'stock': int(product.get('在庫')),
                    'row': i + 2
                }
        self.product_cache = temp_cache
        print(f"[{datetime.now().strftime('%H:%M:%S')}] キャッシュが更新されました。商品数: {len(self.product_cache)}")
        self.info_text.set('商品のバーコードをスキャンしてください')

    def refresh_cache_periodically(self):
        """一定時間ごとにキャッシュを更新し、次の更新を予約する"""
        try:
            self.gc.auth.refresh(self.gc.http_client)
            self.rebuild_cache()
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] キャッシュの自動更新に失敗しました: {e}", file=sys.stderr)
            self.info_text.set("一時的に更新失敗(動作に影響なし)")
            self.after(5000, lambda: self.info_text.set('商品のバーコードをスキャンしてください'))
        finally:
            self.after(REFRESH_INTERVAL_MS, self.refresh_cache_periodically)

    def find_and_update_cache_online(self, jan_code):
        """指定されたJANコードをスプレッドシートから直接検索し、見つかればキャッシュを更新する"""
        try:
            self.info_text.set(f"オンライン検索中...")
            self.update_idletasks()
            cell = self.master_sheet.find(jan_code, in_column=COLUMN_MAP['jan'])
            if cell:
                row_values = self.master_sheet.row_values(cell.row)
                self.product_cache[jan_code] = {
                    'name': row_values[COLUMN_MAP['name'] - 1],
                    'price': int(row_values[COLUMN_MAP['price'] - 1]),
                    'stock': int(row_values[COLUMN_MAP['stock'] - 1]),
                    'row': cell.row
                }
                print(f"[{datetime.now().strftime('%H:%M:%S')}] オンライン検索で商品を発見し、キャッシュを更新: {jan_code}")
                return True
            else:
                return False
        except Exception as e:
            print(f"オンライン検索中にエラー: {e}", file=sys.stderr)
            return False

    def handle_scan(self, event=None):
        """Enterキーが押された（＝スキャンが完了した）時のメイン処理"""
        time.sleep(0.1)
        jan_code = self.entry_text.get().strip()
        if not jan_code: return

        self.cancel_button.config(state=tk.DISABLED)
        self.last_transaction = None
        self.info_text.set(f'スキャンしました: {jan_code}')
        self.update_idletasks()

        product_data = self.product_cache.get(jan_code)
        if not product_data:
            if self.find_and_update_cache_online(jan_code):
                product_data = self.product_cache.get(jan_code)
            else:
                self.info_text.set('商品のバーコードをスキャンしてください')

        if product_data:
            if product_data['stock'] > 0:
                new_stock = product_data['stock'] - 1
                self.product_cache[jan_code]['stock'] = new_stock
                product_name = product_data['name']
                price = product_data['price']
                self.result_text.set(f'{product_name} {price}円\n残り: {new_stock}個')

                timestamp = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
                log_data = [timestamp, jan_code, product_name, 1, price]
                self.last_transaction = {'jan': jan_code, 'log_data': log_data}
                self.cancel_button.config(state=tk.NORMAL)

                thread = threading.Thread(target=self.update_sheets_in_background, args=(product_data['row'], new_stock, log_data, jan_code, COLUMN_MAP['stock']), daemon=True)
                thread.start()
            else:
                self.result_text.set(f"{product_data['name']}\nは在庫がありません！")
        else:
            self.result_text.set('この商品は未登録です')

        self.entry_text.set("")
        self.hidden_entry.focus_set()

    def update_sheets_in_background(self, row, new_stock, log_data, jan_code, stock_col):
        """時間のかかる書き込み処理を裏側で実行する"""
        try:
            self.master_sheet.update_cell(row, stock_col, new_stock)
            self.log_sheet.append_row(log_data)
            print(f"バックグラウンド更新成功: {jan_code}")
        except Exception as e:
            print(f"バックグラウンド更新エラー: {e}", file=sys.stderr)
            error_info = {'jan': jan_code, 'message': f"{log_data[2]}の\n更新に失敗しました"}
            self.update_queue.put(error_info)

    def process_queue(self):
        """キューをチェックして、バックグラウンドからのメッセージがあれば処理する"""
        try:
            message = self.update_queue.get_nowait()
            if message:
                jan_code = message.get('jan')
                if jan_code and jan_code in self.product_cache:
                    self.product_cache[jan_code]['stock'] += 1
                self.result_text.set(message.get('message', '不明なエラー'))
                self.last_transaction = None
                self.cancel_button.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_queue)

    def undo_last_transaction(self):
        """直前のスキャン操作を取り消す処理"""
        if not self.last_transaction:
            self.result_text.set("取り消す操作がありません")
            return

        self.info_text.set(f"取り消し処理中...")
        self.update_idletasks()
        try:
            jan_code = self.last_transaction['jan']
            product_data = self.product_cache.get(jan_code)
            if not product_data:
                raise Exception("キャッシュに商品が見つかりません")

            restored_stock = product_data['stock'] + 1
            self.master_sheet.update_cell(product_data['row'], COLUMN_MAP['stock'], restored_stock)
            self.product_cache[jan_code]['stock'] = restored_stock

            all_log_data = self.log_sheet.get_all_values()
            for i in range(len(all_log_data) - 1, 0, -1):
                log_to_check = [str(item) for item in self.last_transaction['log_data']]
                if all_log_data[i] == log_to_check:
                    self.log_sheet.delete_rows(i + 1)
                    break

            self.result_text.set(f"{product_data['name']}の購入を\n取り消しました (残り: {restored_stock}個)")
        except Exception as e:
            self.result_text.set("取り消し中にエラーが発生しました")
            print(f"取り消しエラー詳細: {e}", file=sys.stderr)
        finally:
            self.last_transaction = None
            self.cancel_button.config(state=tk.DISABLED)
            self.info_text.set('商品のバーコードをスキャンしてください')

    def quit_app(self, event=None):
        """Escapeキーでアプリケーションを終了する"""
        self.destroy()


# ==============================================================================
# アプリケーションの実行ブロック
# ==============================================================================
if __name__ == "__main__":
    app = App()
    app.mainloop()
