import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import os

# 指定のURLから最新の「開催回・抽選日・セット球・当選番号」を抽出する関数
def fetch_latest_draw_from_url(loto_type):
    urls = {
        "ロト7": "http://sougaku.com/loto7/index.html",
        "ロト6": "http://sougaku.com/loto6/index.html",
        "ミニロト": "http://sougaku.com/miniloto/index.html"
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
        total_nums_needed = rule["main"] + rule["bonus"]
        
        full_text = soup.get_text()

        # ページ内のすべてのテーブルを走査し、当選番号が書かれているテーブルを特定
        for table in soup.find_all('table'):
            table_text = table.get_text()
            
            # 当選結果テーブルの条件：「回」が含まれ、かつ「結果」「当選」「ボーナス」などのキーワードがある
            if '回' in table_text and ('結果' in table_text or '当選' in table_text or 'ボーナス' in table_text or '本数字' in table_text):
                
                # 【重要】テーブル内から正確にその結果の「開催回」を抽出（未来の予想回号に惑わされない）
                round_match = re.search(r'第\s*(\d+)\s*回', table_text)
                if not round_match:
                    continue
                draw_round = int(round_match.group(1))
                
                # 日付の抽出（テーブル内を優先、なければページ全体から）
                date_match = re.search(r'(\d{4})[年/\.-](\d{1,2})[月/\.-](\d{1,2})', table_text)
                if date_match:
                    draw_date = f"{date_match.group(1)}/{int(date_match.group(2)):02d}/{int(date_match.group(3)):02d}"
                else:
                    date_match_global = re.search(r'(\d{4})[年/\.-](\d{1,2})[月/\.-](\d{1,2})', full_text)
                    if date_match_global:
                        draw_date = f"{date_match_global.group(1)}/{int(date_match_global.group(2)):02d}/{int(date_match_global.group(3)):02d}"
                    else:
                        draw_date = "不明"
                
                # セット球の抽出（A-J）
                set_match = re.search(r'([A-J])\s*セット|セット\s*球?\s*[:：]?\s*([A-J])|([A-J])セット', table_text, re.IGNORECASE)
                set_ball = "A"
                if set_match:
                    for g in set_match.groups():
                        if g and len(g) == 1:
                            set_ball = g.upper()
                            break
                else:
                    set_match_global = re.search(r'([A-J])\s*セット|セット\s*球?\s*[:：]?\s*([A-J])|([A-J])セット', full_text, re.IGNORECASE)
                    if set_match_global:
                        for g in set_match_global.groups():
                            if g and len(g) == 1:
                                set_ball = g.upper()
                                break
                
                # 当選番号の個数チェック
                cells = [c.get_text(strip=True) for c in table.find_all(['td', 'th'])]
                pure_nums = []
                for c in cells:
                    if c.isdigit() and 1 <= int(c) <= rule["max"]:
                        pure_nums.append(int(c))
                
                if len(pure_nums) >= total_nums_needed:
                    main_part = sorted(pure_nums[:rule["main"]])
                    bonus_part = pure_nums[rule["main"]:total_nums_needed]
                    
                    if len(set(main_part)) == rule["main"]:
                        result_dict = {
                            "開催回": draw_round,
                            "日付": draw_date,
                            "セット": set_ball
                        }
                        if loto_type == "ロト7":
                            for i, n in enumerate(main_part, 1): result_dict[f"第{i}数字"] = n
                            result_dict["BONUS数字1"] = bonus_part[0]
                            result_dict["BONUS数字2"] = bonus_part[1]
                        elif loto_type == "ロト6":
                            for i, n in enumerate(main_part, 1): result_dict[f"第{i}数字"] = n
                            result_dict["BONUS数字"] = bonus_part[0]
                        else:  # ミニロト
                            for i, n in enumerate(main_part, 1): result_dict[f"第{i}数字"] = n
                            result_dict["BONUS数字"] = bonus_part[0]
                            
                        return result_dict, "成功"
                        
        return None, "当選番号のテーブル構造が正しく解析できませんでした。"
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
            # まだ登録されていない新しい回を見つけたら末尾に追加
            new_row_df = pd.DataFrame([latest_drawn_info])
            df = pd.concat([df, new_row_df], ignore_index=True)
            try:
                df.to_csv(filename, index=False, encoding='utf-8')
                return df, f"🎉 最新の抽選結果（第 {latest_drawn_info['開催回']} 回：{latest_drawn_info['日付']} 抽選）を検出し、CSVへ自動追加・保存しました！"
            except Exception as csv_err:
                return df, f"⚠️ 最新回（第 {latest_drawn_info['開催回']} 回）を検出・反映しましたが、CSVへの永続保存に失敗しました: {str(csv_err)}"
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
