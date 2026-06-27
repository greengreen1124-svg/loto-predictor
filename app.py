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

# --- スクレイピング関数（ビアス式数字の厳格取得） ---
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
            
            target_text = ""
            for tag in soup.find_all(['td', 'th', 'p', 'div', 'b']):
                text = tag.get_text()
                if "絞り込み予想" in text or "予想数字" in text:
                    target_text += " " + text
            
            if not target_text:
                target_text = soup.get_text()
                
            numbers = re.findall(r'\b\d{1,2}\b', target_text)
            
            if numbers:
                min_required = 5 if loto_type == "ミニロト" else (6 if loto_type == "ロト6" else 7)
                max_num = 31 if loto_type == "ミニロト" else (43 if loto_type == "ロト6" else 37)
                
                valid_nums = [int(n) for n in numbers if 1 <= int(n) <= max_num]
                unique_nums = sorted(list(set(valid_nums)))
                
                if min_required <= len(unique_nums) < max_num:
                    status_log["numbers_found"] = len(unique_nums)
                    status_log["msg"] = "URLからのリアルタイム取得に成功しました。"
                    status_log["success"] = True
                    return unique_nums, status_log
                    
        status_log["msg"] = "サイトのデザインが変更されたか、予想数字のエリアが見つかりませんでした。"
        return None, status_log
    except Exception as e:
        status_log["msg"] = f"通信または解析中にエラーが発生しました: {str(e)}"
        return None, status_log

# --- 過去トレンド分析関数 ---
def analyze_past_trends(df, loto_type):
    if df is None or df.empty:
        return None

    main_cols = [c for c in df.columns if "第" in c and "数字" in c]
    
    df['sum_val'] = df[main_cols].sum(axis=1)
    df['odds_count'] = df[main_cols].apply(lambda row: sum(1 for x in row if x % 2 != 0), axis=1)
    
    df['numbers_list'] = df[main_cols].values.tolist()
    df['numbers_list'] = df['numbers_list'].apply(lambda x: sorted([int(n) for n in x if pd.notna(n)]))
    
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
    
    analysis = {
        "sum_min": int(recent_30['sum_val'].quantile(0.1)) if len(recent_30) > 0 else 10,
        "sum_max": int(recent_30['sum_val'].quantile(0.9)) if len(recent_30) > 0 else 150,
        "sum_avg": int(recent_30['sum_val'].mean()) if len(recent_30) > 0 else 100,
        "odds_mode": int(recent_30['odds_count'].mode()[0] if not recent_30['odds_count'].empty else len(main_cols)/2),
        "serial_rate": float(recent_30['has_serial'].mean()) if len(recent_30) > 0 else 0.5,
        "back_avg": float(recent_30['back_count'].mean()) if len(recent_30) > 0 else 1.0,
        "slide_avg": float(recent_30['slide_count'].mean()) if len(recent_30) > 0 else 1.0,
        "set_ball_counts": set_counts,
        "last_round": last_row['開催回'] if '開催回' in last_row else '不明',
        "last_date": last_row['日付'] if '日付' in last_row else '不明'
    }
    
    return analysis

# --- AI組み合わせ生成関数 ---
def generate_advanced_prediction(bias_numbers, loto_type, trend_analysis, last_numbers, count=5):
    if not bias_numbers or len(bias_numbers) < 5:
        return []
        
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

    valid_combinations = []
    attempts = 0
    
    while len(valid_combinations) < count and attempts < 30000:
        attempts += 1
        sample = sorted(random.sample(bias_numbers, rule["pick"]))
        
        s_val = sum(sample)
        if not (trend_analysis["sum_min"] <= s_val <= trend_analysis["sum_max"]):
            continue
            
        o_val = sum(1 for x in sample if x % 2 != 0)
        if o_val != trend_analysis["odds_mode"]:
            continue
            
        has_s = any(sample[i+1] - sample[i] == 1 for i in range(len(sample)-1))
        if trend_analysis["serial_rate"] > 0.5 and not has_s and random.random() > 0.3:
            continue
        elif trend_analysis["serial_rate"] <= 0.5 and has_s and random.random() > 0.4:
            continue
            
        b_val = len(set(sample) & last_set)
        if abs(b_val - trend_analysis["back_avg"]) > 1.5:
            continue
            
        sl_val = len(set(sample) & last_slides)
        if abs(sl_val - trend_analysis["slide_avg"]) > 1.5:
            continue
            
        if sample not in valid_combinations:
            valid_combinations.append(sample)
            
    if len(valid_combinations) < count:
        while len(valid_combinations) < count:
            valid_combinations.append(sorted(random.sample(bias_numbers, rule["pick"])))
            
    return valid_combinations


# --- [大改造] 相性遷移＆候補が1つに絞り込めるまで無限に遡る予測関数 ---
def predict_next_set_ball_advanced(df):
    if 'セット' not in df.columns or len(df) < 2:
        return "データなし", "ー", "データ不足のため分析できません"
        
    # 前回のセット球（最新の出目）を取得
    last_set = df['セット'].iloc[-1]
    if pd.isna(last_set) or last_set == "未設定":
        return "データなし", "ー", "前回のセット球データが未設定です"

    # 指定された範囲内で「前回セット球の直後に何が来たか」を集計するインナー関数
    def analyze_transitions(window_size):
        start_idx = max(0, len(df) - 1 - window_size)
        sub_df = df.iloc[start_idx:]
        
        transitions = []
        for i in range(len(sub_df) - 1):
            if sub_df['セット'].iloc[i] == last_set:
                next_val = sub_df['セット'].iloc[i+1]
                if pd.notna(next_val) and next_val != "未設定":
                    transitions.append(next_val)
        return transitions

    # 本命(Hot)と大穴(Cold)の候補リスト（重複タイの確認用）を抽出するインナー関数
    def get_top_and_bottom_candidates(counts_dict):
        if not counts_dict:
            return [], []
        max_val = max(counts_dict.values())
        min_val = min(counts_dict.values())
        
        hots = [k for k, v in counts_dict.items() if v == max_val]
        colds = [k for k, v in counts_dict.items() if v == min_val]
        return hots, colds

    # 初期設定：過去50回からスタート
    current_window = 50
    max_possible_window = len(df) - 1  # 過去データ全体の限界（安全弁）

    # 候補が完全に1つに絞り込めるまで10回ずつ遡り続けるループ
    while True:
        ts = analyze_transitions(current_window)
        counts = {}
        for s in ts:
            counts[s] = counts.get(s, 0) + 1

        if not counts:
            break

        # 現在の集計結果から、本命と大穴の候補数をチェック
        hots, colds = get_top_and_bottom_candidates(counts)

        # 【ループ終了の条件】
        # 本命の候補が1つ（単独1位）かつ 大穴の候補が1つ（単独最下位）に完全に絞り込めた場合、
        # または、CSVの過去全データを使い切ってこれ以上遡れない場合はループを終了する
        if (len(hots) == 1 and len(colds) == 1) or current_window >= max_possible_window:
            break

        # 同数（タイ）が存在し、まだ過去に遡れる場合は、さらに10回ウィンドウを拡大してループを継続
        next_window = current_window + 10
        if next_window > max_possible_window:
            current_window = max_possible_window
        else:
            current_window = next_window

    if not counts:
        return "分析不能", "ー", f"過去のデータのなかに、前回と同じ【{last_set}セット】の事例がありませんでした"

    # 最終的な候補を決定（全データ遡っても同数の場合は、リストの先頭を採択）
    hot_set = hots[0]
    cold_set = colds[0]

    # データ特性上、本命と大穴が同じになってしまった場合の安全処理
    if hot_set == cold_set:
        all_possible_sets = [chr(i) for i in range(ord('A'), ord('K'))]
        unused_sets = [s for s in all_possible_sets if s not in counts and s != last_set]
        if unused_sets:
            cold_set = random.choice(unused_sets)
        else:
            cold_set = "ー"

    status_msg = f"前回【{last_set}セット】の直後傾向を解析（候補を1つに絞るため、過去 {current_window} 回まで自動で遡って確定）"
    if len(hots) > 1 or len(colds) > 1:
        status_msg += " ※全歴史を遡っても同数のため、最直近の優位性から自動選出"

    return hot_set, cold_set, status_msg


# --- Streamlit UI 構築 ---
st.title("🎰 ロト・スマートAI予想システム（過去トレンド完全連動型）")

# サイドバーでロトの種類を選択
loto_choice = st.sidebar.selectbox("ロトの種類を選択", ["ロト7", "ロト6", "ミニロト"])
prediction_rows = st.sidebar.slider("予想する組み合わせ数", 1, 10, 5)

# 対応するCSVファイルの選択
csv_mapping = {
    "ロト7": "loto7_history.csv",
    "ロト6": "loto6_history.csv",
    "ミニロト": "miniloto_history.csv"
}
target_csv = csv_mapping[loto_choice]

# CSVの自動更新＆読み込み
df, sync_message = updater.update_csv_file(loto_choice, target_csv)

# 同期メッセージの表示
if "🎉" in sync_message:
    st.success(sync_message)
elif "ℹ️" in sync_message:
    st.info(sync_message)
else:
    st.warning(sync_message)

# メイン解析
trends = analyze_past_trends(df, loto_choice)

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader(f"📊 直近30回の出目トレンド分析 ({loto_choice})")
    if trends:
        trend_data = {
            "分析項目": ["合計値の範囲 (10%~90%)", "偶数個数の最頻値", "連続数字の発生率", "引っ張り数字の平均個数", "斜め数字の平均個数"],
            "直近30回の傾向値": [
                f"{trends['sum_min']} ～ {trends['sum_max']} (平均: {trends['sum_avg']})",
                f"{trends['odds_mode']} 個",
                f"{trends['serial_rate']*100:.1f} %",
                f"{trends['back_avg']:.2f} 個",
                f"{trends['slide_avg']:.2f} 個"
            ]
        }
        trend_df = pd.DataFrame(trend_data)
        st.table(trend_df)
    else:
        st.warning("傾向データが算出できませんでした。")
    
with col2:
    st.subheader("🔮 次回セット球の相性予測")
    if trends and df is not None:
        # 新しい無限遡り型の相性遷移予測関数を呼び出し
        hot_set, cold_set, status_msg = predict_next_set_ball_advanced(df)
        
        if hot_set != "データなし":
            st.caption(f"💡 【AI解析ステータス】")
            st.info(status_msg)
            st.metric(label="🔥 本命相性球（前回セットの後に最も連鎖しやすい）", value=f"{hot_set} セット")
            st.metric(label="❄️ 大穴相性球（前回セットの後に最も選ばれにくい）", value=f"{cold_set} セット")
        else:
            st.warning(f"セット球データが解析できませんでした（原因: {status_msg}）")
    else:
        st.warning("データ不足のため予測をスキップします。")

# ビアス式データの厳格取得
bias_nums, debug_info = fetch_bias_numbers_strict(loto_choice)

st.markdown("---")
st.subheader(f"🎯 ビアス式数字 × 直近30回フィルター 最終予想")

if debug_info["success"] and bias_nums is not None and trends:
    st.success(f"✅ 【通信成功】創楽のWebサイトから最新のベース数字の同期に成功しました。")
    
    st.write(f"**分析のベースにしたビアス数字:**")
    st.code(", ".join(map(str, bias_nums)))
    
    main_cols = [c for c in df.columns if "第" in c and "数字" in c]
    last_drawn_nums = df[main_cols].iloc[-1].dropna().astype(int).tolist()
    
    st.write(f"**前回（最新）の本数字出目:** 🏆 **第 {trends['last_round']} 回** （{trends['last_date']} 抽選）")
    st.code("  ".join([f"{num:02d}" for num in sorted(last_drawn_nums)]))

    if st.button(f"🔮 上記の傾向をすべて満たす組み合わせを抽出する", type="primary"):
        results = generate_advanced_prediction(bias_nums, loto_choice, trends, last_drawn_nums, prediction_rows)
        
        st.markdown("### 🏹 厳選された予想パターン")
        for i, res in enumerate(results, 1):
            balls = " ".join([f"[{n:02d}]" for n in res])
            st.markdown(f"**予想 {i:02d} :** &nbsp;&nbsp;&nbsp;&nbsp;`{balls}`")
else:
    st.error(f"❌ リアルタイム予想数字の取得に失敗しました。既存のCSV分析のみ利用可能です。({debug_info['msg']})")
