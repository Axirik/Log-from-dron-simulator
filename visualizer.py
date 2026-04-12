import math, time, socket, threading, csv
import tkinter as tk
import matplotlib
import numpy as np
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ── Цвета ──
BG      = '#0d1117'
BG2     = '#161b22'
BORDER  = '#30363d'
FG      = '#f0f6fc'
FG_DIM  = '#8b949e'
BLUE    = '#58a6ff'
GREEN   = '#39d353'
RED     = '#f85149'
ORANGE  = '#f0883e'
PURPLE  = '#bc8cff'

# ── Настройки ──
UDP_PORT = 14551
TAIL     = 300

# ── Общие данные между потоками ──
lock  = threading.Lock()
state = {
    'xs': [], 'ys': [], 'zs': [],
    'rolls': [], 'pitches': [],
    'times': [],
    'cur_x': 0.0, 'cur_y': 0.0, 'cur_z': 0.0,
    'cur_roll': 0.0, 'cur_pitch': 0.0,
    'cur_thrust': 0.0, 'cur_voltage': 12.6,
    'packets': 0,
    'recording': False,
    'csv_writer': None,
    'csv_file': None,
    'running': True,
    'cur_state': 'LANDED'
}

# ── UDP поток ──
def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', UDP_PORT))
    sock.settimeout(0.1)
    print(f"Слушаю порт {UDP_PORT}...")

    while state['running']:
        try:
            data, _ = sock.recvfrom(1024)
            parts = data.decode().strip().split(',')
            t, x, y, z, roll, pitch, thrust, voltage, yaw = map(float, parts[:9])
            drone_state = parts[9]

            with lock:
                state['xs'].append(x)
                state['ys'].append(y)
                state['zs'].append(z)
                state['rolls'].append(roll)
                state['pitches'].append(pitch)
                state['times'].append(time.time())
                state['packets'] += 1
                state['cur_state'] = drone_state
                state.update({
                    'cur_x': x, 'cur_y': y, 'cur_z': z,
                    'cur_roll': roll, 'cur_pitch': pitch,
                    'cur_thrust': thrust, 'cur_voltage': voltage,
                })

                if state['recording'] and state['csv_writer']:
                    state['csv_writer'].writerow(
                        [f"{time.time():.3f}", f"{x:.3f}", f"{y:.3f}",
                         f"{z:.3f}", f"{roll:.3f}", f"{pitch:.3f}",
                         f"{thrust:.3f}", f"{voltage:.3f}"])
                    state['csv_file'].flush()

        except socket.timeout:
            pass
        except Exception as e:
            print(f"Ошибка: {e}")
    sock.close()

# ── Главный класс окна ──
class App:
    def __init__(self, root):
        self.root = root
        root.title("Drone Monitor")
        root.configure(bg=BG)
        root.geometry('1400x700')
        self._build_ui()
        threading.Thread(target=udp_listener, daemon=True).start()
        self._update()

    def _build_ui(self):
        # Левая панель
        left = tk.Frame(self.root, bg=BG2, width=220)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left.pack_propagate(False)

        tk.Label(left, text="ТЕЛЕМЕТРИЯ", bg=BG2,
                 fg=BLUE, font=('Courier', 12, 'bold')).pack(pady=10)

        self.v = {}
        fields = [
            ('X',       'cur_x',       'м'),
            ('Y',       'cur_y',       'м'),
            ('Z',       'cur_z',       'м'),
            ('Roll',    'cur_roll',    '°'),
            ('Pitch',   'cur_pitch',   '°'),
            ('Тяга',    'cur_thrust',  ''),
            ('Батарея', 'cur_voltage', 'В'),
            ('Пакеты',  'packets',     ''),
            ('Статус', 'cur_state', ''),
        ]

        for label, key, unit in fields:
            row = tk.Frame(left, bg=BG2)
            row.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(row, text=label, bg=BG2, fg=FG_DIM,
                     font=('Courier', 9), width=8, anchor='w').pack(side=tk.LEFT)
            var = tk.StringVar(value='--')
            self.v[key] = (var, unit)

            # Батарея красная если низкая
            color = RED if key == 'cur_voltage' else GREEN
            tk.Label(row, textvariable=var, bg=BG2, fg=color,
                     font=('Courier', 10, 'bold')).pack(side=tk.LEFT)

        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, pady=10)

        self.rec_btn = tk.Button(
            left, text='⏺ ЗАПИСЬ', bg='#238636', fg=FG,
            font=('Courier', 9, 'bold'), relief='flat',
            command=self._toggle_recording)
        self.rec_btn.pack(fill=tk.X, padx=10, pady=3)

        tk.Button(
            left, text='🗑 ОЧИСТИТЬ', bg='#21262d', fg=FG,
            font=('Courier', 9), relief='flat',
            command=self._clear).pack(fill=tk.X, padx=10, pady=3)

        tk.Button(
            left, text='✕ ВЫХОД', bg='#b91c1c', fg=FG,
            font=('Courier', 9), relief='flat',
            command=self._quit).pack(fill=tk.X, padx=10, pady=3)

        # Правая часть — три графика
        right = tk.Frame(self.root, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        fig = Figure(figsize=(9, 6), facecolor=BG)
        self.ax3d = fig.add_subplot(121, projection='3d')
        self.ax_alt = fig.add_subplot(222)
        self.ax_rp = fig.add_subplot(224)

        # Стиль 3D
        self.ax3d.set_facecolor(BG)
        self.ax3d.set_title('3D Траектория', color=FG, fontsize=9)

        # Стиль высоты
        self.ax_alt.set_facecolor(BG2)
        self.ax_alt.set_title('Высота Z (м)', color=GREEN, fontsize=9)
        self.ax_alt.tick_params(colors=FG_DIM)
        for spine in self.ax_alt.spines.values():
            spine.set_edgecolor(BORDER)

        # Стиль roll/pitch
        self.ax_rp.set_facecolor(BG2)
        self.ax_rp.set_title('Roll / Pitch', color=ORANGE, fontsize=9)
        self.ax_rp.tick_params(colors=FG_DIM)
        for spine in self.ax_rp.spines.values():
            spine.set_edgecolor(BORDER)

        self.canvas = FigureCanvasTkAgg(fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.fig = fig

    def _update(self):
        try:
            with lock:
                s = dict(state)
            state_colors = {
                'LANDED': '#8b949e',
                'TAKEOFF': '#39d353',
                'HOVER': '#58a6ff',
                'FLYING': '#58a6ff',
                'LANDING': '#e3b341',
                'EMERGENCY': '#f85149',
            }
            cur = s.get('cur_state', 'LANDED')
            # обновляем цвет метки статуса
            if 'cur_state' in self.v:
                self.v['cur_state'][0].set(cur)
            # Обновляем метки
            for key, (var, unit) in self.v.items():
                val = s.get(key, 0)
                if isinstance(val, float):
                    var.set(f"{val:.2f} {unit}")
                else:
                    var.set(f"{val} {unit}")

            # Копируем данные
            with lock:
                xs      = list(state['xs'])
                ys      = list(state['ys'])
                zs      = list(state['zs'])
                rolls   = list(state['rolls'])
                pitches = list(state['pitches'])

            n = len(xs)
            if n > 1:
                self.ax3d.set_zlim(0, max(zs) + 1)
            else:
                self.ax3d.set_zlim(0, 5)  # дефолт когда нет данных

            # 3D траектория
            self.ax3d.cla()
            self.ax3d.set_zlim(bottom=0)
            self.ax3d.set_facecolor(BG)
            self.ax3d.set_title('3D Траектория', color=FG, fontsize=9)
            self.ax3d.tick_params(colors=FG_DIM, labelsize=7)
            if n > 1:
                self.ax3d.plot(xs, ys, zs, color=BLUE, linewidth=1.2)
                self.ax3d.scatter(xs[-1], ys[-1], zs[-1], c=RED,   s=60, zorder=5)
                self.ax3d.scatter(xs[0],  ys[0],  zs[0],  c=GREEN, s=60,
                                  marker='^', zorder=5)


            # График высоты
            self.ax_alt.cla()
            self.ax_alt.set_facecolor(BG2)
            self.ax_alt.set_title('Высота Z (м)', color=GREEN, fontsize=9)
            self.ax_alt.tick_params(colors=FG_DIM, labelsize=7)
            for spine in self.ax_alt.spines.values():
                spine.set_edgecolor(BORDER)
            if n > 1:
                tail = zs[-TAIL:]
                self.ax_alt.plot(tail, color=GREEN, linewidth=1.2)
                self.ax_alt.fill_between(range(len(tail)), tail,
                                          alpha=0.15, color=GREEN)

            # График roll/pitch
            self.ax_rp.cla()
            self.ax_rp.set_facecolor(BG2)
            self.ax_rp.set_title('Roll / Pitch', color=ORANGE, fontsize=9)
            self.ax_rp.tick_params(colors=FG_DIM, labelsize=7)
            for spine in self.ax_rp.spines.values():
                spine.set_edgecolor(BORDER)
            if len(rolls) > 1:
                r = rolls[-TAIL:]
                p = pitches[-TAIL:]
                self.ax_rp.plot(r, color=ORANGE,  linewidth=1.2, label='Roll')
                self.ax_rp.plot(p, color=PURPLE, linewidth=1.2, label='Pitch')
                self.ax_rp.legend(fontsize=7, facecolor=BG2,
                                   edgecolor=BORDER, labelcolor=FG)

            self.canvas.draw_idle()

        except Exception as e:
            print(f"[UI] {e}")

        self.root.after(100, self._update)

    def _toggle_recording(self):
        with lock:
            if not state['recording']:
                f = open('flight_log.csv', 'w', newline='')
                w = csv.writer(f)
                w.writerow(['time','x','y','z','roll','pitch','thrust','voltage'])
                state['csv_file']   = f
                state['csv_writer'] = w
                state['recording']  = True
                self.rec_btn.config(text='⏹ СТОП', bg='#b91c1c')
            else:
                state['recording'] = False
                if state['csv_file']:
                    state['csv_file'].close()
                state['csv_file']   = None
                state['csv_writer'] = None
                self.rec_btn.config(text='⏺ ЗАПИСЬ', bg='#238636')

    def _clear(self):
        with lock:
            state['xs'].clear()
            state['ys'].clear()
            state['zs'].clear()
            state['rolls'].clear()
            state['pitches'].clear()
            state['times'].clear()
            state['packets'] = 0

    def _quit(self):
        state['running'] = False
        self.root.quit()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.protocol('WM_DELETE_WINDOW', app._quit)
    root.mainloop()