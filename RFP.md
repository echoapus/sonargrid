# SonarGrid 專案 -網路與伺服器監控系統（NMS）採購需求建議書 (RFP)-

## 1. 專案背景與建置目標
本公司目前擁有中大型網路維運環境，包含 1,000 台以上之個人電腦（PC）及 500 台以上之實體/虛擬伺服器（Server），以及相關網路設備（交換器、防火牆、無線AP等）。為提升 IT 運作效率、縮短故障衍生時間（MTTR）並落實資產合規

## 2. 專案環境規模
*   **伺服器（Server）：** 約 500+ 台（包含 Linux, VMware ESXi/Hyper-V 虛擬化平台）。
*   **個人電腦（PC）：** 約 1,000+ 台（主要為 Windows 10/11，包含少數 macOS）。
*   **網路設備：** 約 50+ 台（交換器、防火牆、路由器等）。


---

## 3. 功能需求規格（核心審查項目）

### (一) 架構與效能需求
1.  **集中式 Agentless 監控架構：** 系統不得要求於受監控端安裝 Probe/Proxy，須由中央伺服器透過網路協定進行集中式監控與資料收集。
2.  **多種監控協定支援：** 須支援 Agentless（無代理程式，如 SNMP v2c/v3, WMI, WinRM, SSH, ICMP, IPMI）部署模式。
3.  **自動發現（Auto-Discovery）：** 須具備排程排查功能，能依據 IP 網段自動掃描、辨識設備類型（Server/PC/Printer/Switch/Router/Firewall）並自動納管。
4.  **設備類型辨識：** 系統須能透過 SNMP sysDescr/sysObjectID、Printer MIB、Host Resources MIB、WMI/WinRM OS ProductType、SSH OS fingerprint、常見服務 port、MAC OUI 與 hostname 規則輔助判斷設備類型，並記錄辨識來源與可信度。

### (二) 伺服器與網路設備監控（Server & Network）
1.  **效能與健康度：** 須即時監控 CPU 使用率、記憶體消耗、磁碟剩餘空間與 I/O 效能。
2.  **硬體層級監控：** 須能透過 IPMI/SNMP 監控實體伺服器之硬體狀態（如風扇轉速、電源供應器狀態、機殼溫度、RAID 狀態）。
3.  **服務與進程監控：** 須能監控關鍵服務（如 IIS, Apache, MS SQL, MySQL, Active Directory）之存活狀態，並可針對特定 Process 進行監控。
4.  **網路拓撲自動繪製：** 須能自動生成二層/三層（L2/L3）網路拓撲圖，並隨設備狀態變更即時更新顏色（如正常為綠色、異常為紅色）。

### (三) 個人電腦（PC）資產與狀態管理需求
1.  **彈性警報邏輯：** 針對 1,000+ PC，系統須能排除一般下班關機之偽陽性（False Positive）警報，僅針對特定關鍵 PC 或長時離線進行告警。
2.  **軟硬體資產盤點（ITAM）：** 須能自動收集 PC 之硬體規格（CPU、RAM、產品牌、序號）

### (四) 告警與通知機制（Alerting）
1.  **多管道通知：** 當事件觸發時，須支援syslog/email/webhook

### (五) 報表與視覺化（Dashboard & Reporting）
1.  **中文化管理介面：** 系統操作管理介面（Web UI）須支援繁體中文以及美國英文，自由切換。
2.  **客製化儀表板：** 須提供直觀之 Dashboard，
3.  **歷史趨勢報表：** 須能產出日、週、月、季之可用性（Availability）報表與效能趨勢圖，做為未來硬體擴充之依據。
