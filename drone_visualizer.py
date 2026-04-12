import math, time, socket, threading, csv
import tkinter as tk
from tkinter import filedialog
import matplotlib
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
YELLOW  = '#e3b341'

# ── Настройки ──
UDP_PORT = 14551
TAIL     = 300

# ── Цвета состояний ──
STATE_COLORS = {
    'LANDED':    '#8b949e',
    'TAKEOFF':   '#39d353',
    'HOVER':     '#58a6ff',
    'FLYING':    '#58a6ff',
    'LANDING':   '#e3b341',
    'EMERGENCY': '#f85149',
}

# ── Общие данные ──
lock  = threading.Lock()
state = {
    'xs': [], 'ys': [], 'zs': [],
    'rolls': [], 'pitches': [],
    'times': [],
    'cur_x': 0.0, 'cur_y': 0.0, 'cur_z': 0.0,
    'cur_roll': 0.0, 'cur_pitch': 0.0,
    'cur_thrust': 0.0, 'cur_voltage': 0.0,
    'cur_state': 'LANDED',
    'packets': 0,
    'running': True,
    'states': [],
    'mode': 'LIVE',  # LIVE или REPLAY
    'flight_start': None,
    'replay_start': '--',
    'replay_end':   '--',
    'replay_total': 0.0,
}

# ══════════════════════════════════════
#  UDP ПОТОК — режим LIVE
# ══════════════════════════════════════
def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', UDP_PORT))
    sock.settimeout(0.1)
    print(f"[LIVE] Слушаю порт {UDP_PORT}...")

    while state['running']:
        if state['mode'] != 'LIVE':
            time.sleep(0.1)
            continue
        if state['flight_start'] is None and drone_state != 'LANDED':
            state['flight_start'] = time.time()
        if drone_state == 'LANDED':
            state['flight_start'] = None
        try:
            data, _ = sock.recvfrom(1024)
            parts   = data.decode().strip().split(',')
            t, x, y, z, roll, pitch, thrust, voltage, yaw = map(float, parts[:9])
            drone_state = parts[9]
              # инвертируем для отображения

            with lock:
                state['xs'].append(x)
                state['ys'].append(y)
                state['zs'].append(z)
                state['rolls'].append(roll)
                state['pitches'].append(pitch)
                state['states'].append(drone_state)
                state['times'].append(time.time())
                state['packets'] += 1
                state.update({
                    'cur_x': x, 'cur_y': y, 'cur_z': z,
                    'cur_roll': roll, 'cur_pitch': pitch,
                    'cur_thrust': thrust, 'cur_voltage': voltage,
                    'cur_state': drone_state,
                })

        except socket.timeout:
            pass
        except Exception as e:
            print(f"[LIVE] Ошибка: {e}")
    sock.close()

# ══════════════════════════════════════
#  ЗАГРУЗКА CSV — режим REPLAY
# ══════════════════════════════════════
def load_csv(filepath):
    """Читает CSV и заполняет state данными"""
    with lock:
        state['xs'].clear()
        state['ys'].clear()
        state['zs'].clear()
        state['rolls'].clear()
        state['pitches'].clear()
        state['times'].clear()
        state['packets'] = 0


    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            with lock:
                state['xs'].append(float(row['x']))
                state['ys'].append(float(row['y']))
                state['zs'].append(float(row['z']))  # инвертируем
                state['rolls'].append(float(row['roll']))
                state['pitches'].append(float(row['pitch']))
                state['times'].append(float(row['time']))
                state['packets'] += 1
                state['states'].append(row.get('state', 'FLYING'))

    # Показываем последнюю точку в телеметрии
    with lock:
        if state['xs']:
            # Время начала и конца
            t_start = state['times'][0]
            t_end = state['times'][-1]
            total = t_end - t_start

            from datetime import datetime
            state['replay_start'] = datetime.fromtimestamp(t_start).strftime('%H:%M:%S')
            state['replay_end'] = datetime.fromtimestamp(t_end).strftime('%H:%M:%S')
            state['replay_total'] = total

    print(f"[REPLAY] Загружено {state['packets']} точек из {filepath}")

# ══════════════════════════════════════
#  ГЛАВНЫЙ КЛАСС
# ══════════════════════════════════════
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
        # ── Левая панель ──
        left = tk.Frame(self.root, bg=BG2, width=230)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left.pack_propagate(False)

        tk.Label(left, text="ТЕЛЕМЕТРИЯ", bg=BG2,
                 fg=BLUE, font=('Courier', 12, 'bold')).pack(pady=10)

        # Метки телеметрии
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
            ('Статус',  'cur_state',   ''),

        ]

        self._label_widgets = {}  # для динамического цвета

        for label, key, unit in fields:
            row = tk.Frame(left, bg=BG2)
            row.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(row, text=label, bg=BG2, fg=FG_DIM,
                     font=('Courier', 9), width=8, anchor='w').pack(side=tk.LEFT)
            var = tk.StringVar(value='--')
            self.v[key] = (var, unit)
            color = RED if key == 'cur_voltage' else GREEN
            lbl = tk.Label(row, textvariable=var, bg=BG2, fg=color,
                           font=('Courier', 10, 'bold'))
            lbl.pack(side=tk.LEFT)
            self._label_widgets[key] = lbl

        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, pady=10)

        # ── Режим работы ──
        tk.Label(left, text="РЕЖИМ", bg=BG2,
                 fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=3)

        self.mode_var = tk.StringVar(value='LIVE')

        mode_frame = tk.Frame(left, bg=BG2)
        mode_frame.pack(fill=tk.X, padx=10, pady=3)

        tk.Radiobutton(
            mode_frame, text='LIVE', variable=self.mode_var,
            value='LIVE', bg=BG2, fg=GREEN, selectcolor=BG,
            font=('Courier', 9), command=self._set_live
        ).pack(side=tk.LEFT)

        tk.Radiobutton(
            mode_frame, text='REPLAY', variable=self.mode_var,
            value='REPLAY', bg=BG2, fg=ORANGE, selectcolor=BG,
            font=('Courier', 9), command=self._set_replay
        ).pack(side=tk.LEFT)

        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, pady=10)

        # ── Кнопки ──
        tk.Button(
            left, text='🗑 ОЧИСТИТЬ', bg='#21262d', fg=FG,
            font=('Courier', 9), relief='flat',
            command=self._clear).pack(fill=tk.X, padx=10, pady=3)

        tk.Button(
            left, text='✕ ВЫХОД', bg='#b91c1c', fg=FG,
            font=('Courier', 9), relief='flat',
            command=self._quit).pack(fill=tk.X, padx=10, pady=3)
        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, pady=10)

        # Время полёта
        tk.Label(left, text="ВРЕМЯ ПОЛЁТА", bg=BG2,
                 fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=3)

        self.flight_time_var = tk.StringVar(value='00:00')
        tk.Label(left, textvariable=self.flight_time_var, bg=BG2,
                 fg=YELLOW, font=('Courier', 14, 'bold')).pack(pady=3)

        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, pady=10)

        # Легенда состояний
        tk.Label(left, text="ЛЕГЕНДА", bg=BG2,
                 fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=3)

        for s_name, s_color in STATE_COLORS.items():
            row = tk.Frame(left, bg=BG2)
            row.pack(fill=tk.X, padx=10, pady=2)
            # Цветной квадратик
            tk.Label(row, text='■', bg=BG2, fg=s_color,
                     font=('Courier', 10)).pack(side=tk.LEFT)
            tk.Label(row, text=s_name, bg=BG2, fg=FG_DIM,
                     font=('Courier', 8)).pack(side=tk.LEFT, padx=5)

        # ── Правая часть — графики ──
        right = tk.Frame(self.root, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        fig = Figure(figsize=(9, 6), facecolor=BG)
        self.ax3d   = fig.add_subplot(121, projection='3d')
        self.ax_alt = fig.add_subplot(222)
        self.ax_rp  = fig.add_subplot(224)

        self.ax3d.set_facecolor(BG)
        self.ax3d.set_title('3D Траектория', color=FG, fontsize=9)

        for ax, title, color in [
            (self.ax_alt, 'Высота Z (м)', GREEN),
            (self.ax_rp,  'Roll / Pitch',  ORANGE),
        ]:
            ax.set_facecolor(BG2)
            ax.set_title(title, color=color, fontsize=9)
            ax.tick_params(colors=FG_DIM)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
            tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, pady=10)

            tk.Label(left, text="СТАТИСТИКА", bg=BG2,
                     fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=3)

            self.replay_info = tk.StringVar(value='—')
            tk.Label(left, textvariable=self.replay_info,
                     bg=BG2, fg=ORANGE,
                     font=('Courier', 8), justify=tk.LEFT).pack(padx=10)

        self.canvas = FigureCanvasTkAgg(fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.fig = fig

    # ══════════════════════════════════════
    #  РЕЖИМЫ
    # ══════════════════════════════════════
    def _set_live(self):
        state['mode'] = 'LIVE'
        state['cur_state'] = 'LANDED'
        self._clear()
        print("[MODE] Переключено в LIVE")

    def _set_replay(self):
        filepath = filedialog.askopenfilename(
            title="Выбери CSV файл",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filepath:
            state['mode'] = 'REPLAY'
            self._clear()  # очищаем перед загрузкой
            threading.Thread(
                target=load_csv, args=(filepath,), daemon=True
            ).start()
            print(f"[MODE] Переключено в REPLAY: {filepath}")
        else:
            self.mode_var.set('LIVE')
            state['mode'] = 'LIVE'

    # ══════════════════════════════════════
    #  ОБНОВЛЕНИЕ UI
    # ══════════════════════════════════════

    def _update(self):
        try:
            with lock:
                s = dict(state)
                mode = state['mode']
                r_start = state.get('replay_start', '--')
                r_end = state.get('replay_end', '--')
                r_total = state.get('replay_total', 0.0)

            if mode == 'REPLAY':
                m, sec = divmod(int(r_total), 60)
                self.replay_info.set(
                    f"От:    {r_start}\n"
                    f"До:    {r_end}\n"
                    f"Итого: {m:02d}:{sec:02d}"
                )
            else:
                self.replay_info.set('—')

            # Обновляем метки
            for key, (var, unit) in self.v.items():
                val = s.get(key, 0)
                if isinstance(val, float):
                    var.set(f"{val:.2f} {unit}")
                else:
                    var.set(f"{val} {unit}")

            cur_state = s.get('cur_state', 'LANDED')
            status_color = STATE_COLORS.get(cur_state, GREEN)
            self._label_widgets['cur_state'].config(fg=status_color)

            # Копируем данные для графиков
            with lock:
                xs      = list(state['xs'])
                ys      = list(state['ys'])
                zs      = list(state['zs'])
                rolls   = list(state['rolls'])
                pitches = list(state['pitches'])

            n = len(xs)

            # ── 3D траектория ──
            self.ax3d.cla()
            self.ax3d.set_facecolor(BG)
            self.ax3d.set_title('3D Траектория', color=FG, fontsize=9)
            self.ax3d.tick_params(colors=FG_DIM, labelsize=7)
            if n > 1:
                with lock:
                    states = list(state['states'])

                # Рисуем отрезками по состояниям
                i = 0
                while i < n - 1:
                    current_state = states[i] if i < len(states) else 'FLYING'
                    color = STATE_COLORS.get(current_state, BLUE)

                    # Находим конец отрезка с одинаковым состоянием
                    j = i + 1
                    while j < n and states[j] == current_state:
                        j += 1

                    # Рисуем отрезок
                    self.ax3d.plot(
                        xs[i:j + 1], ys[i:j + 1], zs[i:j + 1],
                        color=color, linewidth=1.5
                    )
                    i = j

                # Точка старта и текущая позиция
                self.ax3d.scatter(xs[-1], ys[-1], zs[-1],
                                  color=RED, s=60, zorder=5)
                self.ax3d.scatter(xs[0], ys[0], zs[0],
                                  color=GREEN, s=60, marker='^', zorder=5)

            # ── Высота ──
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

            # ── Roll / Pitch ──
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

    def _clear(self):
        with lock:
            state['xs'].clear()
            state['ys'].clear()
            state['zs'].clear()
            state['rolls'].clear()
            state['pitches'].clear()
            state['times'].clear()
            state['packets'] = 0
            state['states'].clear()
            state['flight_start'] = None

    def _quit(self):
        state['running'] = False
        self.root.quit()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.protocol('WM_DELETE_WINDOW', app._quit)
    root.mainloop()