import os
import threading
import tkinter as tk
import asyncio
import speech_recognition as sr
from deep_translator import GoogleTranslator
import edge_tts
from gtts import gTTS
import pygame
import time

pygame.mixer.init()

# ── Colors ───────────────────────────────────────────────────────
BG       = "#0D0F14"
CARD     = "#161920"
CARD2    = "#1E2230"
ACCENT   = "#4F6EF7"
GREEN    = "#22C97A"
RED      = "#F25C5C"
AMBER    = "#F5A623"
PINK     = "#F472B6"
BLUE     = "#60A5FA"
TEXT     = "#F0F2FF"
TEXT_DIM = "#6B7280"
BORDER   = "#2A2F45"

# ── Voice map ────────────────────────────────────────────────────
VOICES = {
    "hi": {"Male": "hi-IN-MadhurNeural", "Female": "hi-IN-SwaraNeural"},
    "pa": {"Male": "pa_male",            "Female": "pa_female"},   # gTTS handles both
    "en": {"Male": "en-IN-PrabhatNeural","Female": "en-IN-NeerjaNeural"},
}

MODES = {
    "EN -> HI": ("en", "hi", "en-IN", "English -> Hindi"),
    "EN -> PA": ("en", "pa", "en-IN", "English -> Punjabi"),
    "HI -> EN": ("hi", "en", "hi-IN", "Hindi -> English"),
    "PA -> EN": ("pa", "en", "pa-IN", "Punjabi -> English"),
}

# ── Shared state — use a dict so threads always read latest value ─
state = {
    "running": False,
    "mode":    "EN -> HI",
    "gender":  "Female",
}

# ── Window ───────────────────────────────────────────────────────
win = tk.Tk()
win.title("TalkSync - Real-Time Voice Translator")
win.geometry("780x670")
win.configure(bg=BG)
win.resizable(False, False)

F_TITLE  = ("Georgia", 22, "bold")
F_SUB    = ("Georgia", 11, "italic")
F_LABEL  = ("Courier New", 9)
F_LOG    = ("Courier New", 10)
F_BTN    = ("Courier New", 11, "bold")
F_MODE   = ("Courier New", 10, "bold")
F_STATUS = ("Courier New", 10)
F_BADGE  = ("Courier New", 8, "bold")

# ── Header ───────────────────────────────────────────────────────
header = tk.Frame(win, bg=BG)
header.pack(fill="x", padx=30, pady=(24, 0))
tk.Label(header, text="TALKSYNC", font=F_TITLE, bg=BG, fg=TEXT).pack(side="left")
tk.Label(header, text=" LIVE ", font=F_BADGE, bg=RED, fg="white",
         padx=6, pady=3).pack(side="left", padx=(10,0), pady=(6,0))
tk.Label(header, text="Real-Time Voice Translator  |  EN / HI / PA",
         font=F_SUB, bg=BG, fg=TEXT_DIM).pack(side="right", pady=(8,0))
tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12,0))

# ── Helper: log + text boxes (defined early so UI functions can use them) ─
translation_count = [0]
voice_name_lbl    = None   # set later
mode_buttons      = {}
gender_btns       = {}

# ── UI helper functions ──────────────────────────────────────────
def log_msg(msg, color=TEXT_DIM):
    ts = time.strftime("%H:%M:%S")
    log_box.config(state="normal")
    log_box.insert("end", f"[{ts}]  {msg}\n")
    log_box.see("end")
    log_box.config(state="disabled")

def append_text(box, text):
    box.config(state="normal")
    box.insert("end", text + "\n")
    box.see("end")
    box.config(state="disabled")

def clear_box(box):
    box.config(state="normal")
    box.delete("1.0", "end")
    box.config(state="disabled")

def set_status(text, color=TEXT_DIM):
    status_lbl.config(text=text, fg=color)
    dot_canvas.itemconfig(dot, fill=color)

def update_buttons(running):
    if running:
        start_btn.config(state="disabled", bg=CARD2, fg=TEXT_DIM)
        stop_btn.config(state="normal",    bg=RED,   fg="white")
    else:
        start_btn.config(state="normal",   bg=GREEN, fg="#0D1A12")
        stop_btn.config(state="disabled",  bg=CARD2, fg=TEXT_DIM)

def update_voice_label():
    if voice_name_lbl is None:
        return
    tgt   = MODES[state["mode"]][1]
    vname = VOICES[tgt][state["gender"]]
    voice_name_lbl.config(text=f"  voice: {vname}")

# ── Mode selector ────────────────────────────────────────────────
mode_frame = tk.Frame(win, bg=BG)
mode_frame.pack(fill="x", padx=30, pady=(16,0))
tk.Label(mode_frame, text="TRANSLATION MODE", font=F_LABEL,
         bg=BG, fg=TEXT_DIM).pack(anchor="w")
btn_row = tk.Frame(mode_frame, bg=BG)
btn_row.pack(anchor="w", pady=(6,0))

def select_mode(m):
    was_running = state["running"]
    state["running"] = False          # signal current thread to stop
    state["mode"]    = m              # update mode immediately

    clear_box(input_box)
    clear_box(output_box)

    for k, b in mode_buttons.items():
        b.config(bg=ACCENT if k==m else CARD2,
                 fg="white" if k==m else TEXT_DIM)
    update_voice_label()
    log_msg(f"Mode: {MODES[m][3]}", ACCENT)

    if was_running:
        state["running"] = True
        update_buttons(running=True)
        threading.Thread(target=translation_loop, daemon=True).start()
    else:
        update_buttons(running=False)

for i, key in enumerate(MODES.keys()):
    b = tk.Button(btn_row, text=key, font=F_MODE,
                  bg=CARD2, fg=TEXT_DIM,
                  activebackground=ACCENT, activeforeground="white",
                  relief="flat", bd=0, padx=16, pady=8,
                  cursor="hand2", command=lambda k=key: select_mode(k))
    b.grid(row=0, column=i, padx=(0,8))
    mode_buttons[key] = b

# highlight default
mode_buttons["EN -> HI"].config(bg=ACCENT, fg="white")

# ── Gender selector ──────────────────────────────────────────────
tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(14,0))
voice_row = tk.Frame(win, bg=BG)
voice_row.pack(fill="x", padx=30, pady=(12,0))
tk.Label(voice_row, text="OUTPUT VOICE", font=F_LABEL,
         bg=BG, fg=TEXT_DIM).pack(side="left", padx=(0,14))

def select_gender(g):
    was_running      = state["running"]
    state["running"] = False
    state["gender"]  = g              # update gender immediately

    gender_btns["Female"].config(bg=PINK if g=="Female" else CARD2,
                                  fg="white" if g=="Female" else TEXT_DIM)
    gender_btns["Male"].config(bg=BLUE if g=="Male" else CARD2,
                                fg="white" if g=="Male" else TEXT_DIM)
    update_voice_label()
    log_msg(f"Voice: {g}", ACCENT)

    if was_running:
        state["running"] = True
        update_buttons(running=True)
        threading.Thread(target=translation_loop, daemon=True).start()

for g, color in [("Female", PINK), ("Male", BLUE)]:
    b = tk.Button(voice_row,
                  text="F  Female" if g=="Female" else "M  Male",
                  font=F_MODE,
                  bg=PINK if g=="Female" else CARD2,
                  fg="white" if g=="Female" else TEXT_DIM,
                  activebackground=color, activeforeground="white",
                  relief="flat", bd=0, padx=14, pady=7,
                  cursor="hand2", command=lambda x=g: select_gender(x))
    b.pack(side="left", padx=(0,8))
    gender_btns[g] = b

voice_name_lbl = tk.Label(voice_row, text="", font=F_LABEL, bg=BG, fg=TEXT_DIM)
voice_name_lbl.pack(side="left", padx=(4,0))
update_voice_label()
tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12,0))

# ── Text panels ──────────────────────────────────────────────────
panels = tk.Frame(win, bg=BG)
panels.pack(fill="both", padx=30, pady=(14,0))

def make_panel(parent, label_text, col):
    f = tk.Frame(parent, bg=CARD, bd=0, highlightthickness=1,
                 highlightbackground=BORDER)
    f.grid(row=0, column=col, padx=(0,8) if col==0 else (8,0), sticky="nsew")
    parent.columnconfigure(col, weight=1)
    hdr = tk.Frame(f, bg=CARD2, pady=6)
    hdr.pack(fill="x")
    tk.Label(hdr, text=label_text, font=F_LABEL,
             bg=CARD2, fg=TEXT_DIM).pack(side="left", padx=12)
    box = tk.Text(f, height=6, font=F_LOG, bg=CARD, fg=TEXT,
                  insertbackground=TEXT, relief="flat", bd=0,
                  padx=12, pady=10, wrap="word", state="disabled",
                  selectbackground=ACCENT)
    box.pack(fill="both", expand=True)
    return box

input_box  = make_panel(panels, "o  RECOGNIZED SPEECH", 0)
output_box = make_panel(panels, "o  TRANSLATED OUTPUT",  1)

# ── Activity log ─────────────────────────────────────────────────
log_frame = tk.Frame(win, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
log_frame.pack(fill="x", padx=30, pady=(12,0))
log_hdr = tk.Frame(log_frame, bg=CARD2, pady=5)
log_hdr.pack(fill="x")
tk.Label(log_hdr, text="o  ACTIVITY LOG", font=F_LABEL,
         bg=CARD2, fg=TEXT_DIM).pack(side="left", padx=12)
log_box = tk.Text(log_frame, height=3, font=F_LOG, bg=CARD, fg=TEXT_DIM,
                  relief="flat", bd=0, padx=12, pady=8,
                  state="disabled", wrap="word")
log_box.pack(fill="x")

# ── Status bar ───────────────────────────────────────────────────
status_frame = tk.Frame(win, bg=BG)
status_frame.pack(fill="x", padx=30, pady=(10,0))
dot_canvas = tk.Canvas(status_frame, width=10, height=10, bg=BG, highlightthickness=0)
dot_canvas.pack(side="left", pady=4)
dot = dot_canvas.create_oval(1, 1, 9, 9, fill=TEXT_DIM, outline="")
status_lbl = tk.Label(status_frame, text="Idle  --  select a mode and press Start",
                      font=F_STATUS, bg=BG, fg=TEXT_DIM)
status_lbl.pack(side="left", padx=(6,0))
session_lbl = tk.Label(status_frame, text="Session: 0 translations",
                       font=F_STATUS, bg=BG, fg=TEXT_DIM)
session_lbl.pack(side="right")

# ── TTS functions ────────────────────────────────────────────────
async def _edge_tts(text, voice):
    await edge_tts.Communicate(text, voice).save("voice.mp3")

def play_audio(filename):
    time.sleep(0.2)
    if not os.path.exists(filename):
        log_msg(f"Audio file missing: {filename}", RED)
        return
    try:
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        log_msg(f"Playback error: {e}", RED)
    finally:
        try: os.remove(filename)
        except: pass

def speak(text, tgt_lang, gender):
    """gender is passed in explicitly — no global read inside this function."""
    if tgt_lang == "pa":
        # gTTS has real Punjabi voice — no gender choice but works perfectly
        try:
            gTTS(text=text, lang="pa").save("voice_pa.mp3")
            play_audio("voice_pa.mp3")
        except Exception as e:
            log_msg(f"gTTS error: {e}", RED)
    else:
        voice = VOICES[tgt_lang][gender]
        log_msg(f"Voice: {voice}", TEXT_DIM)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_edge_tts(text, voice))
        finally:
            loop.close()
        play_audio("voice.mp3")

# ── Translation loop ─────────────────────────────────────────────
def translation_loop():
    r = sr.Recognizer()
    r.pause_threshold = 0.8
    log_msg(f"Started  |  {MODES[state['mode']][3]}  |  {state['gender']} voice", ACCENT)

    while state["running"]:
        # Read FRESH values from state dict on every iteration
        mode   = state["mode"]
        gender = state["gender"]
        src_lang, tgt_lang, rec_lang, _ = MODES[mode]

        try:
            with sr.Microphone() as source:
                set_status("Listening...", GREEN)
                r.adjust_for_ambient_noise(source, duration=0.4)
                audio = r.listen(source, timeout=6, phrase_time_limit=12)

            if not state["running"]: break

            set_status("Processing...", AMBER)
            speech = r.recognize_google(audio, language=rec_lang)

            if speech.lower() in {"exit", "stop", "quit", "band karo"}:
                log_msg("Stopped by voice command", AMBER)
                state["running"] = False
                break

            append_text(input_box, speech)
            log_msg(f"Heard: {speech[:55]}{'...' if len(speech)>55 else ''}")

            translated = GoogleTranslator(source=src_lang, target=tgt_lang).translate(speech)
            append_text(output_box, translated)
            log_msg(f"Translated: {translated[:50]}{'...' if len(translated)>50 else ''}", TEXT)

            translation_count[0] += 1
            session_lbl.config(text=f"Session: {translation_count[0]} translations")

            if not state["running"]: break

            set_status("Speaking...", ACCENT)
            speak(translated, tgt_lang, gender)   # pass gender explicitly

        except sr.WaitTimeoutError:
            set_status("Listening...  (no speech detected)", GREEN)
        except sr.UnknownValueError:
            log_msg("Could not understand - speak clearly", RED)
        except sr.RequestError:
            log_msg("Network error - check internet", RED)
        except Exception as e:
            log_msg(f"Error: {e}", RED)

    # Only reset UI if this thread was the one that stopped (not replaced)
    if not state["running"]:
        set_status("Idle  --  select a mode and press Start", TEXT_DIM)
        update_buttons(running=False)

# ── Control buttons ──────────────────────────────────────────────
def start():
    if not state["running"]:
        state["running"] = True
        update_buttons(running=True)
        threading.Thread(target=translation_loop, daemon=True).start()

def stop():
    state["running"] = False
    log_msg("Stopped", AMBER)
    set_status("Stopped", RED)
    update_buttons(running=False)

def clear_all():
    clear_box(input_box)
    clear_box(output_box)
    log_msg("Cleared", TEXT_DIM)

ctrl = tk.Frame(win, bg=BG)
ctrl.pack(fill="x", padx=30, pady=(12,20))

start_btn = tk.Button(ctrl, text="START TRANSLATION", font=F_BTN,
                      bg=GREEN, fg="#0D1A12", activebackground="#1aab68",
                      relief="flat", bd=0, padx=20, pady=10,
                      cursor="hand2", command=start)
start_btn.pack(side="left", padx=(0,10))

stop_btn = tk.Button(ctrl, text="STOP", font=F_BTN,
                     bg=CARD2, fg=TEXT_DIM, activebackground=RED,
                     relief="flat", bd=0, padx=20, pady=10,
                     cursor="hand2", command=stop, state="disabled")
stop_btn.pack(side="left", padx=(0,10))

tk.Button(ctrl, text="CLEAR", font=F_BTN,
          bg=CARD2, fg=TEXT_DIM, activebackground=CARD,
          relief="flat", bd=0, padx=20, pady=10,
          cursor="hand2", command=clear_all).pack(side="left")

tk.Label(ctrl, text='say "stop" or "band karo" to pause with voice',
         font=F_LABEL, bg=BG, fg=TEXT_DIM).pack(side="right", pady=6)

log_msg("TalkSync ready  |  select mode, pick a voice, press Start", ACCENT)
win.mainloop()