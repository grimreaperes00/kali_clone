#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 自動化建立 Kali Linux VM 腳本，加入 NLP 指令解析（OpenAI GPT）支援

import os
import re
import sys
import json
import time
import shutil
import subprocess
import argparse
import requests
import openai
from pathlib import Path

TEMPLATE_ID = 9009  # 固定的黃金映像 VM ID

# ========== 檢查 unar ==========
def ensure_unar_available():
    if shutil.which("unar") is not None:
        return  # OK
    print("[WARN] 系統缺少 unar，正在嘗試執行 setup_dependencies.py 自動修復...")
    setup_path = Path("/root/setup_dependencies.py")
    if not setup_path.exists():
        print("[ERROR] 找不到 /root/setup_dependencies.py，無法自動安裝 unar，請手動修復")
        sys.exit(1)
    try:
        subprocess.run(["python3", str(setup_path)], check=True)
    except subprocess.CalledProcessError:
        print("[ERROR] 嘗試執行 setup_dependencies.py 修復 unar 失敗，請手動檢查")
        sys.exit(1)
    if shutil.which("unar") is None:
        print("[ERROR] unar 套件仍未安裝成功，請手動安裝後重試")
        sys.exit(1)
    print("[OK] unar 安裝成功，繼續執行")

# ========== 自然語言轉 CLI 參數 ==========
def parse_nlp_to_args(nlp_instruction: str):
    prompt = f"""
將以下自然語言指令轉換為 JSON 格式參數，對應 CLI 指令中：
--count、--name、--description、--min-mem、--max-mem、--cpu、--bridge、--vlan、--resize、--storage

輸入：「{nlp_instruction}」

請輸出如下：
{{
  "count": 1,
  "name": ["kali-nlp"],
  "description": "Kali NLP VM",
  "min_mem": 4096,
  "max_mem": 8192,
  "cpu": 2,
  "bridge": "vmbr0",
  "vlan": null,
  "resize": "+0G",
  "storage": "local-lvm"
}}
只輸出純 JSON。
"""
    try:
        res = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是參數轉換助手，幫助將中文指令轉成 CLI 所需格式。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
    except Exception as e:
        print(f"[ERROR] 呼叫 OpenAI API 失敗：{e}")
        sys.exit(1)
    result = json.loads(res['choices'][0]['message']['content'])
    defaults = {
        "count": 1,
        "name": ["kali-nlp"],
        "description": "Kali NLP VM",
        "min_mem": 4096,
        "max_mem": 8192,
        "cpu": 2,
        "bridge": "vmbr0",
        "vlan": None,
        "resize": "+0G",
        "storage": "local-lvm"
    }
    for key, val in defaults.items():
        result.setdefault(key, val)
    print("[INFO] 使用 NLP 轉換後參數：")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result

# ========== 從官網抓 Kali 最新版本 ==========
def get_latest_kali_url(base_url: str):
    response = requests.get(base_url)
    dirs = sorted(set(re.findall(r'kali-\d+\.\d+[a-z]?/', response.text)), reverse=True)
    if not dirs:
        raise RuntimeError("無法取得 Kali 最新版本目錄")
    kali_dir = dirs[0].strip('/')
    version = kali_dir.replace("kali-", "")
    filename = f"kali-linux-{version}-qemu-amd64.7z"
    return kali_dir, version, filename, f"{base_url}{kali_dir}/{filename}"

# ========== 自動安裝依賴 ==========
def ensure_installed(package_name):
    if shutil.which(package_name) is None:
        print(f"[INFO] 未安裝 {package_name}，正在安裝 ...")
        subprocess.run(["apt", "update"], check=True)
        subprocess.run(["apt", "install", "-y", package_name], check=True)
    else:
        print(f"[SKIP] 已安裝 {package_name}，跳過安裝")

# ========== VM ID 管理 ==========
def id_in_use(vm_id: int) -> bool:
    vm_conf = Path(f"/etc/pve/qemu-server/{vm_id}.conf")
    ct_conf = Path(f"/etc/pve/lxc/{vm_id}.conf")
    return (
        subprocess.run(["qm", "status", str(vm_id)], stdout=subprocess.DEVNULL).returncode == 0 or
        subprocess.run(["pct", "status", str(vm_id)], stdout=subprocess.DEVNULL).returncode == 0 or
        vm_conf.exists() or
        ct_conf.exists()
    )

def find_available_vm_id(start: int = 100):
    while id_in_use(start):
        start += 1
    return start

# ========== 磁碟容量查詢與單位轉換 ==========
def get_disk_size_gb(vm_id: int, storage: str) -> str:
    result = subprocess.run(["qm", "config", str(vm_id)], stdout=subprocess.PIPE, text=True)
    for line in result.stdout.splitlines():
        if "scsi0:" in line and f"{storage}:" in line:
            for part in line.split(","):
                if part.startswith("size="):
                    return part.split("=")[1]
    return "未知"

def convert_to_gb(size_str: str) -> str:
    if size_str.endswith("G"):
        return size_str
    elif size_str.endswith("M"):
        return f"{float(size_str[:-1]) / 1024:.1f}G"
    elif size_str.endswith("K"):
        return f"{float(size_str[:-1]) / (1024 * 1024):.2f}G"
    return size_str

# ========== 取得 VM 啟動後 IP ==========
def wait_for_ip(vm_id, retries=50, delay=1):
    for _ in range(retries):
        try:
            result = subprocess.run(
                ["qm", "guest", "cmd", str(vm_id), "network-get-interfaces"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for iface in data:
                    if iface.get("name") not in ["eth0", "ens18", "ens3", "enp0s3"]:
                        continue
                    for ip in iface.get("ip-addresses", []):
                        if ip.get("ip-address-type") == "ipv4" and ip.get("ip-address") != "127.0.0.1":
                            return ip.get("ip-address")
        except Exception:
            pass
        time.sleep(delay)
    return "未知"

# ========== 建立模板 ==========
def create_template(args, version):
    vm_id = TEMPLATE_ID
    working_dir = Path(args.workdir).resolve()
    kali_dir, _, filename, kali_url = get_latest_kali_url("https://cdimage.kali.org/")
    iso_path = working_dir / filename
    version_file = working_dir / ".kali_version"

    working_dir.mkdir(parents=True, exist_ok=True)

    qcow2file = next(working_dir.glob("*.qcow2"), None)
    if qcow2file:
        print(f"[INFO] 發現現有的 qcow2 檔案：{qcow2file}，跳過下載與解壓縮")
    else:
        print(f"[INFO] 下載 Kali 映像：{kali_url}")
        subprocess.run(["wget", "-c", "--retry-connrefused", "--tries=5", "--show-progress", kali_url],
                       check=True, cwd=working_dir)
        print("[INFO] 清空工作目錄中其他檔案 ...")
        for f in working_dir.glob("*"):
            if f.name != filename:
                f.unlink()
        print("[INFO] 解壓縮 Kali QEMU 映像 ...")
        subprocess.run(["unar", "-f", filename], check=True, cwd=working_dir)
        qcow2file = next(working_dir.glob("*.qcow2"), None)
        if not qcow2file:
            raise RuntimeError("找不到解壓後的 qcow2 映像")

    if Path(f"/etc/pve/qemu-server/{vm_id}.conf").exists():
        print(f"[INFO] 刪除舊的黃金映像 VM（ID {vm_id}）")
        subprocess.run(["qm", "destroy", str(vm_id)], check=True)

    print("[INFO] 建立黃金映像 VM ...")
    subprocess.run(["qm", "create", str(vm_id),
                    "--memory", str(args.max_mem),
                    "--balloon", str(args.min_mem),
                    "--cores", str(args.cpu),
                    "--name", "kali-template",
                    "--description", "Kali Golden Image Template",
                    "--net0", f"model=virtio,bridge={args.bridge}",
                    "--ostype", "l26",
                    "--machine", "q35"], check=True)
    subprocess.run(["qm", "importdisk", str(vm_id), str(qcow2file), args.storage, "--format", "qcow2"], check=True)
    subprocess.run(["qm", "set", str(vm_id), "--scsi0", f"{args.storage}:vm-{vm_id}-disk-0"], check=True)
    if args.resize != "+0G":
        subprocess.run(["qm", "resize", str(vm_id), "scsi0", args.resize], check=True)
    subprocess.run(["qm", "set", str(vm_id), "--boot", "order=scsi0", "--bootdisk", "scsi0"], check=True)
    subprocess.run(["qm", "template", str(vm_id)], check=True)

    with version_file.open("w") as vf:
        vf.write(version)

    print(f"[OK] Template VM 已建立完成（ID: {vm_id}）")

# ========== 複製 VM ==========
def deploy_vm(args, vm_name, index=None):
    vm_id = find_available_vm_id(100)
    desc = args.description if index is None else f"{args.description} #{index+1}"
    net = f"model=virtio,firewall=0,bridge={args.bridge}"
    if args.vlan:
        net += f",tag={args.vlan}"

    subprocess.run(["qm", "clone", str(TEMPLATE_ID), str(vm_id), "--name", vm_name], check=True)
    subprocess.run(["qm", "set", str(vm_id),
                    "--memory", str(args.max_mem),
                    "--balloon", str(args.min_mem),
                    "--cores", str(args.cpu),
                    "--net0", net,
                    "--description", desc,
                    "--agent", "enabled=1"], check=True)
    subprocess.run(["qm", "start", str(vm_id)], check=True)
    time.sleep(15)  # 等待 15 秒，確保 Guest Agent 啟動
    ip = wait_for_ip(vm_id)
    disk = get_disk_size_gb(vm_id, args.storage)

    return {
        "vm_id": vm_id,
        "name": vm_name,
        "ip": ip,
        "cpu": args.cpu,
        "ram": f"{args.min_mem} ~ {args.max_mem} MB",
        "disk": convert_to_gb(disk)
    }

# ========== 主程式 ==========
if __name__ == "__main__":
    try:
        import openai
    except ImportError:
        print("[ERROR] 尚未安裝 openai 模組，請執行：pip install openai")
        sys.exit(1)
    ensure_unar_available()

    parser = argparse.ArgumentParser(description="建立 Kali Template 並快速複製多台 VM")
    parser.add_argument("--nlp", type=str, help="自然語言描述 VM 建立指令")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--name", nargs='+', default=["kali-vm"])
    parser.add_argument("--description", default="Kali VM auto-generated")
    parser.add_argument("--min-mem", type=int, default=4096)
    parser.add_argument("--max-mem", type=int, default=8192)
    parser.add_argument("--cpu", type=int, default=4)
    parser.add_argument("--bridge", default="vmbr0")
    parser.add_argument("--vlan", type=str)
    parser.add_argument("--resize", default="+0G")
    parser.add_argument("--storage", default="local-lvm")
    parser.add_argument("--workdir", default="/var/lib/vz/template/iso/kali-images")
    args = parser.parse_args()

    if args.nlp:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            key_file = Path("~/.openai_api_key").expanduser()
            if key_file.exists():
                with key_file.open() as f:
                    api_key = f.read().strip()
            else:
                raise RuntimeError("[ERROR] NLP 模式需設定 OPENAI_API_KEY 環境變數或 ~/.openai_api_key")
        openai.api_key = api_key

        parsed_args = parse_nlp_to_args(args.nlp)
        args.count = parsed_args.get("count", 1)
        args.name = parsed_args.get("name", ["kali-nlp"])
        args.description = parsed_args.get("description", "Kali NLP VM")
        args.min_mem = parsed_args.get("min_mem", 4096)
        args.max_mem = parsed_args.get("max_mem", 8192)
        args.cpu = parsed_args.get("cpu", 2)
        args.bridge = parsed_args.get("bridge", "vmbr0")
        args.vlan = parsed_args.get("vlan")
        args.resize = parsed_args.get("resize", "+0G")
        args.storage = parsed_args.get("storage", "local-lvm")

    # 參數驗證
    if args.count < 1:
        raise ValueError("[ERROR] --count 必須大於等於 1")
    if args.min_mem < 512 or args.max_mem < args.min_mem:
        raise ValueError("[ERROR] 記憶體配置無效，請檢查 --min-mem 與 --max-mem")
    if args.cpu < 1:
        raise ValueError("[ERROR] --cpu 必須大於等於 1")
    if args.resize and not re.match(r"^[+-]?\d+[GMK]$", args.resize):
        raise ValueError("[ERROR] --resize 格式無效，請使用類似 +10G 的格式")
    if args.vlan and not args.vlan.isdigit():
        raise ValueError("[ERROR] --vlan 必須是數字")

    # 名稱規則處理
    if len(args.name) == 1:
        vm_names = [args.name[0]] + [f"{args.name[0]}-{i}" for i in range(1, args.count)]
    elif len(args.name) == args.count:
        vm_names = args.name
    else:
        raise ValueError(f"[ERROR] VM 名稱數量（{len(args.name)}）與 --count（{args.count}）不一致")

    working_dir = Path(args.workdir)
    version_file = working_dir / ".kali_version"
    template_conf = Path(f"/etc/pve/qemu-server/{TEMPLATE_ID}.conf")
    qcow2file = next(working_dir.glob("*.qcow2"), None)
    _, version, _, _ = get_latest_kali_url("https://cdimage.kali.org/")

    version_changed = True
    if version_file.exists():
        with version_file.open() as vf:
            if vf.read().strip() == version:
                version_changed = False

    if not template_conf.exists() or not qcow2file or version_changed:
        print(f"[INFO] 偵測到以下情況需建立黃金映像：")
        if not template_conf.exists(): print("  - VM 9000 不存在")
        if not qcow2file: print("  - 缺少 qcow2 映像")
        if version_changed: print(f"  - 發現新版 Kali：{version}")
        create_template(args, version)

    all_vms = []
    for i in range(args.count):
        all_vms.append(deploy_vm(args, vm_names[i], i))

    print("\n=== 所有 Kali VM 建立完成 ===\n")
    for vm in all_vms:
        print(f"📌 VM {vm['name']} (ID: {vm['vm_id']})")
        print(f"🧠 記憶體：{vm['ram']}")
        print(f"🧮 CPU：{vm['cpu']}")
        print(f"💾 磁碟：{vm['disk']}")
        print(f"🌐 IP：{vm['ip']}\n")
