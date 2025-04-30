# 產出乾淨完整的 app.py（Firebase Firestore 版本）
firebase_app_code = """
import streamlit as st
import pandas as pd
import json
import qrcode
from io import BytesIO
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

BASE_URL = "https://bank-firbase.streamlit.app/"  # 修改為你的部署網址

st.set_page_config(page_title="🏌️ Golf BANK v3.3", layout="wide")
st.title("🏌️ Golf BANK 系統")

@st.cache_resource
def init_firebase():
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()

def save_game_to_firebase(game_data, game_id):
    db.collection("games").document(game_id).set(game_data)

def load_game_from_firebase(game_id):
    doc = db.collection("games").document(game_id).get()
    return doc.to_dict() if doc.exists else None

query_params = st.experimental_get_query_params()
if "game_id" in query_params and not st.session_state.get("mode_initialized"):
    st.session_state.mode = "查看端介面"
    st.session_state.current_game_id = query_params["game_id"][0]
    st.session_state.mode_initialized = True
    st.experimental_rerun()

if "mode" not in st.session_state:
    st.session_state.mode = "選擇參賽球員"
if "current_game_id" not in st.session_state:
    st.session_state.current_game_id = ""

@st.cache_data
def load_course_db():
    return pd.read_csv("course_db.csv")

@st.cache_data
def load_players():
    df = pd.read_csv("players.csv")
    return df["name"].dropna().tolist()

course_df = load_course_db()
all_players = load_players()
mode = st.session_state.mode

if mode == "選擇參賽球員":
    st.header("👥 選擇參賽球員（最多4位）")
    player_names = st.multiselect("選擇球員", all_players, key="player_select")
    if len(player_names) > 4:
        st.error("⚠️ 最多只能選擇4位球員參賽")
    elif len(player_names) == 4:
        st.success("✅ 已選擇4位球員")
        st.session_state.selected_players = player_names
        st.session_state.mode = "設定比賽資料"
        st.experimental_rerun()

elif mode == "設定比賽資料":
    st.header("📋 比賽設定")

    player_names = st.session_state.selected_players
    handicaps = {p: st.number_input(f"{p} 差點", 0, 54, 0, key=f"hdcp_{p}") for p in player_names}

    selected_course = st.selectbox("選擇球場名稱", course_df["course_name"].unique())
    areas_df = course_df[course_df["course_name"] == selected_course]
    valid_areas = (
        areas_df.groupby("area")
        .filter(lambda df: len(df) == 9)["area"]
        .unique()
    )

    area_front9 = st.selectbox("前九洞區域", valid_areas, key="front9")
    area_back9 = st.selectbox("後九洞區域", valid_areas, key="back9")

    front9 = areas_df[areas_df["area"] == area_front9].sort_values("hole")
    back9 = areas_df[areas_df["area"] == area_back9].sort_values("hole")

    if len(front9) != 9 or len(back9) != 9:
        st.error("⚠️ 選擇的區域不是完整9洞，請確認資料正確")
        st.stop()

    par = front9["par"].tolist() + back9["par"].tolist()
    hcp = front9["hcp"].tolist() + back9["hcp"].tolist()
    bet_per_person = st.number_input("單人賭金", 10, 1000, 100)

    def generate_game_id():
        today_str = datetime.now().strftime("%Y%m%d")
        existing = db.collection("games").where("game_id", ">=", today_str).stream()
        count = sum(1 for _ in existing)
        return f"{today_str}_{str(count + 1).zfill(2)}"

    if st.button("✅ 開始球局"):
        game_id = generate_game_id()
        game_data = {
            "game_id": game_id,
            "players": player_names,
            "handicaps": handicaps,
            "par": par,
            "hcp": hcp,
            "bet_per_person": bet_per_person,
            "scores": {p: {} for p in player_names},
            "events": {},
            "running_points": {p: 0 for p in player_names},
            "current_titles": {p: "" for p in player_names},
            "hole_logs": [],
            "completed": 0
        }
        save_game_to_firebase(game_data, game_id)
        st.session_state.current_game_id = game_id
        st.session_state.mode = "主控端成績輸入"
        st.experimental_rerun()

elif mode == "主控端成績輸入":
    game_id = st.session_state.current_game_id
    game_data = load_game_from_firebase(game_id)

    if not game_data:
        st.error("⚠️ 找不到該比賽資料")
        st.stop()

    col_left, col_right = st.columns([0.75, 0.25])
    with col_left:
        st.header("⛳ 主控端輸入介面")
    with col_right:
        qr_url = f"{BASE_URL}?game_id={game_id}"
        img = qrcode.make(qr_url)
        buf = BytesIO()
        img.save(buf)
        st.image(buf.getvalue(), use_container_width=True)

    players = game_data["players"]
    par_list = game_data["par"]
    hcp_list = game_data["hcp"]
    hdcp = game_data["handicaps"]

    for hole in range(18):
        par = par_list[hole]
        hcp = hcp_list[hole]
        st.markdown(f"### 第 {hole + 1} 洞 (Par {par} / HCP {hcp})")

        cols = st.columns(len(players))
        scores = {}
        for idx, p in enumerate(players):
            with cols[idx]:
                st.markdown(f"**{p} 押數（{game_data['running_points'].get(p, 0)} 點）**")
                default_score = game_data["scores"].get(p, {}).get(str(hole), par)
                scores[p] = st.number_input(
                    f"{p}", 1, 15, value=default_score, key=f"score_{p}_{hole}_input"
                )

        confirmed_key = f"hole_{hole}_confirmed"
        if confirmed_key not in st.session_state:
            st.session_state[confirmed_key] = hole < game_data["completed"]

        if not st.session_state[confirmed_key]:
            if st.button(f"✅ 確認第 {hole + 1} 洞成績", key=f"confirm_btn_{hole}"):
                scores_raw = {p: scores[p] for p in players}
                adjusted_scores = {}
                for p in players:
                    total_adjust = 0
                    for q in players:
                        if p == q:
                            continue
                        diff = hdcp[q] - hdcp[p]
                        if diff > 0 and hcp <= diff:
                            total_adjust += 1
                    adjusted_scores[p] = scores[p] - total_adjust

                victory_map = {}
                for p in players:
                    wins = 0
                    for q in players:
                        if p == q:
                            continue
                        if adjusted_scores[p] < adjusted_scores[q]:
                            wins += 1
                    victory_map[p] = wins

                winners = [p for p in players if victory_map[p] == len(players) - 1]
                log = f"Hole {hole + 1}: "

                if len(winners) == 1:
                    winner = winners[0]
                    is_birdy = scores_raw[winner] <= (par - 1)
                    birdy_bonus = 1 if is_birdy else 0
                    game_data["running_points"][winner] += 1 + birdy_bonus
                    for p in players:
                        if p != winner and game_data["running_points"][p] > 0:
                            game_data["running_points"][p] -= 1
                    log += f"🏆 {winner} 勝出 {'🐦' if is_birdy else ''}"
                else:
                    log += "⚖️ 平手"

                for p in players:
                    game_data["scores"].setdefault(p, {})[str(hole)] = scores[p]

                game_data["hole_logs"].append(log)
                game_data["completed"] = max(game_data["completed"], hole + 1)

                for p in players:
                    pt = game_data["running_points"][p]
                    if pt >= 4:
                        game_data["current_titles"][p] = "Super Rich"
                    elif pt > 0:
                        game_data["current_titles"][p] = "Rich"
                    else:
                        game_data["current_titles"][p] = ""

                save_game_to_firebase(game_data, game_id)
                st.session_state[confirmed_key] = True
                st.experimental_rerun()
        else:
            last_log = game_data["hole_logs"][hole] if hole < len(game_data["hole_logs"]) else "✅ 已確認"
            st.markdown(f"📝 {last_log}")
        st.divider()

    if game_data["completed"] >= 18:
        st.success("🏁 比賽已完成！")
"""

with open("/mnt/data/app_firebase.py", "w") as f:
    f.write(firebase_app_code)

"/mnt/data/app_firebase.py"
