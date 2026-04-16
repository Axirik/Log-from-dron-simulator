import math
import random

class Simulator:
    LANDED    = 'LANDED'
    TAKEOFF   = 'TAKEOFF'
    HOVER     = 'HOVER'
    FLYING    = 'FLYING'
    LANDING   = 'LANDING'
    EMERGENCY = 'EMERGENCY'

    def __init__(self, drone):
        self.drone = drone
        self.dt    = 0.1
        self.t     = 0.0

        self.control_mode = 'AUTO'
        self.controller_input = {
            'pitch': 0.0, 'roll': 0.0,
            'thr':   0.0, 'yaw':  0.0
        }

        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0

        self.Kp   = 2.1;  self.Ki   = 0.9;  self.Kd   = 1.0
        self.Kp_z = 0.3;  self.Ki_z = 0.005; self.Kd_z = 0.6

        self.integral_x = self.integral_y = self.integral_z = 0.0
        self.prev_err_x = self.prev_err_y = self.prev_err_z = 0.0

        self.wind_x       = 0.0
        self.wind_y       = 0.0
        self.wind_timer   = 0.0
        self.wind_enabled = True

        self.orbit_mode     = False
        self.orbit_radius   = 1.0
        self.orbit_speed    = 1.0
        self.orbit_center_x = 0.0
        self.orbit_center_y = 0.0

    # ══════════════════════════════════════
    #  STATE MACHINE
    # ══════════════════════════════════════
    def update_state(self):
        d = self.drone

        # ── Глобальные условия ──
        if d.voltage <= d.BATTERY_MIN and d.state not in (self.LANDED, self.EMERGENCY):
            d.state           = self.EMERGENCY
            self.wind_enabled = False
            d.thrust          = 0.25
            print("⚠ БАТАРЕЯ РАЗРЯЖЕНА!")
            return

        if d.z <= 0.0 and d.vz <= 0.0 and d.state not in (self.LANDED, self.TAKEOFF):
            prev    = d.state
            d.state = self.LANDED
            d.thrust = 0.5
            d.vx = d.vy = d.vz = 0.0
            d.z  = 0.0
            print("✓ Аварийная посадка." if prev == self.EMERGENCY else "✓ Приземлился.")
            return

        # ── Переходы ──
        if d.state == self.LANDED:
            if d.thrust > 0.5 and d.voltage > d.BATTERY_MIN:
                d.state = self.TAKEOFF
                print("🚀 Взлёт!")

        elif d.state == self.TAKEOFF:
            if d.z > 0.5:
                d.state = self.HOVER

        elif d.state == self.HOVER:
            if abs(d.vx) > 0.15 or abs(d.vy) > 0.15:
                d.state = self.FLYING
            # LANDING только в MANUAL
            elif self.control_mode == 'MANUAL' and d.thrust < 0.45:
                d.state = self.LANDING

        elif d.state == self.FLYING:
            if abs(d.vx) < 0.05 and abs(d.vy) < 0.05:
                d.state = self.HOVER
            elif self.control_mode == 'MANUAL' and d.thrust < 0.45:
                d.state = self.LANDING
            elif self.control_mode == 'AUTO' and self.target_z < 0.5:
                d.state = self.LANDING

        elif d.state == self.LANDING:
            if self.control_mode == 'MANUAL' and d.thrust > 0.5:
                d.state = self.FLYING
            elif self.control_mode == 'AUTO' and self.target_z > 0.5:
                d.state = self.FLYING

        elif d.state == self.EMERGENCY:
            d.thrust = 0.25

    # ══════════════════════════════════════
    #  ВЕТЕР
    # ══════════════════════════════════════
    def update_wind(self):
        if not self.wind_enabled:
            self.wind_x = self.wind_y = 0.0
            return

        self.wind_timer += self.dt
        if self.wind_timer >= 10.0:
            self.wind_x     = random.uniform(-1.5, 1.5)
            self.wind_y     = random.uniform(-1.5, 1.5)
            self.wind_timer = 0.0
            print(f"\n💨 Порыв: wx={self.wind_x:.2f} wy={self.wind_y:.2f}")

    # ══════════════════════════════════════
    #  ПИД
    # ══════════════════════════════════════
    def update_pid(self):
        d = self.drone

        if d.state not in (self.TAKEOFF, self.HOVER, self.FLYING):
            d.pid_pitch  = 0.0
            d.pid_roll   = 0.0
            d.pid_thrust = d.thrust
            if d.state == self.LANDED:
                self.integral_x = self.integral_y = self.integral_z = 0.0
                self.prev_err_x = self.prev_err_y = self.prev_err_z = 0.0
            return

        ex = self.target_x - d.x
        ey = self.target_y - d.y
        ez = self.target_z - d.z

        self.integral_x = max(-5.0, min(5.0, self.integral_x + ex * self.dt))
        self.integral_y = max(-5.0, min(5.0, self.integral_y + ey * self.dt))
        self.integral_z = max(-5.0, min(5.0, self.integral_z + ez * self.dt))

        dx = (ex - self.prev_err_x) / self.dt
        dy = (ey - self.prev_err_y) / self.dt
        dz = (ez - self.prev_err_z) / self.dt

        d.pid_pitch  = self.Kp*ex + self.Ki*self.integral_x + self.Kd*dx
        d.pid_roll   = self.Kp*ey + self.Ki*self.integral_y + self.Kd*dy
        d.pid_thrust = 0.5 + self.Kp_z*ez + self.Ki_z*self.integral_z + self.Kd_z*dz

        d.pid_pitch  = max(-d.MAX_ANGLE, min(d.MAX_ANGLE, d.pid_pitch))
        d.pid_roll   = max(-d.MAX_ANGLE, min(d.MAX_ANGLE, d.pid_roll))
        d.pid_thrust = max(0.3, min(0.9, d.pid_thrust))

        self.prev_err_x = ex
        self.prev_err_y = ey
        self.prev_err_z = ez

    # ══════════════════════════════════════
    #  УПРАВЛЕНИЕ
    # ══════════════════════════════════════
    def manual_loop(self):
        d = self.drone
        d.pid_pitch = self.controller_input['pitch']
        d.pid_roll  = self.controller_input['roll']
        d.yaw_rate  = self.controller_input['yaw']

        thr = self.controller_input['thr']
        if thr != 0:
            d.thrust += thr * self.dt * 3
            d.thrust  = max(0.3, min(0.9, d.thrust))
        else:
            if d.thrust > 0.5:
                d.thrust = max(0.5, d.thrust - 0.005)
            elif d.thrust < 0.5:
                d.thrust = min(0.5, d.thrust + 0.005)

    def auto_loop(self):
        d = self.drone

        if self.orbit_mode:
            self.target_x = self.orbit_center_x + self.orbit_radius * math.sin(self.orbit_speed * self.t)
            self.target_y = self.orbit_center_y + self.orbit_radius * math.cos(self.orbit_speed * self.t)

        if d.state == self.LANDED and self.target_z > 0.1 and d.voltage > d.BATTERY_MIN:
            d.thrust = 0.7

        self.update_pid()

        # Синхронизируем thrust с pid_thrust для визуализации и состояний
        d.thrust = d.pid_thrust

    # ══════════════════════════════════════
    #  ФИЗИКА
    # ══════════════════════════════════════
    def update_physics(self):
        d = self.drone

        if d.state == self.LANDED:
            d.vx = d.vy = d.vz = 0.0
            return

        self.update_wind()

        fx = math.sin(d.pid_pitch) * d.MOTOR_FORCE / d.MASS
        fy = math.sin(d.pid_roll)  * d.MOTOR_FORCE / d.MASS

        ax = fx * math.cos(d.yaw) - fy * math.sin(d.yaw) + self.wind_x / d.MASS
        ay = fx * math.sin(d.yaw) + fy * math.cos(d.yaw) + self.wind_y / d.MASS
        az = (2 * d.pid_thrust * 9.8 - 9.8) / d.MASS

        d.vx = d.vx * d.DRAG_XY + ax * self.dt
        d.vy = d.vy * d.DRAG_XY + ay * self.dt
        d.vz = d.vz * d.DRAG_Z  + az * self.dt

        d.x += d.vx * self.dt
        d.y += d.vy * self.dt
        d.z += d.vz * self.dt

        d.yaw = (d.yaw + d.yaw_rate * self.dt) % (2 * math.pi)

        if d.z <= 0.0 and d.vz <= 0.0:
            d.z = d.vz = 0.0

        d.voltage -= d.thrust * d.BATTERY_DRAIN
        d.voltage  = max(0.0, d.voltage)

    # ══════════════════════════════════════
    #  ГЛАВНЫЙ ШАГ
    # ══════════════════════════════════════
    def step(self):
        if self.drone.state == self.EMERGENCY:
            self.drone.pid_thrust = 0.25
            self.target_z         = self.drone.z
            self.update_pid()
        elif self.control_mode == 'MANUAL':
            self.manual_loop()
        elif self.control_mode == 'AUTO':
            self.auto_loop()

        self.update_state()
        self.update_physics()
        self.t += self.dt