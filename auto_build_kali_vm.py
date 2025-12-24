#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 自動化建立 Kali Linux VM 腳本 - Finalized by Grim Reaper

import os
import re
import subprocess
import requests
import argparse
import json
import time
import shutil
from pathlib import Path

def ensure_installed(package_name):
    """確保必要套件已安裝"""
    if shutil.which(package_name) is None:
        print(f"[INFO] 缺失組件 {package_name}，執行補完計劃 ...")
        subprocess.run(["apt", "update"], check=True)
        subprocess.run(["apt", "install", "-y", package_name], check=True)

def get_latest_kali_url(base_url: str):
    """從混沌網路中擷取最新的 Kali 映像連結"""
    try:
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"無法連接至映像站點，網路路徑阻斷: {e}")

    dirs = sorted(set(re.findall(r'kali-\d+\.\d+[a-z]?/', response.text)), reverse=True)
    if not dirs:
        raise RuntimeError("來源路徑異常，無法識別版本特徵")
    
    kali_dir = dirs[0].strip('/')
    version = kali_dir.replace("kali-", "")
    filename = f"kali-linux-{version}-qemu-amd64.7z"
    return kali_dir, version, filename, f"{base_url}{kali_dir}/{filename}"

def find_available_vm_id(start_vmid):
    """在虛空之中尋找可用的 ID 落點"""
    if start_vmid < 100:
        print(f"[WARN] 起始 ID ({start_vmid}) 違反安全協議，強制修正為 100")
        start_vmid = 100

    used_vmids = set()
    
    # 掃描 QEMU 與 LXC 實體
    for cmd in ['qm list', 'pct list']:
        try:
            out = subprocess.check_output(cmd, shell=True, text=True)
            for line in out.splitlines()[1:]:
                m = re.match(r'\s*(\d+)', line)
                if m: used_vmids.add(int(m.group(1)))
        except Exception: pass
    
    # 掃描殘留的設定檔碎片
    from glob import glob
    for conf_path in glob('/etc/pve/nodes/*/*/*.conf'):
        try: used_vmids.add(int(Path(conf_path).stem))
        except: pass

    vmid = start_vmid
    while vmid in used_vmids:
        vmid += 1
    return vmid

def wait_for_ip(vm_id, retries=50, delay=2):
    """監聽 Guest Agent 的頻率，等待網路介面初始化"""
    for _ in range(retries):
        try:
            result = subprocess.run(
                ["qm", "guest", "cmd", str(vm_id), "network-get-interfaces"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for iface in data:
                    if iface.get("name") not in ["eth0", "ens18", "ens3", "enp0s3"]: continue
                    for ip in iface.get("ip-addresses", []):
                        if ip.get("ip-address-type") == "ipv4" and ip.get("ip-address") != "127.0.0.1":
                            return ip.get("ip-address")
        except Exception: pass
        time.sleep(delay)
    return "未知"

def format_disk_size(size_str):
    """標準化磁碟單位，確保回傳值帶有 G"""
    if not size_str: return None
    # 移除現有單位以便重新格式化
    clean_size = re.sub(r'[gGmMkK]', '', str(size_str))
    if clean_size.isdigit():
        return f"{clean_size}G"
    return size_str

def get_vm_disk_size_gb(vm_id):
    """[Intelligence] 讀取 VM 實際磁碟大小 (GiB)"""
    try:
        out = subprocess.check_output(["qm", "config", str(vm_id)], text=True)
        for line in out.splitlines():
            # 抓取 scsi0, ide0, virtio0 等硬碟配置
            if "size=" in line and ("scsi" in line or "virtio" in line or "ide" in line):
                match = re.search(r'size=(\d+(\.\d+)?)', line)
                if match:
                    size_val = float(match.group(1))
                    # PVE config 通常預設單位是 G，若是 M 需轉換
                    if "M" in line: return size_val / 1024
                    if "K" in line: return size_val / 1048576
                    return size_val
    except Exception:
        pass
    return 0.0

def create_template(args, version):
    """鑄造黃金映像 (Template)"""
    vm_id = args.template_id
    working_dir = Path(args.template_dir).resolve()
    _, _, filename, kali_url = get_latest_kali_url("https://cdimage.kali.org/")
    
    working_dir.mkdir(parents=True, exist_ok=True)
    qcow2file = next(working_dir.glob("*.qcow2"), None)

    if not qcow2file:
        print(f"[ACTION] 擷取原始映像：{kali_url}")
        subprocess.run(["wget", "-c", "--show-progress", kali_url], check=True, cwd=working_dir)
        print("[ACTION] 解構壓縮檔 ...")
        subprocess.run(["unar", "-f", filename], check=True, cwd=working_dir)
        qcow2file = next(working_dir.glob("*.qcow2"), None)
        if not qcow2file: raise RuntimeError("解構失敗，實體丟失")

    if Path(f"/etc/pve/qemu-server/{vm_id}.conf").exists():
        print(f"[WARN] 銷毀舊版 Template (ID {vm_id})")
        subprocess.run(["qm", "destroy", str(vm_id)], check=True)

    print("[ACTION] 建構 Template 核心結構 ...")
    subprocess.run(["qm", "create", str(vm_id),
                    "--memory", str(args.template_memory),
                    "--cores", str(args.template_core),
                    "--name", args.template_name,
                    "--net0", f"model=virtio,bridge={args.template_bridge}",
                    "--ostype", "l26", "--machine", "q35"], check=True)
    
    print(f"[ACTION] 注入磁碟至 {args.template_storage} ...")
    subprocess.run(["qm", "importdisk", str(vm_id), str(qcow2file), args.template_storage, "--format", "qcow2"], check=True)
    subprocess.run(["qm", "set", str(vm_id), "--scsi0", f"{args.template_storage}:vm-{vm_id}-disk-0"], check=True)
    
    # Template 階段也加入防呆，避免不必要的 resize 錯誤
    disk_size_str = format_disk_size(args.template_disk)
    if disk_size_str:
        current_size = get_vm_disk_size_gb(vm_id)
        target_size = float(disk_size_str.rstrip('G'))
        
        if target_size > current_size:
            print(f"[INFO] 設定 Template 磁碟基準為 {disk_size_str}")
            subprocess.run(["qm", "resize", str(vm_id), "scsi0", disk_size_str], check=True)
        else:
            print(f"[INFO] Template 原始大小 ({current_size:.2f}G) 已滿足設定 ({target_size}G)，跳過調整")

    subprocess.run(["qm", "set", str(vm_id), "--boot", "order=scsi0", "--bootdisk", "scsi0"], check=True)
    subprocess.run(["qm", "template", str(vm_id)], check=True)
    
    with (working_dir / ".kali_version").open("w") as vf:
        vf.write(version)
    print(f"[OK] 黃金映像 {vm_id} 鑄造完成")

def deploy_vm(args, vm_name, index):
    """根據參數裂變出新的實體 (VM)"""
    vm_id = find_available_vm_id(args.start_vmid)
    
    desc = f"{args.description} #{index+1}"
    net = f"model=virtio,firewall=0,bridge={args.bridge},tag={args.vlan}"

    print(f"[ACTION] 部署 VM: {vm_name} (ID: {vm_id}) 來源: {args.template_id} ...")
    subprocess.run(["qm", "clone", str(args.template_id), str(vm_id), "--name", vm_name], check=True)
    
    # 重塑個體參數
    subprocess.run(["qm", "set", str(vm_id),
                    "--memory", str(args.memory),
                    "--cores", str(args.core),
                    "--net0", net,
                    "--description", desc,
                    "--agent", "enabled=1"], check=True)
    
    # [Logic Core] 智慧磁碟調整
    target_disk_str = format_disk_size(args.disk)
    if target_disk_str:
        current_gb = get_vm_disk_size_gb(vm_id)
        # 移除 'G' 單位並轉為 float 進行數值比對
        target_gb = float(target_disk_str.replace('G', ''))
        
        # 只有在目標大於現狀時才執行
        if target_gb > current_gb:
            print(f"[INFO] 執行擴容：{current_gb:.2f}G -> {target_gb}G")
            try:
                subprocess.run(["qm", "resize", str(vm_id), "scsi0", target_disk_str], check=True)
            except subprocess.CalledProcessError:
                print(f"[WARN] 擴容指令被拒絕，請檢查儲存空間或參數。")
        elif target_gb < current_gb:
            print(f"[WARN] 目標 ({target_gb}G) 小於來源 ({current_gb:.2f}G)，系統忽略縮容請求。")
        else:
            print(f"[INFO] 磁碟大小相符 ({current_gb:.2f}G)，無需調整。")

    print(f"[INFO] 喚醒 VM {vm_id} ...")
    subprocess.run(["qm", "start", str(vm_id)], check=True)
    time.sleep(10)
    ip = wait_for_ip(vm_id)

    return {"id": vm_id, "name": vm_name, "ip": ip}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建立 Kali Template 並快速複製多台 VM")
    parser.add_argument("--description", default="Kali VM auto-generated")
    
    # === Template 戰略參數 ===
    parser.add_argument('--template-id', type=int, default=9000)
    parser.add_argument('--template-dir', default=os.environ.get('TEMPLATE_DIR', '/var/lib/vz/template/iso/kali-images'))
    parser.add_argument('--template-storage', default=os.environ.get('TEMPLATE_STORAGE', 'local-lvm'))
    parser.add_argument('--template-name', default='kali-template')
    parser.add_argument('--template-bridge', default=os.environ.get('TEMPLATE_BRIDGE', 'vmbr0'))
    parser.add_argument('--template-memory', type=int, default=4096)
    parser.add_argument('--template-core', type=int, default=2)
    parser.add_argument('--template-disk', default='80G')

    # === VM 部署戰術參數 ===
    parser.add_argument('--vmname', nargs='+', default=["kali-vm"], help="VM 名稱列表")
    parser.add_argument('--start-vmid', type=int, default=100)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--core', type=int, default=4)
    parser.add_argument('--memory', type=int, default=8192)
    parser.add_argument('--disk', default='80G')
    parser.add_argument("--bridge", default="vmbr3")
    parser.add_argument("--vlan", type=str, default="100")

    args = parser.parse_args()

    ensure_installed("unar")

    # 名稱序列邏輯驗證
    if len(args.vmname) == 1:
        if args.count == 1:
            vm_names = [args.vmname[0]]
        else:
            vm_names = [f"{args.vmname[0]}-{i+1}" for i in range(args.count)]
    elif len(args.vmname) == args.count:
        vm_names = args.vmname
    else:
        raise ValueError(f"[ERROR] 名稱數量 ({len(args.vmname)}) 與部署數量 ({args.count}) 戰略不匹配")

    # Template 狀態檢查與建構
    try:
        _, version, _, _ = get_latest_kali_url("https://cdimage.kali.org/")
    except Exception as e:
        print(f"[WARN] 外部連結失效，轉為離線模式: {e}")
        version = "unknown"

    version_file = Path(args.template_dir) / ".kali_version"
    current_ver = version_file.read_text().strip() if version_file.exists() else None
    
    template_conf = Path(f"/etc/pve/qemu-server/{args.template_id}.conf")
    # 這裡的邏輯：如果 Template 不存在，或者版本更新了，就重建
    if not template_conf.exists() or (version != "unknown" and current_ver != version):
        create_template(args, version)

    # 執行部署序列
    results = []
    for i in range(args.count):
        results.append(deploy_vm(args, vm_names[i], i))

    print("\n=== 部署任務總結 ===")
    for r in results:
        print(f"ID: {r['id']} | Name: {r['name']} | IP: {r['ip']}")