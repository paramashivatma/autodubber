import datetime

def log(tag, msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{tag:<12}] {msg}", flush=True)
