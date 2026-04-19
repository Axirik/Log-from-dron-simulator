import math
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# =============================================
# ПУТЬ К ФАЙЛУ ЛОГА
# =============================================
path = "24.txt"

# =============================================
# ПОРОГИ ДЕТЕКТОРА ВЕТРА
# =============================================
WIND_ACCEL_THRESHOLD = 1.5   # м/с² — резкое горизонтальное ускорение
WIND_TILT_THRESHOLD  = 3.0   # градусов — минимальный крен/тангаж
WIND_CTRL_MAX        = 0.15  # если пилот дал команду больше — не считаем ветром
WIND_EPISODE_MAX     = 8.0   # сек — эпизод дольше этого = манёвр, не ветер
WIND_DYAW_MAX        = 0.4   # градусов/сек — если yaw активно меняется = манёвр

# =============================================
# ЧИТАЕМ ФАЙЛ И РАЗБИРАЕМ СТРОКИ
# =============================================
nav_pos     = []
nav_vel     = []
altitude    = []
power       = []
orientation = []
control     = []
motors      = {"64": [], "65": [], "66": [], "67": []}

with open(path, "r") as f:
    for line in f:
        parts = line.split()

        # пропускаем строки без timestamp
        if len(parts) < 2:
            continue
        try:
            t = float(parts[0])
        except:
            continue

        msg  = parts[1]
        args = parts[2:]

        if msg == "NavPosition" and len(args) >= 3:
            lat = float(args[0])
            lon = float(args[1])
            alt = float(args[2])
            nav_pos.append((t, lat, lon, alt))

        elif msg == "NavVelocity" and len(args) >= 3:
            nav_vel.append((t, float(args[0]), float(args[1]), float(args[2])))

        elif msg == "Altitude" and len(args) >= 1:
            altitude.append((t, float(args[0])))

        elif msg == "ExtPowerStatus" and len(args) >= 2:
            power.append((t, float(args[1])))

        elif msg == "Orientation" and len(args) >= 3:
            orientation.append((t, float(args[0]), float(args[1]), float(args[2])))

        elif msg == "ControlData" and len(args) >= 4:
            control.append((t, float(args[0]), float(args[1]), float(args[2]), float(args[3])))

        elif msg == "Motor" and len(args) >= 5:
            motor_id = args[0]
            if motor_id in motors:
                motors[motor_id].append((t, int(args[3]), int(args[4])))

print(f"GPS точек:    {len(nav_pos)}")
print(f"Высота:       {len(altitude)}")
print(f"Батарея:      {len(power)}")
print(f"Ориентация:   {len(orientation)}")
print(f"Управление:   {len(control)}")
for mid, vals in motors.items():
    print(f"Мотор {mid}:     {len(vals)}")


# =============================================
# ПЕРЕВОДИМ GPS В МЕТРЫ
# =============================================
lat0 = nav_pos[0][1]
lon0 = nav_pos[0][2]
alt0 = nav_pos[0][3]
t0   = nav_pos[0][0]

R = 6371000

gps_x = []
gps_y = []
gps_z = []
gps_t = []

for (t, lat, lon, alt) in nav_pos:
    x = (lon - lon0) * math.cos(math.radians(lat0)) * R * math.pi / 180
    y = (lat - lat0) * R * math.pi / 180
    z = alt - alt0
    gps_x.append(x)
    gps_y.append(y)
    gps_z.append(z)
    gps_t.append(t - t0)


# =============================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ СГЛАЖИВАНИЯ
# =============================================
def smooth(values, window=5):
    result = []
    n = len(values)
    for i in range(n):
        start = max(0, i - window)
        end   = min(n, i + window + 1)
        avg   = sum(values[start:end]) / (end - start)
        result.append(avg)
    return result


# =============================================
# ДЕТЕКТОР ПОРЫВОВ ВЕТРА
# =============================================
def nearest(series, t_query):
    return min(series, key=lambda row: abs(row[0] - t_query))

# ── Шаг 1: находим эпизоды высокой скорости (> 1 м/с) ──
#   Это кандидаты — потом отфильтруем манёвры от порывов
episodes = []
in_ep    = False
ep_start = 0
ep_vels  = []

for v in nav_vel:
    spd = math.sqrt(v[1]**2 + v[2]**2)
    if spd > 1.0 and not in_ep:
        in_ep    = True
        ep_start = v[0]
        ep_vels  = [v]
    elif spd > 1.0 and in_ep:
        ep_vels.append(v)
    elif spd <= 1.0 and in_ep:
        in_ep = False
        episodes.append((ep_start, v[0], ep_vels))

# ── Шаг 2: для каждого эпизода проверяем три условия ──
wind_events = []

for (t_start, t_end, ep_vels) in episodes:
    dur = t_end - t_start

    # УСЛОВИЕ 1: длительность < 8 сек
    # долгий эпизод = плановый манёвр (петля, разворот)
    if dur > WIND_EPISODE_MAX:
        continue

    # УСЛОВИЕ 2: yaw почти не меняется за эпизод
    # при манёвре дрон разворачивается, при ветре — летит боком
    ori_ep    = [o for o in orientation if t_start <= o[0] <= t_end]
    if len(ori_ep) < 2:
        continue
    delta_yaw    = abs(ori_ep[-1][3] - ori_ep[0][3])
    dyaw_per_sec = delta_yaw / dur
    if dyaw_per_sec > WIND_DYAW_MAX:
        continue

    # УСЛОВИЕ 3: крен направлен ПРОТИВ скорости (dot product < 0)
    # при манёвре крен совпадает с направлением движения (dot > 0)
    # при ветре автопилот наклоняет дрон навстречу сносу (dot < 0)
    dots = []
    for v in ep_vels:
        o   = nearest(ori_ep, v[0])
        dot = v[1] * o[2] + v[2] * o[1]   # vx*pitch + vy*roll
        dots.append(dot)
    avg_dot = sum(dots) / len(dots)
    if avg_dot > 5:
        continue

    # УСЛОВИЕ 4: пилот не давал активных команд
    ctl_ep   = [c for c in control if t_start <= c[0] <= t_end]
    ctrl_max = max(math.sqrt(c[1]**2 + c[2]**2) for c in ctl_ep) if ctl_ep else 0
    if ctrl_max > WIND_CTRL_MAX:
        continue

    # Берём момент максимального ускорения внутри эпизода
    peak = max(ep_vels, key=lambda v: math.sqrt(v[1]**2 + v[2]**2))
    vx_peak    = peak[1]
    vy_peak    = peak[2]
    wind_speed = math.sqrt(vx_peak**2 + vy_peak**2)

    gps_pt = nearest(nav_pos, peak[0])
    gx = (gps_pt[2]-lon0)*math.cos(math.radians(lat0))*R*math.pi/180
    gy = (gps_pt[1]-lat0)*R*math.pi/180
    gz = gps_pt[3] - alt0

    wind_events.append({
        "t":          peak[0] - t0,
        "t_start":    t_start - t0,
        "t_end":      t_end   - t0,
        "dur":        dur,
        "wind_speed": wind_speed,
        "vx":         vx_peak,
        "vy":         vy_peak,
        "dyaw":       dyaw_per_sec,
        "dot":        avg_dot,
        "x": gx, "y": gy, "z": gz,
    })

print(f"\nПорывов ветра: {len(wind_events)}")
for ev in wind_events:
    print(f"  t={ev['t']:.1f}s  {ev['wind_speed']:.2f} м/с  "
          f"dur={ev['dur']:.1f}s  dyaw={ev['dyaw']:.3f}°/с  dot={ev['dot']:.2f}")


# =============================================
# ИДЕАЛЬНАЯ ТРАЕКТОРИЯ
# Шаг 1 — сглаживаем GPS (убираем шум ~1 сек)
# Шаг 2 — в окнах порывов ветра заменяем линейной интерполяцией:
#          прямая от точки до порыва к точке после = куда летел бы без ветра
# =============================================
ideal_x = smooth(gps_x)
ideal_y = smooth(gps_y)
ideal_z = smooth(gps_z)

for ev in wind_events:
    i_start = min(range(len(gps_t)), key=lambda i: abs(gps_t[i] - ev["t_start"]))
    i_end   = min(range(len(gps_t)), key=lambda i: abs(gps_t[i] - ev["t_end"]))
    if i_end >= len(gps_t): i_end = len(gps_t) - 1

    x0, x1 = ideal_x[i_start], ideal_x[i_end]
    y0, y1 = ideal_y[i_start], ideal_y[i_end]
    z0, z1 = ideal_z[i_start], ideal_z[i_end]

    for i in range(i_start, i_end + 1):
        alpha      = (i - i_start) / max(i_end - i_start, 1)
        ideal_x[i] = x0 + alpha * (x1 - x0)
        ideal_y[i] = y0 + alpha * (y1 - y0)
        ideal_z[i] = z0 + alpha * (z1 - z0)


# =============================================
# RMSE
# =============================================
def rmse(real, ideal):
    n = len(real)
    return math.sqrt(sum((real[i] - ideal[i])**2 for i in range(n)) / n)

rmse_x  = rmse(gps_x, ideal_x)
rmse_y  = rmse(gps_y, ideal_y)
rmse_z  = rmse(gps_z, ideal_z)
rmse_3d = math.sqrt(
    sum(
        (gps_x[i] - ideal_x[i])**2 +
        (gps_y[i] - ideal_y[i])**2 +
        (gps_z[i] - ideal_z[i])**2
        for i in range(len(gps_x))
    ) / len(gps_x)
)

print(f"\nRMSE X  = {rmse_x:.3f} м")
print(f"RMSE Y  = {rmse_y:.3f} м")
print(f"RMSE Z  = {rmse_z:.3f} м")
print(f"RMSE 3D = {rmse_3d:.3f} м")


# =============================================
# РИСУЕМ ГРАФИКИ
# =============================================
fig = plt.figure(figsize=(20, 12))
fig.patch.set_facecolor("#050810")

# Сетка: левая колонка — большой трек (занимает всю высоту)
#        правая часть  — 2 колонки по 3 графика
gs = gridspec.GridSpec(
    3, 3,
    figure=fig,
    width_ratios=[1.8, 1, 1],  # левая колонка шире
    hspace=0.40,
    wspace=0.30
)

# ── 1. БОЛЬШОЙ 3D ТРЕК ───────────────────────────────────
ax1 = fig.add_subplot(gs[:, 0], projection="3d")   # все 3 строки, колонка 0
ax1.set_facecolor("#0f1628")
ax1.set_title("3D Траектория", color="white", fontsize=12, pad=10)
ax1.plot(gps_x,   gps_y,   gps_z,   color="#00e5ff", linewidth=1.5, label="реальная")
ax1.plot(ideal_x, ideal_y, ideal_z, color="#a855f7", linewidth=1.2, linestyle="--", label="идеальная")
ax1.scatter(gps_x[0],  gps_y[0],  gps_z[0],  color="#10b981", s=60, label="старт")
ax1.scatter(gps_x[-1], gps_y[-1], gps_z[-1], color="#ef4444", s=60, label="финиш")

# порывы ветра — красные маркеры + стрелки
for ev in wind_events:
    ax1.scatter([ev["x"]], [ev["y"]], [ev["z"]],
                color="#ef4444", s=90, marker="^", zorder=10)
    ax1.quiver(ev["x"], ev["y"], ev["z"],
               ev["vx"] * 2, ev["vy"] * 2, 0,
               color="#ef4444", arrow_length_ratio=0.3, linewidth=1.5, alpha=0.8)
    ax1.text(ev["x"] + 0.5, ev["y"] + 0.5, ev["z"] + 2,
             f"{ev['wind_speed']:.1f}м/с\nt={ev['t']:.0f}s",
             color="#ef4444", fontsize=6.5)

ax1.legend(fontsize=8, labelcolor="white", facecolor="#111827",
           edgecolor="#1e2d47", loc="upper left")
ax1.tick_params(colors="gray", labelsize=7)
ax1.xaxis.pane.fill = False
ax1.yaxis.pane.fill = False
ax1.zaxis.pane.fill = False
ax1.xaxis.pane.set_edgecolor("#1e2d47")
ax1.yaxis.pane.set_edgecolor("#1e2d47")
ax1.zaxis.pane.set_edgecolor("#1e2d47")
ax1.grid(color="#1e2d47", linewidth=0.4)
ax1.set_xlabel("X, м", color="gray", fontsize=8)
ax1.set_ylabel("Y, м", color="gray", fontsize=8)
ax1.set_zlabel("Z, м", color="gray", fontsize=8)

# ── 2. ВЫСОТА ────────────────────────────────────────────
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor("#0f1628")
ax2.set_title("Высота", color="white")
alt_t = [r[0] - t0 for r in altitude]
alt_h = [r[1]      for r in altitude]
ax2.fill_between(alt_t, alt_h, alpha=0.2, color="#a855f7")
ax2.plot(alt_t, alt_h, color="#a855f7", linewidth=1.5)
ax2.tick_params(colors="gray")
ax2.set_xlabel("время, с", color="gray")
ax2.set_ylabel("м",        color="gray")

# ── 3. БАТАРЕЯ ───────────────────────────────────────────
ax3 = fig.add_subplot(gs[0, 2])
ax3.set_facecolor("#0f1628")
ax3.set_title("Батарея", color="white")
pow_t = [r[0] - t0 for r in power]
pow_v = [r[1]      for r in power]
ax3.fill_between(pow_t, pow_v, min(pow_v), alpha=0.15, color="#ef4444")
ax3.plot(pow_t, pow_v, color="#ef4444", linewidth=1.5)
ax3.axhline(7.4, color="#f59e0b", linewidth=0.8, linestyle="--")
ax3.tick_params(colors="gray")
ax3.set_xlabel("время, с", color="gray")
ax3.set_ylabel("В",        color="gray")

# ── 4. RPM МОТОРОВ ───────────────────────────────────────
ax4 = fig.add_subplot(gs[1, 1])
ax4.set_facecolor("#0f1628")
ax4.set_title("RPM моторов", color="white")
colors = {"64": "#00e5ff", "65": "#a855f7", "66": "#10b981", "67": "#f59e0b"}
for mid, vals in motors.items():
    mt  = [r[0] - t0 for r in vals]
    rpm = [r[2]      for r in vals]
    ax4.plot(mt, rpm, color=colors[mid], linewidth=0.8, label=f"M{mid}")
ax4.legend(fontsize=7, labelcolor="white", facecolor="#111827")
ax4.tick_params(colors="gray")
ax4.set_xlabel("время, с", color="gray")
ax4.set_ylabel("RPM",      color="gray")

# ── 5. ОРИЕНТАЦИЯ ────────────────────────────────────────
ax5 = fig.add_subplot(gs[1, 2])
ax5.set_facecolor("#0f1628")
ax5.set_title("Ориентация (roll / pitch / yaw)", color="white")
ori_t = [r[0] - t0 for r in orientation][::20]
ori_r = [r[1]      for r in orientation][::20]
ori_p = [r[2]      for r in orientation][::20]
ori_y = [r[3]      for r in orientation][::20]
ax5.plot(ori_t, ori_r, color="#00e5ff", linewidth=0.9, label="roll")
ax5.plot(ori_t, ori_p, color="#f59e0b", linewidth=0.9, label="pitch")
ax5.plot(ori_t, ori_y, color="#a855f7", linewidth=0.9, label="yaw")
ax5.legend(fontsize=7, labelcolor="white", facecolor="#111827")
ax5.tick_params(colors="gray")
ax5.set_xlabel("время, с", color="gray")
ax5.set_ylabel("градусы",  color="gray")

# ── 6. RMSE ──────────────────────────────────────────────
ax6 = fig.add_subplot(gs[2, 1:])   # занимает обе правые колонки нижней строки
ax6.set_facecolor("#0f1628")
ax6.set_title(f"RMSE отклонение  (3D = {rmse_3d:.3f} м)", color="white")
dev_x  = [abs(gps_x[i] - ideal_x[i]) for i in range(len(gps_x))]
dev_y  = [abs(gps_y[i] - ideal_y[i]) for i in range(len(gps_y))]
dev_z  = [abs(gps_z[i] - ideal_z[i]) for i in range(len(gps_z))]
dev_3d = [math.sqrt(dev_x[i]**2 + dev_y[i]**2 + dev_z[i]**2) for i in range(len(gps_x))]
ax6.plot(gps_t, dev_x,  color="#00e5ff", linewidth=0.9, label=f"|ΔX| {rmse_x:.3f}м")
ax6.plot(gps_t, dev_y,  color="#f59e0b", linewidth=0.9, label=f"|ΔY| {rmse_y:.3f}м")
ax6.plot(gps_t, dev_z,  color="#a855f7", linewidth=0.9, label=f"|ΔZ| {rmse_z:.3f}м")
ax6.plot(gps_t, dev_3d, color="#10b981", linewidth=1.5, label=f"3D  {rmse_3d:.3f}м")

# метки порывов на RMSE
for ev in wind_events:
    ax6.axvline(ev["t"], color="#ef4444", linewidth=0.8, linestyle="--", alpha=0.5)

ax6.legend(fontsize=7, labelcolor="white", facecolor="#111827")
ax6.tick_params(colors="gray")
ax6.set_xlabel("время, с", color="gray")
ax6.set_ylabel("м",        color="gray")

plt.savefig("analysis.png", dpi=150, bbox_inches="tight", facecolor="#050810")
print("\nСохранено: analysis.png")
plt.show()