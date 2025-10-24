# =================== 必須最先呼叫 ===================
import streamlit as st
st.set_page_config(page_title="🏌️ 高爾夫BANK v3.5", layout="centered")

# =================== Imports ===================
import os
import io
from datetime import datetime
import pandas as pd
import pytz
import qrcode
from PIL import Image

import firebase_admin
from firebase_admin import credentials, firestore, initialize_app, get_app

# =================== Firebase 初始化（單例 / 安全） ===================
REQUIRED_KEYS = [
    "type", "project_id", "private_key_id", "private_key",
    "client_email", "client_id", "token_uri"
]

@st.cache_resource(show_spinner=False)
def init_firebase():
    if "firebase" not in st.secrets:
        st.error("❌ 找不到 [firebase] secrets。請在 .streamlit/secrets.toml 或雲端 Secrets 新增。")
        st.stop()

    cfg = dict(st.secrets["firebase"])
    missing = [k for k in REQUIRED_KEYS if k not in cfg or not cfg[k]]
    if missing:
        st.error(f"❌ [firebase] 缺少欄位：{', '.join(missing)}")
        st.stop()

    # 修正 private_key 的 \n
    if "\\n" in cfg["private_key"]:
        cfg["private_key"] = cfg["private_key"].replace("\\n", "\n")

    # 單例 App
    try:
        app = get_app()
    except ValueError:
        cred = credentials.Certificate(cfg)
        app = initialize_app(cred)

    db = firestore.client(app=app)
    return db

db = init_firebase()
st.session_state.db = db
st.session_state.firebase_initialized = True

# =================== 讀取 CSV（球場與球員） ===================
CSV_PATH = "players.csv"
COURSE_DB_PATH = "course_db.csv"

if not os.path.exists(COURSE_DB_PATH):
    st.error("找不到 course_db.csv！請先準備好球場資料。")
    st.stop()
course_df = pd.read_csv(COURSE_DB_PATH)

if "players" not in st.session_state:
    if os.path.exists(CSV_PATH):
        df_players = pd.read_csv(CSV_PATH)
        st.session_state.players = df_players["name"].dropna().tolist()
    else:
        st.session_state.players = []

# =================== URL 參數 & 模式切換 ===================
params = st.query_params
if params.get("mode") == "view":
    st.session_state.mode = "隊員查看端"
    gid = params.get("game_id", "")
    if isinstance(gid, list):
        gid = gid[0]
    if gid:
        st.session_state.game_id = gid

if "mode" not in st.session_state:
    st.session_state.mode = "主控操作端"
mode = st.session_state.mode

# =================== 共用：球場選擇（供建立賽事寫入） ===================
st.title("🏌️ 高爾夫BANK v3.5")

course_options = course_df["course_name"].unique().tolist()
selected_course = st.selectbox("選擇球場", course_options)

def get_area_options(cname):
    return course_df[course_df["course_name"] == cname]["area"].unique().tolist()

filtered_area = get_area_options(selected_course)
front_area = st.selectbox("前九洞區域", filtered_area, key="front_area")
back_area  = st.selectbox("後九洞區域", filtered_area, key="back_area")

def get_course_info(cname, area):
    temp = course_df[(course_df["course_name"] == cname) & (course_df["area"] == area)].sort_values("hole")
    return temp["par"].tolist(), temp["hcp"].tolist()

front_par, front_hcp = get_course_info(selected_course, front_area)
back_par,  back_hcp  = get_course_info(selected_course, back_area)
par = front_par + back_par
hcp = front_hcp + back_hcp

# =================== 若已有 QR / ID 就顯示 ===================
if "game_id" in st.session_state and "qr_bytes" in st.session_state:
    st.image(st.session_state.qr_bytes, width=180, caption="賽況查詢")
    st.markdown(f"**🔐 遊戲 ID： `{st.session_state.game_id}`**")
    st.markdown("---")

# =================== 隊員查看端 ===================
if mode == "隊員查看端":
    from streamlit_autorefresh import st_autorefresh

    if "firebase_initialized" not in st.session_state:
        st.error("❌ Firebase 尚未初始化")
        st.stop()

    if "game_id" not in st.session_state or not st.session_state.game_id:
        st.warning("⚠️ 未帶入 game_id 參數，無法讀取比賽")
        st.stop()

    # 每次刷新都重新拉資料，結合 autorefresh 可即時看到更新
    game_id = st.session_state.game_id
    doc = db.collection("golf_games").document(game_id).get()
    if not doc.exists:
        st.error(f"❌ Firebase 中找不到比賽 `{game_id}`")
        st.stop()

    game_data = doc.to_dict()
    players         = game_data["players"]
    running_points  = game_data["points"]
    current_titles  = game_data.get("titles", {p: "" for p in players})
    hole_logs       = game_data["logs"]
    completed       = game_data["completed_holes"]
    bet_per_person  = game_data["bet_per_person"]

    st.markdown(f"🏷️ **比賽 ID**： `{game_id}`")
    st.markdown(f"💰 **每局賭金**： `{bet_per_person}`")
    st.markdown(" / ".join(players))
    st.markdown("---")

    st.subheader("📊 總結結果")
    total_bet = bet_per_person * len(players)
    result = pd.DataFrame({
        "總點數": [running_points[p] for p in players],
        "結果": [running_points[p] * total_bet - completed * bet_per_person for p in players],
        "頭銜": [current_titles[p] for p in players]
    }, index=players).sort_values("結果", ascending=False)
    st.dataframe(result, use_container_width=True)

    st.subheader("📖 Event Log")
    for line in hole_logs:
        st.text(line)

    # 自動刷新（每 10 秒）
    st_autorefresh(interval=10000, key="view_autorefresh")
    st.stop()

# =================== 主控操作端：球員/差點/賭金 ===================
players_all = st.session_state.players
if "selected_players" not in st.session_state:
    st.session_state.selected_players = []

with st.container(border=True):
    st.subheader("球員管理")
    def update_selection():
        current = st.session_state.player_selector
        st.session_state.selected_players = current[:4]  # 最多 4 位
    players = st.multiselect(
        "選擇參賽球員（最多4位）",
        players_all,
        default=st.session_state.selected_players,
        key="player_selector",
        on_change=update_selection
    )

if not players:
    st.warning("⚠️ 請選擇至少一位球員")
    st.stop()

# 差點/賭金
handicaps = {p: st.number_input(f"{p} 差點", 0, 54, 0, key=f"hcp_{p}") for p in players}
bet_per_person = st.number_input("單局賭金（每人）", 100, 1000, 100)

# =================== 建賽：game_id / 寫入 Firebase / 產生 QR ===================
from datetime import timezone
tz = pytz.timezone("Asia/Taipei")
if (
    mode == "主控操作端"
    and st.session_state.get("firebase_initialized")
    and players
    and 2 <= len(players) <= 4   # 至少兩人
    and not st.session_state.get("game_initialized")
):
    today_str = datetime.now(tz).strftime("%y%m%d")
    games_ref = db.collection("golf_games")
    same_day_count = sum(1 for doc in games_ref.stream() if doc.id.startswith(today_str))
    game_id = f"{today_str}_{same_day_count + 1:02d}"
    st.session_state.game_id = game_id

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
    db.collection("golf_games").document(game_id).set(game_data)
    st.session_state.game_initialized = True

    st.success("✅ 賽事資料已寫入 Firebase")
    st.write("🆔 賽事編號：", game_id)

    # 產生 QR code（請確認你的正式 App 網址）
    game_url = f"https://bank-firbase.streamlit.app/?mode=view&game_id={game_id}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=4)
    qr.add_data(game_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="darkgreen", back_color="white")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    st.session_state.qr_bytes = img_bytes

    st.image(img_bytes, width=180, caption="賽況查詢")
    st.markdown(f"**🔐 遊戲 ID： `{game_id}`**")
    st.markdown("---")

# =================== 初始化逐洞 DataFrame / 狀態 ===================
# 分數 / 事件表（存活於 session_state）
if "scores_df" not in st.session_state or set(st.session_state.get("scores_df", pd.DataFrame()).index) != set(players):
    st.session_state.scores_df = pd.DataFrame(index=players, columns=[f"第{i+1}洞" for i in range(18)])

if "events_df" not in st.session_state or set(st.session_state.get("events_df", pd.DataFrame()).index) != set(players):
    st.session_state.events_df = pd.DataFrame(index=players, columns=[f"第{i+1}洞" for i in range(18)])

if "running_points" not in st.session_state or set(st.session_state.get("running_points", {}).keys()) != set(players):
    st.session_state.running_points = {p: 0 for p in players}

if "current_titles" not in st.session_state or set(st.session_state.get("current_titles", {}).keys()) != set(players):
    st.session_state.current_titles = {p: "" for p in players}

if "hole_logs" not in st.session_state:
    st.session_state.hole_logs = []

if "point_bank" not in st.session_state:
    st.session_state.point_bank = 1

scores = st.session_state.scores_df
events = st.session_state.events_df
running_points = st.session_state.running_points
current_titles = st.session_state.current_titles
hole_logs = st.session_state.hole_logs
point_bank = st.session_state.point_bank

# 事件定義
event_opts_display = ["下沙", "下水", "OB", "丟球", "加3或3推", "Par on"]
event_translate = {
    "下沙": "sand",
    "下水": "water",
    "OB": "ob",
    "丟球": "miss",
    "加3或3推": "3putt_or_plus3",
    "Par on": "par_on"
}
penalty_keywords = {"sand", "water", "ob", "miss", "3putt_or_plus3"}

# =================== 逐洞主流程 ===================
st.markdown("---")
st.subheader("🕳️ 逐洞輸入與結算")

for i in range(18):
    st.markdown(f"### 第{i+1}洞 (Par {par[i]} / HCP {hcp[i]})")

    cols = st.columns(len(players))
    # 畫面輸入（以目前頭銜/點數為提示）
    for j, p in enumerate(players):
        with cols[j]:
            if current_titles.get(p) == "Super Rich Man":
                st.markdown("👑 **Super Rich Man**")
            elif current_titles.get(p) == "Rich Man":
                st.markdown("🏆 **Rich Man**")
            default_score = par[i] if pd.isna(scores.loc[p, f"第{i+1}洞"]) else int(scores.loc[p, f"第{i+1}洞"])
            scores.loc[p, f"第{i+1}洞"] = st.number_input(f"{p} 桿數（目前 {running_points[p]} 點）",
                                                           min_value=1, max_value=15, value=default_score,
                                                           key=f"score_{p}_{i}")
            selected_display = st.multiselect(f"{p} 事件", event_opts_display, default=[],
                                              key=f"event_{p}_{i}")
            selected_internal = [event_translate[d] for d in selected_display]
            events.loc[p, f"第{i+1}洞"] = selected_internal

    confirmed = st.checkbox(f"✅ 確認第{i+1}洞成績", key=f"confirm_{i}")
    if not confirmed:
        st.markdown("---")
        continue

    # ======== 結算邏輯 ========
    raw = scores[f"第{i+1}洞"]
    evt = events[f"第{i+1}洞"]

    # 1) 一對一勝負（讓桿以 HCP 門檻套用於差點低者讓差點高者）
    victory_map = {}
    for p1 in players:
        p1_wins = 0
        for p2 in players:
            if p1 == p2:
                continue
            adj_p1, adj_p2 = raw[p1], raw[p2]
            diff = handicaps[p1] - handicaps[p2]
            # 差點高者獲得在 HCP<=差值 的洞數之讓桿（逐洞比較）
            if diff > 0 and hcp[i] <= diff:      # p1 差點較高 → p1 得到讓桿
                adj_p1 -= 1
            elif diff < 0 and hcp[i] <= -diff:   # p2 差點較高 → p2 得到讓桿
                adj_p2 -= 1
            if adj_p1 < adj_p2:
                p1_wins += 1
        victory_map[p1] = p1_wins

    winners = [p for p in players if victory_map[p] == len(players) - 1]

    # 2) 事件扣點（針對 Rich / Super Rich）
    penalty_pool = 0
    event_penalties_actual = {}
    for p in players:
        acts = evt[p] if isinstance(evt[p], list) else []
        pen = 0
        if current_titles[p] in ["Rich Man", "Super Rich Man"]:
            pen = sum(1 for act in acts if act in penalty_keywords)
            if current_titles[p] == "Super Rich Man" and "par_on" in acts:
                pen += 1
            pen = min(pen, 3)
        actual_penalty = min(pen, running_points[p])  # 不能扣成負數
        running_points[p] -= actual_penalty
        penalty_pool += actual_penalty
        event_penalties_actual[p] = actual_penalty

    # 3) 計分池與 Birdie
    gain_points = point_bank + penalty_pool
    birdie_bonus = 0

    if len(winners) == 1:
        w = winners[0]
        is_birdie = raw[w] <= par[i] - 1
        if is_birdie:
            for p in players:
                if p != w and running_points[p] > 0:
                    running_points[p] -= 1
                    birdie_bonus += 1
            gain_points += birdie_bonus
        running_points[w] += gain_points
        point_bank = 1
    else:
        # 平手時只累積 1 點；事件扣點不進入 bank（避免膨脹）
        point_bank += 1

    # 4) 計算新頭銜（下一洞生效）
    next_titles = current_titles.copy()
    for p in players:
        pt = running_points[p]
        cur = current_titles.get(p, "")

        if cur == "":
            if pt >= 8:
                next_titles[p] = "Super Rich Man"
            elif pt >= 4:
                next_titles[p] = "Rich Man"
            else:
                next_titles[p] = ""
        elif cur == "Rich Man":
            # 記憶規則：Rich 直到回到 0 才取消
            if pt >= 8:
                next_titles[p] = "Super Rich Man"
            elif pt == 0:
                next_titles[p] = ""
            else:
                next_titles[p] = "Rich Man"
        elif cur == "Super Rich Man":
            # 記憶規則：Super Rich 直到 <4 才降回 Rich
            if pt < 4:
                next_titles[p] = "Rich Man"
            else:
                next_titles[p] = "Super Rich Man"

    # 5) Log
    penalty_info = [f"{p} 扣 {event_penalties_actual[p]}點" for p in players if event_penalties_actual[p] > 0]
    penalty_summary = "｜".join(penalty_info) if penalty_info else ""

    if len(winners) == 1:
        bird_icon = " 🐦" if is_birdie else ""
        hole_log = f"🏆 第{i+1}洞勝者：{w}{bird_icon}（+{gain_points}點）"
        if penalty_summary:
            hole_log += f"｜{penalty_summary}"
        if birdie_bonus:
            hole_log += f"｜Birdie 奪得 {birdie_bonus}點"
    else:
        hole_log = f"⚖️ 第{i+1}洞平手（下洞累積 {point_bank}點）"
        if penalty_summary:
            hole_log += f"｜{penalty_summary}"

    if hole_log not in hole_logs:
        hole_logs.append(hole_log)
    st.markdown(hole_log)
    st.markdown("---")

    # 6) 寫回 session 與 Firebase
    current_titles = next_titles
    st.session_state.current_titles = current_titles
    st.session_state.running_points = running_points
    st.session_state.hole_logs = hole_logs
    st.session_state.point_bank = point_bank
    completed = len([k for k in range(18) if st.session_state.get(f"confirm_{k}", False)])

    game_data_update = {
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
    db.collection("golf_games").document(st.session_state.game_id).set(game_data_update)

# =================== 主控端：總結 ===================
st.subheader("📊 總結結果（主控端）")
total_bet = bet_per_person * len(players)
completed = len([i for i in range(18) if st.session_state.get(f"confirm_{i}", False)])
summary_df = pd.DataFrame({
    "總點數": [running_points[p] for p in players],
    "結果": [running_points[p] * total_bet - completed * bet_per_person for p in players],
    "頭銜": [current_titles[p] for p in players]
}, index=players).sort_values("結果", ascending=False)
st.dataframe(summary_df, use_container_width=True)

st.subheader("📖 Event Log")
for line in hole_logs:
    st.text(line)
