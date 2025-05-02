import streamlit as st
import pandas as pd
import os
import firebase_admin
import qrcode
from PIL import Image
import io
from firebase_admin import credentials, firestore

if "firebase_initialized" not in st.session_state:
    try:
        if not firebase_admin._apps:  # ←✅ 關鍵：只有沒初始化過才做
            cred = credentials.Certificate({
                "type": st.secrets["firebase"]["type"],
                "project_id": st.secrets["firebase"]["project_id"],
                "private_key_id": st.secrets["firebase"]["private_key_id"],
                "private_key": st.secrets["firebase"]["private_key"].replace("\\n", "\n"),
                "client_email": st.secrets["firebase"]["client_email"],
                "client_id": st.secrets["firebase"]["client_id"],
                "auth_uri": st.secrets["firebase"]["auth_uri"],
                "token_uri": st.secrets["firebase"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["firebase"]["auth_provider_x509_cert_url"],
                "client_x509_cert_url": st.secrets["firebase"]["client_x509_cert_url"]
            })
            firebase_admin.initialize_app(cred)

        st.session_state.db = firestore.client()
        st.session_state.firebase_initialized = True
    except Exception as e:
        st.error("❌ Firebase 初始化失敗，請確認 secrets 格式與欄位")
        st.exception(e)
        st.stop()


# --- 初始化資料 ---
CSV_PATH = "players.csv"
COURSE_DB_PATH = "course_db.csv"

if "players" not in st.session_state:
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        st.session_state.players = df["name"].dropna().tolist()
    else:
        st.session_state.players = []

if os.path.exists(COURSE_DB_PATH):
    course_df = pd.read_csv(COURSE_DB_PATH)
else:
    st.error("找不到 course_db.csv！請先準備好球場資料。")
    st.stop()

st.set_page_config(page_title="🏌️ 高爾夫BANK系統", layout="centered")
st.title("🏌️ 高爾夫BANK系統")
if "game_id" in st.session_state and "qr_bytes" in st.session_state:
    st.image(st.session_state.qr_bytes, width=180, caption="賽況查詢")
    st.markdown(f"**🔐 遊戲 ID： `{st.session_state.game_id}`**")
    st.markdown("---")


# --- 根據網址參數，自動切換為查看端模式，並初始化 game_id ---
query_params = st.query_params
if "mode" in query_params and query_params["mode"] == "view":
    st.session_state.mode = "隊員查看端"
    game_id_param = query_params.get("game_id", "")
    if isinstance(game_id_param, list):
        game_id_param = game_id_param[0]
    st.session_state.game_id = game_id_param

# --- 模式預設為主控端 ---
if "mode" not in st.session_state:
    st.session_state.mode = "主控操作端"
mode = st.session_state.mode

# --- 查看端邏輯：初始化、讀取 Firebase 資料 ---
if mode == "隊員查看端":

    if "firebase_initialized" not in st.session_state:
        st.error("❌ Firebase 尚未初始化")
        st.stop()

    # ✅ 確保 game_id 已設定
    if "game_id" not in st.session_state:
        query_params = st.query_params
        game_id_param = query_params.get("game_id", "")
        if isinstance(game_id_param, list):
            game_id_param = game_id_param[0]
        if not game_id_param:
            st.warning("⚠️ 未帶入 game_id 參數，無法讀取比賽")
            st.stop()
        st.session_state.game_id = game_id_param

    game_id = st.session_state.game_id
    doc_ref = st.session_state.db.collection("golf_games").document(game_id)
    doc = doc_ref.get()

    if not doc.exists:
        st.error(f"❌ Firebase 中找不到比賽 `{game_id}`")
        st.stop()

    game_data = doc.to_dict()

    # ✅ 將資料解包為主程式變數
    players = game_data["players"]
    scores = pd.DataFrame.from_dict(game_data["scores"], orient="index")
    events = pd.DataFrame.from_dict(game_data["events"], orient="index")
    running_points = game_data["points"]
    current_titles = game_data.get("titles", {p: "" for p in players})
    hole_logs = game_data["logs"]
    completed = game_data["completed_holes"]
    selected_course = game_data["course"]
    front_area = game_data["front_area"]
    back_area = game_data["back_area"]
    bet_per_person = game_data["bet_per_person"]
    par = game_data["par"]
    hcp = game_data["hcp"]

if mode == "隊員查看端":    
    if st.button("🔄 重新整理資料"):
        st.rerun()
    st.subheader("📊 總結結果")
    total_bet = bet_per_person * len(players)
    # ✅ 正確的 completed，直接使用 Firebase 中的已完成洞數
    result = pd.DataFrame({
        "總點數": [running_points[p] for p in players],
        "賭金結果": [running_points[p] * total_bet - completed * bet_per_person for p in players],
        "頭銜": [current_titles[p] for p in players]
    }, index=players).sort_values("賭金結果", ascending=False)
    st.dataframe(result)

    st.subheader("📖 洞別說明 Log")
    for line in hole_logs:
        st.text(line)

    st.stop()


    # ✅ 將狀態資料釋出為主程式變數
    players = st.session_state.players
    scores = st.session_state.scores
    events = st.session_state.events
    running_points = st.session_state.running_points
    current_titles = st.session_state.current_titles
    hole_logs = st.session_state.hole_logs
    completed = st.session_state.completed
    selected_course = st.session_state.selected_course
    front_area = st.session_state.front_area
    back_area = st.session_state.back_area
    bet_per_person = st.session_state.bet_per_person
    par = st.session_state.par
    hcp = st.session_state.hcp



# --- 根據網址參數自動切換查看端模式 ---
query_params = st.query_params
if "mode" in query_params and query_params["mode"] == "view":
    st.session_state.mode = "隊員查看端"
    if "game_id" not in st.session_state and "game_id" in query_params:
        st.session_state.game_id = query_params["game_id"]


# --- 模式設定 ---
if "mode" not in st.session_state:
    st.session_state.mode = "主控操作端"
mode = st.session_state.mode

# --- 查看端邏輯：初始化、讀取 Firebase 資料 ---
if mode == "隊員查看端":

    if "firebase_initialized" not in st.session_state:
        st.error("❌ Firebase 尚未初始化")
        st.stop()

    # ✅ 確保 game_id 已設定
    if "game_id" not in st.session_state:
        query_params = st.query_params
        game_id_param = query_params.get("game_id", "")
        if isinstance(game_id_param, list):
            game_id_param = game_id_param[0]
        if not game_id_param:
            st.warning("⚠️ 未帶入 game_id 參數，無法讀取比賽")
            st.stop()
        st.session_state.game_id = game_id_param

    # ✅ 避免重複讀取 Firebase（只讀一次）
    if "game_data_loaded" not in st.session_state:
        game_id = st.session_state.game_id
        doc_ref = st.session_state.db.collection("golf_games").document(game_id)
        doc = doc_ref.get()

        if not doc.exists:
            st.error(f"❌ Firebase 中找不到比賽 `{game_id}`")
            st.stop()

        game_data = doc.to_dict()
        st.session_state.players = game_data["players"]
        st.session_state.scores = pd.DataFrame.from_dict(game_data["scores"], orient="index")
        st.session_state.events = pd.DataFrame.from_dict(game_data["events"], orient="index")
        st.session_state.running_points = game_data["points"]
        st.session_state.current_titles = game_data.get("titles", {p: "" for p in game_data["players"]})
        st.session_state.hole_logs = game_data["logs"]
        st.session_state.completed = game_data["completed_holes"]
        st.session_state.selected_course = game_data["course"]
        st.session_state.front_area = game_data["front_area"]
        st.session_state.back_area = game_data["back_area"]
        st.session_state.bet_per_person = game_data["bet_per_person"]
        st.session_state.par = game_data["par"]
        st.session_state.hcp = game_data["hcp"]

        st.session_state.game_data_loaded = True
        st.success(f"✅ 成功載入比賽 `{game_id}`")
        st.rerun()  # 🔁 強制 rerun 讓資料轉為可用狀態

    # ✅ 將狀態資料釋出為主程式變數
    players = st.session_state.players
    scores = st.session_state.scores
    events = st.session_state.events
    running_points = st.session_state.running_points
    current_titles = st.session_state.current_titles
    hole_logs = st.session_state.hole_logs
    completed = st.session_state.completed
    selected_course = st.session_state.selected_course
    front_area = st.session_state.front_area
    back_area = st.session_state.back_area
    bet_per_person = st.session_state.bet_per_person
    par = st.session_state.par
    hcp = st.session_state.hcp

        
# --- 球場選擇 ---
course_options = course_df["course_name"].unique().tolist()
selected_course = st.selectbox("選擇球場", course_options)

filtered_area = course_df[course_df["course_name"] == selected_course]["area"].unique().tolist()
front_area = st.selectbox("前九洞區域", filtered_area, key="front_area")
back_area = st.selectbox("後九洞區域", filtered_area, key="back_area")

def get_course_info(cname, area):
    temp = course_df[(course_df["course_name"] == cname) & (course_df["area"] == area)]
    temp = temp.sort_values("hole")
    return temp["par"].tolist(), temp["hcp"].tolist()

front_par, front_hcp = get_course_info(selected_course, front_area)
back_par, back_hcp = get_course_info(selected_course, back_area)
par = front_par + back_par
hcp = front_hcp + back_hcp

 # --- 主控端球員管理 ---
if mode == "主控操作端":
    # 狀態初始化
    if "selected_players" not in st.session_state:
        st.session_state.selected_players = []
    
    # 球員選擇組件
    with st.container(border=True):
        st.subheader("球員管理")
        col1, col2 = st.columns([3, 1])
        
        # 球員多選組件
        def update_selection():
            current = st.session_state.player_selector
            if len(current) > 4:
                st.session_state.selected_players = current[:4]
                st.rerun()
            else:
                st.session_state.selected_players = current
        
        players = st.multiselect(
            "選擇參賽球員（最多4位）",
            st.session_state.players,
            default=st.session_state.selected_players,
            key="player_selector",
            on_change=update_selection
        )

    # 新增球員表單
    with st.form("new_player_form", clear_on_submit=True):
        new_name = st.text_input("新增球員名稱", key="new_player_name")
        if st.form_submit_button("確認新增"):
            if not new_name.strip():
                st.warning("⚠️ 名稱不能為空")
            elif new_name in st.session_state.players:
                st.warning(f"⚠️ {new_name} 已存在")
            else:
                # 原子化更新操作
                st.session_state.players.append(new_name)
                pd.DataFrame({"name": st.session_state.players}).to_csv(CSV_PATH, index=False)
                st.success(f"✅ 已新增 {new_name}")
                st.rerun()

    # 球員數量驗證
    if not players:
        st.warning("⚠️ 請選擇至少一位球員")
        st.stop()


handicaps = {p: st.number_input(f"{p} 差點", 0, 54, 0, key=f"hcp_{p}") for p in players}
bet_per_person = st.number_input("單局賭金（每人）", 100, 1000, 100)

# --- 初始化資料結構 ---
scores = pd.DataFrame(index=players, columns=[f"第{i+1}洞" for i in range(18)])
events = pd.DataFrame(index=players, columns=[f"第{i+1}洞" for i in range(18)])
event_opts_display = ["下沙", "下水", "OB", "丟球", "加3或3推", "Par on"]
event_translate = {"下沙": "sand", "下水": "water", "OB": "ob", "丟球": "miss", "加3或3推": "3putt_or_plus3", "Par on": "par_on"}
penalty_keywords = ["sand", "water", "ob", "miss", "3putt_or_plus3"]

running_points = {p: 0 for p in players}
current_titles = {p: "" for p in players}
hole_logs = []
point_bank = 1

from datetime import datetime
import pytz

tz = pytz.timezone("Asia/Taipei")

import qrcode
import io

# ✅ 主控端：產生 game_id、初始化 Firebase、產生 QR Code
if (
    mode == "主控操作端"
    and st.session_state.get("firebase_initialized")
    and st.session_state.get("selected_players")
    and len(st.session_state.selected_players) == 1
    and not st.session_state.get("game_initialized")
):
    # 產生 YYMMDD_XX game_id
    today_str = datetime.now(tz).strftime("%y%m%d")

    games_ref = st.session_state.db.collection("golf_games")
    same_day_docs = games_ref.stream()
    same_day_count = sum(1 for doc in same_day_docs if doc.id.startswith(today_str))
    new_seq = same_day_count + 1
    game_id = f"{today_str}_{new_seq:02d}"
    st.session_state.game_id = game_id

    players = st.session_state.selected_players
    game_data = {
        "created_date": today_str,
        "players": players,
        "scores": {p: {} for p in players},
        "events": {p: {} for p in players},
        "points": {p: 0 for p in players},
        "titles": {p: "" for p in players},
        "logs": [],
        "par": par,
        "hcp": hcp,
        "course": selected_course,
        "front_area": front_area,
        "back_area": back_area,
        "bet_per_person": bet_per_person,
        "completed_holes": 0
    }

    st.session_state.db.collection("golf_games").document(game_id).set(game_data)
    st.session_state.game_initialized = True

    st.success("✅ 賽事資料已寫入 Firebase")
    st.write("🆔 賽事編號：", game_id)

    # 產生 QR code 並顯示
    game_url = f"https://bank-firbase.streamlit.app/?mode=view&game_id={game_id}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=4
    )
    qr.add_data(game_url)
    qr.make(fit=True)

   img = qr.make_image(fill_color="darkgreen", back_color="white")
   img_bytes = io.BytesIO()
   img.save(img_bytes, format="PNG")
   img_bytes.seek(0)

# 儲存至 session_state 供未來使用
st.session_state.qr_bytes = img_bytes


    st.image(img_bytes, width=180, caption="賽況查詢")
    st.markdown(f"**🔐 遊戲 ID： `{game_id}`**")
    st.markdown("---")
    if "game_id" in st.session_state and "qr_bytes" in st.session_state:
        st.image(st.session_state.qr_bytes, width=180, caption="賽況查詢")
        st.markdown(f"**🔐 遊戲 ID： `{st.session_state.game_id}`**")

# --- 主流程 ---
for i in range(18):
    if mode == "隊員查看端" and not (f"confirm_{i}" in st.session_state and st.session_state[f"confirm_{i}"]):
        continue

    st.subheader(f"第{i+1}洞 (Par {par[i]} / HCP {hcp[i]})")
    title_row = "｜".join(f"{p}：{current_titles[p] or '無'}" for p in players)
    st.markdown(f"🎖️ 本洞頭銜：{title_row}")

    if mode == "主控操作端":
        cols = st.columns(len(players))
        for j, p in enumerate(players):
            with cols[j]:
                if current_titles[p] == "SuperRich":
                    st.markdown("👑 **Super Rich Man**")
                elif current_titles[p] == "Rich":
                    st.markdown("🏆 **Rich Man**")
                scores.loc[p, f"第{i+1}洞"] = st.number_input(f"{p} 桿數（{running_points[p]} 點）", 1, 15, par[i], key=f"score_{p}_{i}")
                selected_display = st.multiselect(f"{p} 事件", event_opts_display, key=f"event_{p}_{i}")
                selected_internal = [event_translate[d] for d in selected_display]
                events.loc[p, f"第{i+1}洞"] = selected_internal

        confirmed = st.checkbox(f"✅ 確認第{i+1}洞成績", key=f"confirm_{i}")
        if not confirmed:
          continue  # ❌ 錯誤：不在迴圈內，會出現 SyntaxError


    if f"confirm_{i}" in st.session_state and st.session_state[f"confirm_{i}"]:
        raw = scores[f"第{i+1}洞"]
        evt = events[f"第{i+1}洞"]
        start_of_hole_bank = point_bank

    # ✅ 扣點處理
        event_penalties = {p: 0 for p in players}
        penalty_pool = 0
        for p in players:
            acts = evt[p] if isinstance(evt[p], list) else []
            pen = 0
            if current_titles[p] in ["Rich", "SuperRich"]:
                pen = sum(1 for act in acts if act in penalty_keywords)
                if current_titles[p] == "SuperRich" and "par_on" in acts:
                    pen += 1
                pen = min(pen, 3)
            running_points[p] -= pen
            penalty_pool += pen
            event_penalties[p] = pen

    # ✅ 勝負判定
    victory_map = {}
    for p1 in players:
        p1_wins = 0
        for p2 in players:
            if p1 == p2:
                continue
            adj_p1, adj_p2 = raw[p1], raw[p2]
            diff = handicaps[p1] - handicaps[p2]
            if diff > 0 and hcp[i] <= diff:
                adj_p1 -= 1
            elif diff < 0 and hcp[i] <= -diff:
                adj_p2 -= 1
            if adj_p1 < adj_p2:
                p1_wins += 1
        victory_map[p1] = p1_wins

    winners = [p for p in players if victory_map[p] == len(players) - 1]
    penalty_info = [f"{p} 扣 {event_penalties[p]}點" for p in players if event_penalties[p] > 0]
    penalty_summary = "｜".join(penalty_info) if penalty_info else ""

    # ✅ 單一勝者處理
    if len(winners) == 1:
        w = winners[0]
        is_birdy = raw[w] <= par[i] - 1
        gain_points = point_bank + penalty_pool

        # ✅ Birdie 額外加分處理
        birdie_bonus = 0
        if is_birdy:
            for p in players:
                if p != w and running_points[p] > 0:
                    running_points[p] -= 1
                    birdie_bonus += 1
            gain_points += birdie_bonus

        running_points[w] += gain_points
        bird_icon = " 🐦" if is_birdy else ""
        extra_info = f"（取得+{gain_points}點）"
        if penalty_summary:
            extra_info += f"｜{penalty_summary}"
        if is_birdy and birdie_bonus > 0:
            extra_info += f"｜Birdie 奪得 {birdie_bonus}點"
        hole_log = f"🏆 第{i+1}洞勝者：{w}{bird_icon}{extra_info}"
        point_bank = 1
    else:
        # ✅ 平手：累積 bank 點
        add_this_hole = 1 + penalty_pool
        point_bank += add_this_hole
        hole_log = f"⚖️ 第{i+1}洞平手"
        if penalty_summary:
            hole_log += f"｜{penalty_summary}"
        hole_log += f"（下洞累積 {point_bank}點）"

    st.markdown(hole_log)
    hole_logs.append(hole_log)

# ✅ 頭銜更新（建議改寫成不使用 elif，避免語法錯）
for p in players:
    if current_titles[p] == "Super Rich Man" and running_points[p] <= 4:
       current_titles[p] = "Rich Man"

    if current_titles[p] == "Rich Man" and running_points[p] == 0:
       current_titles[p] = ""

    if current_titles[p] == "" and running_points[p] >= 8:
       current_titles[p] = "Super Rich Man"

    if current_titles[p] == "" and 4 <= running_points[p] < 8:
       current_titles[p] = "Rich Man"

    # ✅ Firebase 更新
    completed = len([k for k in range(18) if st.session_state.get(f"confirm_{k}", False)])
    game_data = {
        "players": players,
        "scores": scores.to_dict(),
        "events": events.to_dict(),
        "points": running_points,
        "titles": current_titles,
        "logs": hole_logs,
        "par": par,
        "hcp": hcp,
        "course": selected_course,
        "front_area": front_area,
        "back_area": back_area,
        "bet_per_person": bet_per_person,
        "completed_holes": completed
    }
    st.session_state.db.collection("golf_games").document(st.session_state.game_id).set(game_data)

# --- 總結結果（主控端顯示） ---
if mode == "主控操作端":
    st.subheader("📊 總結結果")
    total_bet = bet_per_person * len(players)
    completed = len([i for i in range(18) if st.session_state.get(f"confirm_{i}", False)])
    result = pd.DataFrame({
        "總點數": [running_points[p] for p in players],
        "賭金結果": [running_points[p] * total_bet - completed * bet_per_person for p in players],
        "頭銜": [current_titles[p] for p in players]
    }, index=players).sort_values("賭金結果", ascending=False)
    st.dataframe(result)

# --- 自動刷新控制（僅隊員端）---
if mode == "隊員查看端":
    st.experimental_rerun(interval=10)  # 每10秒自動刷新

# --- 洞別日誌顯示 ---
st.subheader("📖 洞別說明 Log")
for line in hole_logs:
    st.text(line)

