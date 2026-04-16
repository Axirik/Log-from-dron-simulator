import socket
import csv
import time

debug_file   = open('flight_debug.csv', 'w', newline='')
debug_writer = csv.writer(debug_file)

debug_writer.writerow([
    'time', 'sim_t',
    'target_x', 'target_y', 'target_z',
    'err_x', 'err_y', 'err_z',
    'pid_pitch', 'pid_roll', 'pid_thrust',
    'wind_x', 'wind_y',
    'Kp', 'Ki', 'Kd'
])

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 14552))

print("Слушаю debug на порту 14552...")
print("Ctrl+C для остановки")

try:
    while True:
        data, _ = sock.recvfrom(1024)
        parts   = data.decode().strip().split(',')

        sim_t                           = float(parts[0])
        target_x, target_y, target_z   = float(parts[1]), float(parts[2]), float(parts[3])
        err_x, err_y, err_z             = float(parts[4]), float(parts[5]), float(parts[6])
        pid_pitch, pid_roll, pid_thrust = float(parts[7]), float(parts[8]), float(parts[9])
        wind_x, wind_y                  = float(parts[10]), float(parts[11])
        Kp, Ki, Kd                      = float(parts[12]), float(parts[13]), float(parts[14])

        debug_writer.writerow([
            f"{time.time():.3f}", f"{sim_t:.1f}",
            f"{target_x:.3f}", f"{target_y:.3f}", f"{target_z:.3f}",
            f"{err_x:.3f}", f"{err_y:.3f}", f"{err_z:.3f}",
            f"{pid_pitch:.3f}", f"{pid_roll:.3f}", f"{pid_thrust:.3f}",
            f"{wind_x:.3f}", f"{wind_y:.3f}",
            f"{Kp}", f"{Ki}", f"{Kd}"
        ])
        debug_file.flush()

        print(f"t={sim_t:.1f} "
              f"| target=({target_x:.2f}, {target_y:.2f}, {target_z:.2f}) "
              f"| err=({err_x:+.2f}, {err_y:+.2f}, {err_z:+.2f}) "
              f"| wind=({wind_x:.2f}, {wind_y:.2f})")

except KeyboardInterrupt:
    print("\nЗапись остановлена.")
finally:
    debug_file.close()
    sock.close()