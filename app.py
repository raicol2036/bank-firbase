import streamlit as st
st.set_page_config(page_title="🏌️高爾夫BANKv1.3.5", layout="centered")

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

# =================== Firebase 初始化（單例 + 防呆） ===================
REQUIRED_KEYS = [
    "type", "project_id", "private_key_id", "private_key",
    "client_email", "client_id", "token_uri"
]

@st.cache_resource(show_spinner=False)
def init_firebase():
    """初始化並回傳 Firestore client（失敗會直接 st.stop）。"""
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

    db_client = firestore.client(app=app)
    return db_client

# 若 db 不存在或型別不對就重新初始化（避免 AttributeError）
if "db" not in st.session_state or not hasattr(st.session_state.get("db", None), "collection"):
    st.session_state.db = init_firebase()

db = st.session_state.db
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

st.title("🏌️高爾夫BANK v1.3.5")

# =================== 共用：球場選擇（主控端） ===================
if mode == "主控操作端":

    course_options = course_df["course_name"].unique().tolist()
    selected_course = st.selectbox("選擇球場", course_options)

    def get_area_options(cname):
        return course_df[course_df["course_name"] == cname]["area"].unique().tolist()

    filtered_area = get_area_options(selected_course)
    front_area = st.selectbox("前九洞區域", filtered_area, key="front_area")
    back_area  = st.selectbox("後九洞區域", filtered_area, key="back_area")

    def get_course_info(cname, area):
        temp = course_df[
            (course_df["course_name"] == cname) &
            (course_df["area"] == area)
        ].sort_values("hole")
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

    if "db" not in st.session_state or not hasattr(st.session_state.db, "collection"):
        st.error("⚠️ Firebase 連線失效，請重新整理頁面後再試。")
        st.stop()

    if "game_id" not in st.session_state or not st.session_state.game_id:
        st.warning("⚠️ 未帶入 game_id 參數，無法讀取比賽")
        st.stop()

    db = st.session_state.db
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
    completed       = game_data.get("completed_holes", 0)

    bank_bet  = game_data.get("bank_bet_per_person", game_data.get("bet_per_person", 0))
    hole_bet  = game_data.get("hole_bet_per_person", 0)
    enable_hole_bet = hole_bet > 0

    hole_points = game_data.get("hole_points", {p: 0 for p in players})
    cash_result = {}
    if enable_hole_bet:
        total_pts = sum(hole_points.values())
        n = len(players)
        for p in players:
            cash_result[p] = (n * hole_points[p] - total_pts) * hole_bet
    else:
        cash_result = {p: 0 for p in players}

    course      = game_data.get("course", "")
    front_area  = game_data.get("front_area", "")
    back_area   = game_data.get("back_area", "")

    st.markdown("### 📝 比賽資訊")
    st.markdown(f"**比賽球場**　{course}")
    st.markdown(f"**前九洞區域**　{front_area}")
    st.markdown(f"**後九洞區域**　{back_area}")
    st.markdown("")
    st.markdown(f"🧾 **比賽 ID ：** ` {game_id} `")
    st.markdown(f"💰 **BANK 賭金（每人） ：** `{bank_bet}`")
    st.markdown(f"💰 **逐洞賭金（每人） ：** `{hole_bet}`")
    st.markdown("")
    st.markdown("👥 **球員：** " + " / ".join(players))
    st.markdown("---")

    st.subheader("📊 總結結果")

    num_players = len(players)
    result_dict = {
        "BANK點數": [running_points[p] for p in players],
        "BANK結果": [
            ((running_points[p] * num_players) - 18) * bank_bet
            for p in players
        ],
        "頭銜": [current_titles[p] for p in players]
    }
    if enable_hole_bet:
        result_dict["逐洞點數"] = [hole_points[p] for p in players]
        result_dict["逐洞結果"] = [cash_result[p] for p in players]

    sort_col = "逐洞結果" if enable_hole_bet else "BANK結果"
    result = pd.DataFrame(result_dict, index=players).sort_values(sort_col, ascending=False)
    st.dataframe(result, use_container_width=True)

    st.subheader("📖 Event Log")
    if not hole_logs:
        st.info("目前沒有任何紀錄")
    else:
        for line in hole_logs:
            st.write(line)

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
        st.session_state.selected_players = current[:4]
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

handicaps = {p: st.number_input(f"{p} 差點", 0, 54, 0, key=f"hcp_{p}") for p in players}

col_b1, col_b2 = st.columns(2)
with col_b1:
    bank_bet = st.number_input(
        "單局賭金（每人） BANK",
        min_value=0,
        max_value=20000,
        value=100,
        step=50,
        format="%d"
    )
with col_b2:
    hole_bet = st.number_input(
        "單局賭金（每人） 逐洞",
        min_value=0,
        max_value=20000,
        value=0,
        step=50,
        format="%d"
    )

enable_hole_bet = hole_bet > 0

MAX_PLAYERS = 4
MIN_PLAYERS = 2

st.info(f"目前已選 {len(players)}/{MAX_PLAYERS} 位（最多 {MAX_PLAYERS} 位）")

col_a, col_b = st.columns(2)
with col_a:
    start_btn = st.button("🚀 建立賽事（手動）", type="primary", use_container_width=True)
with col_b:
    reset_btn = st.button("🔄 重設賽事（清除本機狀態）", use_container_width=True)

if reset_btn:
    for k in [
        "game_initialized", "game_id", "qr_bytes", "scores_df", "events_df",
        "running_points", "current_titles", "hole_logs", "point_bank",
        "confirmed_holes", "current_hole", "hole_points"
    ]:
        if k in st.session_state:
            del st.session_state[k]
    st.success("已重設本機賽事狀態，請重新選人並按『建立賽事』。")
    st.stop()

if start_btn:
    if len(players) < MIN_PLAYERS:
        st.error(f"至少需要 {MIN_PLAYERS} 位球員才可建立賽事。")
        st.stop()
    if len(players) > MAX_PLAYERS:
        st.error(f"最多僅能選擇 {MAX_PLAYERS} 位球員。")
        st.stop()
    if "db" not in st.session_state or not hasattr(st.session_state.db, "collection"):
        st.error("❌ Firebase 尚未初始化或連線失效")
        st.stop()
    if st.session_state.get("game_initialized"):
        st.warning("本機已存在賽事，如需重建請先點『重設賽事』。")
        st.stop()

    tz = pytz.timezone("Asia/Taipei")
    today_str = datetime.now(tz).strftime("%y%m%d")
    db = st.session_state.db
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
        "bet_per_person": bank_bet,
        "bank_bet_per_person": bank_bet,
        "hole_bet_per_person": hole_bet,
        "completed_holes": 0,
        "hole_points": {p: 0 for p in players},
    }
    db.collection("golf_games").document(game_id).set(game_data)
    st.session_state.game_initialized = True

    st.success("✅ 賽事資料已寫入 Firebase")
    st.write("🆔 賽事編號：", game_id)

    game_url = f"https://bankver13.streamlit.app/?mode=view&game_id={game_id}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=4)
    qr.add_data(game_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="darkgreen", back_color="white")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    st.session_state.qr_bytes = img_bytes

    st.image(img_bytes, width=180, caption="賽況查詢（掃碼免登入）")
    st.markdown(f"**🔐 遊戲 ID： `{game_id}`**")
    st.markdown("---")

# =================== 初始化逐洞資料與狀態 ===================
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

if "confirmed_holes" not in st.session_state:
    st.session_state.confirmed_holes = [False] * 18

if "current_hole" not in st.session_state:
    st.session_state.current_hole = 0

if "hole_points" not in st.session_state or set(st.session_state.get("hole_points", {}).keys()) != set(players):
    st.session_state.hole_points = {p: 0 for p in players}

scores = st.session_state.scores_df
events = st.session_state.events_df
running_points = st.session_state.running_points
current_titles = st.session_state.current_titles
hole_logs = st.session_state.hole_logs
point_bank = st.session_state.point_bank
confirmed_holes = st.session_state.confirmed_holes
current_hole = st.session_state.current_hole
hole_points = st.session_state.hole_points
num_players = len(players)

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
code_to_display = {v: k for k, v in event_translate.items()}

# 👉 新增：記錄每洞 outcome & tie 是否已被追走
hole_outcome = ["none"] * 18      # "tie" / "win"
tie_claimed  = [False] * 18       # 該平手洞是否已被 PAR/Birdie 吃掉

# =================== 依已確認洞重新計算 ===================
running_points = {p: 0 for p in players}
current_titles = {p: "" for p in players}
hole_logs = []
point_bank = 1
hole_points = {p: 0 for p in players}

for i in range(18):
    if not confirmed_holes[i]:
        continue

    raw = scores[f"第{i+1}洞"]
    evt = events[f"第{i+1}洞"]

    # 1️⃣ 勝負計算（兩兩比較）
    victory_map = {}
    for p1 in players:
        p1_wins = 0
        for p2 in players:
            if p1 == p2:
                continue
            adj_p1, adj_p2 = int(raw[p1]), int(raw[p2])
            diff = int(handicaps[p1]) - int(handicaps[p2])
            if diff > 0 and hcp[i] <= diff:
                adj_p1 -= 1
            elif diff < 0 and hcp[i] <= -diff:
                adj_p2 -= 1
            if adj_p1 < adj_p2:
                p1_wins += 1
        victory_map[p1] = p1_wins
    winners = [p for p in players if victory_map[p] == len(players) - 1]

    # 2️⃣ 事件扣點（影響 BANK）
    penalty_pool = 0
    event_penalties_actual = {}
    event_detail_labels = {}

    for p in players:
        acts = evt[p] if isinstance(evt[p], list) else []
        pen = 0
        if current_titles[p] in ["Rich Man", "Super Rich Man"]:
            pen = sum(1 for act in acts if act in penalty_keywords)
            if current_titles[p] == "Super Rich Man" and "par_on" in acts:
                pen += 1
            pen = min(pen, 3)

        actual_penalty = min(pen, running_points[p])
        running_points[p] -= actual_penalty
        penalty_pool += actual_penalty
        event_penalties_actual[p] = actual_penalty

        labels = [code_to_display[a] for a in acts if a in code_to_display]
        event_detail_labels[p] = labels

    # 3️⃣ BANK 計算
    gain_points = point_bank + penalty_pool
    birdie_bonus = 0

    if len(winners) == 1:
        w = winners[0]
        running_points[w] += gain_points

        is_birdie = int(raw[w]) <= int(par[i]) - 1
        if is_birdie:
            for p in players:
                if p != w and running_points[p] > 0:
                    running_points[p] -= 1
                    birdie_bonus += 1
            running_points[w] += birdie_bonus
        point_bank = 1
        hole_outcome[i] = "win"
    else:
        point_bank += 1 + penalty_pool
        hole_outcome[i] = "tie"

    # 4️⃣ 頭銜更新
    next_titles = current_titles.copy()
    for p in players:
        pt = running_points[p]
        cur = current_titles.get(p, "")
        if cur == "":
            if pt >= 8:
                next_titles[p] = "Super Rich Man"
            elif pt >= 4:
                next_titles[p] = "Rich Man"
        elif cur == "Rich Man":
            if pt >= 8:
                next_titles[p] = "Super Rich Man"
            elif pt == 0:
                next_titles[p] = ""
        elif cur == "Super Rich Man":
            if pt < 4:
                next_titles[p] = "Rich Man"
    current_titles = next_titles

    # 5️⃣ 逐洞點數制（計算本洞 side game 點數，並記錄本洞 +N）
    side_gain = 0        # 👉 本洞 winner 逐洞加了幾點（用來寫進 LOG）

    if enable_hole_bet:
        if len(winners) == 1:
            w = winners[0]
            base_points = 1  # 勝洞本身 1 點

            score_w = int(raw[w])
            chase = 0
            if score_w == par[i]:
                chase = 1          # PAR 往前追 1 洞
            elif score_w == par[i] - 1:
                chase = 2          # Birdie 往前追 2 洞
            elif score_w <= par[i] - 2:
                chase = 3          # Eagle 以上追 3 洞（要縮減可改成 2）

            extra = 0
            # 只看「最近的前幾洞」，且只吃「當洞為 tie 且尚未被吃掉」
            for step in range(1, chase + 1):
                j = i - step
                if j < 0:
                    break
                if hole_outcome[j] == "tie" and not tie_claimed[j]:
                    extra += 1
                    tie_claimed[j] = True
                else:
                    break

            side_gain = base_points + extra
            hole_points[w] += side_gain
        else:
            # tie 洞本身不加點，等之後 PAR/Birdie 來吃
            pass

    # 6️⃣ Log（把 side_gain 寫成「逐洞 +N」）
    penalty_info = []
    for p in players:
        if event_penalties_actual.get(p, 0) > 0:
            detail = event_detail_labels.get(p, [])
            if detail:
                penalty_info.append(
                    f"{p} 扣 {event_penalties_actual[p]}點（" + "、".join(detail) + "）"
                )
            else:
                penalty_info.append(f"{p} 扣 {event_penalties_actual[p]}點")
    penalty_summary = "｜".join(penalty_info) if penalty_info else ""

    if len(winners) == 1:
        w = winners[0]
        bird_icon = " 🐦" if int(raw[w]) <= int(par[i]) - 1 else ""
        hole_log = f"🏆 第{i+1}洞勝者：{w}{bird_icon}（Bank +{gain_points}點"
        if birdie_bonus:
            hole_log += f"｜Birdie 轉入 {birdie_bonus}點"
        hole_log += "）"

        # 👉 在現有 LOG 後面加上「逐洞 +N」
        if enable_hole_bet and side_gain > 0:
            hole_log += f"｜逐洞 +{side_gain}點"

        if penalty_summary:
            hole_log += f"｜{penalty_summary}"
    else:
        hole_log = f"⚖️ 第{i+1}洞平手（下洞積分 {point_bank}點）"
        if penalty_summary:
            hole_log += f"｜{penalty_summary}"

    hole_logs.append(hole_log)


    # 6️⃣ 逐洞點數制（真正修正的地方）
    if enable_hole_bet:
        if len(winners) == 1:
            w = winners[0]
            base_points = 1  # 勝洞本身 1 點

            score_w = int(raw[w])
            chase = 0
            if score_w == par[i]:
                chase = 1          # PAR 往前追 1 洞
            elif score_w == par[i] - 1:
                chase = 2          # Birdie 往前追 2 洞
            elif score_w <= par[i] - 2:
                chase = 3          # Eagle 以上追 3 洞（若不想要可改成 2）

            extra = 0
            # 只看「最近的前幾洞」，且只吃「當洞為 tie 且尚未被吃掉」
            for step in range(1, chase + 1):
                j = i - step
                if j < 0:
                    break
                if hole_outcome[j] == "tie" and not tie_claimed[j]:
                    extra += 1
                    tie_claimed[j] = True
                else:
                    # 一旦遇到不是「尚未被吃掉的 tie」，就停止往更前看
                    break

            hole_points[w] += base_points + extra
        else:
            # tie 洞本身不加點，但可能之後被 PAR / Birdie 吃掉
            pass

# 逐洞結果（分別比較 Σ(A-B)*賭金）
cash_result = {p: 0 for p in players}
if enable_hole_bet:
    total_pts = sum(hole_points.values())
    n = len(players)
    for p in players:
        cash_result[p] = (n * hole_points[p] - total_pts) * hole_bet

# 回寫最新狀態
st.session_state.running_points = running_points
st.session_state.current_titles = current_titles
st.session_state.hole_logs = hole_logs
st.session_state.point_bank = point_bank
st.session_state.hole_points = hole_points

# =================== 逐洞輸入（只顯示當洞） ===================
st.markdown("---")
st.subheader("🕳️ 逐洞輸入")

if any(not x for x in confirmed_holes):
    first_unconfirmed = next(i for i, done in enumerate(confirmed_holes) if not done)
    current_hole = first_unconfirmed
    st.session_state.current_hole = current_hole
else:
    current_hole = 18
    st.session_state.current_hole = 18

if current_hole >= 18:
    st.success("✅ 已完成全部 18 洞成績")
else:
    i = current_hole
    st.markdown(f"### 第{i+1}洞 (Par {par[i]} / HCP {hcp[i]})")
    cols = st.columns(len(players))
    for j, p in enumerate(players):
        with cols[j]:
            if current_titles.get(p) == "Super Rich Man":
                st.markdown("👑 **Super Rich Man**")
            elif current_titles.get(p) == "Rich Man":
                st.markdown("🏆 **Rich Man**")

            cur_val = scores.loc[p, f"第{i+1}洞"]
            default_score = par[i] if pd.isna(cur_val) else int(cur_val)
            scores.loc[p, f"第{i+1}洞"] = st.number_input(
                f"{p} 桿數（目前 {running_points[p]} 點）",
                min_value=1, max_value=15, value=default_score, key=f"score_{p}_{i}"
            )

            existing_events = events.loc[p, f"第{i+1}洞"]
            if isinstance(existing_events, list):
                default_events_display = [k for k, v in event_translate.items() if v in existing_events]
            else:
                default_events_display = []
            selected_display = st.multiselect(
                f"{p} 事件", event_opts_display,
                default=default_events_display, key=f"event_{p}_{i}"
            )
            events.loc[p, f"第{i+1}洞"] = [event_translate[d] for d in selected_display]

    confirm_btn = st.button(f"✅ 確認第{i+1}洞成績")

    if confirm_btn:
        confirmed_holes[i] = True
        st.session_state.confirmed_holes = confirmed_holes

        if any(not x for x in confirmed_holes):
            next_hole = next(idx for idx, done in enumerate(confirmed_holes) if not done)
        else:
            next_hole = 18
        st.session_state.current_hole = next_hole

        st.success(f"✅ 已確認第{i+1}洞成績")
        st.rerun()

# =================== 總結結果（主控端） ===================
completed = sum(1 for x in confirmed_holes if x)
st.subheader("📊 總結結果（主控端）")

holes_done = [i for i, ok in enumerate(confirmed_holes) if ok]

detail_df = pd.DataFrame(index=players)
for i in holes_done:
    col_name = f"洞{i+1}"
    detail_df[col_name] = [scores.loc[p, f"第{i+1}洞"] for p in players]

summary_dict = {
    "BANK點數": [running_points[p] for p in players],
    "BANK結果": [
        ((running_points[p] * num_players) - 18) * bank_bet
        for p in players
    ],
    "頭銜": [current_titles[p] for p in players]
}
if enable_hole_bet:
    summary_dict["逐洞點數"] = [hole_points[p] for p in players]
    summary_dict["逐洞結果"] = [cash_result[p] for p in players]

summary_extra = pd.DataFrame(summary_dict, index=players)
summary_table = pd.concat([detail_df, summary_extra], axis=1)

col_order = list(detail_df.columns)
bank_cols = ["BANK點數"]
hole_cols = ["逐洞點數", "逐洞結果"] if enable_hole_bet else []
result_cols = ["BANK結果", "頭銜"]
summary_table = summary_table[col_order + bank_cols + hole_cols + result_cols]

st.dataframe(summary_table, use_container_width=True)

# =================== Event Log（主控端，美化版） ===================
st.subheader("📖 Event Log（主控端）")

if not hole_logs:
    st.info("目前沒有任何紀錄")
else:
    for line in hole_logs:
        if line.startswith("🏆"):
            color = "#4CAF50"
        elif line.startswith("⚖️"):
            color = "#FFC107"
        else:
            color = "#B0BEC5"

        html = f"""
        <div style="margin-left: 1.5rem; margin-bottom: 0.2rem;">
            <span style="color:{color}; font-size:0.95rem;">
                {line}
            </span>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

# =================== 寫回 Firebase ===================
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
    "bet_per_person": bank_bet,
    "bank_bet_per_person": bank_bet,
    "hole_bet_per_person": hole_bet,
    "completed_holes": completed,
    "hole_points": hole_points,
}

if "game_id" not in st.session_state or not st.session_state.game_id:
    st.warning("⚠️ 賽事尚未建立（沒有 game_id），成績目前僅暫存於本機。")
else:
    if "db" not in st.session_state or not hasattr(st.session_state.db, "collection"):
        st.error("⚠️ Firebase 連線失效，成績無法寫回雲端，請重新整理後再試。")
    else:
        try:
            st.session_state.db.collection("golf_games") \
                .document(st.session_state.game_id).set(game_data_update)
        except Exception as e:
            st.error(f"❌ Firebase 寫入失敗：{e}")

# =================== 底部 Game ID & QR ===================
if "game_id" in st.session_state and st.session_state.game_id:
    st.markdown("---")
    st.markdown(f"🆔 **Game ID**：`{st.session_state.game_id}`")
    if "qr_bytes" in st.session_state:
        st.image(st.session_state.qr_bytes, width=160, caption="隊員掃碼查看（免登入）")
