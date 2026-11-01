# Artillery for the GitHub Universe 2026 badge (stripped v1 port).
# Two tanks, destructible terrain, wind, angle/power, local hot-seat or vs CPU.
import os
import sys
import math
import random

APP_DIR = "/system/apps/artillery"
try:
    os.chdir(APP_DIR)
    sys.path.insert(0, APP_DIR)
except OSError:
    pass

from badgeware import State

badge.mode(HIRES | VSYNC)
screen.antialias = image.OFF

W = 320
H = 200          # playfield height (same as the web game)
HUD_Y = 200      # 40 px HUD strip below
G = 0.12         # gravity per 60 Hz step (web game constant)
SPD = 0.22       # power -> speed (web game constant)
WINDK = 0.0016   # wind accel factor (web game constant)
STEP_MS = 1000 / 60
GROUND_R = 12
HIT_R = 18

SKY_TOP = color.rgb(40, 70, 140)
SKY_BOT = color.rgb(120, 170, 220)
DIRT = color.rgb(110, 80, 40)
GRASS = color.rgb(60, 150, 50)
BLACK = color.rgb(0, 0, 0)
WHITE = color.rgb(255, 255, 255)
DIM = color.rgb(170, 170, 170)
HUD_BG = color.rgb(18, 22, 30)
YEL = color.rgb(250, 220, 60)
RED = color.rgb(230, 60, 50)
TANK_COL = (color.rgb(80, 160, 255), color.rgb(255, 120, 60))
SHELL = color.rgb(30, 30, 30)
FIRE = (color.rgb(255, 230, 120), color.rgb(255, 140, 40), color.rgb(200, 60, 20))

sky_rows = []
for _y in range(H):
    t = _y / H
    sky_rows.append(color.rgb(int(40 + 80 * t), int(70 + 100 * t), int(140 + 80 * t)))

field = image(W, H)
field.antialias = image.OFF

settings = {"mode": 1, "diff": 1, "lives": 1}
State.load("artillery", settings)

MENU, AIM, FLIGHT, BOOM, OVER = 0, 1, 2, 3, 4
MODES = ("2 Players", "vs CPU")
DIFFS = ("Easy", "Normal", "Hard")
LIVES = (1, 3, 5)


class Tank:
    def __init__(self, x):
        self.x = x
        self.y = 0
        self.angle = 45
        self.power = 50
        self.lives = 1


height = [0.0] * W
tanks = []
turn = 0
wind = 0
mode = MENU
menu_sel = 0
shot = None          # [x, y, vx, vy]
trail = []
boom = None          # [x, y, r, t0]
winner = -1
msg = ""
acc = 0.0
rep_t = {}
cpu_t = 0
cpu_plan = None


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def ground_y(x):
    x = int(round(x))
    return height[clamp(x, 0, W - 1)]


def make_terrain():
    global height
    h = [0.0] * W
    y = H * 0.62
    dy = 0.0
    for x in range(W):
        dy += (random.random() - 0.5) * 1.6
        dy *= 0.92
        y = clamp(y + dy, H * 0.35, H * 0.88)
        h[x] = y
    for _ in range(8):
        t = h[:]
        for x in range(1, W - 1):
            t[x] = (h[x - 1] + h[x] + h[x + 1]) / 3
        h = t
    height = h


def draw_cols(x0, x1):
    x0 = clamp(int(x0), 0, W - 1)
    x1 = clamp(int(x1), 0, W - 1)
    for x in range(x0, x1 + 1):
        gy = int(height[x])
        # sky column: 8 px gradient bands keep it cheap
        for b in range(0, gy, 8):
            field.pen = sky_rows[b]
            field.rectangle(x, b, 1, min(8, gy - b))
        field.pen = GRASS
        field.rectangle(x, gy, 1, 2)
        field.pen = DIRT
        field.rectangle(x, gy + 2, 1, H - gy - 2)


def settle_tanks():
    for t in tanks:
        t.y = ground_y(t.x) - 4


def crater(cx, cy, r):
    for x in range(int(cx - r), int(cx + r) + 1):
        if x < 0 or x >= W:
            continue
        dx = x - cx
        d = r * r - dx * dx
        if d <= 0:
            continue
        height[x] = min(H - 2, height[x] + math.sqrt(d) * 0.85)
    draw_cols(cx - r - 1, cx + r + 1)
    settle_tanks()


def new_wind():
    global wind
    wind = int(round(random.uniform(-18, 18)))


def new_game():
    global tanks, turn, mode, shot, boom, winner, msg, cpu_plan
    make_terrain()
    draw_cols(0, W - 1)
    tanks = [Tank(36), Tank(W - 36)]
    for t in tanks:
        t.lives = LIVES[settings["lives"]]
    tanks[1].angle = 45
    settle_tanks()
    turn = 0
    shot = None
    boom = None
    winner = -1
    msg = ""
    cpu_plan = None
    new_wind()
    mode = AIM


def is_cpu(i):
    return settings["mode"] == 1 and i == 1


def launch(who, a, p):
    t = tanks[who]
    d = 1 if who == 0 else -1
    rad = (a if who == 0 else 180 - a) * math.pi / 180
    s = p * SPD
    return [t.x + d * 6, t.y - 3, math.cos(rad) * s, -math.sin(rad) * s]


def fire():
    global shot, mode, trail, acc, msg
    t = tanks[turn]
    shot = launch(turn, t.angle, t.power)
    trail = []
    acc = 0.0
    msg = ""
    mode = FLIGHT


def hit_tank(px, py):
    for i in range(2):
        t = tanks[i]
        if t.lives > 0 and math.sqrt((px - t.x) ** 2 + (py - t.y) ** 2) < 6:
            return i
    return -1


def sim_landing(a, p, who, w):
    s = launch(who, a, p)
    x, y, vx, vy = s
    o = tanks[1 - who]
    for _ in range(400):
        vx += w * WINDK
        vy += G
        x += vx
        y += vy
        if x < 0 or x >= W or y >= H:
            return 9999
        if math.sqrt((x - o.x) ** 2 + (y - o.y) ** 2) < 6:
            return 0
        if y >= ground_y(x):
            return math.sqrt((x - o.x) ** 2 + (y - o.y) ** 2)
    return 9999


def cpu_choose():
    # Same search as the web game's aiChoose (a 15..80 step 3, p 25..95 step 5)
    best_a, best_p, best_d = 45, 50, 1e9
    for a in range(15, 81, 3):
        for p in range(25, 96, 5):
            d = sim_landing(a, p, 1, wind)
            if d < best_d:
                best_a, best_p, best_d = a, p, d
    jit = (8, 4, 2)[settings["diff"]]
    pj = (14, 8, 4)[settings["diff"]]
    return (int(clamp(best_a + random.uniform(-jit, jit), 1, 179)),
            int(clamp(best_p + random.uniform(-pj, pj), 1, 100)))


def explode(x, y, victim):
    global shot, boom, mode, msg
    shot = None
    r = HIT_R if victim >= 0 else GROUND_R
    crater(x, y, r)
    if victim >= 0:
        tanks[victim].lives -= 1
        msg = "P%d hit!" % (victim + 1) if not is_cpu(victim) else "CPU hit!"
    boom = [x, y, r, badge.ticks]
    mode = BOOM


def end_turn():
    global turn, mode, winner, cpu_plan, msg
    for i in range(2):
        if tanks[i].lives <= 0:
            winner = 1 - i
            mode = OVER
            return
    turn = 1 - turn
    msg = ""
    cpu_plan = None
    new_wind()
    mode = AIM


def step_shot():
    # one 60 Hz physics step; returns True when shot resolved
    s = shot
    s[2] += wind * WINDK
    s[3] += G
    s[0] += s[2]
    s[1] += s[3]
    x, y = s[0], s[1]
    if x < 0 or x >= W or y >= H:
        global msg
        msg = "Miss"
        end_shot_out()
        return True
    v = hit_tank(x, y)
    if v >= 0:
        explode(x, y, v)
        return True
    if y >= ground_y(x):
        explode(x, ground_y(x), -1)
        return True
    if len(trail) < 120 and (int(x) & 1) == 0:
        trail.append((int(x), int(y)))
    return False


def end_shot_out():
    global shot, boom, mode
    shot = None
    boom = None
    mode = BOOM
    globals()["boom_t"] = badge.ticks


boom_t = 0


# ---------------- input ----------------
def repeat(btn, now):
    # pressed -> immediate; held -> repeat after 300 ms every 60 ms (faster after 1 s)
    if badge.pressed(btn):
        rep_t[btn] = now + 300
        return 1
    if badge.held(btn) and now >= rep_t.get(btn, 0):
        rep_t[btn] = now + 60
        return 1
    return 0


def aim_input(now):
    t = tanks[turn]
    # LEFT/RIGHT swing the barrel the way you press (mirrored for the right-hand tank);
    # UP/DOWN raise/lower power.
    d = 1 if turn == 0 else -1
    if repeat(BUTTON_LEFT, now):
        t.angle = clamp(t.angle + d, 1, 179)
    if repeat(BUTTON_RIGHT, now):
        t.angle = clamp(t.angle - d, 1, 179)
    if repeat(BUTTON_UP, now):
        t.power = clamp(t.power + 1, 1, 100)
    if repeat(BUTTON_DOWN, now):
        t.power = clamp(t.power - 1, 1, 100)
    if badge.pressed(BUTTON_SELECT):
        fire()


def cpu_turn(now):
    global cpu_plan, cpu_t
    t = tanks[turn]
    if cpu_plan is None:
        cpu_plan = cpu_choose()
        cpu_t = now + 400
        return
    # visibly dial in angle/power, then fire
    if now < cpu_t:
        return
    cpu_t = now + 25
    a = cpu_plan[0]
    p = cpu_plan[1]
    if t.angle != a:
        t.angle += 1 if a > t.angle else -1
    elif t.power != p:
        t.power += 1 if p > t.power else -1
    elif len(cpu_plan) == 2:
        cpu_plan = (a, p, 1)
        cpu_t = now + 350
    else:
        fire()


# ---------------- drawing ----------------
def draw_tank(i):
    t = tanks[i]
    if t.lives <= 0:
        return
    x = int(t.x)
    y = int(t.y)
    screen.pen = TANK_COL[i]
    screen.rectangle(x - 5, y - 1, 11, 4)
    screen.rectangle(x - 3, y - 4, 7, 3)
    a = t.angle if i == 0 else 180 - t.angle
    rad = a * math.pi / 180
    screen.line(x, y - 3, int(x + math.cos(rad) * 8), int(y - 3 - math.sin(rad) * 8))
    screen.pen = BLACK
    screen.rectangle(x - 5, y + 3, 11, 1)


def text(s, x, y, pen=WHITE):
    screen.pen = pen
    screen.text(s, x, y)


def ctext(s, y, pen=WHITE):
    w, _ = screen.measure_text(s)
    text(s, (W - w) / 2, y, pen)


def hearts(n):
    return "*" * n if n <= 5 else "%d" % n


def draw_hud():
    screen.pen = HUD_BG
    screen.rectangle(0, HUD_Y, W, 40)
    screen.font = font.nope
    t = tanks[turn]
    name = ("CPU" if is_cpu(turn) else "P%d" % (turn + 1))
    text(name + " TURN", 4, HUD_Y + 3, TANK_COL[turn])
    text("ANG %3d" % t.angle, 4, HUD_Y + 20)
    text("L/R", 60, HUD_Y + 20, DIM)
    text("POW %3d" % t.power, 86, HUD_Y + 20)
    text("U/D", 142, HUD_Y + 20, DIM)
    # wind arrow
    wl = "WIND %2d" % abs(wind)
    text(wl, 172, HUD_Y + 20, YEL)
    cx = 262
    cy = HUD_Y + 26
    screen.pen = YEL
    ln = int(abs(wind) * 1.4) + 2
    d = 1 if wind >= 0 else -1
    if wind != 0:
        screen.line(cx - d * ln // 2, cy, cx + d * ln // 2, cy)
        screen.line(cx + d * ln // 2, cy, cx + d * ln // 2 - d * 4, cy - 3)
        screen.line(cx + d * ln // 2, cy, cx + d * ln // 2 - d * 4, cy + 3)
    text("P1 " + hearts(tanks[0].lives), 100, HUD_Y + 3, TANK_COL[0])
    n2 = "CPU " if settings["mode"] == 1 else "P2 "
    text(n2 + hearts(tanks[1].lives), 186, HUD_Y + 3, TANK_COL[1])
    if msg:
        text(msg, 262, HUD_Y + 3, RED)


def draw_game(now):
    screen.blit(field, vec2(0, 0))
    screen.pen = color.rgb(255, 255, 255, 120)
    for p in trail:
        screen.rectangle(p[0], p[1], 1, 1)
    draw_tank(0)
    draw_tank(1)
    if shot:
        sx = int(shot[0])
        sy = int(shot[1])
        screen.pen = WHITE
        screen.rectangle(sx - 2, sy - 2, 5, 5)
        screen.pen = SHELL
        screen.rectangle(sx - 1, sy - 1, 3, 3)
    if boom:
        el = now - boom[3]
        k = el / 450
        if k < 1:
            r = int(boom[2] * (0.4 + 0.6 * k))
            screen.pen = FIRE[min(2, int(k * 3))]
            screen.shape(shape.circle(boom[0], boom[1], r))
    draw_hud()


def draw_menu():
    screen.pen = BLACK
    screen.rectangle(0, 0, W, 240)
    screen.blit(field, vec2(0, 40))
    screen.pen = color.rgb(0, 0, 0, 150)
    screen.rectangle(40, 60, 240, 150)
    screen.font = font.ziplock
    ctext("ARTILLERY", 10, YEL)
    screen.font = font.nope
    rows = ("Mode: " + MODES[settings["mode"]],
            "CPU: " + DIFFS[settings["diff"]],
            "Lives: %d" % LIVES[settings["lives"]],
            "START")
    for i in range(4):
        y = 74 + i * 26
        if i == menu_sel:
            screen.pen = color.rgb(250, 220, 60, 70)
            screen.rectangle(52, y - 3, 216, 20)
        pen = WHITE if (i != 1 or settings["mode"] == 1) else DIM
        ctext(("< " + rows[i] + " >") if i < 3 else rows[i], y, pen)
    ctext("UP/DN pick  L/R change  SELECT go", 216, DIM)


def draw_over():
    screen.pen = color.rgb(0, 0, 0, 160)
    screen.rectangle(50, 60, 220, 80)
    screen.font = font.ziplock
    if is_cpu(winner):
        s = "CPU WINS"
    else:
        s = "PLAYER %d WINS" % (winner + 1)
    ctext(s, 76, TANK_COL[winner])
    screen.font = font.nope
    ctext("SELECT rematch  BACK menu", 112)


def menu_input():
    global menu_sel, mode
    if badge.pressed(BUTTON_UP):
        menu_sel = (menu_sel - 1) % 4
    if badge.pressed(BUTTON_DOWN):
        menu_sel = (menu_sel + 1) % 4
    d = 0
    if badge.pressed(BUTTON_LEFT):
        d = -1
    if badge.pressed(BUTTON_RIGHT):
        d = 1
    if d and menu_sel < 3:
        k = ("mode", "diff", "lives")[menu_sel]
        n = (2, 3, 3)[menu_sel]
        settings[k] = (settings[k] + d) % n
    if badge.pressed(BUTTON_SELECT):
        if True:
            State.save("artillery", settings)
            new_game()


def to_menu():
    global mode
    mode = MENU


make_terrain()
draw_cols(0, W - 1)


def update():
    global acc, mode, boom
    now = badge.ticks
    dt = badge.ticks_delta
    if dt > 100:
        dt = 100
    if mode == MENU:
        menu_input()
        draw_menu()
        return
    if badge.pressed(BUTTON_HOME) or badge.pressed(BUTTON_MENU) or (badge.pressed(BUTTON_BACK) and mode != OVER):
        to_menu()
        draw_menu()
        return
    if mode == AIM:
        if is_cpu(turn):
            cpu_turn(now)
        else:
            aim_input(now)
    elif mode == FLIGHT:
        acc += dt
        while acc >= STEP_MS and mode == FLIGHT:
            acc -= STEP_MS
            step_shot()
    elif mode == BOOM:
        t0 = boom[3] if boom else boom_t
        if now - t0 > 600:
            boom = None
            end_turn()
    elif mode == OVER:
        if badge.pressed(BUTTON_SELECT):
            new_game()
        elif badge.pressed(BUTTON_BACK):
            to_menu()
    draw_game(now)
    if mode == OVER:
        draw_over()


run(update)
