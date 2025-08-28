import tkinter as tk
from tkinter import font, messagebox
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import sys

# --- 設定 ---
SERVICE_ACCOUNT_FILE = '/home/andolab/okashi-system/useful-figure-462606-f3-d5bf8344ee64.json'
SPREADSHEET_NAME = '購買部在庫管理システム'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

# --- アプリケーションのクラス定義 ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()

        # ★★★ 直前の取引情報を保存するための変数を追加 ★★★
        self.last_transaction = None 

        # --- ウィンドウの基本設定 ---
        self.title("在庫管理システム")
        self.attributes('-fullscreen', True)
        self.configure(bg='#D0F0C0')

        # --- フォントの定義 ---
        self.info_font = font.Font(family="Helvetica", size=16)
        self.result_font = font.Font(family="Helvetica", size=22, weight="bold")
        self.button_font = font.Font(family="Helvetica", size=12)

        # --- 動的に変わる文字列を管理する変数 ---
        self.info_text = tk.StringVar(value="スプレッドシートに接続中...")
        self.result_text = tk.StringVar(value="")
        self.entry_text = tk.StringVar()

        # --- GUI部品（ウィジェット）の作成 ---
        info_label = tk.Label(self, textvariable=self.info_text, font=self.info_font, bg=self.cget('bg'))
        result_label = tk.Label(self, textvariable=self.result_text, font=self.result_font, bg=self.cget('bg'), wraplength=460, justify=tk.CENTER)
        
        # ★★★ 取り消しボタ更 ★★★
        self.cancel_button = tk.Button(
            self, 
            text="取り消す", 
            font=self.button_font, 
            command=self.undo_last_transaction, # 実行する命令を変更
            width=18, # ボタンの幅を調整
            height=2,
            state=tk.DISABLED # ★★★ 最初は押せないように無効化 ★★★
        )
        
        self.hidden_entry = tk.Entry(self, textvariable=self.entry_text)

        # --- ウィジェットの配置 ---
        info_label.pack(pady=25)
        result_label.pack(pady=20, expand=True, fill="both")
        self.cancel_button.pack(side="bottom", pady=20) # cancel_buttonを配置
        self.hidden_entry.place(x=-1000, y=-1000)

        # --- イベントの紐付け ---
        self.bind('<Return>', self.handle_scan)
        self.bind('<Escape>', self.quit_app) # ★★★ Escapeキーで終了する機能を追加 ★★★
        self.hidden_entry.focus_set()


        # --- スプレッドシートへの接続 ---
        self.connect_to_sheets()

    def connect_to_sheets(self):
        try:
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            gc = gspread.authorize(creds)
            spreadsheet = gc.open(SPREADSHEET_NAME)
            self.master_sheet = spreadsheet.worksheet('商品マスタ')
            self.log_sheet = spreadsheet.worksheet('購入履歴')
            self.info_text.set('商品のバーコードをスキャンしてください')
        except Exception as e:
            self.info_text.set("エラー：接続に失敗しました")
            messagebox.showerror("接続エラー", f"スプレッドシートに接続できませんでした。\n設定を確認してください。\n\n詳細: {e}")
            self.destroy()

    def handle_scan(self, event=None):
        time.sleep(0.1)
        jan_code = self.entry_text.get().strip()
        
        if not jan_code:
            return

        self.info_text.set(f'スキャンしました: {jan_code}')
        # ★★★ 新しいスキャンが始まったら、取り消しボタンを一旦無効化 ★★★
        self.cancel_button.config(state=tk.DISABLED)
        self.last_transaction = None
        self.update_idletasks()

        try:
            cell = self.master_sheet.find(jan_code, in_column=6)

            if cell:
                row_values = self.master_sheet.row_values(cell.row)
                product_name = row_values[0]
                price = int(row_values[2])
                current_stock = int(row_values[3])

                if current_stock > 0:
                    new_stock = current_stock - 1
                    self.master_sheet.update_cell(cell.row, 4, new_stock)
                    
                    timestamp = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
                    log_data = [timestamp, jan_code, product_name, 1, price]
                    self.log_sheet.append_row(log_data)
                    
                    self.result_text.set(f'{product_name} {price}円\n残り: {new_stock}個')
                    
                    # ★★★ 成功した取引情報を保存し、取り消しボタンを有効化 ★★★
                    self.last_transaction = {'jan': jan_code, 'row': cell.row, 'log_data': log_data}
                    self.cancel_button.config(state=tk.NORMAL)
                else:
                    self.result_text.set(f'{product_name}\nは在庫がありません！')
            else:
                self.result_text.set('この商品は未登録です')

        except Exception as e:
            self.result_text.set("エラーが発生しました")
            print(f"エラー詳細: {e}", file=sys.stderr)

        self.entry_text.set("")
        self.hidden_entry.focus_set()

    # ★★★ 取り消し処理を行うメソッドを新規作成 ★★★
    def undo_last_transaction(self):
        """直前のスキャン操作を取り消す"""
        if not self.last_transaction:
            self.result_text.set("取り消す操作がありません")
            return

        self.info_text.set(f"取り消し処理中...")
        self.update_idletasks()
        
        try:
            # 1. 在庫マスターの在庫を元に戻す
            jan_code = self.last_transaction['jan']
            sheet_row = self.last_transaction['row']
            
            current_stock = int(self.master_sheet.cell(sheet_row, 4).value)
            restored_stock = current_stock + 1
            self.master_sheet.update_cell(sheet_row, 4, restored_stock)

            # 2. 購入履歴から該当ログを削除する
            # 安全のため、完全に一致する最後の行を探して削除します
            all_log_data = self.log_sheet.get_all_values()
            for i in range(len(all_log_data) - 1, 0, -1): # 下から探す
                # Gspreadのappend_rowは値を文字列として保存することがあるため、比較用に文字列に変換
                log_to_check = [str(item) for item in self.last_transaction['log_data']]
                if all_log_data[i] == log_to_check:
                    self.log_sheet.delete_rows(i + 1)
                    break
            
            product_name = self.master_sheet.cell(sheet_row, 1).value
            self.result_text.set(f"{product_name}の購入を\n取り消しました (残り: {restored_stock}個)")

        except Exception as e:
            self.result_text.set("取り消し中にエラーが発生しました")
            print(f"取り消しエラー詳細: {e}", file=sys.stderr)
        
        finally:
            # 正常でもエラーでも、取り消し処理後はボタンを無効化
            self.last_transaction = None
            self.cancel_button.config(state=tk.DISABLED)
            self.info_text.set('商品のバーコードをスキャンしてください')

    # ★★★ 終了用メソッドを新規作成 ★★★
    def quit_app(self, event=None):
        """アプリケーションを終了する"""
        self.destroy()

# --- アプリケーションの実行 ---
if __name__ == "__main__":
    app = App()
    app.mainloop()
