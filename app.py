import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import re
import random
import os
# 【重要】作成した自動更新用モジュールをインポート
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
            target_element = None
            for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p', 'th', 'td', 'b']):
                if tag.name == 'a' or tag.find('a'):
                    continue
                if '絞り込み予想' in tag.get_text():
                    target_element = tag
                    break
            
            if target_element:
                for next_node in target_element.find_all_next(['p', 'div', 'td', 'tr', 'span']):
                    node_text = next_node.get_text(strip=True)
                    numbers = re.findall(r'\b\d{1,2}\b', node_text)
                    
                    min_required = 5 if loto_type == "ミニロト" else (6 if loto_type == "ロト6" else 7)
                    max_num = 31 if loto_type == "ミニロト" else (43 if loto_type == "ロト6" else 37)
                    
                    valid_nums = [int(n) for n in numbers if 1 <= int(n) <= max_num]
                    unique_nums = sorted(list(set(valid_nums)))
                    
                    if min_required <= len(unique_nums) < max_num:
                        status_log["numbers_found"] = len(unique_nums)
                        status_log["msg"] = "URLからのリアルタイム取得に成功しました。"
                        status_log["success"] = True
                        return unique_nums, status_log
                status_log["msg"] = "有効な数字の組が検出できませんでした。"
            else:
                status_log["msg"] = "「絞り込み予想」キーワードが見つかりませんでした。"
        else:
            status_log["msg"] = f"アクセス拒否 (HTTP {response.status_code})"
    except Exception as e:
        status_log["msg"] = f"通信エラー: {str(e)}"
    return None, status_log


# --- CSVデータの読み込みと「直近30回」の傾向分析 ---
def load_and_analyze_history(loto_type):
    file_map = {
        "ロト7": "loto7_history.csv",
        "ロト6": "loto6_history.csv",
        "ミニロト": "miniloto_history.csv"
    }
    filename = file_map[loto_type]
    
    # 【別ファイル連携】updater.py を呼び出し、最新結果を自動追加したデータフレームを取得
    df, update_info_msg = updater.update_csv_file(loto_type, filename)
    
    if df is None:
        return None, None, update_info_msg, None
        
    if loto_type == "ロト7":
        main_cols = [f"第{i}数字" for i in range(1, 8)]
    elif loto_type == "ロト6":
        main_cols = [f"第{i}数字" for i in range(1, 7)]
    else:
        main_cols = [f"第{i}数字" for i in range(1, 6)]
        
    if not all(col in df.columns for col in main_cols):
        return None, None, f"CSV内にターゲット列名が見つかりません。", None
        
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
    
    # 画面表示用に最新行のデータ（回数、日付）を取得
    last_row = df.iloc[-1]
    
    analysis = {
        "sum_min": int(recent_30['sum_val'].quantile(0.1)),
        "sum_max": int(recent_30['sum_val'].quantile(0.9)),
        "sum_avg": int(recent_30['sum_val'].mean()),
        "odds_mode": int(recent_30['odds_count'].mode()[0] if not recent_30['odds_count'].empty else len(main_cols)/2),
        "serial_rate": float(recent_30['has_serial'].mean()),
        "back_avg": float(recent_30['back_count'].mean()),
        "slide_avg": float(recent_30['slide_count'].mean()),
        "set_ball_counts": set_counts,
        "last_round": last_row['開催回'],
        "last_date": last_row['日付']
    }
    
    last_drawn = df['numbers_list'].iloc[-1]
    return analysis, last_drawn, None, update_info_msg


# --- トレンドフィルター型・予想ロジック ---
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

    valid_combinations = []
    attempts = 0
    
    while len(valid_combinations) < count and attempts < 30000:
        attempts += 1
        sample = sorted(random.sample(bias_numbers, rule["pick"]))
        
        s_val = sum(sample)
        if not (trend_analysis["sum_min"] <= s_val <= trend_analysis["sum_max"]):
            continue
                
        o_val = len([x for x in sample if x % 2 != 0])
        if abs(o_val - trend_analysis["odds_mode"]) > 1:
            continue
            
        has_s = any(sample[j+1] - sample[j] == 1 for j in range(len(sample)-1))
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
        for _ in range(count - len(valid_combinations)):
            valid_combinations.append(sorted(random.sample(bias_numbers, rule["pick"])))
            
    return valid_combinations


def predict_next_set_ball(set_counts):
    if not set_counts or "未設定" in set_counts:
        return "データなし", "ー"
    sorted_sets = sorted(set_counts.items(), key=lambda x: x[1], reverse=True)
    hot_set = sorted_sets[0][0]  
    cold_set = sorted_sets[-1][0] 
    return hot_set, cold_set


# --- Streamlit UI 構築 ---
st.title("🎰 ロト・スマートAI予想システム（過去トレンド完全連動型）")

# サイドバー
st.sidebar.header("⚙️ 条件設定")
loto_choice = st.sidebar.selectbox("くじの種類を選択", ["ロト7", "ロト6", "ミニロト"])
prediction_rows = st.sidebar.slider("予想する組み合わせ数", 1, 10, 5)

# 過去データ解析と自動更新の実行
trends, last_drawn_nums, error_msg, update_msg = load_and_analyze_history(loto_choice)

if error_msg:
    st.error(error_msg)
else:
    # CSV自動更新ステータスの通知表示
    if "🎉" in update_msg:
        st.success(update_msg)
    elif "ℹ️" in update_msg:
        st.info(update_msg)
    else:
        st.warning(update_msg)

    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader(f"📊 直近30回の傾向分析 ({loto_choice})")
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
        else:
            st.warning("セット球データがCSVに存在しません。")

    # ビアス式データの厳格取得
    bias_nums, debug_info = fetch_bias_numbers_strict(loto_choice)
    
    st.markdown("---")
    st.subheader(f"🎯 ビアス式数字 × 直近30回フィルター 最終予想")
    
    if debug_info["success"] and bias_nums is not None:
        st.success(f"✅ 【通信成功】創楽のWebサイトから最新のベース数字の同期に成功しました。")
        
        st.write(f"**分析のベースにしたビアス数字:**")
        st.code(", ".join(map(str, bias_nums)))
        
        # 横並びに配置された最新回の回数、抽選日、出目
        st.write(f"**前回（最新）の本数字出目:** 🏆 **第 {trends['last_round']} 回** （{trends['last_date']} 抽選）")
        st.code("  ".join([f"{num:02d}" for num in sorted(last_drawn_nums)]))

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
    else:
        st.error("❌ 取得失敗：創楽のWebサイトから最新の絞り込み数字をスクレイピングできませんでした。")
        with st.expander("🔍 詳しい通信エラーの原因（デバッグ情報）"):
            st.write(f"**ステータスコード:** {debug_info['status_code']}")
            st.write(f"**エラー詳細:** {debug_info['msg']}")
