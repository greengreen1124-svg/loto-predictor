import urllib.request
import pandas as pd
import re
import os
from bs4 import BeautifulSoup

def fetch_sougaku_data(loto_type):
    """
    指定された創楽（sougaku.com）のURLから最新の公式抽選結果（回号、日付、本数字、ボーナス数字、セット球）を抽出
    """
    if loto_type == "ロト6":
        url = "http://sougaku.com/loto6/index.html"
        num_count = 6
        max_val = 43
    elif loto_type == "ロト7":
        url = "http://sougaku.com/loto7/index.html"
        num_count = 7
        max_val = 37
    elif loto_type == "ミニロト":
        url = "http://sougaku.com/miniloto/index.html"
        num_count = 5
        max_val = 31
    else:
        return None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    res = {}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        # --- 1. テキスト解析による回号・日付・セット球の最速抽出 ---
        soup = BeautifulSoup(html, 'html.parser')
        for noise in soup(["script", "style", "nav", "footer", "header"]):
            noise.decompose()
        full_text = soup.get_text()
        
        # 回号 (例: 第1800回)
        round_m = re.search(r'第\s*(\d+)\s*回', full_text)
        if round_m:
            res['round'] = int(round_m.group(1))
            
        # 抽選日 (例: 2026年7月4日 または 2026/07/04)
        date_m = re.search(r'(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})', full_text)
        if date_m:
            res['date'] = date_m.group(1).replace(' ', '')
            
        # セット球の事前探査 (例: Aセット, セット球: B)
        set_m = re.search(r'セット球\s*[:：\s]*([A-J_a-j])', full_text, re.IGNORECASE)
        if not set_m:
            set_m = re.search(r'([A-J_a-j])\s*セット', full_text, re.IGNORECASE)
        if set_m:
            res['set_ball'] = set_m.group(1).upper()

        # --- 2. Pandasを用いたテーブル要素からの本数字・ボーナス数字の深層抽出 ---
        try:
            dfs = pd.read_html(html)
            for df in dfs:
                df_str = df.to_string()
                # 本数字や当選番号が含まれる結果テーブルを狙い撃ち
                if any(k in df_str for k in ["本数字", "当選番号", "当せん番号", "結果"]):
                    for _, row in df.iterrows():
                        row_str = " ".join(row.astype(str).tolist())
                        
                        # 本数字・ボーナス数字の抽出
                        if any(k in row_str for k in ["本数字", "当選番号", "当せん番号"]):
                            cell_text = ""
                            for cell in row:
                                if any(k in str(cell) for k in ["本数字", "当選番号", "当せん番号"]):
                                    continue
                                cell_text += " " + str(cell)
                            
                            extracted_nums = [int(n) for n in re.findall(r'\d+', cell_text)]
                            valid_nums = [n for n in extracted_nums if 1 <= n <= max_val]
                            
                            if len(valid_nums) >= num_count:
                                res['numbers'] = sorted(valid_nums[:num_count])
                                # 余った数字があればボーナス数字の候補にする
                                if len(valid_nums) > num_count and 'bonus' not in res:
                                    res['bonus'] = valid_nums[num_count:]
                                    
                        # 明示的な「ボーナス」行の処理
                        if "ボーナス" in row_str:
                            cell_text = ""
                            for cell in row:
                                if "ボーナス" in str(cell): continue
                                cell_text += " " + str(cell)
                            b_nums = [int(n) for n in re.findall(r'\d+', cell_text)]
                            valid_b = [n for n in b_nums if 1 <= n <= max_val]
                            if valid_b:
                                res['bonus'] = valid_b

                        # テーブル内からのセット球補完
                        if "セット" in row_str or "球" in row_str:
                            sm = re.search(r'([A-J_a-j])', row_str)
                            if sm and 'set_ball' not in res:
                                res['set_ball'] = sm.group(1).upper()
                    if 'numbers' in res:
                        break 
        except:
            pass

        # --- 3. テーブル解析で本数字が万が一取れなかった場合のテキストフォールバック ---
        if 'numbers' not in res:
            lines = full_text.split('\n')
            for i, line in enumerate(lines):
                if any(k in line for k in ["本数字", "当選番号", "当せん番号"]):
                    context = " ".join(lines[i:i+3])
                    all_digits = [int(n) for n in re.findall(r'\d+', context)]
                    valid_digits = [n for n in all_digits if 1 <= n <= max_val]
                    if len(valid_digits) >= num_count:
                        res['numbers'] = sorted(valid_digits[:num_count])
                        if len(valid_digits) > num_count and 'bonus' not in res:
                            res['bonus'] = valid_digits[num_count:num_count+2]
                        break

        if 'round' in res and 'numbers' in res:
            return res
            
    except Exception as e:
        pass
    return None

def fetch_mizuho_data(loto_type):
    """
    【保険用バックアップ】みずほ銀行の公式サイトから最新の公式抽選結果を取得
    """
    if loto_type == "ロト6":
        url = "https://www.mizuho-bank.co.jp/takarakuji/loto/loto6/index.html"
        num_count = 6
    elif loto_type == "ロト7":
        url = "https://www.mizuho-bank.co.jp/takarakuji/loto/loto7/index.html"
        num_count = 7
    elif loto_type == "ミニロト":
        url = "https://www.mizuho-bank.co.jp/takarakuji/loto/miniloto/index.html"
        num_count = 5
    else:
        return None

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        dfs = pd.read_html(html)
        for df in dfs:
            if df.shape[1] >= 2:
                col0_str = " ".join(df.iloc[:, 0].astype(str).tolist())
                if "抽せん回" in col0_str and "本数字" in col0_str:
                    res = {}
                    for _, row in df.iterrows():
                        k = str(row[0]).strip()
                        v = str(row[1]).strip()
                        if "抽せん回" in k:
                            m = re.search(r'第\s*(\d+)\s*回', v)
                            if m: res['round'] = int(m.group(1))
                        elif "抽せん日" in k:
                            res['date'] = v
                        elif "本数字" in k:
                            nums = [int(n) for n in re.findall(r'\d+', v)]
                            res['numbers'] = sorted(nums[:num_count])
                        elif "ボーナス" in k:
                            bonus_nums = [int(n) for n in re.findall(r'\d+', v)]
                            res['bonus'] = bonus_nums
                    if 'round' in res and 'numbers' in res:
                        return res
    except:
        pass
    return None

def fetch_set_ball(loto_type, round_num):
    """
    【保険用バックアップ】セット球が創楽から直接抽出できなかった場合に専門サイトから補完
    """
    if loto_type == "ロト6":
        url = "https://loto6.thekyo.jp/"
    elif loto_type == "ロト7":
        url = "https://loto7.thekyo.jp/"
    elif loto_type == "ミニロト":
        url = "https://miniloto.thekyo.jp/"
    else:
        return "C"

    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
        
        if f"第{round_num}回" in html or str(round_num) in html:
            m = re.search(r'セット球\s*[:：]\s*([A-J_a-j])', html)
            if not m:
                m = re.search(r'([A-J_a-j])\s*セット', html)
            if m:
                return m.group(1).upper()
    except:
        pass
    return "C"

def fetch_latest_loto_data_hybrid(loto_type):
    """
    最優先で創楽(sougaku.com)から最新データを取得し、不足があればみずほ・専門サイトから完全自動マージする
    """
    # 1. 創楽からデータを取得
    res = fetch_sougaku_data(loto_type)
    
    # 2. 創楽からデータが取れなかった、または回号・本数字が不完全な場合はみずほ銀行から補完
    if not res or 'round' not in res or 'numbers' not in res:
        mizuho = fetch_mizuho_data(loto_type)
        if mizuho:
            if not res: res = {}
            res['round'] = mizuho.get('round')
            res['date'] = mizuho.get('date')
            res['numbers'] = mizuho.get('numbers')
            if 'bonus' in mizuho:
                res['bonus'] = mizuho['bonus']
                
    # 3. セット球の情報が抜けている場合は、専門サイトから安全に補完
    if res and 'round' in res and ('set_ball' not in res or not res['set_ball']):
        res['set_ball'] = fetch_set_ball(loto_type, res['round'])
        
    return res

def update_csv_file(loto_type, filepath):
    """
    WEB（創楽最優先）上の最新回と既存CSVを比較し、新しい抽選結果があれば完全に自動で追記更新するメイン関数
    """
    if not os.path.exists(filepath):
        return False, f"⚠️ CSVファイルが見つかりません: {filepath}"
        
    # ハイブリッド型データチェッカーを起動（創楽URLへ接続）
    web_data = fetch_latest_loto_data_hybrid(loto_type)
    if not web_data or 'round' not in web_data or 'numbers' not in web_data:
        return False, f"⚠️ {loto_type}の最新WEBデータの取得・自動パースに失敗しました。"
        
    # CSVの文字コードを自動判別して読み込み
    try:
        df = pd.read_csv(filepath, encoding='utf-8')
        encoding_used = 'utf-8'
    except:
        try:
            df = pd.read_csv(filepath, encoding='shift_jis')
            encoding_used = 'shift_jis'
        except Exception as e:
            return False, f"⚠️ CSVの読み出しに失敗しました: {e}"
            
    # 列名の表記揺れ対策
    orig_columns = list(df.columns)
    clean_columns = [str(c).strip() for c in df.columns]
    df.columns = clean_columns
    
    # キー列の自動検出
    round_col = next((c for c in df.columns if any(k in c for k in ['回', 'round', 'Round', 'No.', '番号', '開催'])), None)
    date_col = next((c for c in df.columns if any(k in c for k in ['日', 'date', 'Date', '付'])), None)
    set_col = next((c for c in df.columns if any(k in c for k in ['セット', 'set', 'Set']) and not any(k in c for k in ['本数字', 'ボーナス'])), None)
    bonus_cols = [c for c in df.columns if any(k in c for k in ['ボーナス', 'bonus', 'Bonus'])]
    target_cols = [c for c in df.columns if any(k in c for k in ['数字', '本数字', 'num', 'Num']) and c not in bonus_cols]
    
    if not round_col or not target_cols:
        return False, "⚠️ CSVの列構造（回号列または本数字列）を特定できませんでした。"
        
    # CSV内の最新回号を算出
    try:
        csv_latest_round = df[round_col].apply(lambda x: int(''.join(filter(str.isdigit, str(x))))).max()
    except:
        return False, "⚠️ CSV内の最新回号を解析できませんでした。"
        
    # すでに最新状態かチェック
    if web_data['round'] <= csv_latest_round:
        return True, f"✅ すでに最新データ（第{csv_latest_round}回）に更新されています。"
        
    # 新しい行の作成
    new_row = df.iloc[-1].copy()
    
    # 回号の代入
    if "第" in str(df[round_col].iloc[-1]):
        new_row[round_col] = f"第{web_data['round']}回"
    else:
        new_row[round_col] = web_data['round']
        
    # 抽選日
    if date_col and 'date' in web_data:
        new_row[date_col] = web_data['date']
        
    # 本数字
    for i, col in enumerate(target_cols[:len(web_data['numbers'])]):
        new_row[col] = web_data['numbers'][i]
        
    # ボーナス数字
    if bonus_cols and 'bonus' in web_data:
        for i, col in enumerate(bonus_cols[:len(web_data['bonus'])]):
            new_row[col] = web_data['bonus'][i]
            
    # セット球
    if set_col:
        set_ball = web_data.get('set_ball', 'C')
        if "セット" in str(df[set_col].iloc[-1]):
            new_row[set_col] = f"{set_ball}セット"
        else:
            new_row[set_col] = set_ball
            
    # 新しいデータを最後尾にマージ
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.columns = orig_columns
    
    # 上書き保存
    try:
        df.to_csv(filepath, index=False, encoding=encoding_used)
        return True, f"🎉 【創楽同期】第{web_data['round']}回の最新データをWEBから自動取得し、CSVへ追加しました！"
    except Exception as e:
        return False, f"⚠️ CSVファイルの上書き保存に失敗しました: {e}"
