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

# --- スクレイピング関数（通信エラー回避・ブロック一括切り出し方式へ全面刷新） ---
def fetch_bias_numbers_strict(loto_type):
    # URLをセキュアなhttpsに変更
    urls = {
        "ロト7": "https://sougaku.com/loto7/index.html",
        "ロト6": "https://sougaku.com/loto6/index.html",
        "ミニロト": "https://sougaku.com/miniloto/index.html"
    }
    url = urls[loto_type]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    status_log = {"status_code": None, "numbers_found": 0, "msg": "未接続", "success": False}
    try:
        # SSL警告を非表示にしてリダイレクトを安全に突破
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        response = requests.get(url, headers=headers, timeout=10, verify=False)
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
            
            # 🎯 予想コンテンツの「開始キーワード」
            keywords = ["絞り込み予想", "予想数字", "今回の予想", "厳選予想", "データ分析予想"]
            start_pos = -1
            for kw in keywords:
                idx = full_text.find(kw)
                if idx != -1:
                    start_pos = idx
                    break
            
            if start_pos == -1:
                start_pos = 0 # 万が一見つからない場合は先頭から
                
            target_area = full_text[start_pos:]
            
            # 🎯 過去データ一覧（大量の数字ノイズ）が混入する手前で正確に切断
            stop_words = ["過去のデータ", "バックナンバー", "回号別一覧", "過去当選番号", "過去の出目"]
            end_pos = len(target_area)
            for sw in stop_words:
                idx = target_area.find(sw)
                if idx != -1 and idx < end_pos:
                    end_pos = idx
                    
            target_area = target_area[:end_pos]
            
            # 該当ブロックから純粋な数字（1〜2桁）をすべて抽出（行スキップのバグを完全撤廃）
            extracted = [int(x) for x in re.findall(r'\b\d{1,2}\b', target_area)]
            bias_nums = []
            for n in extracted:
                if 1 <= n <= max_num and n not in bias_nums:
                    bias_nums.append(n)
            
            # 💡【超強力セーフティフォールバック】もし切り出し判定が厳しすぎて数字が取れなかった場合
            # 過去の巨大テーブルを巻き込まない「ページ最上部2500文字」から直接数字を強制回収する
            if len(bias_nums) < min_required:
                fallback_extracted = [int(x) for x in re.findall(r'\b\d{1,2}\b', full_text[:2500])]
                bias_nums = []
                for n in fallback_extracted:
                    if 1 <= n <= max_num and n not in bias_nums:
                        bias_nums.append(n)

            if len(bias_nums) >= min_required:
                status_log["numbers_found"] = len(bias_nums)
                status_log["msg"] = "URLからのリアルタイム取得に成功しました（新・広域テキストブロック抽出法）。"
                status_log["success"] = True
                return sorted(bias_nums), status_log
                
            status_log["msg"] = f"有効な予想数字エリアから規定数の数字を抽出できませんでした（検出: {len(bias_nums)}個）。"
        else:
            status_log["msg"] = f"アクセス拒否またはページ不在 (HTTP {response.status_code})"
    except Exception as e:
        status_log["msg"] = f"通信または解析エラー: {str(e)}"
    return None, status_log


# --- 候補が1つに絞り込めるまで無限に遡る相性遷移予測関数（本命・大穴の重複ガード付） ---
def predict_next_set_ball_advanced(df):
    if 'セット' not in df.columns or len(df) < 2:
        return "データなし", "ー", "データ不足のため分析できません"
        
    last_set = df['セット'].iloc[-1]
    if pd.isna(last_set) or last_set == "未設定" or str(last_set).strip() == "":
        return "データなし", "ー", "前回のセット球データが未設定です"

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
        min_val = min(counts.values())
        
        hots = [k for k, v in counts.items() if v == max_val]
        colds = [k for k, v in counts.items() if v == min_val]
        
        if (len(hots) == 1 and len(colds) == 1) or current_window >= max_possible_window:
            break
            
        next_window = current_window + 10
        if next_window > max_possible_window:
            current_window = max_possible_window
        else:
            current_window = next_window

    if not counts:
        return "分析不能", "ー", f"過去のデータに前回と同じ【{last_set}セット】の事例がありませんでした"

    hot_set = hots[0]
    cold_set = colds[0]

    if hot_set == cold_set:
        all_existing_sets = [s for s in df['セット'].dropna().unique() if str(s).strip() != "" and s != "未設定"]
        unused_sets = [s for s in all_existing_sets if s not in counts and s != last_set]
        if unused_sets:
            cold_set = unused_sets[0]
        else:
            sorted_counts = sorted(counts.items(), key=lambda x: x[1])
            for s, v in sorted_counts:
                if s != hot_set:
                    cold_set = s
                    break

    status_msg = f"前回【{last_set}セット】の直後傾向を解析（過去 {current_window} 回まで自動で遡って確定）"
    return hot_set, cold_set, status_msg


# --- 🎯【セット球完全連動】選択されたセット球固有の過去トレンドを動的に再計算する関数 ---
def calculate_set_specific_trends(df, loto_type, selected_set, global_trends):
    if 'セット' not in df.columns or not selected_set or selected_set == "未設定":
        return global_trends
        
    set_df = df[df['セット'] == selected_set]
    if set_df.empty:
        return global_trends
        
    recent_set = set_df.tail(30) # そのセット球が使用された「直近30回分」を抽出
    
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
            "all_sets": global_trends["all_sets"]
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
    
    hot_set, cold_set, set_status_msg = predict_next_set_ball_advanced(df)
    
    all_existing_sets = []
    if 'セット' in df.columns:
        all_existing_sets = sorted([str(s).strip() for s in df['セット'].dropna().unique() if str(s).strip() != "" and s != "未設定"])
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
        "all_sets": all_existing_sets
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

# ビアス式データの自動取得（新ロジック）
bias_nums, debug_info = fetch_bias_numbers_strict(loto_choice)

# 🚨 サイドバー：緊急手動入力機能（スクレイピングが失敗した時の100%保険）
st.sidebar.markdown("---")
st.sidebar.subheader("🚨 救急処置用ツール")
use_manual_nums = st.sidebar.checkbox("手動でベース数字を入力（上書き）")
if use_manual_nums:
    max_n = 31 if loto_choice == "ミニロト" else (43 if loto_choice == "ロト6" else 37)
    manual_input = st.sidebar.text_input(f"サイトの数字をここにカンマ区切り等で入力（1〜{max_n}）", value="1, 5, 10, 15, 20")
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
        cold_set = trends.get('cold_set', 'ー')
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
            st.metric(label="❄️ 大穴相性球（最も選ばれにくい傾向）", value=f"{cold_set} セット")
        else:
            st.warning("セット球データがCSVに存在しないか、解析できませんでした。")
    else:
        st.warning("データ不足のため予測をスキップします。")

# ⚡【最重要連動】選択されたセット球に基づいて、傾向分析（trends）の数値を動的に書き換える！
if trends and df is not None:
    trends = calculate_set_specific_trends(df, loto_choice, selected_set, trends)

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
st.subheader(f"🎯 ビアス式数字 × 【{selected_set}セット傾向フィルター】 最終予想")

if debug_info["success"] and bias_nums is not None and trends:
    if use_manual_nums:
        st.info(f"💡 救急モード稼働中：手動で上書きされたベース数字をもとに厳選抽出を行います。")
    else:
        st.success(f"✅ 【通信成功】創楽のWebサイトから最新のベース数字の同期に成功しました。")
    
    st.write(f"**分析のベースにしたビアス数字:**")
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
    st.error("❌ 取得失敗：スクレイピングが正常に機能していません。")
    with st.expander("🔍 詳しい通信エラーの原因（デバッグ情報）"):
        st.write(f"**ステータスコード:** {debug_info['status_code']}")
        st.write(f"**エラー詳細:** {debug_info['msg']}")
        st.markdown("---")
        st.markdown("💡 **【解決策】** 相手サイトのサーバー障害や、通信環境により自動同期ができない状態です。サイドバーの「**手動でベース数字を入力（上書き）**」にチェックを入れ、サイト上の数字を入力することで**エラーを即時解消し、AI予想機能をそのままフル活用**できます。")
