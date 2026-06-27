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
        full_text = soup.get_text()
        
        # 1. 開催回と日付の抽出
        round_match = re.search(r'第\s*(\d+)\s*回', full_text)
        date_match = re.search(r'(\d{4})[年/\.-](\d{1,2})[月/\.-](\d{1,2})', full_text)
        
        if not round_match or not date_match:
            return None, "ページ内から開催回または抽選日を特定できませんでした。"
            
        draw_round = int(round_match.group(1))
        draw_date = f"{date_match.group(1)}/{int(date_match.group(2)):02d}/{int(date_match.group(3)):02d}"
        
        rules = {
            "ロト7": {"main": 7, "bonus": 2, "max": 37},
            "ロト6": {"main": 6, "bonus": 1, "max": 43},
            "ミニロト": {"main": 5, "bonus": 1, "max": 31}
        }
        rule = rules[loto_type]
        total_nums_needed = rule["main"] + rule["bonus"]
        
        # セット球の抽出 (A-J)
        set_match = re.search(r'([A-J])\s*セット|セット\s*球?\s*[:：]?\s*([A-J])|([A-J])セット', full_text, re.IGNORECASE)
        set_ball = "A"
        if set_match:
            for g in set_match.groups():
                if g and len(g) == 1:
                    set_ball = g.upper()
                    break
        
        # --- [改善] 当選番号の抽出（ハイブリッド型: テーブル解析 + ページ全体解析の二段構え） ---
        main_part = None
        bonus_part = None
        
        # 第一段階：テーブル構造から正規表現で数字をスマートに抜き出す
        for table in soup.find_all('table'):
            table_text = table.get_text()
            if '結果' in table_text or '当選' in table_text or f"第{draw_round}回" in table_text or 'ボーナス' in table_text:
                # マスの区切りに依存せず、表の中から1〜2桁の数字をまとめて抽出
                pure_nums = [int(n) for n in re.findall(r'\b\d{1,2}\b', table_text) if 1 <= int(n) <= rule["max"]]
                
                # 開催回（例: 第668回の「668」）が混ざってインデックスがズレるのを防止
                pure_nums = [n for n in pure_nums if n != draw_round]
                
                if len(pure_nums) >= total_nums_needed:
                    tmp_main = sorted(pure_nums[:rule["main"]])
                    tmp_bonus = pure_nums[rule["main"]:total_nums_needed]
                    
                    # 本数字に重複がないかチェックして合格なら採用
                    if len(set(tmp_main)) == rule["main"]:
                        main_part = tmp_main
                        bonus_part = tmp_bonus
                        break

        # 第二段階：表の構造が変わっていた場合、ページ全体の文章からキーワード周辺を直接狙い撃ち
        if not main_part or not bonus_part:
            pos = full_text.find(f"第{draw_round}回")
            search_area = full_text[pos:pos+3000] if pos != -1 else full_text
            
            # 「本数字」と「ボーナス」の文字の後ろにある数字を個別にスキャン
            main_match = re.search(r'(?:本数字|当選番号|抽せん数字|結果)\s*[:：\s]?\s*((?:\s*\b\d{1,2}\b)+)', search_area)
            bonus_match = re.search(r'(?:ボーナス|bonus|分球|Ｂ|B)\s*[:：\s]?\s*((?:\s*\b\d{1,2}\b)+)', search_area)
            
            if main_match and bonus_match:
                tmp_main = [int(n) for n in re.findall(r'\b\d{1,2}\b', main_match.group(1)) if 1 <= int(n) <= rule["max"]]
                tmp_bonus = [int(n) for n in re.findall(r'\b\d{1,2}\b', bonus_match.group(1)) if 1 <= int(n) <= rule["max"]]
                
                if len(tmp_main) >= rule["main"] and len(tmp_bonus) >= rule["bonus"]:
                    main_part = sorted(tmp_main[:rule["main"]])
                    bonus_part = tmp_bonus[:rule["bonus"]]
            
            # 最終手段：周辺のすべての数字から該当する個数を順番に強制回収する
            if not main_part or not bonus_part:
                all_nums = [int(n) for n in re.findall(r'\b\d{1,2}\b', search_area) if 1 <= int(n) <= rule["max"]]
                exclude_nums = {draw_round, int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))}
                filtered_nums = []
                for n in all_nums:
                    if n not in exclude_nums and n not in filtered_nums:
                        filtered_nums.append(n)
                        if len(filtered_nums) == total_nums_needed:
                            break
                if len(filtered_nums) == total_nums_needed:
                    main_part = sorted(filtered_nums[:rule["main"]])
                    bonus_part = filtered_nums[rule["main"]:total_nums_needed]

        # 最終データの組み立てとバリデーション
        if main_part and bonus_part and len(main_part) == rule["main"] and len(bonus_part) == rule["bonus"]:
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
                        
        return None, "当選番号のテーブル構造およびテキスト構造が正しく解析できませんでした。"
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

# 【独立実行用】パソコンや外部サーバーのCron等で単体実行する場合の処理
if __name__ == "__main__":
    print("--- ロトCSV自動同期スクリプト手動実行 ---")
    targets = {"ロト7": "loto7_history.csv", "ロト6": "loto6_history.csv", "ミニロト": "miniloto_history.csv"}
    for k, v in targets.items():
        _, msg = update_csv_file(k, v)
        print(f"【{k}】: {msg}")
