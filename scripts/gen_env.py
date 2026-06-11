#!/usr/bin/env python3
"""Генерит .env из .env.example: ПУСТЫЕ секрето-значения заполняет случайными (dev).
Существующие значения в .env сохраняет (идемпотентно — добавляет только недостающее).

Зачем: секреты НЕ коммитятся в репозиторий (.env в .gitignore; в docker-compose дефолтов нет).
`make up` без `make secrets` не поднимется — это by design. Прод — .env.production + секрет-стор/KMS.
"""
import os
import secrets

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ex = os.path.join(root, ".env.example")
env = os.path.join(root, ".env")

have = {}
if os.path.exists(env):
    for line in open(env):
        s = line.rstrip("\n")
        if s.strip().startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if v.strip():
            have[k.strip()] = v

out, filled = [], 0
for line in open(ex):
    raw = line.rstrip("\n")
    if raw.strip().startswith("#") or "=" not in raw:
        out.append(raw)
        continue
    k, _, v = raw.partition("=")
    k = k.strip()
    if k in have:
        v = have[k]                      # сохранить уже заданное в .env
    elif not v.strip():
        v = secrets.token_hex(24)        # пустой секрет → случайный
        filled += 1
    out.append(f"{k}={v}")

with open(env, "w") as f:
    f.write("\n".join(out) + "\n")
os.chmod(env, 0o600)
print(f".env готов: заполнено случайными секретов — {filled}; существующие сохранены (права 600).")
