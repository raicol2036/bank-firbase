# 🏌️ Golf BANK System

Golf BANK 是一套專為高爾夫球場即時賭注管理設計的系統。  
支援逐洞成績輸入、自動勝負計算、Rich/SuperRich狀態判定、雲端同步及隊員即時查看，完美適用於高爾夫友誼賽或比賽。

---

## 🚀 功能特色

- 🏌️ 單場 18 洞逐洞輸入與即時同步
- 🏆 自動勝負判定與點數計算
- 👑 Rich / SuperRich 自動晉級、降級
- 📖 洞別成績 Log 自動紀錄
- 📦 Google Drive 雲端自動儲存
- 📱 手機版最佳化顯示（直立友善版）
- 🔗 QR Code 生成分享，隊員即時查看
- 🕰️ 歷史比賽紀錄管理與查詢

---

## 📂 專案結構

```plaintext
/your-project-folder/
├── app.py                # 主程式
├── service_account.json   # Google Drive 金鑰 (本地開發用)
├── requirements.txt       # 套件列表
├── .gitignore             # 忽略設定
├── course_db.csv          # 球場資料表
├── players.csv            # 球員資料表
└── README.md              # 本文件
