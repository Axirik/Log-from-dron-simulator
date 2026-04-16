import socket
import csv
import time

csvfile = open('flight_log.csv', 'w', newline='')
writer  = csv.writer(csvfile)
writer.writerow(['time', 'x', 'y', 'z', 'roll', 'pitch',
                 'thrust', 'voltage', 'yaw', 'state'])

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 14550))

print("Слушаю и пишу в flight_log.csv...")
print("Ctrl+C для остановки")

try:
    while True:
        data, addr = sock.recvfrom(1024)
        parts      = data.decode().strip().split(',')
        t, x, y, z, roll, pitch, thrust, voltage, yaw = map(float, parts[:9])
        drone_state = parts[9]

        writer.writerow([
            f"{time.time():.3f}",
            f"{x:.3f}", f"{y:.3f}", f"{z:.3f}",
            f"{roll:.3f}", f"{pitch:.3f}",
            f"{thrust:.3f}", f"{voltage:.3f}",
            f"{yaw:.3f}", drone_state
        ])
        csvfile.flush()

        print(f"t={t:.1f} | x={x:.2f} y={y:.2f} z={z:.2f} | "
              f"v={voltage:.2f}V | {drone_state}")

except KeyboardInterrupt:
    print("\nЗапись остановлена.")
finally:
    csvfile.close()
    sock.close()