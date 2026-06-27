import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import re
import random
import os
# 自動更新用モジュールをインポート
import updater

# ページの設定
st.set_page_config(page_title="ロトデータ分析＆AI予想", page_icon="🎰", layout="wide")

# --- スクレイピング関数（最新のテキストブロック・スコアリング方式） ---
def fetch_bias_numbers_strict(loto_type):
    urls = {
        "ロト7": "http://sougaku.com/loto7/index.html",
        "ロト6": "http://sougaku.com/loto6/index.html",
        "ミニロト": "http://sougaku.com/miniloto/index.html"
    }
    url = urls[loto_type]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    status_log = {"status_code": None, "numbers_found": 0, "msg": "未接続", "success": False}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        status_log["status_code"] = response.status_code
        response.encoding = response.apparent_encoding
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # メニューやサイドバーのノイズを減らすため、不要なタグを一時的にパージ
            for noise in soup(["script", "style", "header", "footer", "nav"]):
                noise.decompose()
                
            full_text = soup.get_text()
            
            min_required = 5 if loto_type == "ミニロト" else (6 if loto_type == "ロト6" else 7)
            max_num = 31 if loto_type == "ミニロト" else (43 if loto_type == "ロト6" else 37)
            
            # メインの予想コンテンツを示唆するキーワードの登場位置
            keywords = ["絞り込み予想", "予想数字", "今回の予想", "厳選予想"]
            positions = []
            for kw in keywords:
                for m in re.finditer(kw, full_text):
                    positions.append(m.start())
            
            if not positions:
                positions = [0]
                
            best_nums = []
            
            # 各キーワードの後方1200文字のテキストブロックをスキャン
            for pos in positions:
                sub_txt = full_text[pos:pos+1200]
                
                # ブロック内に「過去のデータ一覧」が混入した場合はその手前で切断
                for stop_word in ["過去のデータ", "バックナンバー", "回号別一覧"]:
                    if stop_word in sub_txt:
                        sub_txt = sub_txt.split(stop_word)[0]
                        
                # 該当ブロックから純粋な数字だけを抽出
                extracted = [int(x) for x in re.findall(r'\b\d{1,2}\b', sub_txt)]
                valid_nums = []
                for n in extracted:
                    if 1 <= n <= max_num and n not in valid_nums:
                        valid_nums.append(n)
                
                if min_required <= len(valid_nums) < (max_num - 2):
                    if len(valid_nums) > len(best_nums):
                        best_nums = sorted(valid_nums)
            
            # 行単位でのバックアップスキャン
            if len(best_nums) < min_required:
                for line in full_text.split('\n'):
                    line = line.strip()
                    if any(w in line for w in ["第", "回", "年", "月", "日", "過去"]): continue
                    line_nums = [int(x) for x in re.findall(r'\b\d{1,2}\b', line) if 1 <= int(x) <= max_num]
                    line_nums = list(set(line_nums))
                    if min_required <= len(line_nums) <= (max_num - 5):
                        if len(line_nums) > len(best_nums):
                            best_nums = sorted(line_nums)

            if len(best_nums) >= min_required:
                status_log["numbers_found"] = len(best_nums)
                status_log["msg"] = "URLからのリアルタイム取得に成功しました。"
                status_log["success"] = True
                return best_nums, status_log
                
            status_log["msg"] = "有効な予想数字エリアの特定、または数字の抽出に失敗しました。"
        else:
            status_log["msg"] = f"アクセス拒否 (HTTP {response.status_code})"
    except Exception as e:
        status_log["msg"] = f"通信エラー: {str(e)}"
    return None, status_log


# --- 相性遷移予測関数（本命のみを抽出・大穴ロジックは削除） ---
def predict_next_set_ball_advanced(df):
    if 'セット' not in df.columns or len(df) < 2:
        return "データなし", "データ不足のため分析できません"
        
    last_set = df['セット'].iloc[-1]
    if pd.isna(last_set) or last_set == "未設定" or str(last_set).strip() == "":
        return "データなし", "前回のセット球データが未設定です"

    total_rows = len(df)
    current_window = 50  
    max_possible_window = total_rows - 1  

    while True:
        start_idx = max(0, total_rows - 1 - current_window)
        sub_df = df.iloc[start_idx:]
        
        transitions = []
        for i in range(len(sub_df) - 1):
            if sub_df['セット'].iloc[i] == last_set:
                next_val = sub_df['セット'].iloc[i+1]
                if pd.notna(next_val) and str(next_val).strip() != "" and next_val != "未設定":
                    transitions.append(next_val)
                    
        counts = {}
        for s in transitions:
            counts[s] = counts.get(s, 0) + 1
            
        if not counts:
            if current_window >= max_possible_window: break
            current_window += 10
            continue
            
        max_val = max(counts.values())
        hots = [k for k, v in counts.items() if v == max_val]
        
        if len(hots) == 1 or current_window >= max_possible_window:
            break
            
        next_window = current_window + 10
        if next_window > max_possible_window:
            current_window = max_possible_window
        else:
            current_window = next_window

    if not counts:
        return "分析不能", f"過去のデータに前回と同じ【{last_set}セット】の事例がありませんでした"

    hot_set = hots[0]
    status_msg = f"前回【{last_set}セット】の直後傾向を解析（過去 {current_window} 回まで遡って本命を特定）"
    return hot_set, status_msg


# --- 特定のセット球において出現率の高い強数を割り出す関数 ---
def get_set_ball_strong_numbers(df, set_name, main_cols):
    if set_name == "データなし" or set_name == "分析不能" or 'セット' not in df.columns:
        return []
    
    # 対象のセット球が使われた回だけを全抽出
    df_set = df[df['セット'].str.strip() == str(set_name).strip() if df['セット'].dtype == 'O' else df['セット'] == set_name]
    if df_set.empty:
        return []
        
    all_nums = []
    for col in main_cols:
        all_nums.extend(df_set[col].dropna().astype(int).tolist())
        
    if not all_nums:
        return []
        
    # 出現回数順にソートして上位12個を強数として選出
    freq = pd.Series(all_nums).value_counts()
    strong_numbers = freq.head(12).index.tolist()
    return strong_numbers


# --- CSVデータの読み込みと「直近30回」の傾向分析 ---
def load_and_analyze_history(loto_type):
    file_map = {
        "ロト7": "loto7_history.csv",
        "ロト6": "loto6_history.csv",
        "ミニロト": "miniloto_history.csv"
    }
    filename = file_map[loto_type]
    
    df = None
    update_info_msg = ""
    
    try:
        if hasattr(updater, 'update_csv_file'):
            df, update_info_msg = updater.update_csv_file(loto_type, filename)
    except Exception as e:
        update_info_msg = f"⚠️ 自動更新プロセスで制限が発生しました: {str(e)}"
    
    if df is None:
        if os.path.exists(filename):
            for enc in ['utf-8', 'shift_jis', 'cp932']:
                try:
                    df = pd.read_csv(filename, encoding=enc)
                    break
                except:
                    continue
        else:
            return None, None, f"❌ CSVファイル「{filename}」が見つかりません。", update_info_msg

    if df is None or df.empty:
        return None, None, f"❌ {filename} のデータが空、または正しく読み込めませんでした。", update_info_msg
        
    if loto_type == "ロト7":
        main_cols = [f"第{i}数字" for i in range(1, 8)]
    elif loto_type == "ロト6":
        main_cols = [f"第{i}数字" for i in range(1, 7)]
    else:
        main_cols = [f"第{i}数字" for i in range(1, 6)]
        
    if not all(col in df.columns for col in main_cols):
        return None, None, f"❌ CSV内に解析に必要なターゲット列名が見つかりません。", update_info_msg
        
    def clean_row(row):
        return sorted([int(float(i)) for i in row if pd.notna(i) and str(i).strip() != ''])
        
    df['numbers_list'] = df[main_cols].values.tolist()
    df['numbers_list'] = df['numbers_list'].apply(clean_row)
    
    df['sum_val'] = df['numbers_list'].apply(sum)
    df['odds_count'] = df['numbers_list'].apply(lambda x: len([i for i in x if i % 2 != 0]))
    df['has_serial'] = df['numbers_list'].apply(lambda x: any(x[i+1] - x[i] == 1 for i in range(len(x)-1)))
    df['prev_numbers'] = df['numbers_list'].shift(1)
    
    def calc_back(row):
        if not isinstance(row['prev_numbers'], list): return 0
        return len(set(row['numbers_list']) & set(row['prev_numbers']))
        
    def calc_slide(row):
        if not isinstance(row['prev_numbers'], list): return 0
        prev_set = set(row['prev_numbers'])
        current_set = set(row['numbers_list'])
        slide_candidates = set()
        for x in prev_set:
            slide_candidates.add(x - 1)
            slide_candidates.add(x + 1)
        slide_candidates = slide_candidates - prev_set
        return len(current_set & slide_candidates)
        
    df['back_count'] = df.apply(calc_back, axis=1)
    df['slide_count'] = df.apply(calc_slide, axis=1)
    
    recent_30 = df.tail(30)
    set_counts = recent_30['セット'].value_counts().to_dict() if 'セット' in df.columns else {"未設定": 1}
    
    last_row = df.iloc[-1]
    
    # 本命セットの予測（大穴は返り値から排除）
    hot_set, set_status_msg = predict_next_set_ball_advanced(df)
    
    # 予測された本命セット特有の強数を割り出し
    hot_strong_numbers = get_set_ball_strong_numbers(df, hot_set, main_cols)
    
    analysis = {
        "sum_min": int(recent_30['sum_val'].quantile(0.1)) if len(recent_30) > 0 else 10,
        "sum_max": int(recent_30['sum_val'].quantile(0.9)) if len(recent_30) > 0 else 200,
        "sum_avg": int(recent_30['sum_val'].mean()) if len(recent_30) > 0 else 100,
        "odds_mode": int(recent_30['odds_count'].mode()[0] if not recent_30['odds_count'].empty else len(main_cols)/2),
        "serial_rate": float(recent_30['has_serial'].mean()) if len(recent_30) > 0 else 0.5,
        "back_avg": float(recent_30['back_count'].mean()) if len(recent_30) > 0 else 1.0,
        "slide_avg": float(recent_30['slide_count'].mean()) if len(recent_30) > 0 else 1.0,
        "set_ball_counts": set_counts,
        "last_round": last_row['開催回'] if '開催回' in last_row else '不明',
        "last_date": last_row['日付'] if '日付' in last_row else '不明',
        "hot_set": hot_set,
        "hot_strong_numbers": hot_strong_numbers, # 本命セットの強数リストを格納
        "set_status_msg": set_status_msg
    }
    
    last_drawn = df['numbers_list'].iloc[-1]
    return analysis, last_drawn, None, update_info_msg


# --- トレンドフィルター型・予想ロジック（本命セット強数連動版） ---
def generate_advanced_prediction(bias_numbers, loto_type, trend_analysis, last_numbers, count=5):
    loto_rules = {
        "ロト7": {"pick": 7, "max": 37},
        "ロト6": {"pick": 6, "max": 43},
        "ミニロト": {"pick": 5, "max": 31}
    }
    rule = loto_rules[loto_type]
    
    last_set = set(last_numbers)
    last_slides = set()
    for x in last_set:
        last_slides.add(x - 1)
        last_slides.add(x + 1)
    last_slides = last_slides - last_set

    # 連動させる本命セットの強数
    set_strong_nums = trend_analysis.get("hot_strong_numbers", [])

    valid_combinations = []
    attempts = 0
    
    while len(valid_combinations) < count and attempts < 40000:
        attempts += 1
        sample = sorted(random.sample(bias_numbers, rule["pick"]))
        
        # 1. 本命セットの強数が含まれているかフィルター（強力連動）
        if set_strong_nums:
            match_count = len(set(sample) & set(set_strong_nums))
            # ミニロトは1個以上、ロト6/7は2個以上そのセット球の強数を含むことを条件にする
            min_match = 1 if loto_type == "ミニロト" else 2
            if match_count < min_match:
                continue
        
        # 2. 合計数フィルター
        s_val = sum(sample)
        if not (trend_analysis["sum_min"] <= s_val <= trend_analysis["sum_max"]):
            continue
                
        # 3. 奇偶比フィルター
        o_val = len([x for x in sample if x % 2 != 0])
        if abs(o_val - trend_analysis["odds_mode"]) > 1:
            continue
            
        # 4. 連番フィルター
        has_s = any(sample[j+1] - sample[j] == 1 for j in range(len(sample)-1))
        if trend_analysis["serial_rate"] > 0.5 and not has_s and random.random() > 0.3:
            continue
        elif trend_analysis["serial_rate"] <= 0.5 and has_s and random.random() > 0.4:
            continue
            
        # 5. ひっぱり数フィルター
        b_val = len(set(sample) & last_set)
        if abs(b_val - trend_analysis["back_avg"]) > 1.5:
            continue
            
        # 6. スライド数フィルター
        sl_val = len(set(sample) & last_slides)
        if abs(sl_val - trend_analysis["slide_avg"]) > 1.5:
            continue
            
        if sample not in valid_combinations:
            valid_combinations.append(sample)
            
    # 万が一制限回数内に見つからなかった場合のフォールバック
    if len(valid_combinations) < count:
        for _ in range(count - len(valid_combinations)):
            valid_combinations.append(sorted(random.sample(bias_numbers, rule["pick"])))
            
    return valid_combinations


# --- Streamlit UI 構築 ---
st.title("🎰 ロト・スマートAI予想システム（次回セット球トレンド完全連動版）")

# サイドバー
st.sidebar.header("⚙️ 条件設定")
loto_choice = st.sidebar.selectbox("くじの種類を選択", ["ロト7", "ロト6", "ミニロト"])
prediction_rows = st.sidebar.slider("予想する組み合わせ数", 1, 10, 5)

# 過去データ解析と自動更新の実行
trends, last_drawn_nums, error_msg, update_msg = load_and_analyze_history(loto_choice)

if error_msg:
    st.error(error_msg)
    st.stop()

if update_msg:
    if "🎉" in update_msg: st.success(update_msg)
    elif "ℹ️" in update_msg: st.info(update_msg)
    else: st.warning(update_msg)

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader(f"📊 直近30回の傾向分析 ({loto_choice})")
    if trends:
        trend_df = pd.DataFrame({
            "分析項目": ["① 合計数の出現範囲", "① 合計数の平均値", "② 最も多い奇数個数", "③ 連番の発生確率", "④ 平均ひっぱり個数", "⑤ 平均スライド個数"],
            "直近30回のリアル実績値": [
                f"{trends['sum_min']} 〜 {trends['sum_max']}",
                f"{trends['sum_avg']} ",
                f"{trends['odds_mode']} 個",
                f"{trends['serial_rate']*100:.1f} %",
                f"{trends['back_avg']:.1f} 個",
                f"{trends['slide_avg']:.1f} 個"
            ]
        })
        st.table(trend_df)
    else:
        st.warning("傾向データが算出できませんでした。")
    
with col2:
    st.subheader("🔮 次回セット球の予測＆連動ステータス")
    if trends:
        hot_set = trends.get('hot_set', 'データなし')
        status_msg = trends.get('set_status_msg', '')
        strong_nums = trends.get('hot_strong_numbers', [])
        
        if hot_set != "データなし" and hot_set != "分析不能":
            st.caption("💡 【AI解析ステータス】")
            st.info(status_msg)
            st.metric(label="🔥 本命相性球（次回最も出やすいセット球）", value=f"{hot_set} セット")
            
            if strong_nums:
                st.write(f"📌 **{hot_set}セット使用時の過去の出現強数（上位12選）:**")
                st.code(", ".join([f"{n:02d}" for n in sorted(strong_nums)]))
                st.caption("※下の最終予想では、これらの強数が自動的に組み込まれるよう連動しています。")
        else:
            st.warning("セット球データがCSVに存在しないか、解析できませんでした。")
    else:
        st.warning("データ不足のため予測をスキップします。")

# ビアス式データの厳格取得
bias_nums, debug_info = fetch_bias_numbers_strict(loto_choice)

st.markdown("---")
st.subheader(f"🎯 ビアス式数字 × 過去トレンド × 本命セット球連動 最終予想")

if debug_info["success"] and bias_nums is not None and trends:
    st.success(f"✅ 【通信成功】創楽のWebサイトから最新のベース数字の同期に成功しました。")
    
    st.write(f"**分析のベースにしたビアス数字:**")
    st.code(", ".join(map(str, bias_nums)))
    
    st.write(f"**前回（最新）の本数字出目:** 🏆 **第 {trends['last_round']} 回** （{trends['last_date']} 抽選）")
    st.code("  ".join([f"{num:02d}" for num in sorted(last_drawn_nums)]))

    if st.button(f"🔮 本命セット球の傾向を含む全ての条件を満たす組み合わせを抽出", type="primary"):
        results = generate_advanced_prediction(bias_nums, loto_choice, trends, last_drawn_nums, prediction_rows)
        
        st.markdown("### 🏹 厳選された予想パターン")
        for i, res in enumerate(results, 1):
            balls = "  ".join([f"`{num:02d}`" for num in res])
            res_sum = sum(res)
            res_odds = len([x for x in res if x % 2 != 0])
            res_even = len(res) - res_odds
            
            st.markdown(f"**パターン {i:02d}** : {balls} *(合計: {res_sum} / 奇偶比: {res_odds}:{res_even})*")
else:
    st.error("❌ 取得失敗：創楽のWebサイトから最新の絞り込み数字をスクレイピングできませんでした。")
    with st.expander("🔍 詳しい通信エラーの原因（デバッグ情報）"):
        st.write(f"**ステータスコード:** {debug_info['status_code']}")
        st.write(f"**エラー詳細:** {debug_info['msg']}")
