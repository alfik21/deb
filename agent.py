#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import datetime
import socket
from pathlib import Path
import subprocess
import getpass

# Bezpieczny import openai
#try:
import openai
#except ImportError:
 #   print("❌ Błąd: Brak biblioteki 'openai'. Zainstaluj: pip install openai")
 #   openai = None

# ======= IMPORTY TWOICH MODUŁÓW =======
from modules.system import run as system_run
from modules.intent_router import detect_intent
from modules.model_router import query_model
from modules.mode_manager import load_state
from modules.memory_store import remember
from modules.status_monitor import tool_STATUS_MONITOR
# ####--- RDZEŃ LYRY: INTEGRACJA DUSZY I PAMIĘCI ---####
# Łączymy system z plikami, które masz w folderze /jądro
try:
    from jądro.zarzadca_pamieci import pamiec as LyraMemory
    # Zarządcę duszy zaraz dopiszemy, jeśli go nie masz
    print("✅ [SYSTEM]: Moduł pamięci zintegrowany z jądra.")
except ImportError as e:
    print(f"⚠️ [UWAGA]: Problem z importem jądra: {e}")
    LyraMemory = None

# Importujemy nasze moduły z katalogu /jądro/
from jądro.zarzadca_duszy import zarzadca as LyraSoul


# Zarządzanie modelami
from modules.model_switcher import tool_MODEL_SWITCHER, get_active_local_model_name, tool_SCAN_MODELS
from modules.model_list import tool_MODEL_LIST
from modules.model_profiles import choose_best_model

# Narzędzia (Tools)
from modules.app_tools import tool_APP_CONTROL



from modules.audio_tools import tool_AUDIO_DIAG, tool_AUDIO_FIX
from modules.net_tools import tool_NET_INFO, tool_NET_DIAG, tool_NET_FIX
from modules.system_tools import tool_SYSTEM_DIAG, tool_SYSTEM_FIX, tool_AUTO_OPTIMIZE
from modules.disk_tools import tool_DISK_DIAG
from modules.log_analyzer import tool_LOG_ANALYZE
from modules.tmux_tools import tool_TMUX_SCREEN_DIAG
from modules.voice_input import tool_VOICE_INPUT
from modules.memory_ai import tool_MEMORY_ANALYZE
from modules.desktop_tools import tool_DESKTOP_DIAG, tool_DESKTOP_FIX

# ======= KONFIGURACJA I STANY =======
BAZOWY_KATALOG = Path(__file__).resolve().parent
PLIK_USTAWIENIA = BAZOWY_KATALOG / "config.json"
CURRENT_MODE = "lyra"  # Domyślny tryb startowy: lyra, bash, code

SYSTEM_TOOLS = {
    "DISK_DIAG": tool_DISK_DIAG,
    "NET_INFO": tool_NET_INFO,
    "NET_DIAG": tool_NET_DIAG,
    "NET_FIX": tool_NET_FIX,
    "AUDIO_DIAG": tool_AUDIO_DIAG,
    "AUDIO_FIX": tool_AUDIO_FIX,
    "SYSTEM_DIAG": tool_SYSTEM_DIAG,
    "SYSTEM_FIX": tool_SYSTEM_FIX,
    "AUTO_OPTIMIZE": tool_AUTO_OPTIMIZE,
    "APP_CONTROL": tool_APP_CONTROL,
    "LOG_ANALYZE": tool_LOG_ANALYZE,
    "TMUX_DIAG": tool_TMUX_SCREEN_DIAG,
    "VOICE_INPUT": tool_VOICE_INPUT,
    "MEMORY_ANALYZE": tool_MEMORY_ANALYZE,
    "DESKTOP_DIAG": tool_DESKTOP_DIAG,
    "DESKTOP_FIX": tool_DESKTOP_FIX,
    "STATUS": tool_STATUS_MONITOR
}

# ======= FUNKCJE POMOCNICZE =======

def log_event(msg, filename="agent.log"):
    log_path = BAZOWY_KATALOG / "logs" / filename
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now()} | {msg}\n")

def log_function(msg, file="models.log"):
    log_event(f"[MODELS] {msg}", file)

def query_gpt_online(prompt, model_alias="gpt-5.1"):
    if not openai:
        return "❌ Biblioteka 'openai' nie zainstalowana.", "error"
    try:
        with open(PLIK_USTAWIENIA, "r") as f:
            config = json.load(f)
            api_key = config.get("openai_api_key")
        if not api_key or "TWÓJ_KLUCZ" in api_key:
            return "❌ Błąd: Brak klucza API.", "error"
        real_model = "gpt-4o" if model_alias == "gpt-5.1" else model_alias
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=real_model,
            messages=[{"role": "system", "content": "Jesteś Lyra, zaawansowany asystent AI."}, {"role": "user", "content": prompt}],
            timeout=15
        )
        return response.choices[0].message.content, "online"
    except Exception as e:
        return f"❌ Błąd API: {str(e)}", "error"

def get_detailed_gpu_info():
    gpu_stats = []
    try:
        cards = [d for d in os.listdir('/sys/class/drm/') if d.startswith('card') and len(d) == 5]
        for card in sorted(cards):
            base_path = f"/sys/class/drm/{card}/device"
            t_p, u_p = f"{base_path}/mem_info_vram_total", f"{base_path}/mem_info_vram_used"
            if os.path.exists(t_p):
                with open(t_p, 'r') as f: total = int(f.read().strip()) // (1024**2)
                with open(u_p, 'r') as f: used = int(f.read().strip()) // (1024**2)
                gpu_stats.append(f"GPU{card[-1]}: {used}/{total}MB")
        return " | ".join(gpu_stats) if gpu_stats else "GPU: Idle"
    except: return "GPU: Nie wykryto"

def wyswietl_baner(tryb, model):
    gpu_data = get_detailed_gpu_info()
    czas = datetime.datetime.now().strftime("%H:%M:%S")
    CYAN, GREEN, GRAY, RESET = "\033[96m", "\033[92m", "\033[90m", "\033[0m"
    print(f"\n{CYAN}╔" + "═"*65 + "╗")
    print(f"║ {RESET}Lyra {tryb.upper()} │ {GREEN}Model: {model}{RESET} │ {GRAY}{czas}{RESET}")
    print(f"╟" + "─"*65 + "╢")
    print(f"║ {GRAY}Zasoby: {gpu_data}{RESET}")
    print(f"{CYAN}╚" + "═"*65 + "╝{RESET}")

# ======= GŁÓWNA LOGIKA WYKONAWCZA =======

def run_once(user_input):
    global CURRENT_MODE
    if not user_input.strip(): return
    cmd_clean = user_input.strip()
    cmd_lower = cmd_clean.lower()

    # --- 1. PRZEŁĄCZNIKI TRYBÓW I KOMENDY STANU ---
    if cmd_lower == ":bash":
        CURRENT_MODE = "bash"
        print("\033[93m[MODE]: BASH - System command mode active.\033[0m")
        return
    elif cmd_lower == ":lyra":
        CURRENT_MODE = "lyra"
        print("\033[92m[MODE]: LYRA - AI Chat mode active.\033[0m")
        return
    elif cmd_lower == ":code":
        CURRENT_MODE = "code"
        print("\033[96m[MODE]: CODE - Programming & Debugging mode active.\033[0m")
        return
    elif cmd_lower == ":screen":
        print("\033[90m🔍 Przechwytuję aktywny panel tmux...\033[0m")
        screen = subprocess.run("tmux capture-pane -p", shell=True, capture_output=True, text=True)
        print(f"\n--- TMUX SNAPSHOT ---\n{screen.stdout[-1000:]}\n--------------------")
        return
    elif cmd_lower == ":state":
        print(f"📊 Tryb: {CURRENT_MODE} | GPU: {get_detailed_gpu_info()}")
        return

    # --- 2. TRYB BASH LUB FORCE-SHELL (!) ---
    if CURRENT_MODE == "bash" or cmd_clean.startswith("!"):
        exec_cmd = cmd_clean[1:] if cmd_clean.startswith("!") else cmd_clean
        print(f"\033[90m$ {exec_cmd}\033[0m")
        
        res = subprocess.run(exec_cmd, shell=True, capture_output=True, text=True)
        if res.stdout: print(res.stdout.strip())
        
        # --- AUTO-CONTEXT + SUDO HELPER ---
        if res.returncode != 0:
            error_msg = res.stderr.strip()
            print(f"\033[91m❌ Błąd (kod {res.returncode}):\033[0m {error_msg}")
            
            # --- SUDO HELPER ---
            if "permission denied" in error_msg.lower() or "not permitted" in error_msg.lower():
                print(f"\n\033[93m🛡️ Wykryto brak uprawnień. Czy chcesz spróbować z 'sudo'? (y/n)\033[0m")
                choice = input("\033[93m>>> \033[0m").strip().lower()
                if choice == 'y':
                    sudo_cmd = f"sudo {exec_cmd}"
                    print(f"\033[90m$ {sudo_cmd}\033[0m")
                    os.system(sudo_cmd) 
                    return

            # --- DIAGNOZA AI (Lokalnie -> GPT) ---
            print(f"\n\033[95m🤖 Analizuję problem...\033[0m")
            diag_prompt = f"Zdiagnozuj krótko błąd komendy `{exec_cmd}`: {error_msg}"
            try:
                response, _ = query_model(diag_prompt, "mistral", "local", config={"timeout":20}, history=[])
                if not response or "error" in response.lower(): raise Exception()
                print(f"\033[96m[Lokalna Diagnoza]:\033[0m {response}")
            except:
                response, _ = query_gpt_online(diag_prompt)
                print(f"\033[96m[Diagnoza Online]:\033[0m {response}")
        return

    # --- 3. TRYB LYRA / CODE (AI + NARZĘDZIA) ---
    
    # Obsługa wymuszenia GPT
    if cmd_lower.startswith("gpt "):
        pytanie = cmd_clean[4:].strip()
        print(f"🌐 Wymuszam tryb ONLINE (GPT) dla: {pytanie}")
        odpowiedz, _ = query_gpt_online(pytanie)
        print(f"\n[GPT]:\n{odpowiedz}\n")
        return

    # Strategia i Model
    strategy = choose_best_model(cmd_clean)
    local_target, cloud_target = strategy if strategy else ("mistral", "gpt-4o")
    
    # Prompt Systemowy zależny od trybu
    sys_instruction = "Jesteś Lyra, asystentem operacyjnym."
    if CURRENT_MODE == "code":
        sys_instruction = "Jesteś ekspertem programowania. Podawaj czysty kod, używaj komentarzy, bądź zwięzła."
        local_target = "mistral" # Preferowany Bielik dla kodu lokalnie

    try: active_model = get_active_local_model_name() or "Lokalny"
    except: active_model = "Lokalny"
    
    wyswietl_baner(CURRENT_MODE, active_model)

    # Narzędzia (Tylko w trybie LYRA)
    if CURRENT_MODE == "lyra":
        intent_result = detect_intent(cmd_clean)
        if intent_result:
            tool_name = intent_result[0] if isinstance(intent_result, (tuple, list)) else intent_result.get("tool")
            arg = intent_result[1] if isinstance(intent_result, (tuple, list)) else intent_result.get("arg", "")
            if tool_name in SYSTEM_TOOLS:
                print(f"⚙️ Narzędzie: {tool_name}...")
                print(SYSTEM_TOOLS[tool_name](arg, system_run, log_event))
                return

    # Wywołanie AI
    print(f"🧠 Strategia {CURRENT_MODE}: {local_target} | {cloud_target}")
    full_query = f"{sys_instruction}\n\nZapytanie: {cmd_clean}"
    
    try:
        response, _ = query_model(full_query, local_target, "local", config={"timeout":90}, history=[])
        if not response or "error" in response.lower(): raise Exception("Błąd modelu")
        print(f"\n{response}\n")
    except Exception as e:
        print(f"⚠️ Fallback do {cloud_target} Online... ({e})")
        response, _ = query_gpt_online(full_query, cloud_target)
        print(f"\n[{cloud_target.upper()}]:\n{response}\n")

def start_chat():
    username = getpass.getuser()
    hostname = socket.gethostname()
    print(f"\033[92m--- Lyra Shell Aktywna (Dual Radeon GPU) ---\033[0m")
    print("Komendy: :bash, :lyra, :code, :screen, :state, exit")
    
    while True:
        try:
            # Dynamiczny kolor promptu
            colors = {"lyra": "\033[94m", "bash": "\033[93m", "code": "\033[96m"}
            p_color = colors.get(CURRENT_MODE, "\033[0m")
            
            user_input = input(f"{p_color}{username}@{hostname} ({CURRENT_MODE}):~$ \033[0m").strip()
            
            if not user_input: continue
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("👋 Do widzenia!")
                break
            run_once(user_input)
        except KeyboardInterrupt:
            print("\n👋 Przerwano.")
            break
        except Exception as e:
            print(f"❌ Błąd pętli: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_once(" ".join(sys.argv[1:]))
    else:
        start_chat()
