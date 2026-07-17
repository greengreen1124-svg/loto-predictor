import streamlit as st
import pandas as pd
import numpy as np
import re
import random
import os
from collections import Counter
import updater

# ページの設定
st.set_page_config(page_title="ロトデータ分析＆AI予想", page_icon="🎰", layout="wide")

# --- 🎯【変更】ビアス式数字（絞り込み数字）をCSVから読み込む関数 (app-3.py 方式) ---
def load_bias_numbers_from_csv(loto_type):
    file_map = {
        "ロト7": "loto7_bias.csv",
        "ロト6": "loto6_bias.csv",
        "ミニロト": "miniloto_bias.csv"
    }
    csv_filename = file_map.get(loto_type, "loto6_bias.csv")
    focus_numbers = []
    status_log = {"success": False, "msg": "未取得", "numbers_found": 0}
    
    if os.path.exists(csv_filename):
        # 複数エンコーディングに安全に対応
        for encoding in ['utf-8', 'shift_jis', 'cp932']:
            try:
                with open(csv_filename, 'r', encoding=encoding) as f:
                    for line in f:
                        # app-3.py準拠: '絞り込み数字' または '絞り込み予想' の行を探す
                        if '絞り込み数字' in line or '絞り込み予想' in line or 'ビアス' in line:
                            parts = line.strip().split(',')
                            if len(parts) >= 2:
                                val = parts[-1]  # 最後の列を取得
                                # スペース区切りやカンマ混在でも数字だけを確実に取り出す
                                nums = [int(n) for n in re.findall(r'\d+', val)]
                                focus_numbers.extend(nums)
                if focus_numbers:
                    # 重複を排除しソート
                    focus_numbers = sorted(list(set(focus_numbers)))
                    status_log["success"] = True
                    status_log["msg"] = f"CSV ({csv_filename}) から予想数字の読み込みに成功しました。"
                    status_log["numbers_found"] = len(focus_numbers)
                    return focus_numbers, status_log
            except Exception:
                continue
        status_log["msg"] = f"CSV ({csv_filename}) 内に「絞り込み数字」のデータが見つかりませんでした。"
    else:
        status_log["msg"] = f"CSV ({csv_filename}) が見つかりません。ファイルを作成してください。"
        
    return [], status_log


# --- 🎯【変更】セット球予測関数 (app-3.py の遷移確率MAX＆ローテーション周期理論) ---
def predict_next_set_ball_app3(df):
    if 'セット' not in df.columns or len(df) < 2:
        return "データなし", "ー", "データ不足のため分析できません"
        
    set_history = df['セット'].dropna().astype(str).tolist()
    
    # A〜Jまでのアルファベットを抽出・クレンジング
    clean_sets = []
    for s in set_history:
        m = re.search(r'([A-J_a-j])', s)
        if m:
            clean_sets.append(m.group(1).upper())
            
    if len(clean_sets) < 5:
        return "データなし", "ー", "データ不足のため予測をスキップします"
        
    current_set = clean_sets[-1]
    transitions = []
    
    # 全履歴から「今回と同じセット球が出た次」に何が出たかを集計
    for i in range(len(clean_sets) - 1):
        if clean_sets[i] == current_set:
            transitions.append(clean_sets[i+1])
            
    # 直近30回のデータから未出現（または最も出現が少ない）セットを割り出す
    recent_sets = clean_sets[-30:]
    set_counts = {letter: recent_sets.count(letter) for letter in list("ABCDEFGHIJ")}
    least_frequent_sets = [k for k, v in set_counts.items() if v == min(set_counts.values())]
    
    predicted_set = "C" 
    set_info = "（デフォルト値）"
    
    # app-3.py の優先順位ロジック
    if transitions:
        predicted_set = max(set(transitions), key=transitions.count)
        set_info = f"直近【{current_set}】からの遷移確率MAX理論に基づく自動予測"
    elif least_frequent_sets:
        predicted_set = random.choice(least_frequent_sets)
        set_info = f"直近30回の未出現ローテーション周期に基づく自動予測"
        
    # UI側の変数との互換性のため、cold_setとして最小出現を返す
    cold_set = least_frequent_sets[0] if least_frequent_sets else "ー"
    
    return predicted_set, cold_set, set_info


# --- セット球完全連動：固有の過去トレンド＆出やすい数字を動的に再計算する関数 ---
def calculate_set_specific_trends(df, loto_type, selected_set, global_trends):
    if 'セット' not in df.columns or not selected_set or selected_set == "未設定":
        return global_trends
        
    # クレンジング（"Aセット" -> "A" などに統一して比較）
    def get_clean_set(s):
        m = re.search(r'([A-J_a-j])', str(s))
        return m.group(1).upper() if m else str(s)
        
    df_temp = df.copy()
    df_temp['clean_set'] = df_temp['セット'].apply(get_clean_set)
    set_df = df_temp[df_temp['clean_set'] == selected_set]
    
    if set_df.empty:
        return global_trends
        
    recent_set = set_df.tail(30)
    
    all_nums = [num for nums_list in set_df['numbers_list'] for num in nums_list]
    top_nums = [item[0] for item in Counter(all_nums).most_common(10)] if all_nums else []
    
    if len(recent_set) >= 3:
        specific_trends = {
            "sum_min": int(recent_set['sum_val'].quantile(0.1)) if len(recent_set) >= 10 else int(recent_set['sum_val'].min()),
            "sum_max": int(recent_set['sum_val'].quantile(0.9)) if len(recent_set) >= 10 else int(recent_set['sum_val'].max()),
            "sum_avg": int(recent_set['sum_val'].mean()),
            "odds_mode": int(recent_set['odds_count'].mode()[0] if not recent_set['odds_count'].empty else global_trends["odds_mode"]),
            "serial_rate": float(recent_set['has_serial'].mean()),
            "back_avg": float(recent_set['back_count'].mean()),
            "slide_avg": float(recent_set['slide_count'].mean()),
            "last_round": global_trends["last_round"],
            "last_date": global_trends["last_date"],
            "hot_set": global_trends["hot_set"],
            "cold_set": global_trends["cold_set"],
            "set_status_msg": global_trends["set_status_msg"],
            "all_sets": global_trends["all_sets"],
            "top_numbers": top_nums
        }
        return specific_trends
    return global_trends


# --- CSVデータの読み込みと事前加工 ---
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
        update_info_msg = f"⚠️ 自動更新プロセス制限: {str(e)}"
    
    if df is None:
        if os.path.exists(filename):
            try:
                df = pd.read_csv(filename, encoding='utf-8')
            except Exception:
                try:
                    df = pd.read_csv(filename, encoding='shift_jis')
                except Exception as e:
                    return None, None, None, f"❌ CSV読み込みエラー: {str(e)}", update_info_msg
        else:
            return None, None, None, f"❌ CSV「{filename}」が見つかりません。", update_info_msg

    if df is None or df.empty:
        return None, None, None, f"❌ データが空です。", update_info_msg
        
    if loto_type == "ロト7":
        main_cols = [f"第{i}数字" for i in range(1, 8)]
    elif loto_type == "ロト6":
        main_cols = [f"第{i}数字" for i in range(1, 7)]
    else:
        main_cols = [f"第{i}数字" for i in range(1, 6)]
        
    if not all(col in df.columns for col in main_cols):
        return None, None, None, f"❌ 解析に必要な列名がCSV内にありません。", update_info_msg
        
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
    
    # 🎯【変更】app-3.py のロジックを使って次回のセット球を予測する
    hot_set, cold_set, set_status_msg = predict_next_set_ball_app3(df)
    
    all_existing_sets = []
    if 'セット' in df.columns:
        all_existing_sets = sorted([str(s).strip() for s in df['セット'].dropna().unique() if str(s).strip() != "" and s != "未設定"])
        # クレンジング（アルファベット1文字へ統一）
        all_existing_sets = sorted(list(set([re.search(r'([A-J_a-j])', s).group(1).upper() for s in all_existing_sets if re.search(r'([A-J_a-j])', s)])))

    if not all_existing_sets:
        all_existing_sets = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
    
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
        "cold_set": cold_set,
        "set_status_msg": set_status_msg,
        "all_sets": all_existing_sets,
        "top_numbers": []
    }
    
    last_drawn = df['numbers_list'].iloc[-1]
    return df, analysis, last_drawn, None, update_info_msg


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


# --- Streamlit UI 構築 ---
st.title("🎰 ロト・スマートAI予想システム（セット球完全連動型）")

# サイドバー
st.sidebar.header("⚙️ 条件設定")
loto_choice = st.sidebar.selectbox("くじの種類を選択", ["ロト7", "ロト6", "ミニロト"])
prediction_rows = st.sidebar.slider("予想する組み合わせ数", 1, 10, 5)

# 過去データ解析と自動更新の実行
df, trends, last_drawn_nums, error_msg, update_msg = load_and_analyze_history(loto_choice)

if error_msg:
    st.error(error_msg)
    st.stop()

if update_msg:
    if "🎉" in update_msg: st.success(update_msg)
    elif "ℹ️" in update_msg: st.info(update_msg)
    else: st.warning(update_msg)

# 🎯【変更】ビアス式データの自動取得を CSVファイルからの読み込みに変更
bias_nums, debug_info = load_bias_numbers_from_csv(loto_choice)

# 🚨 サイドバー：緊急手動入力機能
st.sidebar.markdown("---")
st.sidebar.subheader("🚨 救急処置用ツール")
use_manual_nums = st.sidebar.checkbox("手動でベース数字を入力（上書き）")
if use_manual_nums:
    max_n = 31 if loto_choice == "ミニロト" else (43 if loto_choice == "ロト6" else 37)
    manual_input = st.sidebar.text_input(f"予想に使用する数字をカンマやスペース区切りで入力（1〜{max_n}）", value="1, 5, 10, 15, 20")
    parsed = [int(x) for x in re.findall(r'\b\d{1,2}\b', manual_input)]
    bias_nums = sorted(list(set([n for n in parsed if 1 <= n <= max_n])))
    
    min_req = 5 if loto_choice == "ミニロト" else (6 if loto_choice == "ロト6" else 7)
    if len(bias_nums) >= min_req:
        debug_info["success"] = True
        debug_info["msg"] = "手動入力データへの切り替えに成功しました。"
    else:
        debug_info["success"] = False
        debug_info["msg"] = f"手動入力された数字が足りません（最低 {min_req} 個必要）。"

col1, col2 = st.columns([1, 1])

# 🛠️ 先に右側の col2 を処理して、選択されたセット球を取得する
with col2:
    st.subheader("🔮 次回セット球の予測・選択")
    selected_set = "未設定"
    if trends:
        hot_set = trends.get('hot_set', 'データなし')
        status_msg = trends.get('set_status_msg', '')
        available_sets = trends.get('all_sets', ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'])
        
        if hot_set != "データなし":
            st.caption("💡 【AI解析ステータス】")
            st.info(status_msg)
            
            try:
                default_idx = available_sets.index(str(hot_set).strip())
            except ValueError:
                default_idx = 0
            
            # ターゲットセット球のドロップダウン
            selected_set = st.selectbox(
                "🔥 ターゲットセット球（切り替えると、左側のフィルター傾向値と最終予想がそのセット球専用に変化します）",
                options=available_sets,
                index=default_idx
            )
        else:
            st.warning("セット球データがCSVに存在しないか、解析できませんでした。")
    else:
        st.warning("データ不足のため予測をスキップします。")

# ⚡【最重要連動】選択されたセット球に基づいて、傾向分析＆出やすい数字を動的に書き換える
if trends and df is not None:
    trends = calculate_set_specific_trends(df, loto_choice, selected_set, trends)

# 🛠️ 右側に「出やすい数字TOP10」をスマートに表示
with col2:
    if trends and "top_numbers" in trends and trends["top_numbers"]:
        st.markdown(f"### 📈 【{selected_set}セット】で出やすい数字 TOP10")
        formatted_nums = " 🌟 " + " , ".join([f"**{num:02d}**" for num in trends["top_numbers"]])
        st.success(formatted_nums)

# 🛠️ 書き換えられた trends（セット球固有データ）を使って左側の表を表示
with col1:
    st.subheader(f"📊 【{selected_set} セット】限定の傾向分析 ({loto_choice})")
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

st.markdown("---")
st.subheader(f"🎯 絞り込み数字 × 【{selected_set}セット傾向フィルター】 最終予想")

if debug_info["success"] and bias_nums is not None and trends:
    if use_manual_nums:
        st.info(f"💡 救急モード稼働中：手動で上書きされたベース数字をもとに厳選抽出を行います。")
    else:
        st.success(f"✅ {debug_info['msg']}")
    
    st.write(f"**分析のベースにした数字（候補母集団）:**")
    st.code(", ".join(map(str, bias_nums)))
    
    st.write(f"**前回（最新）の本数字出目:** 🏆 **第 {trends['last_round']} 回** （{trends['last_date']} 抽選）")
    st.code("  ".join([f"{num:02d}" for num in sorted(last_drawn_nums)]))

    if st.button(f"🔮 【{selected_set}セット】の出目傾向をすべて満たす組み合わせを抽出する", type="primary"):
        results = generate_advanced_prediction(bias_nums, loto_choice, trends, last_drawn_nums, prediction_rows)
        
        st.markdown(f"### 🏹 厳選された予想パターン（{selected_set}セット専用）")
        for i, res in enumerate(results, 1):
            balls = "  ".join([f"`{num:02d}`" for num in res])
            res_sum = sum(res)
            res_odds = len([x for x in res if x % 2 != 0])
            res_even = len(res) - res_odds
            
            st.markdown(f"**パターン {i:02d}** : {balls} *(合計: {res_sum} / 奇偶比: {res_odds}:{res_even})*")
else:
    st.error("❌ 取得失敗：予想のベースとなる数字が用意されていません。")
    with st.expander("🔍 エラーの原因（デバッグ情報）"):
        st.write(f"**エラー詳細:** {debug_info['msg']}")
        st.markdown("---")
        st.markdown("💡 **【解決策】** \n1. アプリと同じフォルダに `loto6_bias.csv` などのファイルを作成し、`絞り込み数字, 02 03 09...` のように記入してください。\n2. または、サイドバーの「**手動でベース数字を入力（上書き）**」にチェックを入れて直接入力してください。")
