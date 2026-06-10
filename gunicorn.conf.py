import threading

def post_worker_init(worker):
    if int(worker.wid) == 1:
        from bot_control import start_bot
        t = threading.Thread(target=start_bot, daemon=True)
        t.start()
