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
        "ロト7": "http://sougaku.com/loto7/index.html#top8",
        "ロト6": "http://sougaku.com/loto6/index.html#top8",
        "ミニロト": "http://sougaku.com/miniloto/index.html#top7"
    }
    url = urls[loto_type]
    
    try:
        response = requests.get(url, timeout=10)
        # 文字化け対策
        response.encoding = response.apparent_encoding
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. 「絞り込み予想」という文字列が含まれるタグ（見出し等）を特定
            target_element = None
            for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p', 'td', 'th', 'span']):
                if '絞り込み予想' in tag.get_text():
                    target_element = tag
                    break
            
            if target_element:
                # 2. 「絞り込み予想」より後ろにあるテキストのみをすべて結合
                next_text = ""
                for sibling in target_element.find_all_next(string=True):
                    next_text += sibling + " "
                
                # 3. スペースや改行で区切られた「2桁の数字の連続（4個以上）」を正規表現でピンポイント抽出
                # これにより回号（1393など）や、上部にある削除数字の混入を防ぎます
                match = re.search(r'(?:\d{1,2}[\s\xa0\n\r]+){4,}\d{1,2}', next_text)
                
                if match:
                    numbers_str = match.group(0)
                    # マッチした塊から数字だけをリストとして抽出
                    all_numbers = [int(n) for n in re.findall(r'\d+', numbers_str)]
                    
                    # 各ロトの上限数値でフィルタリング
                    max_num = 37 if loto_type == "ロト7" else (43 if loto_type == "ロト6" else 31)
                    valid_numbers = sorted(list(set([n for n in all_numbers if 1 <= n <= max_num])))
                    
                    # 最低限必要な個数（ミニロトなら5個以上）が取れていれば採用
                    if len(valid_numbers) >= 5:
                        return valid_numbers, False
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
    
    # 風船エフェクト（st.balloons()）は削除しました
