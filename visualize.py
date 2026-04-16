import csv
import time
import matplotlib.pyplot as plt
import socket

# Открываем сокет
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 14551))
sock.settimeout(0.1)  # не висим вечно на одном пакете

# Списки координат
xs, ys, zs = [], [], []

# Включаем интерактивный режим — график не блокирует код
plt.ion()
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')

print("Слушаю данные...")


with open('flight_log.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['time', 'x', 'y', 'z'])  # заголовок


    while True:
        # Пробуем получить данные
        try:
            data, _ = sock.recvfrom(1024)
            #print(f"Получил: {data.decode()}")  # добавь эту строку
            message = data.decode()
            t, x, y, z, roll, pitch, thrust, voltage = map(float, message.split(','))
            xs.append(float(x))
            ys.append(float(y))
            zs.append(float(z))

            writer.writerow([time.time(), float(x), float(y), float(z)])
            csvfile.flush()  # сразу сохраняем на диск

        except socket.timeout:
            pass  # данных нет — просто идём дальше

        # Перерисовываем график
        ax.cla()
        if len(xs) > 1:
            ax.set_xlim(min(xs) - 1, max(xs) + 1)
            ax.set_ylim(min(ys) - 1, max(ys) + 1)
            ax.set_zlim(min(zs) - 1, max(zs) + 1)
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.set_title('Полёт дрона в реальном времени')

        if len(xs) > 1:
            ax.plot(xs, ys, zs, 'b-', linewidth=1)
            ax.scatter(xs[-1], ys[-1], zs[-1], c='red', s=100)

        fig.canvas.draw()  # добавь эту строку
        fig.canvas.flush_events()  # и эту
        plt.pause(0.05)
        # В конце цикла после plt.pause
