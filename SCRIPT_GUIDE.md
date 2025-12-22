# 🎯 Kali VM 腳本使用指南

## 📊 腳本功能總結

### 🏆 **推薦使用**: `ultimate_kali_builder.py` (新建立)
```bash
# 建立單個 VM
sudo python3 ultimate_kali_builder.py --username kali --password 'MyPass123'

# 建立多個 VM
sudo python3 ultimate_kali_builder.py --username kali --password 'MyPass123' --count 5 --start-vm

# 完整配置
sudo python3 ultimate_kali_builder.py \
  --username admin \
  --password 'StrongPass!' \
  --ssh-key "$(cat ~/.ssh/id_rsa.pub)" \
  --count 3 \
  --name "kali-cluster" \
  --cpu 8 \
  --max-mem 16384 \
  --resize "+50G" \
  --start-vm
```

## 📋 所有腳本比較

| 腳本 | 功能 | 效率 | Cloud-Init | 推薦度 |
|------|------|------|------------|--------|
| `ultimate_kali_builder.py` | ⭐ 模板+複製+Cloud-Init | 🚀🚀🚀 | ✅ 自動 | 🏆 **強烈推薦** |
| `auto_build_kali_vm.py` | 模板+複製 | 🚀🚀 | ❌ 無 | ⭐ 高效但缺 Cloud-Init |
| `test_kali.py` | 模板+複製+NLP | 🚀🚀 | ❌ 無 | ⚠️ 需要 OpenAI API |
| `integrated_kali_builder.sh` | 基礎+Cloud-Init | 🚀 | ✅ 分離 | ✅ 簡單可靠 |
| `base_kali.sh` | 基礎建立 | 🐌 | ❌ 無 | ⚠️ 效率低 |
| `gen_cloudinit.sh` | 僅 Cloud-Init | N/A | ✅ 專業 | ✅ 專門工具 |

## 🚀 使用建議

### 🎯 **一般使用** → `ultimate_kali_builder.py`
- 整合所有功能
- 最高效率 (黃金映像模板)
- 自動 Cloud-Init 配置
- 支援批次建立

### 🔧 **分步控制** → `auto_build_kali_vm.py` + `gen_cloudinit.sh`
```bash
# 1. 先建立 VM
sudo python3 auto_build_kali_vm.py --count 3 --name kali-test

# 2. 再配置 Cloud-Init (假設建立的 VM ID 是 100, 101, 102)
for vmid in 100 101 102; do
  sudo ./gen_cloudinit.sh --vmid $vmid --username kali --password 'MyPass123'
done
```

### 🏗️ **快速簡單** → `integrated_kali_builder.sh`
```bash
sudo ./integrated_kali_builder.sh --username kali --password 'MyPass123' --start-vm
```

## 🧹 腳本整理建議

### 保留的腳本 (核心功能)
```
✅ ultimate_kali_builder.py     # 主要使用
✅ auto_build_kali_vm.py        # 備用高效版
✅ gen_cloudinit.sh             # 專門工具
✅ integrated_kali_builder.sh   # 簡單版本
```

### 可選保留 (特殊用途)
```
⚠️ test_kali.py                # 如果需要 NLP 功能
⚠️ base_kali.sh                # 學習/除錯用
```

### 可刪除 (重複功能)
```
❌ build_kali_with_cloudinit.py # 被 ultimate 取代
```

## 📝 快速測試

### 測試 Ultimate Builder
```bash
cd /root/kali/PROXMOX

# 基本測試
sudo python3 ultimate_kali_builder.py \
  --username testuser \
  --password 'Test123!' \
  --name test-ultimate

# 檢查結果
qm list | grep test-ultimate
```

### 清理測試 VM
```bash
# 刪除測試 VM (假設 ID 是 100)
qm stop 100
qm destroy 100
```

## 🔄 移轉建議

### 從舊腳本移轉到 Ultimate Builder

**舊指令:**
```bash
# 舊方式 1: base_kali.sh
sudo ./base_kali.sh

# 舊方式 2: auto_build + cloudinit
sudo python3 auto_build_kali_vm.py --count 3
sudo ./gen_cloudinit.sh --vmid 100 --username kali --password 'xxx'
```

**新指令:**
```bash
# 新方式: 一次完成
sudo python3 ultimate_kali_builder.py \
  --username kali \
  --password 'xxx' \
  --count 3 \
  --start-vm
```

## 📚 常用範例

### 開發環境 (單 VM)
```bash
sudo python3 ultimate_kali_builder.py \
  --username developer \
  --password 'DevPass123!' \
  --name kali-dev \
  --cpu 4 \
  --max-mem 8192 \
  --start-vm
```

### 測試環境 (多 VM)
```bash
sudo python3 ultimate_kali_builder.py \
  --username tester \
  --password 'TestPass123!' \
  --count 5 \
  --name kali-test \
  --cpu 2 \
  --max-mem 4096 \
  --start-vm
```

### 安全實驗室 (高配置)
```bash
sudo python3 ultimate_kali_builder.py \
  --username security \
  --ssh-key "$(cat ~/.ssh/id_rsa.pub)" \
  --count 3 \
  --name kali-lab \
  --cpu 8 \
  --max-mem 16384 \
  --resize "+100G" \
  --start-vm
```

## 🔍 故障排除

### 常見問題
1. **權限問題**: 必須使用 `sudo`
2. **模板衝突**: 使用 `--rebuild-template` 強制重建
3. **磁碟空間**: 確保有足夠空間下載和解壓縮
4. **網路問題**: 檢查到 kali.org 的連線

### Debug 模式
```bash
# 檢查模板狀態
qm status 9000

# 重建模板
sudo python3 ultimate_kali_builder.py \
  --username kali \
  --password 'xxx' \
  --rebuild-template

# 查看 VM 列表
qm list
```
