import math
import time
import socket
import threading
import random
import subprocess
import sys

# ══════════════════════════════════════
#  ПЕРЕМЕННЫЕ
# ══════════════════════════════════════

x, y, z    = 0.0, 0.0, 0.0
vx, vy, vz = 0.0, 0.0, 0.0
yaw        = 0.0
yaw_rate   = 0.0
thrust     = 0.5
voltage    = 12.6
dt         = 0.1
t          = 0.0

control_mode       = 'MANUAL'
controller_process = None

controller_input = {
    'pitch': 0.0, 'roll': 0.0,
    'thr':   0.0, 'yaw':  0.0
}

target_x = 0.0
target_y = 0.0
target_z = 0.0

Kp   = 2.1;  Ki   = 0.9;  Kd   = 1
Kp_z = 0.3;  Ki_z = 0.005;  Kd_z = 0.6

integral_x = 0.0;  integral_y = 0.0;  integral_z = 0.0
prev_err_x = 0.0;  prev_err_y = 0.0;  prev_err_z = 0.0

pid_pitch  = 0.0
pid_roll   = 0.0
pid_thrust = 0.5

wind_x       = 0.0
wind_y       = 0.0
wind_timer   = 0.0
WIND_ENABLED = True

LANDED    = 'LANDED'
TAKEOFF   = 'TAKEOFF'
HOVER     = 'HOVER'
FLYING    = 'FLYING'
LANDING   = 'LANDING'
EMERGENCY = 'EMERGENCY'

drone_state = LANDED

orbit_mode   = False
orbit_radius = 1.0
orbit_speed  = 1.0

send_every = 3
counter    = 0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ══════════════════════════════════════
#  КОНТРОЛЛЕР
# ══════════════════════════════════════
def start_controller():
    global controller_process
    if controller_process is None or controller_process.poll() is not None:
        controller_process = subprocess.Popen(
            [sys.executable, 'controller.py']
        )
        print("🎮 Контроллер запущен")

def stop_controller():
    global controller_process
    if controller_process and controller_process.poll() is None:
        controller_process.terminate()
        controller_process = None
        controller_input['pitch'] = 0.0
        controller_input['roll']  = 0.0
        controller_input['thr']   = 0.0
        controller_input['yaw']   = 0.0
        print("🎮 Контроллер остановлен")

# ══════════════════════════════════════
#  КОНСОЛЬ
# ══════════════════════════════════════
names = {
    't':  'thrust',    'y':  'yaw',
    'c':  'circle',    's':  'speed',
    'kp': 'Kp',        'ki': 'Ki',       'kd': 'Kd',
    'tx': 'target_x',  'ty': 'target_y', 'tz': 'target_z',
    'w':  'wind'
}

def read_commands():
    global target_x, target_y, target_z
    global thrust, yaw_rate
    global Kp, Ki, Kd, Kp_z, Ki_z, Kd_z
    global orbit_mode, orbit_radius, orbit_speed
    global WIND_ENABLED

    while True:
        try:
            cmd        = input()
            key, value = cmd.split('=')
            value      = float(value)

            if   key == 'tx': target_x += value
            elif key == 'ty': target_y += value
            elif key == 'tz': target_z  = value
            elif key in ('thrust', 't'):
                thrust = value
                # Взлёт через консоль работает в обоих режимах
            elif key in ('yaw', 'y'): yaw_rate = value
            elif key == 'kp': Kp  = Kp_z  = value
            elif key == 'ki': Ki  = Ki_z  = value
            elif key == 'kd': Kd  = Kd_z  = value
            elif key == 'w':
                WIND_ENABLED = bool(int(value))
                print(f"Ветер: {'ВКЛ' if WIND_ENABLED else 'ВЫКЛ'}")
            elif key in ('circle', 'c'):
                orbit_radius = value
                orbit_mode   = not orbit_mode
                print(f"Круг: {'ВКЛ' if orbit_mode else 'ВЫКЛ'} r={orbit_radius}")
            elif key in ('speed', 's'):
                orbit_speed = value

            full_name = names.get(key, key)
            print(f"Установлено: {full_name} = {value}")

        except ValueError:
            print("Команды консоли:")
            print("  t=0.7    — тяга (взлёт)")
            print("  tz=5     — цель высота 5м (AUTO)")
            print("  tx=3     — цель вперёд 3м (AUTO)")
            print("  ty=3     — цель вправо 3м (AUTO)")
            print("  kp/ki/kd — настройка ПИД")
            print("  w=1      — ветер вкл/выкл")
            print("  c=2      — автокруг радиусом 2м")

thread = threading.Thread(target=read_commands, daemon=True)
thread.start()

# ══════════════════════════════════════
#  ПОТОК КОНТРОЛЛЕРА
# ══════════════════════════════════════
def read_controller():
    global control_mode

    sock_ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_ctrl.bind(('0.0.0.0', 14553))
    sock_ctrl.settimeout(0.1)

    while True:
        try:
            data, _ = sock_ctrl.recvfrom(1024)
            parts   = data.decode().strip().split(',')

            if parts[0] == 'MODE':
                new_mode     = parts[1]
                control_mode = new_mode
                if new_mode == 'MANUAL':
                    start_controller()
                elif new_mode == 'AUTO':
                    stop_controller()
                print(f"Режим переключён: {new_mode}")
                continue

            # Только в MANUAL и только от controller.py
            if parts[0] == 'MANUAL' and control_mode == 'MANUAL':
                controller_input['pitch'] = float(parts[1])
                controller_input['roll']  = float(parts[2])
                controller_input['thr']   = float(parts[3])
                controller_input['yaw']   = float(parts[4])

        except socket.timeout:
            pass

ctrl_thread = threading.Thread(target=read_controller, daemon=True)
ctrl_thread.start()

print("=" * 40)
print("  СИМУЛЯТОР ДРОНА С ПИД")
print("=" * 40)
print("  КОНСОЛЬ:")
print("  t=0.7  — взлёт")
print("  tz=5   — цель высота 5м (AUTO)")
print("  tx/ty  — цель по X/Y   (AUTO)")
print("  w=1    — ветер")
print("  kp/ki/kd — ПИД")
print("  c=2    — автокруг")
print("  КОНТРОЛЛЕР (MANUAL):")
print("  W/S/A/D    — движение")
print("  Shift/Ctrl — вверх/вниз")
print("  Q/E        — поворот")
print("=" * 40)

# ══════════════════════════════════════
#  ГЛОБАЛЬНЫЕ УСЛОВИЯ
# ══════════════════════════════════════


# ══════════════════════════════════════
#  STATE MACHINE
# ══════════════════════════════════════
def update_state():
    global drone_state, thrust, vx, vy, vz, z, WIND_ENABLED,pid_thrust, pid_roll, pid_pitch

    # ── Глобальные условия — проверяем первыми ──
    if voltage <= 6.6 and drone_state not in (LANDED, EMERGENCY):
        drone_state  = EMERGENCY
        WIND_ENABLED = False
        thrust = 0.25
        pid_thrust=pid_roll=pid_pitch=0
        print("⚠ БАТАРЕЯ РАЗРЯЖЕНА!")
        return

    if z <= 0.0 and vz <= 0.0 and drone_state not in (LANDED, TAKEOFF):
        drone_state = LANDED
        thrust      = 0.5
        vx = vy = vz = 0.0
        z  = 0.0
        if drone_state == EMERGENCY:
            print("✓ Аварийная посадка.")
        else:
            print("✓ Приземлился.")
        return

    # ── Переходы по состояниям ──
    if drone_state == LANDED:
        if thrust > 0.5 and voltage > 6.6:
            drone_state = TAKEOFF
            print("🚀 Взлёт!")

    elif drone_state == TAKEOFF:
        if z > 0.5 and vz == 0:
            drone_state = HOVER

    elif drone_state == HOVER:
        if abs(vx) > 0.1 or abs(vy) > 0.1:
            drone_state = FLYING
        elif thrust < 0.45:
            drone_state = LANDING

    elif drone_state == FLYING:
        if thrust < 0.45:
            drone_state = LANDING


# ══════════════════════════════════════
#  ВЕТЕР
# ══════════════════════════════════════
def update_wind():
    global wind_x, wind_y, wind_timer

    if not WIND_ENABLED:
        wind_x = wind_y = 0.0
        return

    wind_timer += dt
    if wind_timer >= 10.0:
        wind_x     = random.uniform(-1.5, 1.5)
        wind_y     = random.uniform(-1.5, 1.5)
        wind_timer = 0.0
        print(f"\n💨 Порыв: wx={wind_x:.2f} wy={wind_y:.2f}")

# ══════════════════════════════════════
#  ПИД РЕГУЛЯТОР
# ══════════════════════════════════════
def pid_control():
    global pid_pitch, pid_roll, pid_thrust
    global integral_x, integral_y, integral_z
    global prev_err_x, prev_err_y, prev_err_z

    if drone_state not in (TAKEOFF, HOVER, FLYING):
        pid_pitch  = 0.0
        pid_roll   = 0.0
        pid_thrust = thrust
        if drone_state == LANDED:
            integral_x = integral_y = integral_z = 0.0
            prev_err_x = prev_err_y = prev_err_z = 0.0
        return

    error_x = target_x - x
    error_y = target_y - y
    error_z = target_z - z
    #print(f"errors: ex={error_x:.2f} ey={error_y:.2f} pitch={pid_pitch:.3f} roll={pid_roll:.3f}")

    integral_x = max(-5.0, min(5.0, integral_x + error_x * dt))
    integral_y = max(-5.0, min(5.0, integral_y + error_y * dt))
    integral_z = max(-5.0, min(5.0, integral_z + error_z * dt))

    deriv_x = (error_x - prev_err_x) / dt
    deriv_y = (error_y - prev_err_y) / dt
    deriv_z = (error_z - prev_err_z) / dt

    pid_pitch  = Kp*error_x + Ki*integral_x + Kd*deriv_x
    pid_roll   = Kp*error_y + Ki*integral_y + Kd*deriv_y
    pid_thrust = 0.5 + Kp_z*error_z + Ki_z*integral_z + Kd_z*deriv_z

    pid_pitch  = max(-0.8, min(0.8, pid_pitch))
    pid_roll   = max(-0.8, min(0.8, pid_roll))
    pid_thrust = max(0.3,  min(0.9, pid_thrust))

    prev_err_x = error_x
    prev_err_y = error_y
    prev_err_z = error_z

# ══════════════════════════════════════
#  MANUAL LOOP
# ══════════════════════════════════════
def manual_loop():
    global pid_pitch, pid_roll, pid_thrust, thrust, yaw_rate

    pid_pitch = controller_input['pitch']
    pid_roll  = controller_input['roll']
    yaw_rate  = controller_input['yaw']

    thr = controller_input['thr']
    if thr != 0:
        thrust += thr * dt * 3
        thrust  = max(0.3, min(0.9, thrust))
    else:
        # Плавно возвращаем к висению
        if thrust > 0.5:
            thrust = max(0.5, thrust - 0.005)
        elif thrust < 0.5:
            thrust = min(0.5, thrust + 0.005)

    # Взлёт от контроллера
    if drone_state == LANDED and thrust > 0.5:
        pass  # update_state обработает

    # Всегда обновляем pid_thrust из thrust
    pid_thrust = thrust

# ══════════════════════════════════════
#  AUTO LOOP
# ══════════════════════════════════════
def auto_loop():
    global target_x, target_y, thrust

    #print(f"AUTO_LOOP: state={drone_state} target_z={target_z} thrust={thrust:.2f}")

    if orbit_mode:
        target_x = orbit_radius * math.sin(orbit_speed * t)
        target_y = orbit_radius * math.cos(orbit_speed * t)

    if drone_state == LANDED and target_z > 0.1:
        thrust = 0.7
    pid_control()

# ══════════════════════════════════════
#  PHYSICS LOOP
# ══════════════════════════════════════
def physics_loop():
    global x, y, z, vx, vy, vz, yaw, voltage

    if drone_state == LANDED:
        # Дрон на земле — полная остановка
        vx = vy = vz = 0.0
        return

    update_wind()

    # Силы в системе дрона → переводим в мир через yaw
    fx = math.sin(pid_pitch) * 5.0
    fy = math.sin(pid_roll)  * 5.0

    ax = fx * math.cos(yaw) - fy * math.sin(yaw) + wind_x
    ay = fx * math.sin(yaw) + fy * math.cos(yaw) + wind_y
    az = 2 * pid_thrust * 9.8 - 9.8

    vx = vx * 0.85 + ax * dt
    vy = vy * 0.85 + ay * dt
    vz = vz * 0.98 + az * dt

    x += vx * dt
    y += vy * dt
    z += vz * dt

    # Нормализуем yaw в диапазон 0..2π
    yaw = (yaw + yaw_rate * dt) % (2 * math.pi)

    # Земля
    if z <= 0.0 and vz <= 0.0:
        z = vz = 0.0

    # Батарея только в воздухе
    voltage -= thrust * 0.0013
    voltage  = max(voltage, 0.0)

# ══════════════════════════════════════
#  ОТПРАВКА
# ══════════════════════════════════════
def send_telemetry():
    global counter

    message = (f"{t:.1f},{x:.3f},{y:.3f},{z:.3f},"
               f"{pid_roll:.3f},{pid_pitch:.3f},{thrust:.3f},"
               f"{voltage:.3f},{yaw:.3f},{drone_state}")

    debug = (f"{t:.1f},"
             f"{target_x:.3f},{target_y:.3f},{target_z:.3f},"
             f"{target_x-x:.3f},{target_y-y:.3f},{target_z-z:.3f},"
             f"{pid_pitch:.3f},{pid_roll:.3f},{pid_thrust:.3f},"
             f"{wind_x:.3f},{wind_y:.3f},"
             f"{Kp},{Ki},{Kd}")

    counter += 1
    if counter >= send_every:
        sock.sendto(message.encode(), ('127.0.0.1', 14550))
        sock.sendto(message.encode(), ('127.0.0.1', 14551))
        sock.sendto(debug.encode(),   ('127.0.0.1', 14552))
        counter = 0

# ══════════════════════════════════════
#  ГЛАВНЫЙ ЦИКЛ
# ══════════════════════════════════════
while True:
    update_state()

    if drone_state == EMERGENCY:
        # Только снижение — ПИД держит X/Y но не взлетает
        pid_thrust = 0.25
        target_z = z
        pid_control()  # держим позицию пока снижаемся

    if control_mode == 'MANUAL':
        manual_loop()
    elif control_mode == 'AUTO':
        auto_loop()

    physics_loop()
    send_telemetry()

    t  += dt
    time.sleep(dt)