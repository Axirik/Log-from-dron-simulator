import csv
import time
import math
import socket
import threading
import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.gridspec as gridspec

# ══════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ══════════════════════════════════════════════════════════
UDP_IP   = '0.0.0.0'
UDP_PORT = 14551
CSV_FILE = 'flight_log.csv'
TAIL     = 200   # сколько последних точек показывать на 2D-графиках

CSV_HEADER = [
    'timestamp_unix', 'flight_time_s',
    'x', 'y', 'z',
    'roll_deg', 'pitch_deg',
    'thrust_pct', 'voltage_v',
    'speed_m_s',
    'dist_from_home_m',
    'altitude_agl_m',
]

# ══════════════════════════════════════════════════════════
#  ЦВЕТА
# ══════════════════════════════════════════════════════════
BG       = '#0d1117'
BG2      = '#161b22'
BORDER   = '#30363d'
FG       = '#f0f6fc'
FG_DIM   = '#8b949e'
BLUE     = '#58a6ff'
GREEN    = '#39d353'
RED      = '#f85149'
ORANGE   = '#f0883e'
PURPLE   = '#bc8cff'
YELLOW   = '#e3b341'

# ══════════════════════════════════════════════════════════
#  ГЛОБАЛЬНОЕ СОСТОЯНИЕ
# ══════════════════════════════════════════════════════════
data_lock = threading.Lock()

# state — единый словарь, доступный обоим потокам через data_lock
state = {
    # накопленные ряды данных
    'xs': [], 'ys': [], 'zs': [],
    'rolls': [], 'pitches': [],
    'thrusts': [], 'voltages': [],
    'speeds': [],
    'times': [],          # unix-время каждого пакета

    # текущие (последние) значения для панели телеметрии
    'cur_x': 0.0, 'cur_y': 0.0, 'cur_z': 0.0,
    'cur_roll': 0.0, 'cur_pitch': 0.0,
    'cur_thrust': 0.0, 'cur_voltage': 0.0,
    'cur_speed': 0.0,
    'cur_dist': 0.0,

    # статистика
    'max_alt': 0.0,
    'max_speed': 0.0,
    'packet_count': 0,
    'flight_start': None,   # unix-время первого пакета

    # управление
    'recording': False,
    'running': True,
    'csv_writer': None,
    'csv_file': None,
}

# ══════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ВЫЧИСЛЕНИЯ
# ══════════════════════════════════════════════════════════

def calc_speed(xs, ys, zs, ts):
    """
    Мгновенная скорость = евклидово смещение между двумя
    последними точками, делённое на время между ними.
    Возвращает 0 если точек меньше двух.
    """
    if len(xs) < 2:
        return 0.0
    dx = xs[-1] - xs[-2]
    dy = ys[-1] - ys[-2]
    dz = zs[-1] - zs[-2]
    dt = ts[-1] - ts[-2]
    if dt <= 0:
        return 0.0
    return math.sqrt(dx**2 + dy**2 + dz**2) / dt


def calc_dist(xs, ys, zs):
    """
    Прямолинейное расстояние от начала координат (точка взлёта).
    """
    if not xs:
        return 0.0
    return math.sqrt(xs[-1]**2 + ys[-1]**2 + zs[-1]**2)

# ══════════════════════════════════════════════════════════
#  UDP-ПОТОК  (работает в фоне, не блокирует UI)
# ══════════════════════════════════════════════════════════

def udp_listener():
    """
    Бесконечный цикл приёма UDP-пакетов.
    Запускается в daemon-потоке — автоматически завершается
    при закрытии главного окна.

    Формат пакета (от симулятора):
        t,x,y,z,roll,pitch,thrust,voltage
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    sock.settimeout(0.1)          # таймаут нужен, чтобы проверять state['running']
    print(f"[UDP] Слушаю {UDP_IP}:{UDP_PORT}")

    while state['running']:
        try:
            data, _ = sock.recvfrom(1024)
            t, x, y, z, roll, pitch, thrust, voltage = map(
                float, data.decode().strip().split(','))

            now = time.time()

            # ── блокируем словарь state на время записи ──
            with data_lock:
                if state['flight_start'] is None:
                    state['flight_start'] = now

                # добавляем точку в накопленные ряды
                state['xs'].append(x)
                state['ys'].append(y)
                state['zs'].append(z)
                state['rolls'].append(roll)
                state['pitches'].append(pitch)
                state['thrusts'].append(thrust)
                state['voltages'].append(voltage)
                state['times'].append(now)
                state['packet_count'] += 1

                # вычисляем производные
                speed = calc_speed(state['xs'], state['ys'],
                                   state['zs'], state['times'])
                dist  = calc_dist(state['xs'], state['ys'], state['zs'])
                state['speeds'].append(speed)

                # обновляем «текущие» значения (читаются UI-потоком)
                state.update({
                    'cur_x': x, 'cur_y': y, 'cur_z': z,
                    'cur_roll': roll, 'cur_pitch': pitch,
                    'cur_thrust': thrust, 'cur_voltage': voltage,
                    'cur_speed': speed, 'cur_dist': dist,
                    'max_alt':   max(state['max_alt'],   z),
                    'max_speed': max(state['max_speed'], speed),
                })

                # запись в CSV (только когда пользователь нажал «Начать запись»)
                if state['recording'] and state['csv_writer']:
                    flight_time = now - state['flight_start']
                    state['csv_writer'].writerow([
                        f"{now:.3f}",
                        f"{flight_time:.2f}",
                        f"{x:.4f}", f"{y:.4f}", f"{z:.4f}",
                        f"{roll:.4f}", f"{pitch:.4f}",
                        f"{thrust:.4f}", f"{voltage:.4f}",
                        f"{speed:.4f}",
                        f"{dist:.4f}",
                        f"{z:.4f}",          # altitude AGL = z (взлёт с z=0)
                    ])
                    # flush() — сразу на диск; без него при краше теряем буфер
                    state['csv_file'].flush()

        except socket.timeout:
            pass   # данных нет — просто идём дальше
        except Exception as e:
            print(f"[UDP] Ошибка разбора: {e}")

    sock.close()
    print("[UDP] Сокет закрыт")

# ══════════════════════════════════════════════════════════
#  ГЛАВНЫЙ КЛАСС GUI
# ══════════════════════════════════════════════════════════

class DroneGUI:
    """
    Строит окно tkinter с двумя зонами:
      • Левая панель  — телеметрия, статистика, кнопки управления
      • Правая часть  — matplotlib-холст с 4 графиками:
          [0,0] span=3 rows  — 3D траектория
          [0,1]              — Высота Z
          [1,1]              — Скорость
          [2,1]              — Roll + Pitch (°) и Voltage (В) — двойная ось Y
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Drone Flight Monitor")
        root.configure(bg=BG)
        root.geometry('1400x860')
        root.resizable(True, True)

        self._build_layout()
        threading.Thread(target=udp_listener, daemon=True).start()
        self._update_loop()

    # ──────────────────────────────────────────
    #  КОМПОНОВКА ОКНА
    # ──────────────────────────────────────────

    def _build_layout(self):
        left = tk.Frame(self.root, bg=BG, width=280)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0), pady=10)
        left.pack_propagate(False)

        right = tk.Frame(self.root, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._build_left_panel(left)
        self._build_plot_area(right)

    # ──────────────────────────────────────────
    #  ЛЕВАЯ ПАНЕЛЬ
    # ──────────────────────────────────────────

    def _build_left_panel(self, parent):
        tk.Label(parent, text='DRONE MONITOR', bg=BG,
                 fg=BLUE, font=('Consolas', 14, 'bold')).pack(pady=(0, 2))
        tk.Label(parent, text='Real-Time Telemetry', bg=BG,
                 fg=FG_DIM, font=('Consolas', 9)).pack()

        self.conn_var = tk.StringVar(value='● ОЖИДАНИЕ')
        self._conn_lbl = tk.Label(parent, textvariable=self.conn_var,
                                  bg=BG, fg=ORANGE,
                                  font=('Consolas', 10, 'bold'))
        self._conn_lbl.pack(pady=(6, 0))

        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=8)

        f = self._section(parent, ' ПОЗИЦИЯ')
        self.v_x    = self._row(f, 'X', 0)
        self.v_y    = self._row(f, 'Y', 1)
        self.v_z    = self._row(f, 'Z', 2)
        self.v_dist = self._row(f, 'Дист. от дома', 3)

        f2 = self._section(parent, ' ОРИЕНТАЦИЯ')
        self.v_roll  = self._row(f2, 'Roll',  0)
        self.v_pitch = self._row(f2, 'Pitch', 1)

        f3 = self._section(parent, ' ДВИГАТЕЛЬ / ПИТАНИЕ')
        self.v_thrust  = self._row(f3, 'Тяга',       0)
        self.v_voltage = self._row(f3, 'Напряжение', 1)
        self.v_speed   = self._row(f3, 'Скорость',   2)

        f4 = self._section(parent, ' СТАТИСТИКА')
        self.v_maxalt   = self._row(f4, 'Макс. высота',   0)
        self.v_maxspeed = self._row(f4, 'Макс. скорость', 1)
        self.v_packets  = self._row(f4, 'Пакетов',        2)
        self.v_ftime    = self._row(f4, 'Время полёта',   3)

        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=10)

        btn = tk.Frame(parent, bg=BG)
        btn.pack(fill=tk.X)

        self.rec_btn = tk.Button(
            btn, text='⏺  НАЧАТЬ ЗАПИСЬ',
            bg='#238636', fg='white', activebackground='#2ea043',
            font=('Consolas', 10, 'bold'), relief='flat', cursor='hand2',
            command=self._toggle_recording)
        self.rec_btn.pack(fill=tk.X, pady=3)

        tk.Button(btn, text='   ОЧИСТИТЬ ТРЕК',
                  bg='#21262d', fg=RED, activebackground='#30363d',
                  font=('Consolas', 10), relief='flat', cursor='hand2',
                  command=self._clear_track).pack(fill=tk.X, pady=3)

        tk.Button(btn, text='X  ВЫЙТИ',
                  bg='#21262d', fg=FG_DIM, activebackground='#30363d',
                  font=('Consolas', 10), relief='flat', cursor='hand2',
                  command=self._quit).pack(fill=tk.X, pady=3)

        self.rec_status = tk.Label(parent, text='', bg=BG,
                                   fg=RED, font=('Consolas', 9))
        self.rec_status.pack(pady=(4, 0))

    def _section(self, parent, title: str) -> tk.Frame:
        tk.Label(parent, text=title, bg=BG, fg=FG,
                 font=('Consolas', 10, 'bold')).pack(anchor='w', pady=(10, 2))
        frame = tk.Frame(parent, bg=BG2)
        frame.pack(fill=tk.X)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        return frame

    def _row(self, parent, label: str, row: int) -> tk.StringVar:
        tk.Label(parent, text=label, bg=BG2, fg=FG_DIM,
                 font=('Consolas', 9), anchor='w').grid(
            row=row, column=0, sticky='w', padx=8, pady=2)
        var = tk.StringVar(value='—')
        tk.Label(parent, textvariable=var, bg=BG2,
                 fg=BLUE, font=('Consolas', 11, 'bold'),
                 anchor='e').grid(row=row, column=1, sticky='e', padx=8, pady=2)
        return var

    # ──────────────────────────────────────────
    #  ОБЛАСТЬ ГРАФИКОВ
    # ──────────────────────────────────────────

    def _build_plot_area(self, parent):
        self.fig = Figure(figsize=(10, 8), facecolor=BG)

        # GridSpec 3×2:
        #   колонка 0 (3D) — занимает строки 0..2
        #   колонка 1      — три отдельных графика
        gs = gridspec.GridSpec(3, 2, figure=self.fig,
                               hspace=0.45, wspace=0.32)

        self.ax3d   = self.fig.add_subplot(gs[:, 0], projection='3d')
        self.ax_alt = self.fig.add_subplot(gs[0, 1])
        self.ax_spd = self.fig.add_subplot(gs[1, 1])
        self.ax_arp = self.fig.add_subplot(gs[2, 1])  # roll+pitch+voltage

        self._style_3d(self.ax3d)
        self._style_2d(self.ax_alt, 'Высота Z (м)',        GREEN)
        self._style_2d(self.ax_spd, 'Скорость (м/с)',      BLUE)
        self._style_2d(self.ax_arp, 'Roll / Pitch / Volt', PURPLE)

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # ──────────────────────────────────────────
    #  СТИЛИ ОСЕЙ
    # ──────────────────────────────────────────

    def _style_3d(self, ax):
        ax.set_facecolor(BG)
        for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
            pane.fill = False
            pane.set_edgecolor(BORDER)
        ax.tick_params(colors=FG_DIM, labelsize=7)
        ax.set_xlabel('X', color=FG_DIM, fontsize=8)
        ax.set_ylabel('Y', color=FG_DIM, fontsize=8)
        ax.set_zlabel('Z', color=FG_DIM, fontsize=8)
        ax.set_title('3D Траектория', color=FG, fontsize=9, pad=8)

    def _style_2d(self, ax, title: str, color: str):
        ax.set_facecolor(BG2)
        ax.tick_params(colors=FG_DIM, labelsize=7)
        ax.set_title(title, color=color, fontsize=8, pad=4)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)

    # ──────────────────────────────────────────
    #  УПРАВЛЕНИЕ ЗАПИСЬЮ
    # ──────────────────────────────────────────

    def _toggle_recording(self):
        with data_lock:
            if not state['recording']:
                f = open(CSV_FILE, 'w', newline='', encoding='utf-8')
                w = csv.writer(f)
                w.writerow(CSV_HEADER)
                state['csv_file']   = f
                state['csv_writer'] = w
                state['recording']  = True
                self.rec_btn.config(text='⏹  ОСТАНОВИТЬ ЗАПИСЬ', bg='#b91c1c')
                self.rec_status.config(text=f'● Запись: {CSV_FILE}', fg=RED)
            else:
                state['recording'] = False
                if state['csv_file']:
                    state['csv_file'].close()
                state['csv_file']   = None
                state['csv_writer'] = None
                self.rec_btn.config(text='⏺  НАЧАТЬ ЗАПИСЬ', bg='#238636')
                self.rec_status.config(text='Запись остановлена', fg=FG_DIM)

    def _clear_track(self):
        with data_lock:
            for key in ('xs','ys','zs','rolls','pitches',
                        'thrusts','voltages','speeds','times'):
                state[key].clear()
            state['max_alt']      = 0.0
            state['max_speed']    = 0.0
            state['flight_start'] = None

    def _quit(self):
        state['running'] = False
        with data_lock:
            if state['csv_file']:
                state['csv_file'].close()
        self.root.quit()
        self.root.destroy()

    # ──────────────────────────────────────────
    #  ЦИКЛ ОБНОВЛЕНИЯ  (~12 fps)
    # ──────────────────────────────────────────

    def _update_loop(self):
        """
        root.after() планирует вызов этой функции через 80 мс.
        Это НЕ отдельный поток — событие в очереди tkinter.
        Безопасно обращаться к виджетам без блокировок.
        """
        try:
            self._refresh_labels()
            self._refresh_plots()
        except Exception as e:
            print(f"[UI] Ошибка: {e}")
        self.root.after(80, self._update_loop)

    def _refresh_labels(self):
        with data_lock:
            s = dict(state)  # копия скалярных полей

        if s['packet_count'] > 0:
            self.conn_var.set('● ПОДКЛЮЧЕНО')
            self._conn_lbl.config(fg=GREEN)
        else:
            self.conn_var.set('● ОЖИДАНИЕ')
            self._conn_lbl.config(fg=ORANGE)

        self.v_x.set(f"{s['cur_x']:.2f} м")
        self.v_y.set(f"{s['cur_y']:.2f} м")
        self.v_z.set(f"{s['cur_z']:.2f} м")
        self.v_dist.set(f"{s['cur_dist']:.2f} м")
        self.v_roll.set(f"{s['cur_roll']:.1f}°")
        self.v_pitch.set(f"{s['cur_pitch']:.1f}°")
        self.v_thrust.set(f"{s['cur_thrust']*100:.1f}%")
        self.v_voltage.set(f"{s['cur_voltage']:.2f} В")
        self.v_speed.set(f"{s['cur_speed']:.2f} м/с")
        self.v_maxalt.set(f"{s['max_alt']:.2f} м")
        self.v_maxspeed.set(f"{s['max_speed']:.2f} м/с")
        self.v_packets.set(str(s['packet_count']))

        if s['flight_start']:
            elapsed = time.time() - s['flight_start']
            m, sec = divmod(int(elapsed), 60)
            self.v_ftime.set(f"{m:02d}:{sec:02d}")
        else:
            self.v_ftime.set('00:00')

    def _refresh_plots(self):
        # копируем списки под локом, освобождаем лок до перерисовки
        with data_lock:
            xs       = list(state['xs'])
            ys       = list(state['ys'])
            zs       = list(state['zs'])
            speeds   = list(state['speeds'])
            rolls    = list(state['rolls'])
            pitches  = list(state['pitches'])
            voltages = list(state['voltages'])

        n = len(xs)

        # ── 3D-траектория ─────────────────────
        self.ax3d.cla()
        self._style_3d(self.ax3d)
        if n > 1:
            pad = 1
            self.ax3d.set_xlim(min(xs)-pad, max(xs)+pad)
            self.ax3d.set_ylim(min(ys)-pad, max(ys)+pad)
            self.ax3d.set_zlim(min(zs)-pad, max(zs)+pad)
            self.ax3d.plot(xs, ys, zs, color=BLUE, linewidth=1.2, alpha=0.85)
            self.ax3d.scatter(xs[-1], ys[-1], zs[-1], c=RED,   s=60, zorder=5)
            self.ax3d.scatter(xs[0],  ys[0],  zs[0],  c=GREEN, s=60, marker='^', zorder=5)

        # ── Высота ────────────────────────────
        self.ax_alt.cla()
        self._style_2d(self.ax_alt, 'Высота Z (м)', GREEN)
        if n > 1:
            t = zs[-TAIL:]
            self.ax_alt.plot(t, color=GREEN, linewidth=1.2)
            self.ax_alt.fill_between(range(len(t)), t, alpha=0.15, color=GREEN)

        # ── Скорость ──────────────────────────
        self.ax_spd.cla()
        self._style_2d(self.ax_spd, 'Скорость (м/с)', BLUE)
        if len(speeds) > 1:
            t = speeds[-TAIL:]
            self.ax_spd.plot(t, color=BLUE, linewidth=1.2)
            self.ax_spd.fill_between(range(len(t)), t, alpha=0.15, color=BLUE)

        # ── Roll + Pitch + Voltage ─────────────
        #
        # Две оси Y на одном графике:
        #   ax_arp  — левая ось,  Roll° (фиолетовый) + Pitch° (жёлтый)
        #   ax_v    — правая ось, Voltage В (оранжевый, пунктир)
        #
        # twinx() создаёт новую ось Y, совмещённую по X с ax_arp.
        # После cla() twin-ось нужно пересоздавать каждый кадр.
        #
        self.ax_arp.cla()
        self._style_2d(self.ax_arp, 'Roll / Pitch / Voltage', PURPLE)

        if len(rolls) > 1:
            r   = rolls[-TAIL:]
            p   = pitches[-TAIL:]
            idx = range(len(r))

            # левая ось — углы
            self.ax_arp.plot(idx, r, color=PURPLE, linewidth=1.2, label='Roll °')
            self.ax_arp.plot(idx, p, color=YELLOW, linewidth=1.2, label='Pitch °')
            self.ax_arp.set_ylabel('Угол (°)', color=FG_DIM, fontsize=7)
            self.ax_arp.tick_params(axis='y', colors=FG_DIM, labelsize=7)



            # объединяем легенды обеих осей в одну
            l1, lb1 = self.ax_arp.get_legend_handles_labels()
            self.ax_arp.legend(l1 , lb1 ,
                               loc='upper left', fontsize=7,
                               facecolor=BG2, edgecolor=BORDER,
                               labelcolor=FG)

        # draw_idle — откладывает перерисовку до следующей итерации
        # event loop, не блокирует UI
        self.canvas.draw_idle()


# ══════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════
if __name__ == '__main__':
    root = tk.Tk()
    app = DroneGUI(root)
    root.protocol('WM_DELETE_WINDOW', app._quit)
    root.mainloop()
