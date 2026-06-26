import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import re
import random
import os

# ページの設定
st.set_page_config(page_title="ロトデータ分析＆AI予想", page_icon="🎰", layout="wide")

# --- スクレイピング関数（ビアス式数字の取得） ---
@st.cache_data(ttl=3600)
def fetch_bias_numbers(loto_type):
    urls = {
        "ロト7": "http://sougaku.com/loto7/index.html",
        "ロト6": "http://sougaku.com/loto6/index.html",
        "ミニロト": "http://sougaku.com/miniloto/index.html"
    }
    url = urls[loto_type]
    try:
        response = requests.get(url, timeout=10)
        response.encoding = response.apparent_encoding
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            target_element = None
            for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p', 'th', 'td']):
                if tag.name == 'a' or tag.find('a'):
                    continue
                if '絞り込み予想' in tag.get_text():
                    target_element = tag
                    break
            
            if target_element:
                for next_node in target_element.find_all_next(['p', 'div', 'td', 'tr']):
                    node_text = next_node.get_text(strip=True)
                    numbers = re.findall(r'\b\d{1,2}\b', node_text)
                    min_required = 5 if loto_type == "ミニロト" else (6 if loto_type == "ロト6" else 7)
                    max_num = 31 if loto_type == "ミニロト" else (43 if loto_type == "ロト6" else 37)
                    
                    valid_nums_in_node = [int(n) for n in numbers if 1 <= int(n) <= max_num]
                    unique_nums = sorted(list(set(valid_nums_in_node)))
                    
                    if min_required <= len(unique_nums) < max_num:
                        return unique_nums, False
    except:
        pass

    fallback_data = {
        "ロト7": [1, 5, 9, 12, 14, 19, 23, 26, 30, 32, 35, 37],
        "ロト6": [2, 6, 11, 15, 18, 22, 27, 31, 35, 38, 41, 43],
        "ミニロト": [3, 7, 11, 14, 19, 22, 25, 28, 31]
    }
    return fallback_data[loto_type], True


# --- CSVデータの読み込みと「直近30回」の高度な傾向分析 ---
def load_and_analyze_history(loto_type):
    file_map = {
        "ロト7": "loto7_history.csv",
        "ロト6": "loto6_history.csv",
        "ミニロト": "miniloto_history.csv"
    }
    filename = file_map[loto_type]
    
    if not os.path.exists(filename):
        return None, None, f"ファイル `{filename}` が見つかりません。GitHubリポジトリにCSVを配置してください。"
    
    # 文字コード対応
    for enc in ['utf-8', 'cp932', 'shift_jis']:
        try:
            df = pd.read_csv(filename, encoding=enc)
            break
        except:
            continue
    else:
        return None, None, "CSVファイルの読み込みに失敗しました。"
    
    # 提供されたCSVの列名に完全準拠
    if loto_type == "ロト7":
        main_cols = [f"第{i}数字" for i in range(1, 8)]
    elif loto_type == "ロト6":
        main_cols = [f"第{i}数字" for i in range(1, 7)]
    else:
        main_cols = [f"第{i}数字" for i in range(1, 6)]
        
    if not all(col in df.columns for col in main_cols):
        return None, None, f"CSV内にターゲット列名が見つかりません。列名が「第1数字」等になっているか確認してください。"
        
    # 全データの本数字を数値リスト化して格納
    df['numbers_list'] = df[main_cols].values.tolist()
    df['numbers_list'] = df['numbers_list'].apply(lambda x: sorted([int(i) for i in x if pd.notna(i)]))
    
    # 傾向の先行一括計算
    df['sum_val'] = df['numbers_list'].apply(sum)
    df['odds_count'] = df['numbers_list'].apply(lambda x: len([i for i in x if i % 2 != 0]))
    df['has_serial'] = df['numbers_list'].apply(lambda x: any(x[i+1] - x[i] == 1 for i in range(len(x)-1)))
    
    # 「1つ前の回」の数字をシフト（昇順データなので、shift(1)が過去回になる）
    df['prev_numbers'] = df['numbers_list'].shift(1)
    
    # ひっぱり計算
    def calc_back(row):
        if not isinstance(row['prev_numbers'], list): return 0
        return len(set(row['numbers_list']) & set(row['prev_numbers']))
        
    # スライド計算（前回の±1、ただしひっぱりは除く）
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
    
    # 末尾の30行（＝最新の直近30回）を抽出して統計を取る
    recent_30 = df.tail(30)
    
    set_counts = recent_30['セット'].value_counts().to_dict() if 'セット' in df.columns else {"未設定": 1}
    
    analysis = {
        "sum_min": int(recent_30['sum_val'].quantile(0.1)),
        "sum_max": int(recent_30['sum_val'].quantile(0.9)),
        "sum_avg": int(recent_30['sum_val'].mean()),
        "odds_mode": int(recent_30['odds_count'].mode()[0] if not recent_30['odds_count'].empty else len(main_cols)/2),
        "serial_rate": float(recent_30['has_serial'].mean()),
        "back_avg": float(recent_30['back_count'].mean()),
        "slide_avg": float(recent_30['slide_count'].mean()),
        "set_ball_counts": set_counts
    }
    
    # 完全に一番最後の行＝最新の（前回）出目
    last_drawn = df['numbers_list'].iloc[-1]
    
    return analysis, last_drawn, None


# --- トレンドフィルター型・次世代予想ロジック ---
def generate_advanced_prediction(bias_numbers, loto_type, trend_analysis, last_numbers, count=5):
    loto_rules = {
        "ロト7": {"pick": 7, "max": 37},
        "ロト6": {"pick": 6, "max": 43},
        "ミニロト": {"pick": 5, "max": 31}
    }
    rule = loto_rules[loto_type]
    
    if len(bias_numbers) < rule["pick"]:
        bias_numbers = list(set(bias_numbers) | set(range(1, rule["max"] + 1)))
        
    last_set = set(last_numbers)
    last_slides = set()
    for x in last_set:
        last_slides.add(x - 1)
        last_slides.add(x + 1)
    last_slides = last_slides - last_set

    valid_combinations = []
    attempts = 0
    
    # 膨大なランダムシミュレーションから、直近30回の全傾向を満たすものだけを「ふるい落とし」
    while len(valid_combinations) < count and attempts < 30000:
        attempts += 1
        sample = sorted(random.sample(bias_numbers, rule["pick"]))
        
        # 1. 合計数フィルター
        if not (trend_analysis["sum_min"] <= sum(sample) <= trend_analysis["max"]):
            s_val = sum(sample)
            if not (trend_analysis["sum_min"] <= s_val <= trend_analysis["sum_max"]):
                continue
                
        # 2. 奇数偶数比フィルター (最頻値から±1個まで許容)
        o_val = len([x for x in sample if x % 2 != 0])
        if abs(o_val - trend_analysis["odds_mode"]) > 1:
            continue
            
        # 3. 連番発生確率フィルター
        has_s = any(sample[j+1] - sample[j] == 1 for j in range(len(sample)-1))
        if trend_analysis["serial_rate"] > 0.5 and not has_s and random.random() > 0.3:
            continue
        elif trend_analysis["serial_rate"] <= 0.5 and has_s and random.random() > 0.4:
            continue
            
        # 4. ひっぱり数フィルター (直近平均から±1.5個以内)
        b_val = len(set(sample) & last_set)
        if abs(b_val - trend_analysis["back_avg"]) > 1.5:
            continue
            
        # 5. スライド数フィルター (直近平均から±1.5個以内)
        sl_val = len(set(sample) & last_slides)
        if abs(sl_val - trend_analysis["slide_avg"]) > 1.5:
            continue
            
        if sample not in valid_combinations:
            valid_combinations.append(sample)
            
    # 万が一、条件が厳しすぎて目標数に達さなかった場合のセーフティ
    if len(valid_combinations) < count:
        for _ in range(count - len(valid_combinations)):
            valid_combinations.append(sorted(random.sample(bias_numbers, rule["pick"])))
            
    return valid_combinations


# --- セット球予測 ---
def predict_next_set_ball(set_counts):
    if not set_counts or "未設定" in set_counts:
        return "データなし", "ー"
    sorted_sets = sorted(set_counts.items(), key=lambda x: x[1], reverse=True)
    hot_set = sorted_sets[0][0]  # 直近30回で最多登場
    cold_set = sorted_sets[-1][0] # 直近30回で最少登場
    return hot_set, cold_set


# --- Streamlit UI 構築 ---
st.title("🎰 ロト・スマートAI予想システム（過去トレンド完全連動型）")
st.write("創楽の「ビアス式絞り込み数字」に対し、アップロードされたCSVの最新30回分から弾き出した5大傾向データを掛け合わせて厳選予想します。")

# サイドバー
st.sidebar.header("⚙️ 条件設定")
loto_choice = st.sidebar.selectbox("くじの種類を選択", ["ロト7", "ロト6", "ミニロト"])
prediction_rows = st.sidebar.slider("予想する組み合わせ数", 1, 10, 5)

# 過去データ解析の実行
trends, last_drawn_nums, error_msg = load_and_analyze_history(loto_choice)

if error_msg:
    st.error(error_msg)
else:
    # 画面を2カラムに分割してダッシュボード化
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader(f"📊 【本物】直近30回の傾向分析 ({loto_choice})")
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
        
    with col2:
        st.subheader("🔮 次回セット球の予測")
        hot_set, cold_set = predict_next_set_ball(trends['set_ball_counts'])
        if hot_set != "データなし":
            st.metric(label="🔥 本命トレンド球（直近30回で最も使われている）", value=f"{hot_set} セット")
            st.metric(label="❄️ 大穴デジタル球（直近30回で出現が最も滞っている）", value=f"{cold_set} セット")
            with st.expander("直近30回の全セット球の使用内訳"):
                st.write(trends['set_ball_counts'])
        else:
            st.warning("セット球データがCSVに存在しません。")

    # ビアス式データの取得
    bias_nums, is_fallback = fetch_bias_numbers(loto_choice)
    
    st.markdown("---")
    st.subheader(f"🎯 ビアス式数字 × 直近30回フィルター 最終予想")
    
    if is_fallback:
        st.info("⚠️ 創楽のウェブサイトからリアルタイム取得ができなかったため、標準バックアップ数字を使用しています。")
    else:
        st.success(f"✅ 創楽「ビアス式 絞り込み」から {len(bias_nums)} 個のベース数字の同期に成功しました。")
        
    st.write(f"**分析のベースにしたビアス数字:**")
    st.code(", ".join(map(str, bias_nums)))
    st.write(f"**前回（最新）の本数字出目:** {sorted(last_drawn_nums)}")

    # 予想実行ボタン
    if st.button(f"🔮 上記の傾向をすべて満たす組み合わせを抽出する", type="primary"):
        results = generate_advanced_prediction(bias_nums, loto_choice, trends, last_drawn_nums, prediction_rows)
        
        st.markdown("### 🏹 厳選された予想パターン")
        for i, res in enumerate(results, 1):
            balls = "  ".join([f"`{num:02d}`" for num in res])
            res_sum = sum(res)
            res_odds = len([x for x in res if x % 2 != 0])
            res_even = len(res) - res_odds
            
            st.markdown(f"**パターン {i:02d}** : {balls} *(合計: {res_sum} / 奇偶比: {res_odds}:{res_even})*")
