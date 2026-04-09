import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 14550))

print("Слушаю...")

while True:
    data, addr = sock.recvfrom(1024)
    message = data.decode()
    t, x, y, z, roll, pitch, thrust, voltage = map(float, message.split(','))
    print(f"Получил: t={t:.1f} x={x:.2f} y={y:.2f} z={z:.2f} thrust={thrust:.1f} roll={roll:.1f} pitch={pitch:.1f} v={voltage:.2f}")