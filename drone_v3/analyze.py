import csv
import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from collections import defaultdict

# ══════════════════════════════════════
#  ЦВЕТА СОСТОЯНИЙ
# ══════════════════════════════════════
STATE_COLORS = {
    'LANDED':    '#8b949e',
    'TAKEOFF':   '#39d353',
    'HOVER':     '#58a6ff',
    'FLYING':    '#f0883e',
    'LANDING':   '#e3b341',
    'EMERGENCY': '#f85149',
}

BG   = '#0d1117'
BG2  = '#161b22'
FG   = '#f0f6fc'
GRID = '#21262d'

# ══════════════════════════════════════
#  ЗАГРУЗКА
# ══════════════════════════════════════
def load_flight(path):
    rows = []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            rows.append({
                'time':    float(row['time']),
                'x':       float(row['x']),
                'y':       float(row['y']),
                'z':       float(row['z']),
                'roll':    float(row['roll']),
                'pitch':   float(row['pitch']),
                'thrust':  float(row['thrust']),
                'voltage': float(row['voltage']),
                'state':   row['state'].strip(),
            })
    return rows

def load_debug(path):
    rows = []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            rows.append({
                'time':     float(row['time']),
                'sim_t':    float(row['sim_t']),
                'target_x': float(row['target_x']),
                'target_y': float(row['target_y']),
                'target_z': float(row['target_z']),
                'err_x':    float(row['err_x']),
                'err_y':    float(row['err_y']),
                'err_z':    float(row['err_z']),
                'wind_x':   float(row['wind_x']),
                'wind_y':   float(row['wind_y']),
                'Kp':       float(row['Kp']),
                'Ki':       float(row['Ki']),
                'Kd':       float(row['Kd']),
            })
    return rows

# ══════════════════════════════════════
#  МЕТРИКИ
# ══════════════════════════════════════
def rmse(values):
    if not values:
        return 0.0
    return math.sqrt(sum(v**2 for v in values) / len(values))

# ══════════════════════════════════════
#  ГРАФИКИ
# ══════════════════════════════════════
def plot_all(flight, debug):
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(16, 12), facecolor=BG)
    fig.suptitle('Анализ полёта', color=FG, fontsize=14, fontweight='bold')

    # ── График 1 — 3D реальная vs плановая ──
    ax3d = fig.add_subplot(221, projection='3d')
    ax3d.set_facecolor(BG2)
    ax3d.set_title('Реальная vs Плановая траектория', color=FG, fontsize=9)
    ax3d.tick_params(colors='#8b949e', labelsize=7)

    # Реальная траектория — по состояниям
    xs     = [r['x']     for r in flight]
    ys     = [r['y']     for r in flight]
    zs     = [r['z']     for r in flight]
    states = [r['state'] for r in flight]
    n      = len(xs)

    i = 0
    while i < n - 1:
        cs    = states[i]
        color = STATE_COLORS.get(cs, '#58a6ff')
        j     = i + 1
        while j < n and states[j] == cs:
            j += 1
        ax3d.plot(xs[i:j+1], ys[i:j+1], zs[i:j+1],
                  color=color, linewidth=1.5)
        i = j

    # Плановая траектория — только ключевые точки где цель менялась
    waypoints = []
    prev_tx = prev_ty = prev_tz = None

    for r in debug:
        tx, ty, tz = r['target_x'], r['target_y'], r['target_z']
        if tx != prev_tx or ty != prev_ty or tz != prev_tz:
            drone_x = tx - r['err_x'] if prev_tx is not None else 0.0
            drone_y = ty - r['err_y'] if prev_ty is not None else 0.0
            drone_z = tz - r['err_z'] if prev_tz is not None else 0.0
            waypoints.append({
                'drone_x': drone_x,
                'drone_y': drone_y,
                'drone_z': drone_z,
                'target_x': tx,
                'target_y': ty,
                'target_z': tz,
            })
            prev_tx, prev_ty, prev_tz = tx, ty, tz

    if len(waypoints) > 1:
        # Фильтр орбиты
        filtered = [waypoints[0]]
        for p in waypoints[1:]:
            prev = filtered[-1]
            dist = math.sqrt(
                (p['target_x'] - prev['target_x']) ** 2 +
                (p['target_y'] - prev['target_y']) ** 2 +
                (p['target_z'] - prev['target_z']) ** 2
            )
            if dist > 2.0:
                filtered.append(p)
        waypoints = filtered

        # Строим непрерывную цепочку
        # старт → точка смены 1 → точка смены 2 → ... → финальная цель
        chain_x = [0.0]  # старт
        chain_y = [0.0]
        chain_z = [waypoints[0]['target_z']]  # высота взлёта

        for p in waypoints[1:]:
            # Точка где был дрон при смене цели
            chain_x.append(p['drone_x'])
            chain_y.append(p['drone_y'])
            chain_z.append(p['drone_z'])

        # Финальная цель
        last = waypoints[-1]
        chain_x.append(last['target_x'])
        chain_y.append(last['target_y'])
        chain_z.append(last['target_z'])

        ax3d.plot(chain_x, chain_y, chain_z,
                  color='#ffffff', linewidth=1.0,
                  linestyle='--', alpha=0.4, label='план')



        last = waypoints[-1]
        ax3d.scatter([last['target_x']], [last['target_y']], [last['target_z']],
                     color='#ffffff', s=20, alpha=0.7, zorder=5)

        ax3d.plot([], [], color='#ffffff', linestyle='--', alpha=0.4, label='план')



    ax3d.scatter(xs[0],  ys[0],  zs[0],  color='#39d353', s=50, marker='^')
    ax3d.scatter(xs[-1], ys[-1], zs[-1], color='#f85149', s=50)

    handles = [mpatches.Patch(color=c, label=s)
               for s, c in STATE_COLORS.items()
               if s in set(states)]
    handles.append(mpatches.Patch(color='#ffffff', alpha=0.4, label='план'))
    ax3d.legend(handles=handles, fontsize=6,
                facecolor=BG2, edgecolor=GRID, labelcolor=FG)

    # ── График 2 — Батарея ──
    ax_bat = fig.add_subplot(222)
    ax_bat.set_facecolor(BG2)
    ax_bat.set_title('Батарея', color='#f85149', fontsize=9)
    ax_bat.tick_params(colors='#8b949e', labelsize=7)
    for spine in ax_bat.spines.values():
        spine.set_edgecolor(GRID)

    times_f  = [r['time'] - flight[0]['time'] for r in flight]
    voltages = [r['voltage'] for r in flight]

    ax_bat.plot(times_f, voltages, color='#f85149', linewidth=1.5)
    ax_bat.fill_between(times_f, voltages, min(voltages),
                        alpha=0.15, color='#f85149')
    ax_bat.axhline(y=6.6, color='#e3b341', linewidth=1.0,
                   linestyle='--', alpha=0.7, label='мин 6.6В')
    ax_bat.set_xlabel('время (сек)', color='#8b949e', fontsize=8)
    ax_bat.set_ylabel('В', color='#8b949e', fontsize=8)
    ax_bat.legend(fontsize=7, facecolor=BG2, edgecolor=GRID, labelcolor=FG)
    ax_bat.grid(color=GRID, linewidth=0.5)

    ax_bat.annotate(f"{voltages[0]:.2f}В",
                    xy=(times_f[0], voltages[0]),
                    color='#39d353', fontsize=7,
                    xytext=(5, 5), textcoords='offset points')
    ax_bat.annotate(f"{voltages[-1]:.2f}В",
                    xy=(times_f[-1], voltages[-1]),
                    color='#f85149', fontsize=7,
                    xytext=(-30, 5), textcoords='offset points')

    # ── График 3 — Состояния (временная шкала) ──
    ax_states = fig.add_subplot(212)
    ax_states.set_facecolor(BG2)
    ax_states.set_title('Состояния по времени', color=FG, fontsize=9)
    ax_states.tick_params(colors='#8b949e', labelsize=7)
    for spine in ax_states.spines.values():
        spine.set_edgecolor(GRID)

    state_list = list(STATE_COLORS.keys())
    y_map      = {s: i for i, s in enumerate(state_list)}

    i = 0
    while i < n - 1:
        cs    = states[i]
        color = STATE_COLORS.get(cs, '#58a6ff')
        j     = i + 1
        while j < n and states[j] == cs:
            j += 1
        t0 = times_f[i]
        t1 = times_f[min(j, n-1)]
        y  = y_map.get(cs, 0)
        ax_states.barh(y, t1 - t0, left=t0, height=0.6,
                       color=color, alpha=0.85)
        i = j

    ax_states.set_yticks(list(y_map.values()))
    ax_states.set_yticklabels(list(y_map.keys()),
                              color='#8b949e', fontsize=8)
    ax_states.set_xlabel('время (сек)', color='#8b949e', fontsize=8)
    ax_states.grid(axis='x', color=GRID, linewidth=0.5)

    plt.tight_layout()
    plt.savefig('flight_analysis.png', dpi=150,
                bbox_inches='tight', facecolor=BG)
    print("\n  График сохранён: flight_analysis.png")
    plt.show()

# ══════════════════════════════════════
#  АНАЛИЗ
# ══════════════════════════════════════
def analyze(flight_path='flight_log.csv', debug_path='flight_debug.csv'):
    print("Загружаю данные...")
    flight = load_flight(flight_path)
    debug  = load_debug(debug_path)

    if not flight or not debug:
        print("Ошибка: файлы пустые!")
        return

    n_f = len(flight)
    n_d = len(debug)
    print(f"  flight_log:   {n_f} пакетов")
    print(f"  flight_debug: {n_d} пакетов")

    duration = flight[-1]['time'] - flight[0]['time']
    m, sec   = divmod(int(duration), 60)

    print(f"\n{'='*50}")
    print(f"  ВРЕМЯ ПОЛЁТА: {m:02d}:{sec:02d}  ({duration:.1f} сек)")
    print(f"{'='*50}")

    # RMSE
    # Было
    err_x = [r['err_x'] for r in debug]
    err_y = [r['err_y'] for r in debug]
    err_z = [r['err_z'] for r in debug]
    err_3d = [math.sqrt(r['err_x'] ** 2 + r['err_y'] ** 2 + r['err_z'] ** 2)
              for r in debug]

    print(f"\n  RMSE ОТКЛОНЕНИЯ ОТ ПЛАНОВОЙ ТРАЕКТОРИИ:")
    print(f"  {'X':>8}  {'Y':>8}  {'Z':>8}  {'3D':>8}")
    print(f"  {rmse(err_x):>8.3f}  {rmse(err_y):>8.3f}  "
          f"{rmse(err_z):>8.3f}  {rmse(err_3d):>8.3f}  м")

    print(f"\n  МАКСИМАЛЬНЫЕ ОТКЛОНЕНИЯ:")
    print(f"  X:  {max(abs(e) for e in err_x):.3f} м")
    print(f"  Y:  {max(abs(e) for e in err_y):.3f} м")
    print(f"  Z:  {max(abs(e) for e in err_z):.3f} м")
    print(f"  3D: {max(err_3d):.3f} м")

    # Стало
    segments = []
    current_segment = []
    prev_tx = prev_ty = prev_tz = None

    for r in debug:
        tx, ty, tz = r['target_x'], r['target_y'], r['target_z']
        if tx != prev_tx or ty != prev_ty or tz != prev_tz:
            if current_segment:
                segments.append(current_segment)
            current_segment = []
            prev_tx, prev_ty, prev_tz = tx, ty, tz
        current_segment.append(r)
    if current_segment:
        segments.append(current_segment)

    stable_err_x = []
    stable_err_y = []
    stable_err_z = []
    all_err_x = []
    all_err_y = []
    all_err_z = []

    for seg in segments:
        n = len(seg)
        stable = seg[int(n * 0.5):]
        stable_err_x.extend([r['err_x'] for r in stable])
        stable_err_y.extend([r['err_y'] for r in stable])
        stable_err_z.extend([r['err_z'] for r in stable])
        all_err_x.extend([r['err_x'] for r in seg])
        all_err_y.extend([r['err_y'] for r in seg])
        all_err_z.extend([r['err_z'] for r in seg])

    err_3d_stable = [math.sqrt(ex ** 2 + ey ** 2 + ez ** 2)
                     for ex, ey, ez in zip(stable_err_x, stable_err_y, stable_err_z)]
    err_3d_all = [math.sqrt(ex ** 2 + ey ** 2 + ez ** 2)
                  for ex, ey, ez in zip(all_err_x, all_err_y, all_err_z)]

    print(f"\n  RMSE (стабильная часть — дрон у цели):")
    print(f"  {'X':>8}  {'Y':>8}  {'Z':>8}  {'3D':>8}")
    print(f"  {rmse(stable_err_x):>8.3f}  {rmse(stable_err_y):>8.3f}  "
          f"{rmse(stable_err_z):>8.3f}  {rmse(err_3d_stable):>8.3f}  м")

    print(f"\n  RMSE (весь полёт включая переходы):")
    print(f"  {'X':>8}  {'Y':>8}  {'Z':>8}  {'3D':>8}")
    print(f"  {rmse(all_err_x):>8.3f}  {rmse(all_err_y):>8.3f}  "
          f"{rmse(all_err_z):>8.3f}  {rmse(err_3d_all):>8.3f}  м")

    print(f"\n  МАКСИМАЛЬНЫЕ ОТКЛОНЕНИЯ (стабильная часть):")
    print(f"  X:  {max(abs(e) for e in stable_err_x):.3f} м")
    print(f"  Y:  {max(abs(e) for e in stable_err_y):.3f} м")
    print(f"  Z:  {max(abs(e) for e in stable_err_z):.3f} м")
    print(f"  3D: {max(err_3d_stable):.3f} м")

    # Влияние ветра
    with_wind    = [r for r in debug
                    if abs(r['wind_x']) > 0.01 or abs(r['wind_y']) > 0.01]
    without_wind = [r for r in debug
                    if abs(r['wind_x']) <= 0.01 and abs(r['wind_y']) <= 0.01]

    if with_wind and without_wind:
        ew  = [math.sqrt(r['err_x']**2 + r['err_y']**2) for r in with_wind]
        enw = [math.sqrt(r['err_x']**2 + r['err_y']**2) for r in without_wind]
        print(f"\n  ВЛИЯНИЕ ВЕТРА (XY):")
        print(f"  С ветром:    RMSE = {rmse(ew):.3f} м  ({len(with_wind)} пакетов)")
        print(f"  Без ветра:   RMSE = {rmse(enw):.3f} м  ({len(without_wind)} пакетов)")
        if rmse(enw) > 0:
            print(f"  Ветер ухудшает точность в {rmse(ew)/rmse(enw):.1f}x")

    # Состояния
    state_counts = defaultdict(int)
    for r in flight:
        state_counts[r['state']] += 1

    print(f"\n  ВРЕМЯ В КАЖДОМ СОСТОЯНИИ:")
    dt = duration / n_f
    for s, count in sorted(state_counts.items()):
        secs   = count * dt
        pct    = count / n_f * 100
        m2, s2 = divmod(int(secs), 60)
        print(f"  {s:<12} {m2:02d}:{s2:02d}  ({pct:.1f}%)")

    # Батарея
    v_start = flight[0]['voltage']
    v_end   = flight[-1]['voltage']
    drain   = v_start - v_end
    drain_per_min    = drain / (duration / 60) if duration > 0 else 0
    remaining_min    = (v_end - 6.6) / drain_per_min if drain_per_min > 0 else 0

    print(f"\n  БАТАРЕЯ:")
    print(f"  Начало:         {v_start:.2f} В")
    print(f"  Конец:          {v_end:.2f} В")
    print(f"  Расход:         {drain:.2f} В")
    print(f"  Расход/мин:     {drain_per_min:.3f} В/мин")
    print(f"  Остаток полёта: ~{remaining_min:.1f} мин")

    kp = debug[-1]['Kp']
    ki = debug[-1]['Ki']
    kd = debug[-1]['Kd']
    print(f"\n  ПИД: Kp={kp}  Ki={ki}  Kd={kd}")
    print(f"\n{'='*50}")
    print("  АНАЛИЗ ЗАВЕРШЁН")
    print(f"{'='*50}\n")

    plot_all(flight, debug)

# ══════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════
if __name__ == '__main__':
    import sys
    flight_path = sys.argv[1] if len(sys.argv) > 2 else 'flight_log.csv'
    debug_path  = sys.argv[2] if len(sys.argv) > 2 else 'flight_debug.csv'
    analyze(flight_path, debug_path)