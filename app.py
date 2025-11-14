import streamlit as st
st.set_page_config(page_title="🏌️高爾夫BANKv1.3.3", layout="centered")

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

st.title("🏌️高爾夫BANK v1.3.3")

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
if "game_id" in st.session_state and "qr_bytes"_
