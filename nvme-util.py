#!/usr/bin/env python3
import subprocess
import shutil
import json
import argparse

# -------------------
# Helpers
# -------------------
def run_json(cmd):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except Exception as e:
        print(f"Error running {cmd}: {e}")
        return None

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        print(f"Error running {cmd}: {e}")
        return None

def human_bytes(n):
    if not isinstance(n, int) or n < 0:
        return "Unknown"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(n)
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.1f}{units[i]}"

# -------------------
# NVMe functions
# -------------------
def detect_nvme_devices():
    if not shutil.which("nvme"):
        print("nvme-cli not installed. Run: sudo apt install nvme-cli")
        return []
    data = run_json(["nvme", "list", "-o", "json"])
    if not data or "Devices" not in data:
        return []
    results = []
    for d in data["Devices"]:
        results.append({
            "device": d.get("DevicePath"),
            "model": d.get("ModelNumber", "Unknown"),
            "serial": d.get("SerialNumber", "Unknown"),
            "firmware": d.get("Firmware", "Unknown"),
            "capacity_bytes": d.get("PhysicalSize") or d.get("UsedBytes"),
        })
    return results

def get_smart_info(device):
    return run_json(["nvme", "smart-log", device, "-o", "json"])

def get_error_log(device):
    return run_json(["nvme", "error-log", device, "-o", "json"])

def get_fw_log(device):
    """Return a list of firmware slots (handle missing keys)"""
    fw = run_json(["nvme", "fw-log", device, "-o", "json"])
    slots = []
    if fw and "fw_log" in fw and isinstance(fw["fw_log"], list):
        for i, s in enumerate(fw["fw_log"]):
            if isinstance(s, dict):
                slots.append({
                    "slot": i + 1,
                    "revision": s.get("revision", "Unknown"),
                    "valid": s.get("valid", "Unknown"),
                    "active": s.get("active", "Unknown")
                })
    return slots

def get_self_test_log(device):
    return run_json(["nvme", "device-self-test", device, "-n", "0", "-o", "json"])

def start_self_test(device, mode="short"):
    test_code = "1" if mode == "short" else "2"
    print(f"Starting {mode} self-test on {device}...")
    return run_cmd(["nvme", "device-self-test", device, "-s", test_code])

# -------------------
# Printers
# -------------------
def print_device_info(dev):
    cap = human_bytes(dev["capacity_bytes"]) if dev["capacity_bytes"] else "Unknown"
    print(f"\n=== {dev['device']} ===")
    print(f"Model: {dev['model']}")
    print(f"Serial: {dev['serial']}")
    print(f"Firmware: {dev['firmware']}")
    print(f"Capacity: {cap}")

    # SMART
    smart = get_smart_info(dev["device"])
    if smart:
        print("\n--- SMART / Health Info ---")
        temp = smart.get("temperature")
        print(f"Temperature: {temp} K ({temp-273.15:.1f} ¢XC)" if temp else "Temperature: Unknown")
        print(f"Available Spare: {smart.get('avail_spare')}% (Threshold: {smart.get('spare_thresh')}%)")
        print(f"Percentage Used: {smart.get('percent_used')}%")
        print(f"Data Units Read: {smart.get('data_units_read')}")
        print(f"Data Units Written: {smart.get('data_units_written')}")
        print(f"Power Cycles: {smart.get('power_cycles')}")
        print(f"Power On Hours: {smart.get('power_on_hours')}")
        print(f"Unsafe Shutdowns: {smart.get('unsafe_shutdowns')}")
        print(f"Media Errors: {smart.get('media_errors')}")
        print(f"Error Log Entries: {smart.get('num_err_log_entries')}")

    # Error log
    err = get_error_log(dev["device"])
    if err:
        print("\n--- Error Log ---")
        entries = err.get("error_log") or []
        if entries:
            for e in entries:
                print(f"  ErrorCount={e.get('error_count')}, CmdID={e.get('cid')}, Status={e.get('status')}")
        else:
            print("  No errors logged.")

    # Firmware log
    fw_slots = get_fw_log(dev["device"])
    if fw_slots:
        print("\n--- Firmware Slots ---")
        for s in fw_slots:
            print(f"  Slot {s['slot']}: Revision={s['revision']}, Active={s['active']}, Valid={s['valid']}")

    # Self-test status
    st = get_self_test_log(dev["device"])
    if st:
        print("\n--- Device Self-Test Status ---")
        print(f"Current Operation: {st.get('current_operation', 'Unknown')}")
        print(f"Last Result: {st.get('result', 'Unknown')}")

# -------------------
# Main
# -------------------
def main():
    parser = argparse.ArgumentParser(description="NVMe SSD Inspector")
    parser.add_argument("--self-test", choices=["short", "long"], help="Run self-test on all NVMe drives")
    args = parser.parse_args()

    devices = detect_nvme_devices()
    if not devices:
        print("No NVMe devices found.")
        return
    print(f"Detected {len(devices)} NVMe SSD(s).")

    for dev in devices:
        print_device_info(dev)
        if args.self_test:
            result = start_self_test(dev["device"], args.self_test)
            if result:
                print(f"\nSelf-test command output:\n{result}")

if __name__ == "__main__":
    main()
