import math
import time
import socket
import threading

# ── Состояние дрона ──
x, y, z       = 0.0, 0.0, 0.0
vx, vy, vz    = 0.0, 0.0, 0.0
roll, pitch   = 0.0, 0.0
yaw           = 0.0
yaw_rate      = 0.0
thrust        = 0.5
voltage       = 12.6
dt            = 0.1
t             = 0.0

# Состояния
LANDED    = 'LANDED'
TAKEOFF   = 'TAKEOFF'
HOVER     = 'HOVER'
FLYING    = 'FLYING'
LANDING   = 'LANDING'
EMERGENCY = 'EMERGENCY'

drone_state = LANDED
# ── Режим круга ──
orbit_mode   = False
orbit_radius = 1.0
orbit_speed  = 1.0

send_every = 3
counter    = 0

names = {
    'r': 'roll',   'p': 'pitch',
    't': 'thrust', 'y': 'yaw',
    'c': 'circle', 's': 'speed'
}

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def read_commands():
    global roll, pitch, thrust, yaw_rate, orbit_mode, orbit_radius, orbit_speed
    while True:
        try:
            cmd = input()
            key, value = cmd.split('=')
            value = float(value)
            if key in ('roll', 'r'):
                roll = value
            elif key in ('pitch', 'p'):
                pitch = value
            elif key in ('thrust', 't'):
                thrust = value
            elif key in ('yaw', 'y'):
                yaw_rate = value
            elif key in ('circle', 'c'):
                orbit_radius = value
                orbit_mode = not orbit_mode
            elif key in ('speed', 's'):
                orbit_speed = value
                print(f"Режим круга: {'ВКЛ' if orbit_mode else 'ВЫКЛ'}")
            full_name = names.get(key, key)  # если нет в словаре — оставляем как есть
            print(f"Установлено: {full_name} = {value}")

        except:
            print("Формат команд:")
            print("  roll=0.1      — наклон вправо")
            print("  pitch=0.1     — наклон вперёд")
            print("  thrust=0.7    — вверх  | 0.5 висение | 0.3 вниз")
            print("  yaw=0.5       — поворот вправо")
            print("  circle=2      — круг радиусом 2м")
            print("  speed=1.0     — скорость круга")

thread = threading.Thread(target=read_commands, daemon=True)
thread.start()

print("=" * 40)
print("  СИМУЛЯТОР ДРОНА ЗАПУЩЕН")
print("=" * 40)
print("  thrust=0.7 — взлёт")
print("  thrust=0.5 — висение")
print("  pitch=0.1  — вперёд")
print("  roll=0.1   — вправо")
print("  yaw=0.5    — поворот")
print("  circle=2   — автокруг")
print("  speed=1.0  — скорость круга")
print("=" * 40)


def check_global_conditions():
    global drone_state, thrust

    # Батарея критическая
    if voltage <= 6.6 and drone_state not in (LANDED, EMERGENCY):
        drone_state = EMERGENCY
        print("⚠ БАТАРЕЯ РАЗРЯЖЕНА!")
        return  # дальше не проверяем

    # Касание земли
    if z <= 0.0 and vz <= 0.0 and drone_state not in (LANDED, TAKEOFF):
        z_fixed     = 0.0
        drone_state = LANDED
        thrust      = 0.5
        print("✓ Приземлился.")
        return
def update_state():
    global drone_state, thrust

    if drone_state == LANDED:
        if thrust > 0.5:
            drone_state = TAKEOFF

    elif drone_state == TAKEOFF:
        if vz < 0.05:
            drone_state = HOVER

    elif drone_state == HOVER:
        if abs(vx) > 0.1 or abs(vy) > 0.1:
            drone_state = FLYING
        elif thrust < 0.5:
            drone_state = LANDING

    elif drone_state == FLYING:
        if abs(vx) < 0.1 and abs(vy) < 0.1:
            drone_state = HOVER
        elif thrust < 0.5:
            drone_state = LANDING

    elif drone_state == LANDING:
        pass  # посадка обрабатывается в global conditions

    elif drone_state == EMERGENCY:
        thrust = 0.25  # авто-снижение



while True:
    check_global_conditions()
    update_state()  # обновляем состояние

    # Физика только если не на земле
    if drone_state != LANDED:
        if orbit_mode:
            roll  = orbit_radius * math.cos(orbit_speed * t) * 0.3
            pitch = orbit_radius * math.sin(orbit_speed * t) * 0.3

        fx = math.sin(pitch) * 3.0
        fy = math.sin(roll)  * 3.0
        ax = fx * math.cos(yaw) - fy * math.sin(yaw)
        ay = fx * math.sin(yaw) + fy * math.cos(yaw)
        az = 2 * thrust * 9.8 - 9.8

        vx = vx * 0.85 + ax * dt
        vy = vy * 0.85 + ay * dt
        vz = vz * 0.98 + az * dt

        x += vx * dt
        y += vy * dt
        z += vz * dt

        yaw += yaw_rate * dt

        # Земля
        if z <= 0.0 and vz <= 0.0:
            z  = 0.0
            vz = 0.0

        # Батарея только в воздухе
        voltage -= thrust * 0.0013
        voltage  = max(voltage, 0.0)

    # Отправка
    message = (f"{t:.1f},{x:.3f},{y:.3f},{z:.3f},"
               f"{roll:.3f},{pitch:.3f},{thrust:.3f},"
               f"{voltage:.3f},{yaw:.3f},{drone_state}")

    counter += 1
    if counter >= send_every:
        sock.sendto(message.encode(), ('127.0.0.1', 14550))
        sock.sendto(message.encode(), ('127.0.0.1', 14551))
        counter = 0

    t  += dt
    time.sleep(dt)