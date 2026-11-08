"""Start the HoloSafe backend on 0.0.0.0 and print the LAN URLs."""
import socket
import uvicorn


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ip = lan_ip()
    bar = "=" * 64
    print(f"\n{bar}\n  HOLOSAFE online\n"
          f"  Command Center : http://localhost:5173/\n"
          f"  Hologram       : http://localhost:5173/holo\n"
          f"  Phone report   : http://{ip}:5173/report   (same Wi-Fi)\n"
          f"  Backend API    : http://{ip}:8000/health\n{bar}\n", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["app", "hazards", "seed"])
