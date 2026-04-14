import socket
import time
import threading
from pynput import keyboard

# ── Настройки ──
SIMULATOR_IP   = '127.0.0.1'
SIMULATOR_PORT = 14553
SEND_RATE      = 0.05   # 20 раз в секунду

# ── Параметры управления ──
MAX_ANGLE  = 0.5   # максимальный наклон
MAX_THR    = 0.3   # максимальная дельта тяги
ACCEL_RATE = 0.02  # как быстро растёт крен
DECAY_RATE = 0.05  # как быстро выравнивается
THR_ACCEL  = 0.02  # как быстро растёт тяга
THR_DECAY  = 0.03  # как быстро падает тяга
YAW_SPEED  = 0.5


sock         = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
keys_pressed = set()
running      = True


# ── Текущие значения ──
current_pitch = 0.0
current_roll  = 0.0
current_thr   = 0.0  # добавили
yaw_out       = 0.0





print("=" * 40)
print("  КОНТРОЛЛЕР ДРОНА — MANUAL")
print("=" * 40)
print("  W/S     — вперёд/назад")
print("  A/D     — влево/вправо")
print("  SHIFT   — вверх")
print("  CTRL    — вниз")
print("  Q/E     — поворот влево/вправо")
print("  ESC     — выход")
print("=" * 40)

RU_TO_EN = {
    'ц': 'w', 'ф': 'a', 'ы': 's', 'в': 'd',
    'й': 'q', 'у': 'e',
}



# ══════════════════════════════════════
#  ОБРАБОТКА КЛАВИШ
# ══════════════════════════════════════
def on_press(key):
    try:
        char = key.char.lower()
        char = RU_TO_EN.get(char, char)
        keys_pressed.add(char)
    except AttributeError:
        keys_pressed.add(key)

def on_release(key):
    try:
        keys_pressed.discard(key.char.lower())
    except AttributeError:
        keys_pressed.discard(key)
    if key == keyboard.Key.esc:
        return False

# ══════════════════════════════════════
#  ГЛАВНЫЙ ЦИКЛ
# ══════════════════════════════════════
def control_loop():
    global current_pitch, current_roll, current_thr, yaw_out

    while running:

        # ── Pitch (вперёд/назад) ──
        if 'w' in keys_pressed:
            current_pitch = min(current_pitch + ACCEL_RATE, MAX_ANGLE)
        elif 's' in keys_pressed:
            current_pitch = max(current_pitch - ACCEL_RATE, -MAX_ANGLE)
        else:
            # Плавно возвращаем к нулю
            if current_pitch > 0:
                current_pitch = max(0.0, current_pitch - DECAY_RATE)
            elif current_pitch < 0:
                current_pitch = min(0.0, current_pitch + DECAY_RATE)

        # ── Roll (влево/вправо) ──
        if 'd' in keys_pressed:
            current_roll = min(current_roll + ACCEL_RATE, MAX_ANGLE)
        elif 'a' in keys_pressed:
            current_roll = max(current_roll - ACCEL_RATE, -MAX_ANGLE)
        else:
            if current_roll > 0:
                current_roll = max(0.0, current_roll - DECAY_RATE)
            elif current_roll < 0:
                current_roll = min(0.0, current_roll + DECAY_RATE)

        # ── Тяга (вверх/вниз) ──
        if (keyboard.Key.shift in keys_pressed or
                keyboard.Key.shift_l in keys_pressed or
                keyboard.Key.shift_r in keys_pressed):
            current_thr = min(current_thr + THR_ACCEL, MAX_THR)
        elif (keyboard.Key.ctrl in keys_pressed or
              keyboard.Key.ctrl_l in keys_pressed or
              keyboard.Key.ctrl_r in keys_pressed):
            current_thr = max(current_thr - THR_ACCEL, -MAX_THR)
        else:
            # Плавно возвращаем к нулю
            if current_thr > 0:
                current_thr = max(0.0, current_thr - THR_DECAY)
            elif current_thr < 0:
                current_thr = min(0.0, current_thr + THR_DECAY)

        # ── Yaw (поворот) ──
        if 'q' in keys_pressed:
            yaw_out = -YAW_SPEED
        elif 'e' in keys_pressed:
            yaw_out =  YAW_SPEED
        else:
            yaw_out = 0.0

        # Отправляем
        msg = (f"MANUAL,{current_pitch:.3f},{current_roll:.3f},"
               f"{current_thr:.3f},{yaw_out:.3f}")
        sock.sendto(msg.encode(), (SIMULATOR_IP, SIMULATOR_PORT))

        # Показываем текущие значения
        print(f"\r  pitch={current_pitch:+.2f} "
              f"roll={current_roll:+.2f} "
              f"thr={current_thr:+.2f} "
              f"yaw={yaw_out:+.2f}    ", end='', flush=True)

        time.sleep(SEND_RATE)

# Запускаем цикл в фоне
ctrl_thread = threading.Thread(target=control_loop, daemon=True)
ctrl_thread.start()

# Слушаем клавиши — блокирует до ESC
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

running = False
print("\nКонтроллер остановлен.")
sock.close()