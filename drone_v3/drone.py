class Drone:
    # ── Конфиг (меняй под разные дроны) ──
    MOTOR_FORCE   = 5.0
    MASS = 0.5
    DRAG_XY       = 0.85
    DRAG_Z        = 0.98
    BATTERY_MAX   = 12.6
    BATTERY_MIN   = 6.6
    BATTERY_DRAIN = 0.0013
    MAX_ANGLE     = 0.8

    def __init__(self):
        # Позиция и скорость
        self.x  = self.y  = self.z  = 0.0
        self.vx = self.vy = self.vz = 0.0

        # Ориентация
        self.yaw      = 0.0
        self.yaw_rate = 0.0

        # Силовая установка
        self.thrust  = 0.5
        self.voltage = self.BATTERY_MAX

        # Состояние
        self.state = 'LANDED'

        # Выход ПИД
        self.pid_pitch  = 0.0
        self.pid_roll   = 0.0
        self.pid_thrust = 0.5

    def reset(self):
        self.__init__()