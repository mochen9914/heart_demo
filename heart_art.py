"""
绯樱星尘之心 (Neon Bloom Stardust Heart)
========================================
纯 Python 标准库 (tkinter + math) 实时像素级加法发光 (Additive RGB Bloom) 渲染，无需安装第三方包。

核心视觉与算法设计：
1. 等弧长重采样心形曲线 (Equal-Arclength Heart Curve)：
   消除传统参数方程在心形凹口与尖端处的点密度堆积，使整颗 ❤️ 轮廓线条均匀、饱满、丝滑。
2. 像素级加法霓虹辉光引擎 (Additive Bloom Pixel Buffer)：
   基于 P6 原生帧缓冲实现真正的光学叠加发光——粒子密集交叠处自动由深绯红渐变为樱花粉直至璀璨星白。
3. 六重浪漫动态细节：
   - 天鹅绒内腔指数扩散呼吸波
   - 高亮柔光 ❤️ 主轮廓
   - 外缘闪烁星雾光环
   - 随双峰心跳 (Lub-Dub) 向外扩散的 ❤️ 星尘涟漪波
   - 沿 ❤️ 轮廓双向流淌的星光彗星
   - 十字星芒闪烁 + 升腾流萤 + 鼠标仙女棒星尘拖尾

运行方式：
    python3 heart_art.py

交互操作：
    - 移动鼠标：挥洒发光星尘拖尾
    - 空格键 / 鼠标左键点击：切换 4 套高定艺术配色并激发心形扩散波
    - P 键：定格 / 继续画面
    - Esc 键：退出程序
"""

import math
import random
import tkinter as tk


# 饱和度截断查找表（替代 min(255, x)，大幅加速像素加法混合）
CLAMP = bytes(range(256)) + b"\xff" * 512

# 4 套高定发光配色方案（RGB 叠加权重经过专门调校，交叠处自然泛白发光）
THEMES = [
    {
        "name": "绯樱星尘 · Sakura Rose",
        "bg_rgb": (7, 3, 11),
        "glow_rgb": (28, 6, 20),
        "inner_rgb": (132, 24, 60),
        "aura_rgb": (168, 42, 90),
        "rim_rgb": (182, 58, 102),
        "comet_rgb": (230, 170, 198),
        "star_rgb": (255, 215, 236),
        "hud": "#9e6b82",
    },
    {
        "name": "炽恋真红 · Ruby Flame",
        "bg_rgb": (9, 2, 4),
        "glow_rgb": (34, 5, 8),
        "inner_rgb": (150, 16, 26),
        "aura_rgb": (190, 28, 38),
        "rim_rgb": (210, 42, 48),
        "comet_rgb": (255, 195, 145),
        "star_rgb": (255, 232, 205),
        "hud": "#a86468",
    },
    {
        "name": "星河蓝钻 · Starry Sapphire",
        "bg_rgb": (3, 7, 15),
        "glow_rgb": (8, 22, 42),
        "inner_rgb": (24, 76, 155),
        "aura_rgb": (38, 125, 195),
        "rim_rgb": (56, 148, 215),
        "comet_rgb": (185, 235, 255),
        "star_rgb": (225, 248, 255),
        "hud": "#648cb0",
    },
    {
        "name": "鎏金香槟 · Champagne Gold",
        "bg_rgb": (9, 6, 3),
        "glow_rgb": (30, 18, 6),
        "inner_rgb": (138, 74, 18),
        "aura_rgb": (178, 108, 28),
        "rim_rgb": (198, 132, 42),
        "comet_rgb": (255, 226, 175),
        "star_rgb": (255, 246, 220),
        "hud": "#9e8462",
    },
]


def build_uniform_heart_table(n_uniform: int = 2048) -> tuple[list[float], list[float]]:
    """构造严格等弧长分布的经典 ❤️ 轮廓采样表，确保心形曲线各处亮度均匀"""
    n_raw = 4096
    raw_x = [0.0] * n_raw
    raw_y = [0.0] * n_raw
    arc = [0.0] * n_raw
    prev_x, prev_y = 0.0, -5.0
    acc = 0.0

    for i in range(n_raw):
        t = (i / n_raw) * math.tau
        sin_t = math.sin(t)
        x = 16.0 * (sin_t * sin_t * sin_t)
        y = -(
            13.0 * math.cos(t)
            - 5.0 * math.cos(2.0 * t)
            - 2.0 * math.cos(3.0 * t)
            - math.cos(4.0 * t)
        )
        raw_x[i] = x
        raw_y[i] = y
        if i > 0:
            acc += math.hypot(x - prev_x, y - prev_y)
        arc[i] = acc
        prev_x, prev_y = x, y

    ux = [0.0] * n_uniform
    uy = [0.0] * n_uniform
    j = 0
    for k in range(n_uniform):
        target = (k / n_uniform) * acc
        while j < n_raw - 1 and arc[j] < target:
            j += 1
        ux[k] = raw_x[j]
        uy[k] = raw_y[j]
    return ux, uy


class StardustHeartApp:
    """像素级发光星尘动态爱心渲染器"""

    BUF_W = 880
    BUF_H = 650
    CENTER_Y = 2.0  # 心形几何中心纵坐标校准值
    SCALE = 12.0
    UNIFORM_N = 2048

    def __init__(self, root: tk.Tk):
        self.root = root
        self.win_w = self.BUF_W
        self.win_h = self.BUF_H
        self.root.title("绯樱星尘之心 · Neon Stardust Heart")

        self.theme_idx = 0
        self.time_t = 0.0
        self.paused = False
        self.pulse_waves: list[float] = [0.25]  # 心形扩散波进度列表 (0.0 -> 1.0)
        self.last_cycle_idx = 0

        # 构造等弧长心形轮廓表与各层粒子
        self.ux, self.uy = build_uniform_heart_table(self.UNIFORM_N)
        self._init_particles()

        # 初始化 P6 像素帧缓冲（零额外头部拼接开销）
        header = f"P6\n{self.BUF_W} {self.BUF_H}\n255\n".encode("ascii")
        self.hdr_len = len(header)
        self.frame_bytes = bytearray(self.hdr_len + self.BUF_W * self.BUF_H * 3)
        self.frame_bytes[: self.hdr_len] = header
        self.bg_cache: dict[int, bytearray] = {}

        bg_hex = self._rgb_to_hex(THEMES[0]["bg_rgb"])
        self.root.configure(bg=bg_hex)
        self.canvas = tk.Canvas(
            root,
            width=self.win_w,
            height=self.win_h,
            bg=bg_hex,
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.photo = tk.PhotoImage(width=self.BUF_W, height=self.BUF_H)
        self.img_id = self.canvas.create_image(
            self.win_w // 2, self.win_h // 2, image=self.photo
        )

        self.hud_id = self.canvas.create_text(
            24,
            self.win_h - 22,
            anchor="w",
            fill=THEMES[0]["hud"],
            font=("Helvetica Neue", 12),
            text=self._hud_text(),
        )

        # 绑定交互事件
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", self._next_theme)
        self.canvas.bind("<Configure>", self._on_resize)
        self.root.bind("<space>", self._next_theme)
        self.root.bind("<p>", self._toggle_pause)
        self.root.bind("<P>", self._toggle_pause)
        self.root.bind("<Escape>", lambda _: self.root.destroy())

    @staticmethod
    def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _hud_text(self) -> str:
        name = THEMES[self.theme_idx]["name"]
        state = "  [已定格]" if self.paused else ""
        return f"♥ {name}{state}    |    [空格/点击] 切换配色与心形涟漪    [P] 定格    [滑动鼠标] 挥洒星尘"

    def _init_particles(self) -> None:
        cy0 = self.CENTER_Y
        n_uni = self.UNIFORM_N
        ux, uy = self.ux, self.uy

        # 1. 高亮心形主轮廓粒子 (1,900 颗)
        self.rim_pts: list[tuple[float, float, float]] = []
        for i in range(1900):
            idx = (i * n_uni) // 1900
            sp = random.gauss(1.0, 0.015)
            self.rim_pts.append(
                (ux[idx] * sp, cy0 + (uy[idx] - cy0) * sp, random.uniform(0.0, math.tau))
            )

        # 2. 天鹅绒内腔指数扩散粒子 (3,800 颗，带各向同性柔化消除中线折痕)
        self.inner_pts: list[tuple[float, float, float, float]] = []
        for _ in range(3800):
            idx = random.randrange(n_uni)
            d = -0.22 * math.log(max(random.random(), 1e-3))
            if d < 0.86:
                s = 1.0 - d
                jx = random.gauss(0.0, 1.05 * d)
                jy = random.gauss(0.0, 1.05 * d)
                self.inner_pts.append(
                    (
                        ux[idx] * s + jx,
                        cy0 + (uy[idx] - cy0) * s + jy,
                        s,
                        random.uniform(0.0, math.tau),
                    )
                )

        # 3. 外缘心形星雾粒子 (1,450 颗)
        self.aura_pts: list[tuple[float, float, float, float]] = []
        for _ in range(1450):
            idx = random.randrange(n_uni)
            d = -0.095 * math.log(max(random.random(), 1e-3))
            if d < 0.46:
                s = 1.015 + d
                self.aura_pts.append(
                    (
                        ux[idx] * s + random.gauss(0.0, 0.28),
                        cy0 + (uy[idx] - cy0) * s + random.gauss(0.0, 0.28),
                        d,
                        random.uniform(0.0, math.tau),
                    )
                )

        # 4. 扩散波采样模板点 (500 颗)
        self.ripple_tpl: list[tuple[float, float, float]] = []
        for i in range(500):
            idx = (i * n_uni) // 500
            self.ripple_tpl.append(
                (
                    ux[idx] + random.gauss(0.0, 0.26),
                    (uy[idx] - cy0) + random.gauss(0.0, 0.26),
                    random.uniform(0.55, 1.0),
                )
            )

        # 5. 十字星芒闪烁点 (155 颗)
        self.stars: list[tuple[float, float, float]] = []
        for _ in range(155):
            idx = random.randrange(n_uni)
            s = random.uniform(0.68, 1.15)
            self.stars.append(
                (
                    ux[idx] * s + random.gauss(0.0, 0.3),
                    cy0 + (uy[idx] - cy0) * s + random.gauss(0.0, 0.3),
                    random.uniform(0.0, math.tau),
                )
            )

        # 6. 升腾心火流萤粒子 (70 颗: [x, y, vy, phase, age, max_age])
        self.embers: list[list[float]] = [self._new_ember(random_age=True) for _ in range(70)]

        # 7. 鼠标挥洒星尘粒子 ([px, py, vx, vy, age, max_age])
        self.mouse_sparks: list[list[float]] = []

    def _new_ember(self, random_age: bool = False) -> list[float]:
        idx = random.randrange(self.UNIFORM_N)
        s = random.uniform(0.92, 1.06)
        x = self.ux[idx] * s
        y = self.CENTER_Y + (self.uy[idx] - self.CENTER_Y) * s
        vy = random.uniform(0.045, 0.11)
        phase = random.uniform(0.0, math.tau)
        max_age = float(random.randint(70, 140))
        age = random.uniform(0.0, max_age) if random_age else 0.0
        return [x, y, vy, phase, age, max_age]

    def _get_bg_buffer(self, theme_idx: int) -> bytearray:
        """生成平滑暗角柔光背景缓冲（边缘渐隐至纯背景色，全屏无接缝）"""
        if theme_idx in self.bg_cache:
            return self.bg_cache[theme_idx]

        w, h = self.BUF_W, self.BUF_H
        cx, cy = w * 0.5, h * 0.5 + 5.0
        bg_r, bg_g, bg_b = THEMES[theme_idx]["bg_rgb"]
        gl_r, gl_g, gl_b = THEMES[theme_idx]["glow_rgb"]

        bg = bytearray(w * h * 3)
        gx_table = [
            math.exp(-(((px - cx) / 295.0) ** 2) * 1.4) * min(1.0, min(px, w - 1 - px) / 70.0)
            for px in range(w)
        ]
        for py in range(h):
            gy = math.exp(-(((py - cy) / 255.0) ** 2) * 1.4) * min(1.0, min(py, h - 1 - py) / 70.0)
            row_off = py * w * 3
            for px, gx in enumerate(gx_table):
                g = gx * gy
                i = row_off + px * 3
                bg[i] = bg_r + int(gl_r * g)
                bg[i + 1] = bg_g + int(gl_g * g)
                bg[i + 2] = bg_b + int(gl_b * g)

        self.bg_cache[theme_idx] = bg
        return bg

    @staticmethod
    def _heartbeat(cycle_pos: float) -> float:
        """真实心脏双峰搏动曲线 (Lub-Dub)"""
        p = cycle_pos % 1.0
        lub = math.exp(-48.0 * (p - 0.15) ** 2)
        dub = 0.55 * math.exp(-68.0 * (p - 0.32) ** 2)
        return lub + dub

    def render_frame(self) -> None:
        """将所有星尘层以光学加法混合渲染至 P6 像素帧缓冲"""
        w, h = self.BUF_W, self.BUF_H
        cx = w * 0.5
        cy = h * 0.5 - 20.0
        scale = self.SCALE
        cy0 = self.CENTER_Y
        stride = w * 3
        clamp = CLAMP
        t = self.time_t

        theme = THEMES[self.theme_idx]
        in_r, in_g, in_b = theme["inner_rgb"]
        au_r, au_g, au_b = theme["aura_rgb"]
        rm_r, rm_g, rm_b = theme["rim_rgb"]
        cm_r, cm_g, cm_b = theme["comet_rgb"]
        st_r, st_g, st_b = theme["star_rgb"]

        buf = memoryview(self.frame_bytes)[self.hdr_len :]
        buf[:] = self._get_bg_buffer(self.theme_idx)

        cycle = t * 0.78
        beat = self._heartbeat(cycle)
        rim_wave = 1.0 + beat * 0.092

        # 每次主心跳峰值自动触发一道柔和向外扩散的心形星尘涟漪
        cycle_idx = int(cycle)
        if cycle_idx > self.last_cycle_idx:
            self.last_cycle_idx = cycle_idx
            if len(self.pulse_waves) < 3:
                self.pulse_waves.append(0.0)

        # 1. 天鹅绒内腔扩散层（带由内向外的弹性呼吸波纹）
        for rx, ry, s, ph in self.inner_pts:
            wave = 1.0 + beat * (0.085 + 0.072 * (1.0 - s)) + 0.012 * math.sin(t * 3.0 - s * 5.0)
            px = int(cx + rx * scale * wave)
            py = int(cy + ry * scale * wave)
            if 1 <= px < w - 1 and 1 <= py < h - 1:
                k = s * s
                r = int(in_r * k) + 8
                g = int(in_g * k) + 2
                b = int(in_b * k) + 5
                i0 = py * stride + px * 3
                buf[i0] = clamp[buf[i0] + r]
                buf[i0 + 1] = clamp[buf[i0 + 1] + g]
                buf[i0 + 2] = clamp[buf[i0 + 2] + b]
                r2, g2, b2 = r >> 1, g >> 1, b >> 1
                for off in (-3, 3, -stride, stride):
                    j = i0 + off
                    buf[j] = clamp[buf[j] + r2]
                    buf[j + 1] = clamp[buf[j + 1] + g2]
                    buf[j + 2] = clamp[buf[j + 2] + b2]

        # 2. 心形扩散涟漪波
        alive_waves: list[float] = []
        for prog in self.pulse_waves:
            prog += 0.014
            if prog < 1.0:
                alive_waves.append(prog)
                r_scale = 1.02 + prog * 0.38
                fade = math.sin(prog * math.pi) * 0.58
                for hx, dhy, w_mul in self.ripple_tpl:
                    px = int(cx + hx * r_scale * scale)
                    py = int(cy + (cy0 + dhy * r_scale) * scale)
                    if 1 <= px < w - 1 and 1 <= py < h - 1:
                        kf = fade * w_mul
                        rr = int(au_r * kf)
                        rg = int(au_g * kf)
                        rb_c = int(au_b * kf)
                        i0 = py * stride + px * 3
                        buf[i0] = clamp[buf[i0] + rr]
                        buf[i0 + 1] = clamp[buf[i0 + 1] + rg]
                        buf[i0 + 2] = clamp[buf[i0 + 2] + rb_c]
                        for off in (-3, 3, -stride, stride):
                            j = i0 + off
                            buf[j] = clamp[buf[j] + (rr >> 1)]
                            buf[j + 1] = clamp[buf[j + 1] + (rg >> 1)]
                            buf[j + 2] = clamp[buf[j + 2] + (rb_c >> 1)]
        self.pulse_waves = alive_waves

        # 3. 外缘心形闪烁星雾
        for rx, ry, d, ph in self.aura_pts:
            wave = 1.0 + beat * (0.10 + 0.12 * d)
            px = int(cx + rx * scale * wave)
            py = int(cy + ry * scale * wave)
            if 2 <= px < w - 2 and 2 <= py < h - 2:
                tw = 0.55 + 0.45 * math.sin(t * 4.4 + ph)
                fade = max(0.12, 1.0 - d * 2.0) * tw
                r = int(au_r * fade)
                g = int(au_g * fade)
                b = int(au_b * fade)
                i0 = py * stride + px * 3
                buf[i0] = clamp[buf[i0] + r]
                buf[i0 + 1] = clamp[buf[i0 + 1] + g]
                buf[i0 + 2] = clamp[buf[i0 + 2] + b]
                r2, g2, b2 = r >> 1, g >> 1, b >> 1
                for off in (-3, 3, -stride, stride):
                    j = i0 + off
                    buf[j] = clamp[buf[j] + r2]
                    buf[j + 1] = clamp[buf[j + 1] + g2]
                    buf[j + 2] = clamp[buf[j + 2] + b2]

        # 4. 璀璨心形主轮廓（3x3 柔光核叠加，使心形边缘通透发亮）
        for rx, ry, ph in self.rim_pts:
            px = int(cx + rx * scale * rim_wave)
            py = int(cy + ry * scale * rim_wave)
            if 2 <= px < w - 2 and 2 <= py < h - 2:
                tw = 0.72 + 0.28 * math.sin(t * 5.0 + ph)
                r = int(rm_r * tw)
                g = int(rm_g * tw)
                b = int(rm_b * tw)
                i0 = py * stride + px * 3
                buf[i0] = clamp[buf[i0] + r]
                buf[i0 + 1] = clamp[buf[i0 + 1] + g]
                buf[i0 + 2] = clamp[buf[i0 + 2] + b]
                r2, g2, b2 = r >> 1, g >> 1, b >> 1
                for off in (-3, 3, -stride, stride):
                    j = i0 + off
                    buf[j] = clamp[buf[j] + r2]
                    buf[j + 1] = clamp[buf[j + 1] + g2]
                    buf[j + 2] = clamp[buf[j + 2] + b2]
                r4, g4, b4 = r >> 2, g >> 2, b >> 2
                for off in (-stride - 3, -stride + 3, stride - 3, stride + 3):
                    j = i0 + off
                    buf[j] = clamp[buf[j] + r4]
                    buf[j + 1] = clamp[buf[j + 1] + g4]
                    buf[j + 2] = clamp[buf[j + 2] + b4]

        # 5. 沿 ❤️ 轮廓双向游走的流光彗星
        ux, uy = self.ux, self.uy
        n_uni = self.UNIFORM_N
        for dir_sign, speed_mul in ((1, 0.20), (-1, 0.20)):
            head_u = (dir_sign * t * speed_mul) % 1.0
            for step_i in range(85):
                u_pos = (head_u - dir_sign * step_i * 0.0018) % 1.0
                idx = int(u_pos * n_uni) % n_uni
                fade = ((85 - step_i) / 85.0) ** 1.85
                px = int(cx + ux[idx] * scale * rim_wave)
                py = int(cy + (cy0 + (uy[idx] - cy0)) * scale * rim_wave)
                if 2 <= px < w - 2 and 2 <= py < h - 2:
                    r = int(cm_r * fade * 0.85)
                    g = int(cm_g * fade * 0.85)
                    b = int(cm_b * fade * 0.85)
                    i0 = py * stride + px * 3
                    buf[i0] = clamp[buf[i0] + r]
                    buf[i0 + 1] = clamp[buf[i0 + 1] + g]
                    buf[i0 + 2] = clamp[buf[i0 + 2] + b]
                    for off in (-3, 3, -stride, stride):
                        j = i0 + off
                        buf[j] = clamp[buf[j] + (r >> 1)]
                        buf[j + 1] = clamp[buf[j + 1] + (g >> 1)]
                        buf[j + 2] = clamp[buf[j + 2] + (b >> 1)]

        # 6. 升腾心火流萤粒子
        for em in self.embers:
            em[4] += 1.0
            if em[4] >= em[5]:
                em[:] = self._new_ember(random_age=False)
            em[1] -= em[2]
            sway_x = em[0] + 0.45 * math.sin(t * 2.4 + em[3])
            px = int(cx + sway_x * scale * rim_wave)
            py = int(cy + em[1] * scale)
            if 2 <= px < w - 2 and 2 <= py < h - 2:
                fade = math.sin((em[4] / em[5]) * math.pi) * 0.85
                r, g, b = int(cm_r * fade), int(cm_g * fade), int(cm_b * fade)
                i0 = py * stride + px * 3
                buf[i0] = clamp[buf[i0] + r]
                buf[i0 + 1] = clamp[buf[i0 + 1] + g]
                buf[i0 + 2] = clamp[buf[i0 + 2] + b]
                for off in (-3, 3, -stride, stride):
                    j = i0 + off
                    buf[j] = clamp[buf[j] + (r >> 1)]
                    buf[j + 1] = clamp[buf[j + 1] + (g >> 1)]
                    buf[j + 2] = clamp[buf[j + 2] + (b >> 1)]

        # 7. 十字星芒高光闪烁点
        for rx, ry, ph in self.stars:
            tw = math.sin(t * 3.8 + ph)
            if tw > 0.38:
                inten = ((tw - 0.38) / 0.62) ** 1.5
                px = int(cx + rx * scale * rim_wave)
                py = int(cy + ry * scale * rim_wave)
                if 4 <= px < w - 4 and 4 <= py < h - 4:
                    r, g, b = int(st_r * inten), int(st_g * inten), int(st_b * inten)
                    i0 = py * stride + px * 3
                    buf[i0] = clamp[buf[i0] + r]
                    buf[i0 + 1] = clamp[buf[i0 + 1] + g]
                    buf[i0 + 2] = clamp[buf[i0 + 2] + b]
                    for arm in (1, 2, 3):
                        ar, ag, ab = r >> arm, g >> arm, b >> arm
                        for off in (-3 * arm, 3 * arm, -stride * arm, stride * arm):
                            j = i0 + off
                            buf[j] = clamp[buf[j] + ar]
                            buf[j + 1] = clamp[buf[j + 1] + ag]
                            buf[j + 2] = clamp[buf[j + 2] + ab]

        # 8. 鼠标仙女棒星尘拖尾
        alive_sparks: list[list[float]] = []
        for sp in self.mouse_sparks:
            sp[4] += 1.0
            if sp[4] < sp[5]:
                alive_sparks.append(sp)
                sp[0] += sp[2]
                sp[1] += sp[3]
                sp[3] -= 0.03  # 轻盈上浮感
                px, py = int(sp[0]), int(sp[1])
                if 3 <= px < w - 3 and 3 <= py < h - 3:
                    fade = (1.0 - sp[4] / sp[5]) ** 1.4
                    r, g, b = int(st_r * fade), int(st_g * fade), int(st_b * fade)
                    i0 = py * stride + px * 3
                    buf[i0] = clamp[buf[i0] + r]
                    buf[i0 + 1] = clamp[buf[i0 + 1] + g]
                    buf[i0 + 2] = clamp[buf[i0 + 2] + b]
                    for off in (-3, 3, -stride, stride):
                        j = i0 + off
                        buf[j] = clamp[buf[j] + (r >> 1)]
                        buf[j + 1] = clamp[buf[j + 1] + (g >> 1)]
                        buf[j + 2] = clamp[buf[j + 2] + (b >> 1)]
        self.mouse_sparks = alive_sparks

        self.photo.configure(data=bytes(self.frame_bytes))

    def step(self) -> None:
        if not self.paused:
            self.time_t += 0.018
            self.render_frame()
        self.root.after(16, self.step)

    def _on_mouse_move(self, event: tk.Event) -> None:
        # 将窗口鼠标坐标映射至渲染缓冲区坐标并生成星尘火花
        bx = event.x - (self.win_w - self.BUF_W) * 0.5
        by = event.y - (self.win_h - self.BUF_H) * 0.5
        if 10 < bx < self.BUF_W - 10 and 10 < by < self.BUF_H - 10:
            if len(self.mouse_sparks) < 90:
                for _ in range(2):
                    self.mouse_sparks.append(
                        [
                            bx + random.uniform(-4.0, 4.0),
                            by + random.uniform(-4.0, 4.0),
                            random.uniform(-0.8, 0.8),
                            random.uniform(-1.1, 0.4),
                            0.0,
                            float(random.randint(22, 42)),
                        ]
                    )

    def _next_theme(self, _event: tk.Event | None = None) -> None:
        self.theme_idx = (self.theme_idx + 1) % len(THEMES)
        theme = THEMES[self.theme_idx]
        bg_hex = self._rgb_to_hex(theme["bg_rgb"])
        self.root.configure(bg=bg_hex)
        self.canvas.configure(bg=bg_hex)
        self.canvas.itemconfig(self.hud_id, fill=theme["hud"], text=self._hud_text())
        # 点击时额外激发一道心形扩散波
        if len(self.pulse_waves) < 4:
            self.pulse_waves.append(0.0)
        if self.paused:
            self.render_frame()

    def _toggle_pause(self, _event: tk.Event | None = None) -> None:
        self.paused = not self.paused
        self.canvas.itemconfig(self.hud_id, text=self._hud_text())

    def _on_resize(self, event: tk.Event) -> None:
        if event.width > 100 and event.height > 100:
            self.win_w = event.width
            self.win_h = event.height
            self.canvas.coords(self.img_id, self.win_w // 2, self.win_h // 2)
            self.canvas.coords(self.hud_id, 24, self.win_h - 22)


def main() -> None:
    root = tk.Tk()
    app = StardustHeartApp(root)
    app.step()
    root.mainloop()


if __name__ == "__main__":
    main()
