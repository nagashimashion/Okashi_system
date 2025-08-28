import tkinter as tk
from tkinter import font, messagebox
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import sys
import os
import threading  # ★★★ 新規：バックグラウンド処理（スレッド）のためにインポート ★★★
import queue      # ★★★ 新規：スレッド間の通信のためにインポート ★★★

# --- 設定 ---
# SERVICE_ACCOUNT_FILEは環境変数から取得するように変更
CREDENTIALS_ENV_VAR = 'KASHI_KIOSK_CREDS_PATH'
SPREADSHEET_NAME = '購買部在庫管理システム'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
REFRESH_INTERVAL_MS = 3600000 

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.last_transaction = None
        self.product_cache = {}
        # ★★★ 新規：バックグラウンド処理との通信用キュー ★★★
        self.update_queue = queue.Queue()

        self.title("在庫管理システム")
        self.attributes('-fullscreen', True)
        self.configure(bg='#D0F0C0')

        self.info_font = font.Font(family="Helvetica", size=16)
        self.result_font = font.Font(family="Helvetica", size=22, weight="bold")
        self.button_font = font.Font(family="Helvetica", size=12)

        self.info_text = tk.StringVar(value="スプレッドシートに接続中...")
        self.result_text = tk.StringVar(value="")
        self.entry_text = tk.StringVar()

        info_label = tk.Label(self, textvariable=self.info_text, font=self.info_font, bg=self.cget('bg'))
        result_label = tk.Label(self, textvariable=self.result_text, font=self.result_font, bg=self.cget('bg'), wraplength=460, justify=tk.CENTER)
        self.cancel_button = tk.Button(self, text="取り消す", font=self.button_font, command=self.undo_last_transaction, width=18, height=2, state=tk.DISABLED)
        self.hidden_entry = tk.Entry(self, textvariable=self.entry_text)

        info_label.pack(pady=25)
        result_label.pack(pady=20, expand=True, fill="both")
        self.cancel_button.pack(side="bottom", pady=20)
        self.hidden_entry.place(x=-1000, y=-1000)

        self.bind('<Return>', self.handle_scan)
        self.bind('<Escape>', self.quit_app)
        self.hidden_entry.focus_set()

        self.connect_and_build_cache()
        
        # ★★★ 新規：キューを定期的にチェックする処理を開始 ★★★
        self.process_queue()

    def connect_and_build_cache(self):
        try:
            credential_path = os.environ.get(CREDENTIALS_ENV_VAR, '/home/andolab/okashi-system/useful-figure-462606-f3-d5bf8344ee64.json')
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
        self.info_text.set("商品マスタを読み込み中...")
        self.update_idletasks()
        all_products = self.master_sheet.get_all_records()
        temp_cache = {}
        for i, product in enumerate(all_products):
            jan_code = str(product.get('JAN'))
            if jan_code:
                temp_cache[jan_code] = {'name': product.get('商品名'), 'price': int(product.get('価格')), 'stock': int(product.get('在庫')), 'row': i + 2}
        self.product_cache = temp_cache
        self.info_text.set('商品のバーコードをスキャンしてください')

    def refresh_cache_periodically(self):
        try:
            self.gc.auth.refresh(self.gc.http_client)
            self.rebuild_cache()
        except Exception as e:
            print(f"キャッシュの自動更新に失敗: {e}", file=sys.stderr)
        finally:
            self.after(REFRESH_INTERVAL_MS, self.refresh_cache_periodically)

    def handle_scan(self, event=None):
        time.sleep(0.1)
        jan_code = self.entry_text.get().strip()
        if not jan_code: return

        self.cancel_button.config(state=tk.DISABLED)
        self.last_transaction = None
        self.info_text.set(f'スキャンしました: {jan_code}')
        self.update_idletasks()

        product_data = self.product_cache.get(jan_code)
        if product_data:
            if product_data['stock'] > 0:
                # --- 楽観的UIの核心部分 ---
                # 1. まずローカルのキャッシュと画面を即座に更新
                new_stock = product_data['stock'] - 1
                self.product_cache[jan_code]['stock'] = new_stock
                product_name = product_data['name']
                price = product_data['price']
                self.result_text.set(f'{product_name} {price}円\n残り: {new_stock}個')
                
                # 2. 取り消し情報を準備し、ボタンを有効化
                timestamp = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
                log_data = [timestamp, jan_code, product_name, 1, price]
                self.last_transaction = {'jan': jan_code, 'log_data': log_data}
                self.cancel_button.config(state=tk.NORMAL)

                # 3. 時間のかかる書き込み処理をバックグラウンドに任せる
                thread = threading.Thread(
                    target=self.update_sheets_in_background,
                    args=(product_data['row'], new_stock, log_data, jan_code),
                    daemon=True
                )
                thread.start()
            else:
                self.result_text.set(f"{product_data['name']}\nは在庫がありません！")
        else:
            self.result_text.set('この商品は未登録です')

        self.entry_text.set("")
        self.hidden_entry.focus_set()

    # ★★★ 新規：バックグラウンドでスプレッドシートを更新するメソッド ★★★
    def update_sheets_in_background(self, row, new_stock, log_data, jan_code):
        """時間のかかる書き込み処理を裏側で実行する"""
        try:
            self.master_sheet.update_cell(row, 4, new_stock)
            self.log_sheet.append_row(log_data)
            print(f"バックグラウンド更新成功: {jan_code}")
        except Exception as e:
            print(f"バックグラウンド更新エラー: {e}", file=sys.stderr)
            # エラーが起きたことをメインスレッドに通知
            error_info = {'jan': jan_code, 'message': f"{log_data[2]}の\n更新に失敗しました"}
            self.update_queue.put(error_info)

    # ★★★ 新規：バックグラウンドからの通知を処理するメソッド ★★★
    def process_queue(self):
        """キューをチェックして、バックグラウンドからのメッセージがあれば処理する"""
        try:
            message = self.update_queue.get_nowait()
            if message:
                # 在庫更新に失敗した場合、キャッシュの在庫数を元に戻す
                jan_code = message.get('jan')
                if jan_code and jan_code in self.product_cache:
                    self.product_cache[jan_code]['stock'] += 1
                
                # 画面にエラーを表示
                self.result_text.set(message.get('message', '不明なエラー'))
                
                # 取り消し情報をクリアし、ボタンを無効化
                self.last_transaction = None
                self.cancel_button.config(state=tk.DISABLED)

        except queue.Empty:
            pass
        finally:
            # 100ミリ秒後にもう一度自身を呼び出す
            self.after(100, self.process_queue)

    def undo_last_transaction(self):
        if not self.last_transaction: return
        self.info_text.set(f"取り消し処理中...")
        self.update_idletasks()
        try:
            jan_code = self.last_transaction['jan']
            product_data = self.product_cache.get(jan_code)
            if not product_data: raise Exception("キャッシュに商品が見つかりません")

            restored_stock = product_data['stock'] + 1
            self.master_sheet.update_cell(product_data['row'], 4, restored_stock)
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
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
