import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import os
import datetime

# 指定の一覧URLから最新（一番下）の「開催回・抽選日・セット球・当選番号」を抽出する関数
def fetch_latest_draw_from_url(loto_type):
    urls = {
        "ロト7": "http://sougaku.com/loto7/data/list1/index_10.html",
        "ロト6": "http://sougaku.com/loto6/data/list1/index_10.html",
        "ミニロト": "http://sougaku.com/miniloto/data/list1/index_10.html"
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
        
        # 💡 最新10回ページで「年(西暦)」が行内で省略されている場合のための自動補完システム
        current_year = datetime.datetime.now().year
        page_text = soup.get_text()
        year_match = re.search(r'(20\d{2})年', page_text)
        default_year = int(year_match.group(1)) if year_match else current_year
        
        valid_results = []
        
        # ページ内のすべてのテーブルのすべての行（tr）を走査
        for table in soup.find_all('table'):
            for tr in table.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if len(cells) < 5:  # 列数が少なすぎるヘッダーや空白行はスキップ
                    continue
                
                # 1. 開催回の取得（1番目のセルから数値を抽出）
                draw_round = None
                rm = re.search(r'(\d+)', cells[0])
                if rm:
                    draw_round = int(rm.group(1))
                
                if not draw_round or draw_round < 1:
                    continue
                
                # 2. 日付の取得（2番目のセルから柔軟に解析・年の自動補完付き）
                draw_date = None
                date_text = cells[1]
                
                dm1 = re.search(r'(20\d{2})[年/\.-](\d{1,2})[月/\.-](\d{1,2})', date_text)
                dm2 = re.search(r'(\d{1,2})[月/](\d{1,2})', date_text)
                
                if dm1:
                    draw_date = f"{dm1.group(1)}/{int(dm1.group(2)):02d}/{int(dm1.group(3)):02d}"
                elif dm2:
                    draw_date = f"{default_year}/{int(dm2.group(1)):02d}/{int(dm2.group(2)):02d}"
                else:
                    # 日付の形式が合わなければ、ヘッダー行等とみなしてスキップ
                    continue
                
                # 3. セット球の取得（末尾のセルからA-Jのアルファベットを探索）
                set_ball = "A"
                for cell in reversed(cells):
                    sm = re.search(r'\b([A-J])\b', cell, re.IGNORECASE)
                    if sm:
                        set_ball = sm.group(1).upper()
                        break
                
                # 4. 当選番号の抽出（インデックス2以降のセルから数字を順番に正確に回収）
                pure_nums = []
                for cell in cells[2:]:
                    # セット球のセル（単体のアルファベット）はスキップ
                    if re.search(r'\b[A-J]\b', cell, re.IGNORECASE) and len(cell) <= 3:
                        continue
                    
                    num_matches = re.findall(r'\d+', cell)
                    for n in num_matches:
                        val = int(n)
                        if 1 <= val <= rule["max"]:
                            pure_nums.append(val)
                
                # 5. データの検証（本数字＋ボーナスの個数が正確に揃っているか）
                if len(pure_nums) >= total_needed:
                    main_nums = sorted(pure_nums[:rule["main"]])
                    bonus_nums = pure_nums[rule["main"]:total_needed]
                    
                    # 本数字に重複がないかチェック
                    if len(set(main_nums)) == rule["main"]:
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
                        
                        valid_results.append(result_dict)
        
        if valid_results:
            # 💡 ご指定通り、リストの一番下（最下行）を最新回として採用して返却
            return valid_results[-1], "成功"
            
        return None, "最新10回一覧テーブルから有効な結果行を検出・解析できませんでした。"
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
