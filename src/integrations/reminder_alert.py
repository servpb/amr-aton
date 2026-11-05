"""Local popup delivery in an isolated process; never executes reminder text."""
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

_processes = []
_lock = threading.Lock()


def show_reminder_alert(item, db_path, *, allow_sound, audio_event):
    """Return after UI readiness; failure leaves caller free to use a tray fallback."""
    with _lock:
        _processes[:] = [p for p in _processes if p.poll() is None]
        if len(_processes) >= 3:
            raise RuntimeError("alert_capacity")
        process = subprocess.Popen([sys.executable, "-m", "src.integrations.reminder_alert"],
            cwd=str(Path(__file__).resolve().parents[2]), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        _processes.append(process)
    ready = queue.Queue(maxsize=1)
    audio_done = threading.Event()
    def watch():
        try:
            for line in process.stdout:
                event=line.strip()
                if event == "READY":
                    ready.put(True)
                elif event in ("AUDIO_START", "AUDIO_END"):
                    audio_event(event == "AUDIO_START")
                    if event == "AUDIO_END": audio_done.set()
        finally:
            audio_event(False)
            audio_done.set()
            process.stdout.close()
    threading.Thread(target=watch,daemon=True).start()
    try:
        process.stdin.write(json.dumps({"id":item["id"],"db_path":str(db_path),
                                       "sound":bool(allow_sound)}))
        process.stdin.close()
        ready.get(timeout=8)
        if allow_sound:
            audio_done.wait(timeout=35)
    except Exception:
        process.terminate()
        raise RuntimeError("alert_not_ready") from None


def main():
    import tkinter as tk
    from tkinter import ttk
    from datetime import datetime
    from src.core.reminders import ReminderStore
    payload=json.loads(sys.stdin.read(4096))
    store=ReminderStore(payload["db_path"])
    item=store.get(payload["id"])
    if not item or item["state"] not in ("delivering","notified"):
        return
    root=tk.Tk()
    root.title("Aton — lembrete")
    root.geometry("480x270")
    root.minsize(420,250)
    root.attributes("-topmost",True)
    frame=ttk.Frame(root,padding=22);frame.pack(fill="both",expand=True)
    ttk.Label(frame,text="Você tem um lembrete",font=("Segoe UI",14,"bold")).pack(anchor="w")
    ttk.Label(frame,text=item["title"],wraplength=425,font=("Segoe UI",12)).pack(anchor="w",pady=14)
    due=datetime.fromtimestamp(item["due_at"]).astimezone().strftime("%d/%m às %H:%M")
    ttk.Label(frame,text="Horário previsto: "+due).pack(anchor="w")
    status=tk.StringVar(value="")
    ttk.Label(frame,textvariable=status,wraplength=420).pack(anchor="w",pady=8)
    stopped=threading.Event()
    speech_thread=[None]
    def close():
        stopped.set()
        if speech_thread[0] is not None:
            speech_thread[0].join(timeout=0.5)
        root.destroy()
    def act(action):
        try:
            if store.respond_to_alert(item["id"],action): close()
            else: status.set("Este aviso já foi atualizado. Pode fechar a janela.")
        except Exception:
            status.set("Não foi possível salvar. Tente novamente.")
    buttons=ttk.Frame(frame);buttons.pack(side="bottom",fill="x")
    ttk.Button(buttons,text="Concluir",command=lambda:act("complete")).pack(side="left")
    ttk.Button(buttons,text="Adiar 10 minutos",command=lambda:act("snooze")).pack(side="left",padx=8)
    ttk.Button(buttons,text="Fechar",command=close).pack(side="right")
    root.protocol("WM_DELETE_WINDOW",close)
    def speak():
        print("AUDIO_START",flush=True)
        try:
            import winsound
            import comtypes
            from comtypes.client import CreateObject
            comtypes.CoInitialize()
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                voice=CreateObject("SAPI.SpVoice",dynamic=True)
                voice.Rate=3  # Moderately faster than the Windows default (0).
                for token in voice.GetVoices():
                    if "416" in token.GetAttribute("Language").lower().split(";"):
                        voice.Voice=token;break
                # Async + IsNotXML: titles remain literal data, never SSML/code.
                voice.Speak("Você tem um lembrete: "+item["title"],17)
                import time
                deadline=time.monotonic()+30
                while not voice.WaitUntilDone(100):
                    if stopped.is_set() or time.monotonic()>deadline:
                        voice.Speak("",3);break
            finally: comtypes.CoUninitialize()
        except Exception:
            pass  # The visible reminder remains usable if speech is unavailable.
        finally: print("AUDIO_END",flush=True)
    print("READY",flush=True)
    if payload.get("sound"):
        def start_speech():
            speech_thread[0]=threading.Thread(target=speak,daemon=True)
            speech_thread[0].start()
        root.after(250,start_speech)
    root.mainloop()


if __name__ == "__main__":
    main()
