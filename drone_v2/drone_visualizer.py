import math, time, socket, threading, csv
import tkinter as tk
from tkinter import filedialog
import matplotlib
import matplotlib.patches
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import math

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

UDP_PORT = 14551
TAIL     = 300

STATE_COLORS = {
    'LANDED':    '#8b949e',
    'TAKEOFF':   '#39d353',
    'HOVER':     '#58a6ff',
    'FLYING':    '#58a6ff',
    'LANDING':   '#e3b341',
    'EMERGENCY': '#f85149',
}

lock  = threading.Lock()
state = {
    'xs': [], 'ys': [], 'zs': [],
    'rolls': [], 'pitches': [],
    'times': [], 'states': [],
    'cur_x': 0.0, 'cur_y': 0.0, 'cur_z': 0.0,
    'cur_roll': 0.0, 'cur_pitch': 0.0,
    'cur_thrust': 0.0, 'cur_voltage': 0.0,
    'cur_state': 'LANDED',
    'cur_yaw': 0.0,
    'packets': 0,
    'running': True,
    'mode': 'LIVE',
    'flight_start': None,
    'replay_start': '--',
    'replay_end':   '--',
    'replay_total': 0.0,
}

# ══════════════════════════════════════
#  UDP ПОТОК
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
        try:
            data, _ = sock.recvfrom(1024)
            parts   = data.decode().strip().split(',')
            t, x, y, z, roll, pitch, thrust, voltage, yaw = map(float, parts[:9])
            drone_state = parts[9]

            with lock:
                if state['flight_start'] is None and drone_state != 'LANDED':
                    state['flight_start'] = time.time()
                if drone_state == 'LANDED':
                    state['flight_start'] = None

                state['xs'].append(x)
                state['ys'].append(y)
                state['zs'].append(z)
                state['rolls'].append(roll)
                state['pitches'].append(pitch)
                state['states'].append(drone_state)
                state['times'].append(time.time())
                state['cur_yaw'] = yaw
                state['packets'] += 1
                state.update({
                    'cur_x': x, 'cur_y': y, 'cur_z': z,
                    'cur_roll': math.degrees(roll), 'cur_pitch': math.degrees(pitch),
                    'cur_thrust': thrust, 'cur_voltage': voltage,
                    'cur_state': drone_state,
                })

        except socket.timeout:
            pass
        except Exception as e:
            print(f"[LIVE] Ошибка: {e}")
    sock.close()

# ══════════════════════════════════════
#  ЗАГРУЗКА CSV
# ══════════════════════════════════════
def load_csv(filepath):
    with lock:
        for key in ('xs','ys','zs','rolls','pitches','times','states'):
            state[key].clear()
        state['packets'] = 0

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            with lock:
                state['xs'].append(float(row['x']))
                state['ys'].append(float(row['y']))
                state['zs'].append(float(row['z']))
                state['rolls'].append(float(row['roll']))
                state['pitches'].append(float(row['pitch']))
                state['times'].append(float(row['time']))
                state['states'].append(row.get('state', 'FLYING'))
                state['packets'] += 1

    with lock:
        if state['xs']:
            from datetime import datetime
            t_start = state['times'][0]
            t_end   = state['times'][-1]
            total   = t_end - t_start
            state['replay_start'] = datetime.fromtimestamp(t_start).strftime('%H:%M:%S')
            state['replay_end']   = datetime.fromtimestamp(t_end).strftime('%H:%M:%S')
            state['replay_total'] = total
            state.update({
                'cur_x':     state['xs'][-1],
                'cur_y':     state['ys'][-1],
                'cur_z':     state['zs'][-1],
                'cur_roll':  state['rolls'][-1],
                'cur_pitch': state['pitches'][-1],
                'cur_state': 'REPLAY',
            })

    print(f"[REPLAY] Загружено {state['packets']} точек из {filepath}")

# ══════════════════════════════════════
#  ГЛАВНЫЙ КЛАСС
# ══════════════════════════════════════
class App:
    def __init__(self, root):
        self.root = root
        root.title("Drone Monitor")
        root.configure(bg=BG)
        root.geometry('1400x750')
        self.ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._build_ui()
        threading.Thread(target=udp_listener, daemon=True).start()
        self._update()

    def _build_ui(self):
        # ══════════════════════════════
        #  ЛЕВАЯ ПАНЕЛЬ
        # ══════════════════════════════
        left = tk.Frame(self.root, bg=BG2, width=240)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left.pack_propagate(False)

        tk.Label(left, text="ТЕЛЕМЕТРИЯ", bg=BG2,
                 fg=BLUE, font=('Courier', 12, 'bold')).pack(pady=10)

        # Метки телеметрии
        self.v = {}
        self._label_widgets = {}
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

        for label, key, unit in fields:
            row = tk.Frame(left, bg=BG2)
            row.pack(fill=tk.X, padx=10, pady=2)
            tk.Label(row, text=label, bg=BG2, fg=FG_DIM,
                     font=('Courier', 9), width=8, anchor='w').pack(side=tk.LEFT)
            var   = tk.StringVar(value='--')
            self.v[key] = (var, unit)
            color = RED if key == 'cur_voltage' else GREEN
            lbl   = tk.Label(row, textvariable=var, bg=BG2, fg=color,
                             font=('Courier', 10, 'bold'))
            lbl.pack(side=tk.LEFT)
            self._label_widgets[key] = lbl

        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, pady=8)

        # ── Кнопки управления ──
        btn_frame = tk.Frame(left, bg=BG2)
        btn_frame.pack(fill=tk.X, padx=5)

        tk.Button(btn_frame, text='🗑 ОЧИСТИТЬ', bg='#21262d', fg=FG,
                  font=('Courier', 9), relief='flat',
                  command=self._clear).pack(side=tk.LEFT, fill=tk.X,
                                           expand=True, padx=2)
        tk.Button(btn_frame, text='✕ ВЫХОД', bg='#b91c1c', fg=FG,
                  font=('Courier', 9), relief='flat',
                  command=self._quit).pack(side=tk.LEFT, fill=tk.X,
                                          expand=True, padx=2)

        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, pady=8)

        # ── Вкладки ──
        tabs_frame = tk.Frame(left, bg=BG2)
        tabs_frame.pack(fill=tk.X, padx=5)

        self._tab_frames = {}
        self._tab_btns   = {}

        for tab_name, tab_key in [('ИНФО', 'info'),
                                   ('ЛЕГЕНДА', 'legend'),
                                   ('СТАТ', 'stats')]:
            btn = tk.Button(
                tabs_frame, text=tab_name, bg='#21262d', fg=FG_DIM,
                font=('Courier', 8), relief='flat',
                command=lambda k=tab_key: self._switch_tab(k))
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
            self._tab_btns[tab_key] = btn

        # ── Вкладка ИНФО ──
        info_frame = tk.Frame(left, bg=BG2)
        self._tab_frames['info'] = info_frame

        tk.Label(info_frame, text="ВРЕМЯ ПОЛЁТА", bg=BG2,
                 fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=3)
        self.flight_time_var = tk.StringVar(value='00:00')
        tk.Label(info_frame, textvariable=self.flight_time_var, bg=BG2,
                 fg=YELLOW, font=('Courier', 18, 'bold')).pack(pady=3)

        tk.Frame(info_frame, bg=BORDER, height=1).pack(fill=tk.X, pady=5)

        # Режим данных (LIVE/REPLAY)
        tk.Label(info_frame, text="ИСТОЧНИК", bg=BG2,
                 fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=3)

        self.mode_var = tk.StringVar(value='LIVE')
        src_frame = tk.Frame(info_frame, bg=BG2)
        src_frame.pack(fill=tk.X, padx=10, pady=3)

        tk.Radiobutton(src_frame, text='LIVE', variable=self.mode_var,
                       value='LIVE', bg=BG2, fg=GREEN, selectcolor=BG,
                       font=('Courier', 9),
                       command=self._set_live).pack(side=tk.LEFT)
        tk.Radiobutton(src_frame, text='REPLAY', variable=self.mode_var,
                       value='REPLAY', bg=BG2, fg=ORANGE, selectcolor=BG,
                       font=('Courier', 9),
                       command=self._set_replay).pack(side=tk.LEFT)

        tk.Frame(info_frame, bg=BORDER, height=1).pack(fill=tk.X, pady=5)

        # Режим полёта (MANUAL/AUTO)
        tk.Label(info_frame, text="РЕЖИМ ПОЛЁТА", bg=BG2,
                 fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=3)

        self.flight_mode = tk.StringVar(value='MANUAL')
        flight_frame = tk.Frame(info_frame, bg=BG2)
        flight_frame.pack(fill=tk.X, padx=10, pady=3)

        tk.Radiobutton(flight_frame, text='MANUAL', variable=self.flight_mode,
                       value='MANUAL', bg=BG2, fg=GREEN, selectcolor=BG,
                       font=('Courier', 9),
                       command=self._switch_flight_mode).pack(side=tk.LEFT)
        tk.Radiobutton(flight_frame, text='AUTO', variable=self.flight_mode,
                       value='AUTO', bg=BG2, fg=ORANGE, selectcolor=BG,
                       font=('Courier', 9),
                       command=self._switch_flight_mode).pack(side=tk.LEFT)

        # ── Вкладка ЛЕГЕНДА ──
        legend_frame = tk.Frame(left, bg=BG2)
        self._tab_frames['legend'] = legend_frame

        tk.Label(legend_frame, text="СОСТОЯНИЯ", bg=BG2,
                 fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=5)

        for s_name, s_color in STATE_COLORS.items():
            row = tk.Frame(legend_frame, bg=BG2)
            row.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(row, text='■', bg=BG2, fg=s_color,
                     font=('Courier', 12)).pack(side=tk.LEFT)
            tk.Label(row, text=s_name, bg=BG2, fg=FG,
                     font=('Courier', 9)).pack(side=tk.LEFT, padx=8)

        # ── Вкладка СТАТИСТИКА ──
        stats_frame = tk.Frame(left, bg=BG2)
        self._tab_frames['stats'] = stats_frame

        tk.Label(stats_frame, text="СТАТИСТИКА", bg=BG2,
                 fg=FG_DIM, font=('Courier', 9, 'bold')).pack(pady=5)

        self.replay_info = tk.StringVar(value='—')
        tk.Label(stats_frame, textvariable=self.replay_info,
                 bg=BG2, fg=ORANGE,
                 font=('Courier', 9), justify=tk.LEFT).pack(padx=10, pady=5)

        # Показываем вкладку ИНФО по умолчанию
        self._switch_tab('info')

        # ══════════════════════════════
        #  ПРАВАЯ ЧАСТЬ — ГРАФИКИ
        # ══════════════════════════════
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

        self.canvas = FigureCanvasTkAgg(fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.fig = fig

    # ══════════════════════════════════════
    #  ВКЛАДКИ
    # ══════════════════════════════════════
    def _switch_tab(self, tab_key):
        for key, frame in self._tab_frames.items():
            frame.pack_forget()
            self._tab_btns[key].config(fg=FG_DIM, bg='#21262d')

        self._tab_frames[tab_key].pack(fill=tk.BOTH, expand=True, padx=5)
        self._tab_btns[tab_key].config(fg=FG, bg='#30363d')

    # ══════════════════════════════════════
    #  РЕЖИМЫ
    # ══════════════════════════════════════
    def _set_live(self):
        state['mode']      = 'LIVE'
        state['cur_state'] = 'LANDED'
        self._clear()
        print("[MODE] LIVE")

    def _set_replay(self):
        filepath = filedialog.askopenfilename(
            title="Выбери CSV файл",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if filepath:
            state['mode'] = 'REPLAY'
            self._clear()
            threading.Thread(target=load_csv, args=(filepath,),
                             daemon=True).start()
        else:
            self.mode_var.set('LIVE')
            state['mode'] = 'LIVE'

    def _switch_flight_mode(self):
        mode = self.flight_mode.get()
        msg  = f"MODE,{mode}"
        self.ctrl_sock.sendto(msg.encode(), ('127.0.0.1', 14553))
        print(f"[FLIGHT MODE] {mode}")

    # ══════════════════════════════════════
    #  ОБНОВЛЕНИЕ UI
    # ══════════════════════════════════════
    def _update(self):
        try:
            with lock:
                s       = dict(state)
                mode    = state['mode']
                r_start = state['replay_start']
                r_end   = state['replay_end']
                r_total = state['replay_total']
                start   = state['flight_start']

            # Метки телеметрии
            for key, (var, unit) in self.v.items():
                val = s.get(key, 0)
                if isinstance(val, float):
                    var.set(f"{val:.2f} {unit}")
                else:
                    var.set(f"{val} {unit}")

            # Цвет статуса
            cur_state    = s.get('cur_state', 'LANDED')
            status_color = STATE_COLORS.get(cur_state, GREEN)
            self._label_widgets['cur_state'].config(fg=status_color)

            # Время полёта
            if start:
                elapsed = int(time.time() - start)
                m, sec  = divmod(elapsed, 60)
                self.flight_time_var.set(f"{m:02d}:{sec:02d}")
            else:
                self.flight_time_var.set("00:00")

            # Статистика REPLAY
            if mode == 'REPLAY':
                m, sec = divmod(int(r_total), 60)
                self.replay_info.set(
                    f"От:    {r_start}\n"
                    f"До:    {r_end}\n"
                    f"Итого: {m:02d}:{sec:02d}")
            else:
                self.replay_info.set('—')

            # Данные для графиков
            with lock:
                xs      = list(state['xs'])
                ys      = list(state['ys'])
                zs      = list(state['zs'])
                rolls   = list(state['rolls'])
                pitches = list(state['pitches'])
                states  = list(state['states'])

            n = len(xs)
            #Ориентация дрона
            # Удаляем старый индикатор если есть
            if hasattr(self, 'ax_hud'):
                self.ax_hud.remove()

            # Добавляем оси в левый нижний угол фигуры
            # [left, bottom, width, height] — в долях от размера фигуры
            self.ax_hud = self.fig.add_axes([0.01, 0.01, 0.13, 0.22],
                                            facecolor='#0d1117')
            self._draw_drone_indicator_ax(
                s.get('cur_roll', 0.0),
                s.get('cur_pitch', 0.0),
                s.get('cur_yaw', 0.0)  # добавь cur_yaw в state
            )

            # 3D траектория
            self.ax3d.cla()
            self.ax3d.set_facecolor(BG)
            self.ax3d.set_title('3D Траектория', color=FG, fontsize=9)
            self.ax3d.tick_params(colors=FG_DIM, labelsize=7)
            if n > 1:
                self.ax3d.set_zlim(0, max(zs) + 1 if max(zs) > 0 else 5)
                i = 0
                while i < n - 1:
                    cs    = states[i] if i < len(states) else 'FLYING'
                    color = STATE_COLORS.get(cs, BLUE)
                    j     = i + 1
                    while j < n and states[j] == cs:
                        j += 1
                    self.ax3d.plot(xs[i:j+1], ys[i:j+1], zs[i:j+1],
                                   color=color, linewidth=1.5)
                    i = j
                self.ax3d.scatter(xs[-1], ys[-1], zs[-1],
                                  color=RED, s=60, zorder=5)
                self.ax3d.scatter(xs[0], ys[0], zs[0],
                                  color=GREEN, s=60, marker='^', zorder=5)

            # Высота
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

            # Roll / Pitch
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

    def _draw_drone_indicator_ax(self, roll, pitch, yaw):
        ax = self.ax_hud
        ax.cla()
        ax.set_xlim(-1, 1)
        ax.set_ylim(-1, 1)
        ax.set_aspect('equal')
        ax.axis('off')
        ax.set_facecolor(BG)

        # Длина луча к мотору
        arm = 0.55

        # Углы моторов с учётом yaw
        for i, base_angle in enumerate([135, 45, 225, 315]):
            angle = math.radians(base_angle + math.degrees(yaw))

            # Смещение по roll/pitch — наклон дрона
            dx = math.sin(roll) * 0.2
            dy = math.sin(pitch) * 0.2

            # Конец луча
            ex = dx + arm * math.cos(angle)
            ey = dy + arm * math.sin(angle)

            # Луч
            ax.plot([dx, ex], [dy, ey],
                    color='#30363d', lw=2.5, solid_capstyle='round')

            # Пропеллер — эллипс имитирует наклон
            scale_x = 1.0 - abs(math.sin(roll)) * 0.4
            scale_y = 1.0 - abs(math.sin(pitch)) * 0.4
            ellipse = matplotlib.patches.Ellipse(
                (ex, ey),
                width=0.22 * scale_x,
                height=0.22 * scale_y,
                color='#21262d',
                ec='#58a6ff', lw=1.0
            )
            ax.add_patch(ellipse)

            # Мотор
            dot = matplotlib.patches.Circle((ex, ey), 0.035, color='#58a6ff')
            ax.add_patch(dot)

        # Тело дрона
        bx = math.sin(roll) * 0.2
        by = math.sin(pitch) * 0.2
        body = matplotlib.patches.Circle(
            (bx, by), 0.10,
            color='#161b22', ec='#30363d', lw=1.2
        )
        ax.add_patch(body)

        # Стрелка вперёд — поворачивается с yaw
        arrow_angle = math.pi / 2 + yaw
        ax.annotate('',
                    xy=(bx + 0.22 * math.cos(arrow_angle),
                        by + 0.22 * math.sin(arrow_angle)),
                    xytext=(bx, by),
                    arrowprops=dict(arrowstyle='->', color=GREEN, lw=1.5))

        # Текст углов
        ax.text(0, -0.92,
                f'R{math.degrees(roll):+.0f}° '
                f'P{math.degrees(pitch):+.0f}° '
                f'Y{math.degrees(yaw):+.0f}°',
                color=FG_DIM, fontsize=5.5, ha='center',
                fontfamily='monospace')

    def _clear(self):
        with lock:
            for key in ('xs','ys','zs','rolls','pitches','times','states'):
                state[key].clear()
            state['packets']      = 0
            state['flight_start'] = None

    def _quit(self):
        state['running'] = False
        self.root.quit()
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app  = App(root)
    root.protocol('WM_DELETE_WINDOW', app._quit)
    root.mainloop()