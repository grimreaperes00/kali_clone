# Kali Linux Proxmox VM 批次自動部署腳本

本專案提供一套自動化腳本，協助你在 Proxmox VE 環境下，快速建立 Kali Linux 黃金映像（Template）並批次複製多台 VM，適合大量測試、教學、滲透演練等場景。

---

## 特色
- 自動下載並解壓 Kali 官方 QEMU 映像
- 一鍵建立黃金映像（Template VM）
- 支援多台 VM 批次部署，名稱自動編號
- 支援自訂 CPU、記憶體、磁碟、網路橋、VLAN
- 自動尋找可用 VMID，避免衝突
- 支援磁碟自動擴容
- 全程無需手動進入 Proxmox 介面

---

## 需求
- Proxmox VE 7/8/9
- Python 3.7+
- 已安裝 `unar`、`wget`、`requests`（可自動安裝）
- 網路可連線 Kali 官方映像站

---

## 使用方式

### 1. 參數說明

| 參數                | 預設值                | 說明                       |
|---------------------|-----------------------|----------------------------|
| --template-id       | 9000                  | Template VM ID             |
| --template-dir      | /var/lib/vz/template/iso/kali-images | Template 映像暫存目錄 |
| --template-storage  | local-lvm             | Template 儲存名稱          |
| --template-name     | kali-template         | Template VM 名稱           |
| --template-bridge   | vmbr0                 | Template VM 網路橋         |
| --template-memory   | 4096                  | Template 記憶體 (MB)       |
| --template-core     | 2                     | Template CPU 核心數        |
| --template-disk     | 80G                   | Template 磁碟大小          |
| --vmname            | kali-vm               | VM 名稱（可自動編號）      |
| --start-vmid        | 100                   | VMID 起始值                |
| --count             | 1                     | 建立幾台 VM                |
| --core              | 4                     | VM CPU 核心數              |
| --memory            | 8192                  | VM 記憶體 (MB)             |
| --disk              | 80G                   | VM 磁碟大小                |
| --bridge            | vmbr3                 | VM 網路橋                  |
| --vlan              | 100                   | VM VLAN tag                |
| --description       | Kali VM auto-generated| VM 描述                    |

### 2. 執行範例

建立 3 台 Kali VM，名稱 kali-lab-1、kali-lab-2、kali-lab-3，VMID 從 200 開始：

```bash
sudo python3 auto_build_kali_vm.py \
  --vmname kali-lab \
  --count 3 \
  --start-vmid 200 \
  --core 2 \
  --memory 4096 \
  --disk 40G \
  --bridge vmbr3 \
  --vlan 100
```

### 3. 常見問題
- **Q: VMID 衝突怎麼辦？**
  - 腳本會自動尋找未被占用的 VMID。
- **Q: 下載太慢/失敗？**
  - 請確認網路可連線 https://cdimage.kali.org/
- **Q: 需要 root 權限嗎？**
  - 需要，請用 sudo 執行。

---

