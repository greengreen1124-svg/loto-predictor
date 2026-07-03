import urllib.request
import pandas as pd
import re
import os

def fetch_mizuho_data(loto_type):
    """
    みずほ銀行の公式サイトから最新の公式抽選結果（回号、日付、本数字、ボーナス数字）を取得
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
            
        # pandasのread_htmlを用いてテーブル要素を抽出
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
    except Exception as e:
        pass
    return None

def fetch_set_ball(loto_type, round_num):
    """
    みずほ銀行には掲載されない「セット球(A〜J)」の情報を専門サイトから補完抽出
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
        
        # 該当の最新回が掲載されているか確認し、セット球（A〜J）を正規表現で抽出
        if f"第{round_num}回" in html or str(round_num) in html:
            m = re.search(r'セット球\s*[:：]\s*([A-J_a-j])', html)
            if not m:
                m = re.search(r'([A-J_a-j])\s*セット', html)
            if m:
                return m.group(1).upper()
    except:
        pass
    return "C"  # 取得できない場合のデフォルト

def update_csv_file(loto_type, filepath):
    """
    WEB上の最新回と既存CSVを比較し、新しい抽選結果があれば自動で追記更新するメイン関数
    """
    if not os.path.exists(filepath):
        return False, f"⚠️ CSVファイルが見つかりません: {filepath}"
        
    # WEBから最新公式データを取得
    web_data = fetch_mizuho_data(loto_type)
    if not web_data:
        return False, f"⚠️ {loto_type}のWEB最新データの取得に失敗しました。"
        
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
            
    # 列名の表記揺れ対策（トリム処理）
    orig_columns = list(df.columns)
    clean_columns = [str(c).strip() for c in df.columns]
    df.columns = clean_columns
    
    # 各種キー列の自動判別
    round_col = next((c for c in df.columns if any(k in c for k in ['回', 'round', 'Round', 'No.', '番号', '開催'])), None)
    date_col = next((c for c in df.columns if any(k in c for k in ['日', 'date', 'Date', '付'])), None)
    set_col = next((c for c in df.columns if any(k in c for k in ['セット', 'set', 'Set']) and not any(k in c for k in ['本数字', 'ボーナス'])), None)
    bonus_cols = [c for c in df.columns if any(k in c for k in ['ボーナス', 'bonus', 'Bonus'])]
    target_cols = [c for c in df.columns if any(k in c for k in ['数字', '本数字', 'num', 'Num']) and c not in bonus_cols]
    
    if not round_col or not target_cols:
        return False, "⚠️ CSVの列構造（回号列または本数字列）を特定できませんでした。"
        
    # CSV内の最新回号を取得
    try:
        csv_latest_round = df[round_col].apply(lambda x: int(''.join(filter(str.isdigit, str(x))))).max()
    except:
        return False, "⚠️ CSV内の最新回号を解析できませんでした。"
        
    # すでに最新状態かチェック
    if web_data['round'] <= csv_latest_round:
        return True, f"✅ すでに最新データ（第{csv_latest_round}回）に更新されています。"
        
    # 新しい行の作成（データ整合性保持のため、最終行の書式をコピーして上書き）
    new_row = df.iloc[-1].copy()
    
    # 回号のフォーマット（数値か「第XX回」か）を合わせて代入
    if "第" in str(df[round_col].iloc[-1]):
        new_row[round_col] = f"第{web_data['round']}回"
    else:
        new_row[round_col] = web_data['round']
        
    # 抽選日
    if date_col:
        new_row[date_col] = web_data['date']
        
    # 本数字
    for i, col in enumerate(target_cols[:len(web_data['numbers'])]):
        new_row[col] = web_data['numbers'][i]
        
    # ボーナス数字（CSVに列が存在する場合）
    if bonus_cols and 'bonus' in web_data:
        for i, col in enumerate(bonus_cols[:len(web_data['bonus'])]):
            new_row[col] = web_data['bonus'][i]
            
    # セット球
    if set_col:
        set_ball = fetch_set_ball(loto_type, web_data['round'])
        if "セット" in str(df[set_col].iloc[-1]):
            new_row[set_col] = f"{set_ball}セット"
        else:
            new_row[set_col] = set_ball
            
    # 昇順（古い順）の最後尾に新しいデータを結合
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    
    # 列名を元に戻す
    df.columns = orig_columns
    
    # 上書き保存
    try:
        df.to_csv(filepath, index=False, encoding=encoding_used)
        return True, f"🎉 第{web_data['round']}回の最新データをWEBから自動取得し、CSVへ追加しました！"
    except Exception as e:
        return False, f"⚠️ CSVファイルの上書き保存に失敗しました: {e}"
