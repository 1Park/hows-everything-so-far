"""투명 유리잔 + 음료 3종(water / coke / coffee — 팀 데모 음료) × 잔량 4단계 합성 이미지 생성기.

실제 사진을 찍기 전 파이프라인 검증용. 합성 이미지 정확도는 실제 정확도를 보장하지 않는다.

출력 구조 (ImageFolder 형식, 클래스 = 폴더명):
  data/synthetic/coke__full/0000.png
  data/synthetic/coffee__low/0003.png
  data/synthetic/empty/0012.png
"""

import argparse
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

SIZE = 320

DRINKS = {
    # coke vs coffee 는 둘 다 짙은 갈색 → 실제로 구분되는 단서만 넣는다: coke 는 반투명(붉은기)+기포+연한 거품,
    # coffee 는 불투명+기포 없음+크레마(밝은 갈색 윗면). 실사에서 이 단서가 약하면 구분이 어려울 수 있다.
    "coke": dict(rgb=(60, 26, 12), jitter=10, alpha=(0.84, 0.93), foam=(205, 175, 135), foam_p=0.6, bubbles=True),
    "coffee": dict(rgb=(52, 34, 22), jitter=10, alpha=(0.96, 0.995), foam=(170, 115, 65), foam_p=0.5, bubbles=False),
    # 물: 색 대신 굴절(배경 좌우 반전)·밝은 수면선·옅은 틴트로만 보인다
    "water": dict(rgb=(205, 220, 230), jitter=10, alpha=(0.10, 0.25), foam=None, refract=True),
}

# 잔 높이 대비 액체 높이 비율
LEVELS = {
    "full": (0.80, 0.95),
    "mid": (0.40, 0.60),
    "low": (0.10, 0.25),
    "empty": (0.0, 0.03),
}


def background(rng: random.Random) -> Image.Image:
    kind = rng.choice(["wood", "white", "gray", "dark"])
    base = {
        "wood": (150, 105, 65),
        "white": (225, 222, 215),
        "gray": (140, 140, 145),
        "dark": (50, 48, 52),
    }[kind]
    base = np.array([c + rng.randint(-20, 20) for c in base], dtype=np.float32)
    img = np.ones((SIZE, SIZE, 3), np.float32) * base
    # 조명 그라디언트
    gx = np.linspace(-1, 1, SIZE)[None, :, None] * rng.uniform(-25, 25)
    gy = np.linspace(-1, 1, SIZE)[:, None, None] * rng.uniform(-25, 25)
    img += gx + gy
    if kind == "wood":
        stripes = np.sin(np.linspace(0, rng.uniform(20, 60), SIZE))[:, None, None] * 10
        img += stripes
    # 테이블 끝선 (뒤쪽 벽)
    horizon = rng.randint(30, 110)
    img[:horizon] = img[:horizon] * rng.uniform(0.6, 1.2)
    img += np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, 4, img.shape)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def lerp(a, b, t):
    return a + (b - a) * t


def draw_glass(img: Image.Image, drink: str | None, level: float, rng: random.Random) -> Image.Image:
    w_top = rng.uniform(90, 140)
    h = rng.uniform(150, 220)
    w_bot = w_top * rng.uniform(0.65, 0.9)
    cx = SIZE / 2 + rng.uniform(-35, 35)
    bottom = SIZE - rng.uniform(25, 60)
    top = bottom - h
    base_th = rng.uniform(6, 14)  # 두꺼운 유리 바닥

    def x_at(y):  # y에서 잔 안쪽 반폭
        t = (bottom - y) / h
        return lerp(w_bot, w_top, t) / 2

    inner_bottom = bottom - base_th
    inner_h = inner_bottom - top

    # 원통형 물잔 = 수평 렌즈: 액체 구간 뒤 배경이 좌우 반전·확대돼 보인다
    if drink is not None and DRINKS[drink].get("refract") and level >= 0.05:
        liq_top = inner_bottom - inner_h * level
        x0, x1 = int(cx - w_top / 2), int(cx + w_top / 2)
        y0, y1 = int(liq_top), int(inner_bottom)
        region = img.crop((x0, y0, x1, y1))
        rw, rh = region.size
        zoom = rng.uniform(1.15, 1.4)
        big = region.resize((int(rw * zoom), rh), Image.BILINEAR)
        left = (big.width - rw) // 2
        region = big.crop((left, 0, left + rw, rh)).transpose(Image.FLIP_LEFT_RIGHT)
        region = ImageEnhance.Brightness(region.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 1.5)))).enhance(
            rng.uniform(1.0, 1.12))
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).polygon(
            [(cx - x_at(y0) + 2, y0), (cx + x_at(y0) - 2, y0), (cx + x_at(y1) - 2, y1), (cx - x_at(y1) + 2, y1)], fill=255)
        layer = img.copy()
        layer.paste(region, (x0, y0))
        img = Image.composite(layer, img, mask)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # 유리 몸체 (아주 옅은 틴트)
    body = [(cx - w_top / 2, top), (cx + w_top / 2, top), (cx + w_bot / 2, bottom), (cx - w_bot / 2, bottom)]
    d.polygon(body, fill=(230, 240, 245, rng.randint(18, 40)))

    if drink is not None:
        spec = DRINKS[drink]
        col = [max(0, min(255, c + rng.randint(-spec["jitter"], spec["jitter"]))) for c in spec["rgb"]]
        a = int(255 * rng.uniform(*spec["alpha"]))
        if level < 0.05:  # empty: 잔여 얇은 막
            a = int(a * rng.uniform(0.15, 0.4))
        liq_top = inner_bottom - inner_h * max(level, 0.012)
        # 세로 그라디언트 띠로 그려서 깊이감
        steps = 24
        for i in range(steps):
            y0 = lerp(liq_top, inner_bottom, i / steps)
            y1 = lerp(liq_top, inner_bottom, (i + 1) / steps)
            shade = 1.0 - 0.25 * (i / steps)
            c = tuple(int(v * shade) for v in col)
            d.polygon(
                [(cx - x_at(y0) + 2, y0), (cx + x_at(y0) - 2, y0), (cx + x_at(y1) - 2, y1), (cx - x_at(y1) + 2, y1)],
                fill=(*c, a),
            )
        # 메니스커스 (액체 윗면 타원)
        rx = x_at(liq_top) - 2
        ry = rng.uniform(3, 8)
        top_col = tuple(min(255, int(v * 1.25) + 10) for v in col)
        d.ellipse([cx - rx, liq_top - ry, cx + rx, liq_top + ry], fill=(*top_col, a))
        if spec.get("refract") and level >= 0.05:  # 물: 수면선이 밝게 반사
            d.ellipse([cx - rx, liq_top - ry, cx + rx, liq_top + ry], outline=(250, 252, 255, rng.randint(120, 220)),
                      width=rng.randint(1, 3))
        # 콜라 거품 / 기포
        if spec["foam"] and level > 0.05 and rng.random() < spec.get("foam_p", 0.6):
            fh = rng.uniform(3, 10)
            d.rectangle([cx - rx + 2, liq_top - fh, cx + rx - 2, liq_top], fill=(*spec["foam"], 200))
        if level > 0.05 and spec.get("bubbles", True):
            for _ in range(rng.randint(0, 25)):
                by = rng.uniform(liq_top + 5, inner_bottom - 2)
                bx = cx + rng.uniform(-x_at(by) + 6, x_at(by) - 6)
                br = rng.uniform(0.8, 2.2)
                d.ellipse([bx - br, by - br, bx + br, by + br], fill=(255, 255, 255, rng.randint(60, 140)))

    # 유리 테두리 + 바닥 + 하이라이트
    edge = (245, 248, 250, rng.randint(140, 220))
    lw = rng.randint(2, 3)
    d.line([body[0], body[3]], fill=edge, width=lw)
    d.line([body[1], body[2]], fill=edge, width=lw)
    d.line([body[3], body[2]], fill=edge, width=lw)
    d.ellipse([cx - w_top / 2, top - 6, cx + w_top / 2, top + 6], outline=edge, width=lw)
    d.rectangle([cx - w_bot / 2 + 2, inner_bottom, cx + w_bot / 2 - 2, bottom], fill=(235, 242, 245, 60))
    hx = cx - w_top / 2 + rng.uniform(10, 22)
    d.line([(hx, top + 12), (hx - 4, bottom - 15)], fill=(255, 255, 255, rng.randint(70, 150)), width=rng.randint(3, 7))

    # 그림자
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        [cx - w_bot / 2 - 10, bottom - 6, cx + w_bot / 2 + 25, bottom + 10], fill=(0, 0, 0, rng.randint(40, 90))
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(5))

    out = Image.alpha_composite(img.convert("RGBA"), shadow)
    out = Image.alpha_composite(out, overlay)
    return out.convert("RGB")


def photometric(img: Image.Image, rng: random.Random) -> Image.Image:
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.7, 1.25))
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.8, 1.2))
    img = ImageEnhance.Color(img).enhance(rng.uniform(0.8, 1.2))
    # 색온도
    arr = np.asarray(img).astype(np.float32)
    warm = rng.uniform(-15, 15)
    arr[..., 0] += warm
    arr[..., 2] -= warm
    arr += np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, rng.uniform(1, 6), arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    img = img.rotate(rng.uniform(-6, 6), resample=Image.BILINEAR, fillcolor=tuple(arr[5, 5].clip(0, 255).astype(int)))
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.3)))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--per-class", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    classes = [(d, lv) for d in DRINKS for lv in LEVELS if lv != "empty"] + [(None, "empty")]
    for drink, lvl in classes:
        name = "empty" if lvl == "empty" else f"{drink}__{lvl}"
        cdir = out / name
        cdir.mkdir(parents=True, exist_ok=True)
        for i in range(args.per_class):
            # empty: 깨끗한 잔 또는 음료 잔여막이 남은 잔
            dr = drink if drink else rng.choice([None, *DRINKS.keys()])
            level = rng.uniform(*LEVELS[lvl])
            img = draw_glass(background(rng), dr, level, rng)
            photometric(img, rng).save(cdir / f"{i:04d}.png")
        print(f"{name}: {args.per_class}")


if __name__ == "__main__":
    main()
