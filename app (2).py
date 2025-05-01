import streamlit as st
import pandas as pd
import os
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- Firebase 初始化 ---
if "firebase_initialized" not in st.session_state:
    try:
        if not firebase_admin._apps:
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

st.set_page_config(page_title="🏌️ 高爾夫BANK系統", layout="wide")
st.title("🏌️ 高爾夫BANK系統")

# --- 模式設定 ---
if "mode" not in st.session_state:
    st.session_state.mode = "主控操作端"
mode = st.session_state.mode

# --- 隊員查看端：Firebase 資料同步 ---
game_id = None
if mode == "隊員查看端":
    game_id = st.text_input("輸入遊戲ID", key="game_id_input")
    if not game_id:
        st.warning("請輸入遊戲ID")
        st.stop()
    
    doc_ref = st.session_state.db.collection("golf_games").document(game_id)
    try:
        doc = doc_ref.get()
        if doc.exists:
            game_data = doc.to_dict()
            st.session_state.players = game_data["players"]
            scores = pd.DataFrame.from_dict(game_data["scores"], orient="index")
            events = pd.DataFrame.from_dict(game_data["events"], orient="index")
            running_points = game_data["points"]
            hole_logs = game_data["logs"]
            completed = game_data["completed_holes"]
            selected_course = game_data["course"]
            front_area = game_data["front_area"]
            back_area = game_data["back_area"]
            bet_per_person = game_data["bet_per_person"]
            par = game_data["par"]
            hcp = game_data["hcp"]
        else:
            st.warning("找不到指定遊戲ID，請確認輸入正確")
            st.stop()
    except Exception as e:
        st.error("Firebase 資料讀取失敗")
        st.exception(e)
        st.stop()

# --- 主控端遊戲初始化 ---
if mode == "主控操作端" and "game_id" not in st.session_state:
    st.session_state.game_id = datetime.now().strftime("%Y%m%d%H%M%S")
    st.write(f"本場遊戲ID：**{st.session_state.game_id}**")

# --- 球場選擇 (主控端可編輯，隊員端只讀) ---
course_options = course_df["course_name"].unique().tolist()
if mode == "主控操作端":
    selected_course = st.selectbox("選擇球場", course_options)
else:
    selected_course = st.selectbox("選擇球場", [selected_course], disabled=True)

# --- 區域選擇 (主控端可編輯，隊員端只讀) ---
filtered_area = course_df[course_df["course_name"] == selected_course]["area"].unique().tolist()
if mode == "主控操作端":
    front_area = st.selectbox("前九洞區域", filtered_area, key="front_area")
    back_area = st.selectbox("後九洞區域", filtered_area, key="back_area")
else:
    front_area = st.selectbox("前九洞區域", [front_area], disabled=True, key="front_area")
    back_area = st.selectbox("後九洞區域", [back_area], disabled=True, key="back_area")

# --- 獲取球場資料 ---
def get_course_info(cname, area):
    temp = course_df[(course_df["course_name"] == cname) & (course_df["area"] == area)]
    temp = temp.sort_values("hole")
    return temp["par"].tolist(), temp["hcp"].tolist()

if mode == "主控操作端":
    front_par, front_hcp = get_course_info(selected_course, front_area)
    back_par, back_hcp = get_course_info(selected_course, back_area)
    par = front_par + back_par
    hcp = front_hcp + back_hcp

# --- 球員設定 ---
if mode == "主控操作端":
    players = st.multiselect("選擇參賽球員（最多4位）", st.session_state.players, max_selections=4)
    new = st.text_input("新增球員")
    if new:
        if new not in st.session_state.players:
            st.session_state.players.append(new)
            pd.DataFrame({"name": st.session_state.players}).to_csv(CSV_PATH, index=False)
        if new not in players and len(players) < 4:
            players.append(new)
    handicaps = {p: st.number_input(f"{p} 差點", 0, 54, 0, key=f"hcp_{p}") for p in players}
    bet_per_person = st.number_input("單局賭金（每人）", 10, 1000, 100)

# --- 初始化資料結構 ---
if mode == "主控操作端":
    scores = pd.DataFrame(index=players, columns=[f"第{i+1}洞" for i in range(18)])
    events = pd.DataFrame(index=players, columns=[f"第{i+1}洞" for i in range(18)])
    running_points = {p: 0 for p in players}
    current_titles = {p: "" for p in players}
    hole_logs = []
    point_bank = 1

# --- 主流程循環 ---
event_opts_display = ["下沙", "下水", "OB", "丟球", "加3或3推", "Par on"]
event_translate = {"下沙": "sand", "下水": "water", "OB": "ob", "丟球": "miss", "加3或3推": "3putt_or_plus3", "Par on": "par_on"}
penalty_keywords = ["sand", "water", "ob", "miss", "3putt_or_plus3"]

if mode == "主控操作端":
    completed_holes = len([k for k in range(18) if st.session_state.get(f"confirm_{k}", False)])
else:
    completed_holes = completed if "completed" in locals() else 0

for i in range(18):
    if mode == "隊員查看端" and i >= completed_holes:
        continue
    
    st.subheader(f"第{i+1}洞 (Par {par[i]} / HCP {hcp[i]})")
    
    # 模式分支
    if mode == "主控操作端":
        cols = st.columns(len(players))
        for j, p in enumerate(players):
            with cols[j]:
                if current_titles[p] == "SuperRich":
                    st.markdown("👑 **Super Rich Man**")
                elif current_titles[p] == "Rich":
                    st.markdown("🏆 **Rich Man**")
                scores.loc[p, f"第{i+1}洞"] = st.number_input(
                    f"{p} 桿數（{running_points[p]} 點）", 
                    1, 15, par[i], 
                    key=f"score_{p}_{i}"
                )
                selected_display = st.multiselect(
                    f"{p} 事件", 
                    event_opts_display, 
                    key=f"event_{p}_{i}"
                )
                selected_internal = [event_translate[d] for d in selected_display]
                events.loc[p, f"第{i+1}洞"] = selected_internal
        
        confirmed = st.checkbox(f"✅ 確認第{i+1}洞成績", key=f"confirm_{i}")
        if not confirmed:
            continue
    else:
        cols = st.columns(len(players))
        for j, p in enumerate(players):
            with cols[j]:
                st.markdown(f"**{p}**")
                score = scores.loc[p, f"第{i+1}洞"] if f"第{i+1}洞" in scores.columns else "N/A"
                st.write(f"桿數: {score}")
                event_list = events.loc[p, f"第{i+1}洞"] if f"第{i+1}洞" in events.columns else []
                event_display = [k for k, v in event_translate.items() if v in event_list]
                st.write(f"事件: {', '.join(event_display) if event_display else '無'")
        
        if i < len(hole_logs):
            st.markdown(f"`{hole_logs[i]}`")
    
    # 共用邏輯（分數計算）
    if mode == "主控操作端":
        # ...（原有分數計算與Firebase存儲邏輯保持不變）
        # 寫入Firebase
        game_data = {
            "players": players,
            "scores": scores.to_dict(orient="index"),
            "events": events.apply(lambda x: x.tolist()).to_dict(orient="index"),
            "points": running_points,
            "titles": current_titles,
            "logs": hole_logs,
            "par": par,
            "hcp": hcp,
            "course": selected_course,
            "front_area": front_area,
            "back_area": back_area,
            "bet_per_person": bet_per_person,
            "completed_holes": completed_holes
        }
        st.session_state.db.collection("golf_games").document(st.session_state.game_id).set(game_data)

# --- 總結結果 ---
st.subheader("📊 總結結果")
if mode == "主控操作端":
    total_bet = bet_per_person * len(players)
    result = pd.DataFrame({
        "總點數": [running_points[p] for p in players],
        "賭金結果": [(running_points[p] - completed_holes) * bet_per_person for p in players],
        "頭銜": [current_titles[p] for p in players]
    }, index=players).sort_values("賭金結果", ascending=False)
else:
    result = pd.DataFrame({
        "總點數": [running_points[p] for p in players],
        "賭金結果": [(running_points[p] - completed_holes) * bet_per_person for p in players],
        "頭銜": [current_titles[p] for p in players]
    }, index=players).sort_values("賭金結果", ascending=False)

st.dataframe(result)

st.subheader("📖 洞別說明 Log")
for line in hole_logs:
    st.text(line)

# 隊員端自動刷新
if mode == "隊員查看端":
    st.experimental_rerun(interval=5)
