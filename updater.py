import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import os
import datetime

# 各ロトのトップページにある「抽選結果速報」直下のテーブルから最新データを抽出する関数
def fetch_latest_draw_from_url(loto_type):
    # 🔗 ユーザー指定のトップページURL
    urls = {
        "ロト7": "http://sougaku.com/loto7/",
        "ロト6": "http://sougaku.com/loto6/",
        "ミニロト": "http://sougaku.com/miniloto/"
    }
    url = urls[loto_type]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None, f"サイトアクセス失敗 (HTTP {response.status_code})"
        
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        rules = {
            "ロト7": {"main": 7, "bonus": 2, "max": 37},
            "ロト6": {"main": 6, "bonus": 1, "max": 43},
            "ミニロト": {"main": 5, "bonus": 1, "max": 31}
        }
        rule = rules[loto_type]
        total_needed = rule["main"] + rule["bonus"]
        
        # 🔍 1. 各ページ固有の「抽選結果速報」の見出しテキストを全角半角対応で検索
        if loto_type == "ロト7":
            pattern = r"ロト[7７].*抽選結果速報"
        elif loto_type == "ロト6":
            pattern = r"ロト[6６].*抽選結果速報"
        else:
            pattern = r"ミニロト.*抽選結果速報"
            
        anchor = soup.find(string=re.compile(pattern))
        if not anchor:
            # 万が一見つからない場合のフォールバック
            anchor = soup.find(string=re.compile("抽選結果速報"))
            
        if not anchor:
            return None, f"ページ内に「{loto_type}抽選結果速報」の文字が見つかりませんでした。"
            
        # 🎯 2. 見出しの「すぐ後ろにある最初のテーブル」をピンポイントで取得（ノイズ排除）
        table = anchor.find_next('table')
        if not table:
            return None, "抽選結果速報の見出しの下にテーブルが見つかりませんでした。"
            
        table_text = table.get_text()
        current_year = datetime.datetime.now().year
        
        draw_round = None
        draw_date = None
        set_ball = "A"
        pure_nums = []
        
        # 開催回の特定 (例: 第600回)
        rm = re.search(r'第?\s*(\d+)\s*回', table_text)
        if rm:
            draw_round = int(rm.group(1))
            
        # 抽選日の特定 (例: 2026年6月25日 または 06/25)
        dm1 = re.search(r'(20\d{2})[年/\.-](\d{1,2})[月/\.-](\d{1,2})', table_text)
        dm2 = re.search(r'(\d{1,2})[月/](\d{1,2})', table_text)
        if dm1:
            draw_date = f"{dm1.group(1)}/{int(dm1.group(2)):02d}/{int(dm1.group(3)):02d}"
        elif dm2:
            draw_date = f"{current_year}/{int(dm2.group(1)):02d}/{int(dm2.group(2)):02d}"
            
        # セット球の特定 (例: Aセット、または単に A)
        sm = re.search(r'\b([A-J])\b|([A-J])セット', table_text, re.IGNORECASE)
        if sm:
            set_ball = (sm.group(1) or sm.group(2)).upper()
            
        # 🧮 3. 同一セル内に文字と数字が同居していても安全に数字を抜くクリーンアップ処理
        for cell in table.find_all(['td', 'th']):
            cell_text = cell.get_text(strip=True)
            
            # 「第◯回」や「日付」の数字を誤検知しないよう、該当部分の文字列をあらかじめ消去
            cell_text = re.sub(r'第?\s*\d+\s*回', '', cell_text)
            cell_text = re.sub(r'(20\d{2})[年/\.-]\d{1,2}[月/\.-]\d{1,2}日?', '', cell_text)
            cell_text = re.sub(r'\d{1,2}[月/]\d{1,2}日?', '', cell_text)
            
            # 残ったクリーンなテキストから純粋な当選番号（1〜MAX）のみを回収
            num_matches = re.findall(r'\d+', cell_text)
            for n in num_matches:
                val = int(n)
                if 1 <= val <= rule["max"]:
                    pure_nums.append(val)
                    
        # 💡 4. データの検証と整形
        if draw_round and draw_date and len(pure_nums) >= total_needed:
            main_nums = sorted(pure_nums[:rule["main"]]) # 本数字は昇順ソート
            bonus_nums = pure_nums[rule["main"]:total_needed]
            
            if len(set(main_nums)) == rule["main"]: # 重複チェック
                result_dict = {
                    "開催回": draw_round,
                    "日付": draw_date,
                    "セット": set_ball
                }
                for i, n in enumerate(main_nums, 1):
                    result_dict[f"第{i}数字"] = n
                
                if loto_type == "ロト7":
                    result_dict["BONUS数字1"] = bonus_nums[0]
                    result_dict["BONUS数字2"] = bonus_nums[1]
                else:
                    result_dict["BONUS数字"] = bonus_nums[0]
                
                return result_dict, "成功"
                
        return None, f"速報テーブルから必要なデータを正しく解析できませんでした。(検出数字数: {len(pure_nums)})"
    except Exception as e:
        return None, f"通信・解析エラー: {str(e)}"

# CSVデータを読み込み、新回があれば追記して保存・返却するメイン関数
def update_csv_file(loto_type, filename):
    if not os.path.exists(filename):
        return None, f"ファイル `{filename}` が見つかりません。リポジトリにCSVを配置してください。"
    
    df = None
    for enc in ['utf-8', 'cp932', 'shift_jis']:
        try:
            df = pd.read_csv(filename, encoding=enc)
            break
        except:
            continue
            
    if df is None:
        return None, "CSVファイルの読み込みに失敗しました。"
        
    latest_drawn_info, scrape_msg = fetch_latest_draw_from_url(loto_type)
    
    if latest_drawn_info:
        current_max_round = df['開催回'].max()
        if latest_drawn_info["開催回"] > current_max_round:
            # 新しい最新回が見つかったら末尾に自動追記
            new_row_df = pd.DataFrame([latest_drawn_info])
            df = pd.concat([df, new_row_df], ignore_index=True)
            try:
                df.to_csv(filename, index=False, encoding='utf-8')
                return df, f"🎉 最新の抽選結果（第 {latest_drawn_info['開催回']} 回：{latest_drawn_info['日付']} 抽選）を検出し、CSVへ自動追加・保存しました！"
            except Exception as csv_err:
                return df, f"⚠️ 最新回（第 {latest_drawn_info['開催回']} 回）を検出・反映しましたが、CSVへの保存に失敗しました: {str(csv_err)}"
        else:
            return df, f"ℹ️ CSVデータは最新の状態です（最新の同期回: 第 {current_max_round} 回）。"
    else:
        return df, f"⚠️ 抽選結果の自動同期スキップ: {scrape_msg}（CSVの既存データで分析を継続します）"

if __name__ == "__main__":
    print("--- ロトCSV自動同期スクリプト手動実行 ---")
    targets = {"ロト7": "loto7_history.csv", "ロト6": "loto6_history.csv", "ミニロト": "miniloto_history.csv"}
    for k, v in targets.items():
        _, msg = update_csv_file(k, v)
        print(f"【{k}】: {msg}")
