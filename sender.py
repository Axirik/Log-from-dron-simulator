import socket
import time
import math

# Создаём UDP сокет — это наша "радиостанция"
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

t = 0  # время в секундах

while True:
    # Имитируем круговой полёт
    x = math.sin(t) * 2  # летим по кругу радиусом 2 метра
    y = math.cos(t) * 2
    z = -1.5  # высота 1.5 метра (минус потому что NED)

    # Отправляем просто текст для начала
    message = f"{x},{y},{z}"
    sock.sendto(message.encode(), ('127.0.0.1', 14550))
    sock.sendto(message.encode(), ('127.0.0.1', 14551))  # добавь эту строку

    print(f"Отправил: x={x:.2f} y={y:.2f} z={z}")

    t += 0.1  # было t += 1
    time.sleep(0.1)  # было time.sleep(1)