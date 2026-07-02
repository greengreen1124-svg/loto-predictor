import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup

def update_csv_file(loto_type, filename):
    """
    創楽のウェブサイトから「抽選結果速報」の下にある5つの要素
    (抽選回、抽選日、セット球、本数字、ボーナス数字)を抽出し、CSVファイルを自動更新する関数
    """
    urls = {
        "ロト7": "http://sougaku.com/loto7/index.html",
        "ロト6": "http://sougaku.com/loto6/index.html",
        "ミニロト": "http://sougaku.com/miniloto/index.html"
    }
    
    # くじ種ごとの基本ルール設定
    rules = {
        "ロト7": {"main_count": 7, "bonus_count": 2, "keyword": "ロト７抽選結果速報"},
        "ロト6": {"main_count": 6, "bonus_count": 1, "keyword": "ロト６抽選結果速報"},
        "ミニロト": {"main_count": 5, "bonus_count": 1, "keyword": "ミニロト抽選結果速報"}
    }
    
    current_rule = rules[loto_type]
    url = urls[loto_type]
    
    # 1. 既存のCSVファイルを読み込み
    df = None
    if os.path.exists(filename):
        for encoding in ['utf-8', 'shift_jis', 'cp932']:
            try:
                df = pd.read_csv(filename, encoding=encoding)
                break
            except Exception:
                continue
    
    if df is None or df.empty:
        return df, f"⚠️ CSVファイル「{filename}」を読み込めないか、空データのため自動更新をスキップしました。"

    # 列名のクレンジング
    df.columns = [str(c).strip() for c in df.columns]
    
    # CSV内の既存の列構造をインテリジェントに把握
    round_col = next((c for c in df.columns if any(k in c for k in ['回', 'round', 'No.', '番号', '開催'])), None)
    date_col = next((c for c in df.columns if any(k in c for k in ['日', 'date', '付'])), None)
    set_col = next((c for c in df.columns if any(k in c for k in ['セット', 'set', '球'])), None)
    main_cols = [c for c in df.columns if '第' in c and '数字' in c and 'ボーナス' not in c]
    bonus_cols = [c for c in df.columns if 'ボーナス' in c or 'Bonus' in c]
    
    # 最新（最後尾）の開催回を取得
    latest_round_in_csv = None
    if round_col and not df.empty:
        last_val = str(df[round_col].iloc[-1])
        r_num = re.search(r'\d+', last_val)
        if r_num:
            latest_round_in_csv = int(r_num.group())

    # 2. Webサイトから最新の抽選速報データをスクレイピング
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        if response.status_code != 200:
            return df, f"ℹ️ サイトにアクセスできませんでした (HTTP {response.status_code})。既存データで解析します。"
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 不要なタグを排除
        for noise in soup(["script", "style", "nav", "header", "footer"]):
            noise.decompose()
            
        full_text = soup.get_text()
        
        # 「〇〇抽選結果速報」というキーワードの直下エリアを特定して切り出し
        target_kw = current_rule["keyword"]
        start_idx = full_text.find(target_kw)
        if start_idx == -1:
            start_idx = full_text.find("抽選結果速報")
            
        if start_idx == -1:
            return df, "ℹ️ ページ内から「抽選結果速報」エリアを検出できませんでした。既存データで解析します。"
            
        # 見出しの下、最大1000文字の範囲をピンポイント抽出
        target_area = full_text[start_idx : start_idx + 1000]
        
        # 3. 5つの重要要素の抽出処理
        # ① 抽選回
        round_match = re.search(r'(?:抽選回|開催回|第)\s*(\d+)\s*回', target_area)
        if not round_match:
            return df, "ℹ️ 速報エリアから最新の「抽選回」を特定できませんでした。"
        scraped_round_num = int(round_match.group(1))
        
        # ② 抽選日（メッセージ表示に使うため、判定順序を上に移動しました）
        date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日|\d{4}/\d{1,2}/\d{1,2})', target_area)
        scraped_date = date_match.group(1) if date_match else "不明"
        
        # 🎯【変更箇所】すでに最新データがある場合のメッセージに「抽選日」を併記
        if latest_round_in_csv and scraped_round_num <= latest_round_in_csv:
            return df, f"🎉 データは最新です (最新の第 {scraped_round_num} 回 [抽選日: {scraped_date}] までCSVに反映済み)。"
            
        # ③ セット球
        set_match = re.search(r'(?:セット球|セット|球)\s*[:：]?\s*([A-J_a-j])', target_area)
        scraped_set = set_match.group(1).upper() if set_match else "C"
        
        # ④・⑤ 本数字とボーナス数字の全数字候補を順番通りに配列化
        all_numbers = [int(n) for n in re.findall(r'\b\d{1,2}\b', target_area)]
        
        valid_pool = []
        for n in all_numbers:
            max_limit = 43 if loto_type == "ロト6" else (37 if loto_type == "ロト7" else 31)
            if 1 <= n <= max_limit:
                valid_pool.append(n)
                
        total_needed = current_rule["main_count"] + current_rule["bonus_count"]
        if len(valid_pool) < total_needed:
            return df, f"ℹ️ 速報エリアから十分な個数の本数字・ボーナス数字を分離できませんでした。"
            
        scraped_mains = valid_pool[:current_rule["main_count"]]
        scraped_bonuses = valid_pool[current_rule["main_count"]:total_needed]
        
        # 4. 新しい行データの組み立てとCSVへの書き込み
        new_row = {}
        
        # 抽選回列の設定
        if round_col:
            sample_val = str(df[round_col].iloc[-1])
            if "第" in sample_val and "回" in sample_val:
                new_row[round_col] = f"第{scraped_round_num}回"
            else:
                new_row[round_col] = scraped_round_num
                
        # 抽選日列の設定
        if date_col:
            new_row[date_col] = scraped_date
            
        # セット球列の設定
        if set_col:
            new_row[set_col] = scraped_set
            
        # 本数字列へのマッピング
        main_cols_sorted = sorted(main_cols, key=lambda x: [int(s) for s in re.findall(r'\d+', x)][0] if re.findall(r'\d+', x) else 0)
        for i, col_name in enumerate(main_cols_sorted):
            if i < len(scraped_mains):
                new_row[col_name] = scraped_mains[i]
                
        # ボーナス数字列へのマッピング
        bonus_cols_sorted = sorted(bonus_cols, key=lambda x: [int(s) for s in re.findall(r'\d+', x)][0] if re.findall(r'\d+', x) else 0)
        for i, col_name in enumerate(bonus_cols_sorted):
            if i < len(scraped_bonuses):
                new_row[col_name] = scraped_bonuses[i]
                
        # 既存のCSVに含まれるその他の全ての列を空文字で初期化
        for col in df.columns:
            if col not in new_row:
                new_row[col] = ""
                
        # 新しい行をデータフレームへ追加してCSV保存
        new_df = pd.DataFrame([new_row])
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(filename, index=False, encoding='utf-8')
        
        # 🎯【変更箇所】新着データ検知時のメッセージに「抽選日」を分かりやすく併記
        return df, f"🎉 新着データ検知！【第 {scraped_round_num} 回（抽選日: {scraped_date}）】の抽選結果（セット球: {scraped_set}）を自動取得し、CSVへ追加しました！"
        
    except Exception as e:
        return df, f"⚠️ 自動更新中に予期せぬエラーが発生しました: {str(e)}"
