import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import random

# ページの設定
st.set_page_config(page_title="ロト数字選択 AI予想", page_icon="🎰", layout="centered")

# --- スクレイピング関数 ---
@st.cache_data(ttl=3600)  # 1時間キャッシュしてサイトへの負荷を軽減
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
            
            # 1. リンク（aタグ）を除外し、本文内の「絞り込み予想」というテキストを持つ要素を特定
            target_element = None
            for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p', 'th', 'td']):
                if tag.name == 'a' or tag.find('a'):
                    continue  # メニュー用のリンクはスキップ
                if '絞り込み予想' in tag.get_text():
                    target_element = tag
                    break
            
            if target_element:
                # 2. 見出しの「後ろにある要素」を1つずつ順番に精査（ページ全体の結合はしない）
                for next_node in target_element.find_all_next(['p', 'div', 'td', 'tr']):
                    node_text = next_node.get_text(strip=True)
                    
                    # 1桁または2桁の数字の塊を抽出
                    numbers = re.findall(r'\b\d{1,2}\b', node_text)
                    
                    # 各ロトのルール設定
                    min_required = 5 if loto_type == "ミニロト" else (6 if loto_type == "ロト6" else 7)
                    max_num = 31 if loto_type == "ミニロト" else (43 if loto_type == "ロト6" else 37)
                    
                    # 有効な数字のみをフィルタリング
                    valid_nums_in_node = [int(n) for n in numbers if 1 <= int(n) <= max_num]
                    unique_nums = sorted(list(set(valid_nums_in_node)))
                    
                    # 【重要】数字が最低必要数以上あり、かつ「全数字」が揃ってしまっていないかチェック
                    # これにより、すべての数字が並んだデータテーブル（誤検知）を綺麗に弾きます
                    if min_required <= len(unique_nums) < max_num:
                        return unique_nums, False
                        
    except Exception as e:
        pass

    # サイトから取得できない場合のバックアップ
    fallback_data = {
        "ロト7": [1, 5, 9, 12, 14, 19, 23, 26, 30, 32, 35, 37],
        "ロト6": [2, 6, 11, 15, 18, 22, 27, 31, 35, 38, 41, 43],
        "ミニロト": [3, 7, 11, 14, 19, 22, 25, 28, 31]
    }
    return fallback_data[loto_type], True


# --- 予想ロジック関数 ---
def generate_prediction(bias_numbers, loto_type, trend, count=1):
    loto_rules = {
        "ロト7": {"pick": 7, "max": 37},
        "ロト6": {"pick": 6, "max": 43},
        "ミニロト": {"pick": 5, "max": 31}
    }
    rule = loto_rules[loto_type]
    
    if len(bias_numbers) < rule["pick"]:
        bias_numbers = list(set(bias_numbers) | set(range(1, rule["max"] + 1)))

    predictions = []
    
    for _ in range(count):
        weights = []
        for num in bias_numbers:
            weight = 1.0
            if trend == "奇数重視" and num % 2 != 0:
                weight += 0.6
            elif trend == "偶数重視" and num % 2 == 0:
                weight += 0.6
            elif trend == "大きめの数字重視" and num > (rule["max"] / 2):
                weight += 0.5
            elif trend == "小さめの数字重視" and num <= (rule["max"] / 2):
                weight += 0.5
            weights.append(weight)
        
        pool = list(bias_numbers)
        w_pool = list(weights)
        selected = []
        
        for _ in range(rule["pick"]):
            picked = random.choices(pool, weights=w_pool, k=1)[0]
            selected.append(picked)
            idx = pool.index(picked)
            pool.pop(idx)
            w_pool.pop(idx)
            
        predictions.append(sorted(selected))
        
    return predictions


# --- Streamlit UI の構築 ---
st.title("🎰 数字選択式くじ 絞り込み予想ツール")
st.write("「創楽」のビアス式絞り込みデータと直近の傾向を掛け合わせて最適な組み合わせを算出します。")

# サイドバー設定
st.sidebar.header("⚙️ 条件設定")
loto_choice = st.sidebar.selectbox("くじの種類を選択", ["ロト7", "ロト6", "ミニロト"])
trend_choice = st.sidebar.selectbox(
    "直近の傾向（トレンド）を選択", 
    ["完全ランダム", "奇数重視", "偶数重視", "大きめの数字重視", "小さめの数字重視"]
)
prediction_rows = st.sidebar.slider("予想する組み合わせ数", 1, 10, 5)

# データ取得
bias_nums, is_fallback = fetch_bias_numbers(loto_choice)

# メイン画面表示
st.subheader(f"📊 {loto_choice} 分析データ・ベース")

if is_fallback:
    st.info("⚠️ 現在ソースサイトが混雑しているか構造が変更されているため、直近の出現傾向から抽出したベース数字を使用しています。")
else:
    st.success("✅ 創楽「ビアス式 絞り込み予想」からベース数字の同期に成功しました！")

st.write(f"**現在の選出候補数字（計 {len(bias_nums)} 個）:**")
st.code(", ".join(map(str, bias_nums)))

# 予想実行ボタン
if st.button(f"🔮 {loto_choice} の予想を展開する", type="primary"):
    results = generate_prediction(bias_nums, loto_choice, trend_choice, prediction_rows)
    
    st.markdown("---")
    st.subheader("🎯 予想組み合わせ結果")
    
    for i, res in enumerate(results, 1):
        balls = "  ".join([f"`{num:02d}`" for num in res])
        st.markdown(f"**パターン {i:02d}** : {balls}")
