# SonarGrid NMS Coding Plan

本計畫依據 `RFP.md` 規劃。第一版目標是交付可用的集中式資訊收集系統：不安裝 Probe / Proxy、不做 SPA、不上外部 DB，先用單機架構跑通 discovery、設備資訊收集、SNMP 推論式 topology、基本查詢與匯出。

## 1. 架構方向

RFP 規模：

- Server: 500+ 台
- PC: 1,000+ 台
- Network devices: 50+ 台

限制：

- 不允許在被收集資訊的設備端安裝 Probe / Proxy
- 第一版使用 SQLite
- 第一版使用輕量 Web 技術

架構：

```text
Browser
  |
  v
Flask Web App
  |
  +-- Auth / Session
  +-- Device Inventory
  +-- Discovery
  +-- Collection Scheduler
  +-- Topology
  +-- Dashboard / Reports
  +-- Settings
  |
  v
SQLite DB file
  |
  +-- devices / collection_jobs
  +-- observations / job_runs
  +-- topology_nodes / topology_edges
  +-- credentials / settings
  +-- users / audit_logs

Background Worker
  |
  +-- ICMP
  +-- SNMP v2c/v3
  +-- SSH
  +-- WinRM / WMI
  +-- IPMI
  |
  v
Servers / PCs / Printers / Network Devices
```

## 2. 技術選型

Backend:

- Python
- Flask
- Jinja2 templates
- `sqlite3`
- SQL migration files
- Python thread / queue / time loop for background worker

Frontend:

- Server-rendered HTML
- Plain CSS
- Vanilla JavaScript
- 少量 `fetch()` 做局部更新

Collection integrations:

- ICMP: 系統 `ping` 或 socket
- SNMP: 需要時引入單一 SNMP library
- SSH: 需要時引入單一 SSH library
- WinRM / WMI: 需要時引入對應 library
- IPMI: 需要時引入單一 IPMI library 或 `ipmitool` wrapper

暫不採用：

- React / Vue / Angular SPA
- FastAPI
- HTMX / Alpine.js
- SQLAlchemy / ORM
- Celery / Redis / RabbitMQ
- PostgreSQL / InfluxDB / Elasticsearch

## 3. SQLite 使用原則

SQLite 適合第一版單機部署，但要控制寫入與資料量。

- 啟用 WAL mode
- 資訊收集寫入集中由 background worker 處理
- `observations`、`job_runs` 建立時間欄位索引
- raw observations 保留 30-90 天
- rollup observations 保留 1-3 年
- audit logs 保留至少 1 年
- DB file 納入備份與還原流程
- 寫入量或報表查詢明顯卡住時，再升級 PostgreSQL / time-series storage

## 4. 核心資料模型

- `devices`: 被收集資訊的設備
- `device_type_detections`: 設備類型辨識紀錄
- `device_groups`: 設備群組
- `interfaces`: 網路介面
- `collection_jobs`: 資訊收集任務定義
- `job_runs`: 資訊收集任務執行紀錄
- `observations`: 每次取得的設備資訊與 SNMP/WMI/SSH 結果
- `topology_nodes`: 推論式拓撲節點
- `topology_edges`: 推論式拓撲連線與可信度
- `topology_snapshots`: topology freeze 時保留的目前狀態
- `credentials`: 加密保存的連線憑證
- `settings`: 系統設定
- `users`: 使用者，第一版只做基本登入
- `audit_logs`: 操作稽核

## 5. Device Type Detection

Auto-Discovery 需要辨識設備類型，不只判斷有無回應。

辨識來源：

- SNMP: `sysDescr`、`sysObjectID`、`sysName`、Printer MIB、Host Resources MIB
- WMI / WinRM: OS name、OS ProductType、manufacturer、model、hostname
- SSH: OS fingerprint、hostname、virtualization hints
- Port fingerprint: 9100/515/631 for printer、3389 for Windows、5985/5986 for WinRM、22 for SSH、445 for SMB
- MAC OUI: vendor lookup
- Hostname rule: `PC-*`、`SRV-*`、`PRN-*`

分類：

- `pc`
- `server`
- `printer`
- `switch`
- `router`
- `firewall`
- `ups`
- `unknown`

每次辨識需保存：

- `device_type`
- `detection_confidence`: `high` / `medium` / `low`
- `detection_source`: `snmp` / `wmi` / `winrm` / `ssh` / `port` / `oui` / `hostname`
- `detection_notes`

## 6. SNMP 推論式 Topology

第一版需要產生 L2 / L3 topology，但不能依賴 LLDP / CDP。拓撲資料改由 SNMP 已知資訊推論。

可用資料：

- `ifTable` / `ifXTable`: interface index、name、alias、status、speed、MAC
- `ipAddrTable` 或 `ipAddressTable`: interface IP
- `ipNetToMediaTable` 或 ARP table: IP-to-MAC 對應
- `dot1dTpFdbTable`: bridge forwarding database，MAC-to-port 對應
- `dot1dBasePortTable`: bridge port 與 interface index 對應
- routing table: L3 next-hop 與 subnet 關係
- ARP scan / ping scan 結果
- device inventory: IP、MAC、hostname、device_type

推論方式：

- 以 switch FDB 的 MAC-to-port 找出 endpoint 接在哪個 switch port
- 以 ARP table 將 IP 對應到 MAC，再對回 device inventory
- 以 interface IP/subnet 與 routing table 推論 L3 gateway / router 關係
- 多台 switch 都看到同一批 MAC 時，標示為 uplink / shared segment candidate
- 無法唯一判斷的連線標記為 `inferred_low_confidence`

限制：

- 不使用 LLDP / CDP
- 第一版只做自動推論與可信度標示，不做手動拖拉編輯器
- 推論結果需保存來源表格與 confidence，避免把猜測當成事實
- 支援 topology freeze：啟用後維持目前 topology，不新增、不刪除、不更新節點與連線
- freeze 啟用時，discovery cleanup 不得移除既有 topology 節點或連線

## 7. 第一版設定頁範圍

第一版只放必要啟動設定。

保留：

- 系統設定：系統名稱、語言、時區、資料保留天數、SQLite 備份路徑
- 掃描 / Discovery 設定：IP range、掃描排程、timeout、retry、最大並行數、啟用 ICMP/SNMP/WinRM/WMI/SSH/port fingerprint
- Credential 設定：SNMP、Windows、SSH、IPMI credential 與測試連線
- 通知設定：Email SMTP、Webhook URL、Syslog server、測試通知
- Topology 設定：暫停 / 恢復 topology 更新
- 系統維護：立即備份、清理舊 observations、查看 worker 狀態、查看 job_runs、查看 audit logs

不在第一版設定頁範圍內的項目不列入本計畫。

Credential 安全規則：

- secret 加密後才寫入 SQLite
- 加密 key 來自環境變數或部署時產生的本機檔案，不寫入 SQLite
- UI 不回顯 secret，只顯示名稱、類型、套用範圍與最後測試結果
- 匯出設定不得包含 secret 明文

## 8. Coding Phases

### Phase 0: 基礎骨架

目標：建立可登入、可啟動、可存資料的 NMS 骨架。

- Flask app
- Jinja2 layout
- Plain CSS
- SQLite 初始化與 migration
- 基本登入 / session
- 基本 audit log
- Device / Collection Job / Observation schema

驗收：

- 可登入系統
- 可開啟首頁
- 可執行 migration 建立 SQLite DB
- 可新增、編輯、標記 inactive / archive 設備

### Phase 1: 設備納管與 Auto-Discovery

目標：掃描 IP 網段並建立設備清單。

- IP range 掃描
- ICMP ping 探測
- SNMP v2c/v3 探測
- WMI / WinRM OS ProductType 探測
- SSH OS fingerprint 探測
- 常見 port fingerprint
- MAC OUI / hostname 規則判斷
- 設備類型自動分類
- 掃描排程
- 重複設備偵測
- 連續三天未取得資訊的設備才自動標記 inactive，不 hard delete

驗收：

- 可掃描指定網段
- 可識別有回應 / 無回應
- 可辨識 PC / Server / Printer / Switch / Router / Firewall
- 可記錄辨識來源與可信度
- 重複掃描不會重複納管
- 設備連續三天未取得任何資訊時才會自動標記 inactive
- inactive 設備保留歷史 observations 與 topology 關聯

### Phase 2: 集中式 Collection Scheduler / Worker

目標：不安裝 Probe / Proxy，由 Central Server 執行資訊收集任務。

- Collection scheduler
- Background worker
- Job queue / job_runs
- Timeout / retry / concurrency 控制
- Worker 狀態
- 依設備類型套用預設檢查頻率
- 遵守 topology freeze flag，暫停時不寫入 topology 變更

驗收：

- Central 可排程並執行資訊收集任務
- Worker 可並行處理多台設備
- 任務失敗會留下 job_runs 與錯誤原因
- Worker 失敗會留下 job_runs 錯誤紀錄
- topology freeze 啟用時，worker 不新增、不刪除、不更新 topology nodes / edges
- topology freeze 啟用時，cleanup 不會 archive 任何 topology 既有節點

### Phase 3: 設備資訊收集

目標：取得設備資訊與 SNMP/WMI/SSH 原始觀測資料，不做健康判斷與告警。

- CPU / memory / disk 基本資訊，能取得才保存
- Network interface 流量
- ICMP response time
- SNMP interface table
- SNMP ARP / FDB / interface tables for topology
- Observation 歷史儲存
- topology freeze 啟用時，仍可保存 observations，但不更新 topology

驗收：

- 可查看最近一次取得的設備資訊
- 可查詢歷史 observations
- 可依設備與資料來源篩選
- 可保存 topology 推論所需的 SNMP 原始資料
- topology freeze 啟用時，topology 畫面維持暫停前狀態

### Phase 4: 資訊收集狀態與通知

目標：顯示資訊收集是否成功，並在系統收集任務失敗時通知管理者。不做設備健康監控與 threshold 告警。

- Job success / failed 狀態
- 連續失敗次數
- 最後成功取得資訊時間
- Email 通知
- Webhook 通知
- Syslog forwarding
- 失敗通知確認 / 關閉

驗收：

- 資訊收集失敗會留下 job_runs 錯誤
- 連續失敗可通知 email / webhook / syslog
- 可送出 email / webhook / syslog
- 不做 CPU / memory / disk threshold 告警

### Phase 5: 第一版 Dashboard / Report

目標：提供可查詢的基本畫面與 topology。

- Device inventory overview
- Observation summary
- Worker status
- Job run status
- Last successful collection summary
- SNMP 推論式 L2 / L3 topology
- 拓撲節點依資訊收集狀態上色
- 拓撲連線顯示 confidence
- 暫停 / 恢復 topology 更新按鈕
- topology freeze 狀態標示
- CSV 匯出
- 繁體中文 / 英文切換

驗收：

- 可查看設備清單與最後取得資訊時間
- 可查看資訊收集成功 / 失敗狀態
- 可查詢 worker / job 狀態
- 可產生不用 LLDP / CDP 的推論式 topology
- 可暫停 topology 更新，暫停期間不新增或減少拓撲節點/連線
- 可恢復 topology 更新
- 可匯出 CSV

## 9. 本計畫範圍

- Phase 0: 基礎骨架
- Phase 1: 設備納管與 Auto-Discovery
- Phase 2: 集中式 Collection Scheduler / Worker
- Phase 3: 設備資訊收集
- Phase 4: 資訊收集狀態與通知
- Phase 5: 第一版 Dashboard / Report

## 10. 技術取捨

- 先做 modular monolith，不先拆微服務
- 先用 SQLite，不先導入 PostgreSQL / InfluxDB / Elasticsearch
- 先用 background worker，不先導入 Celery / Redis / RabbitMQ
- 先用 server-rendered HTML，不先做 SPA 或前端 build pipeline
- 先用 `sqlite3` 和 SQL files，不先導入 ORM
- 不安裝 Probe / Proxy，除非未來限制改變
- Topology 使用 SNMP 現有資訊推論，不依賴 LLDP / CDP
- 第一版只取得資訊，不做健康監控、threshold alert、異常偵測或 AI 分析
- 先支援 CSV 匯出，Excel / PDF 樣式報表等需求確認後再做
