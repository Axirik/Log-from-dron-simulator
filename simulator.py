import math
import time
import socket
import threading

# Начальные условия
x, y, z = 0.0, 0.0, 0.0
vx, vy, vz = 0.0, 0.0, 0.0
roll, pitch = 0.0, 0.0
thrust = 0.5
voltage = 12.6
dt = 0.1
t = 0
orbit_mode = False
orbit_radius = 0.1
orbit_speed  = 1.0

send_every = 5  # отправляем каждые 5 итераций
counter = 0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def read_commands():
    global roll, pitch, thrust, orbit_mode, orbit_radius
    while True:
        try:
            cmd = input()
            key, value = cmd.split('=')
            value = float(value)

            if key == 'roll':
                roll = value
            elif key == 'pitch':
                pitch = value
            elif key == 'thrust':
                thrust = value
            elif key == 'circle':
                orbit_radius = float(value)
                orbit_mode = not orbit_mode

            print(f"Установлено: {key} = {value}")
        except:
            print("Формат: roll=0.1 или pitch=0.2 или thrust=0.7")

# Запускаем поток управления
thread = threading.Thread(target=read_commands, daemon=True)
thread.start()

print("Симулятор запущен! Управление:")
print("  roll=0.1   — наклон вправо")
print("  pitch=0.1  — наклон вперёд")
print("  thrust=0.7 — подъём вверх")
print("  thrust=0.5 — висение")
print("  thrust=0.3 — снижение")
print("  circle=1 — режим полета по кругу, 1 - радиус в м")

while True:
    if orbit_mode:
        roll = orbit_radius * math.cos(orbit_speed * t)
        pitch = orbit_radius * math.sin(orbit_speed * t)
    # Физика
    ax = math.sin(roll) * 9.8
    ay = math.sin(pitch) * 9.8
    az = 2 * thrust * 9.8 - 9.8

    vx = vx * 0.98 + ax * dt
    vy = vy * 0.98 + ay * dt
    vz = vz * 0.98 + az * dt

    x += vx * dt
    y += vy * dt
    z += vz * dt

    # Батарея
    voltage -= thrust * 0.0013
    voltage = max(voltage, 0.0)  # не уходит ниже нуля

    message = f"{t:.1f},{x:.3f},{y:.3f},{z:.3f},{roll:.3f},{pitch:.3f},{thrust:.3f},{voltage:.3f}"
    counter += 1
    if counter >= send_every:
        sock.sendto(message.encode(), ('127.0.0.1', 14550))
        sock.sendto(message.encode(), ('127.0.0.1', 14551))
        counter = 0

    #print(f"t={t:.1f} x={x:.2f} y={y:.2f} z={z:.2f} thrust={thrust:.1f} v={voltage:.2f}")
    t += dt
    time.sleep(dt)