import time
import socket
import threading
import subprocess
import sys

from drone_v3.drone import Drone
from simulator  import Simulator

drone = Drone()
sim   = Simulator(drone)
sock  = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

controller_process = None

# ══════════════════════════════════════
#  КОНТРОЛЛЕР
# ══════════════════════════════════════
def start_controller():
    global controller_process
    if controller_process is None or controller_process.poll() is not None:
        controller_process = subprocess.Popen([sys.executable, 'controller.py'])
        print("🎮 Контроллер запущен")

def stop_controller():
    global controller_process
    if controller_process and controller_process.poll() is None:
        controller_process.terminate()
        controller_process = None
        sim.controller_input = {'pitch': 0.0, 'roll': 0.0, 'thr': 0.0, 'yaw': 0.0}
        print("🎮 Контроллер остановлен")

# ══════════════════════════════════════
#  UDP — приём команд от контроллера
# ══════════════════════════════════════
def read_controller():
    sock_ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_ctrl.bind(('0.0.0.0', 14553))
    sock_ctrl.settimeout(0.1)

    while True:
        try:
            data, _ = sock_ctrl.recvfrom(1024)
            parts   = data.decode().strip().split(',')

            if parts[0] == 'MODE':
                mode = parts[1]
                sim.control_mode = mode
                if mode == 'MANUAL':
                    start_controller()
                elif mode == 'AUTO':
                    stop_controller()
                print(f"Режим: {mode}")
                continue

            if parts[0] == 'MANUAL' and sim.control_mode == 'MANUAL':
                sim.controller_input['pitch'] = float(parts[1])
                sim.controller_input['roll']  = float(parts[2])
                sim.controller_input['thr']   = float(parts[3])
                sim.controller_input['yaw']   = float(parts[4])

        except socket.timeout:
            pass

threading.Thread(target=read_controller, daemon=True).start()

# ══════════════════════════════════════
#  КОНСОЛЬ
# ══════════════════════════════════════
def read_commands():
    names = {
        't': 'thrust', 'y': 'yaw',
        'c': 'circle', 's': 'speed',
        'kp': 'Kp', 'ki': 'Ki', 'kd': 'Kd',
        'tx': 'target_x', 'ty': 'target_y', 'tz': 'target_z',
        'w': 'wind'
    }

    while True:
        try:
            cmd        = input()
            key, value = cmd.split('=')
            value      = float(value)

            d = drone
            s = sim

            if   key == 'tx': s.target_x += value
            elif key == 'ty': s.target_y += value
            elif key == 'tz': s.target_z  = value
            elif key in ('thrust', 't'): d.thrust    = value
            elif key in ('yaw',    'y'): d.yaw_rate  = value
            elif key == 'kp': s.Kp  = s.Kp_z  = value
            elif key == 'ki': s.Ki  = s.Ki_z  = value
            elif key == 'kd': s.Kd  = s.Kd_z  = value
            elif key == 'w':
                s.wind_enabled = bool(int(value))
                print(f"Ветер: {'ВКЛ' if s.wind_enabled else 'ВЫКЛ'}")
            elif key in ('circle', 'c'):
                s.orbit_radius = value
                s.orbit_mode = not s.orbit_mode
                if s.orbit_mode:
                    # Запоминаем текущую позицию как центр
                    s.orbit_center_x = drone.x
                    s.orbit_center_y = drone.y
                    print(f"Круг вокруг ({drone.x:.1f}, {drone.y:.1f}) r={value}")

            print(f"Установлено: {names.get(key, key)} = {value}")

        except ValueError:
            print("Команды:")
            print("  t=0.7    — тяга")
            print("  tz=5     — цель высота")
            print("  tx/ty    — цель X/Y")
            print("  kp/ki/kd — ПИД")
            print("  w=1      — ветер")
            print("  c=2      — автокруг")

threading.Thread(target=read_commands, daemon=True).start()

# ══════════════════════════════════════
#  ОТПРАВКА ТЕЛЕМЕТРИИ
# ══════════════════════════════════════
def send_telemetry(counter):
    d = drone
    s = sim

    message = (f"{s.t:.1f},{d.x:.3f},{d.y:.3f},{d.z:.3f},"
               f"{d.pid_roll:.3f},{d.pid_pitch:.3f},{d.thrust:.3f},"
               f"{d.voltage:.3f},{d.yaw:.3f},{d.state}")

    debug = (f"{s.t:.1f},"
             f"{s.target_x:.3f},{s.target_y:.3f},{s.target_z:.3f},"
             f"{s.target_x-d.x:.3f},{s.target_y-d.y:.3f},{s.target_z-d.z:.3f},"
             f"{d.pid_pitch:.3f},{d.pid_roll:.3f},{d.pid_thrust:.3f},"
             f"{s.wind_x:.3f},{s.wind_y:.3f},"
             f"{s.Kp},{s.Ki},{s.Kd}")

    if counter >= 3:
        sock.sendto(message.encode(), ('127.0.0.1', 14550))
        sock.sendto(message.encode(), ('127.0.0.1', 14551))
        sock.sendto(debug.encode(),   ('127.0.0.1', 14552))
        return 0

    return counter + 1

# ══════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════
print("=" * 40)
print("  СИМУЛЯТОР ДРОНА С ПИД")
print("=" * 40)
print("  t=0.7  — взлёт")
print("  tz=5   — цель высота (AUTO)")
print("  tx/ty  — цель X/Y   (AUTO)")
print("  w=1    — ветер")
print("  kp/ki/kd — ПИД")
print("  c=2    — автокруг")
print("=" * 40)

counter = 0
while True:
    sim.step()
    counter = send_telemetry(counter)
    time.sleep(sim.dt)