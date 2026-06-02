"""Статический скан артефактов моделей — БЕЗ десериализации (SUP-01).

`pickletools.genops` разбирает байткод pickle, НИКОГДА не вызывая pickle.load,
поэтому payload не исполняется. Ловим обращения к опасным глобалам
(os/subprocess/...) — классический pickle-RCE через __reduce__/__setstate__.

Это намеренно простой собственный сканер: его задача — поймать очевидный
pickle-RCE на приёме. Он не претендует на полноту (ShadowLogic, отравление
весов — остаточные риски, см. SUP-06), но честно делает то, что заявляет.
"""
import ast
import json
import pickletools
import re
import struct

DANGEROUS_MODULES = {
    "os", "posix", "nt", "subprocess", "sys", "shutil", "socket", "ctypes",
    "builtins", "__builtin__", "commands", "pty", "platform", "multiprocessing",
    "webbrowser", "importlib", "runpy", "code", "codeop", "operator",
}
DANGEROUS_CALLABLES = {
    "system", "popen", "exec", "eval", "compile", "spawn", "spawnl", "spawnv",
    "fork", "call", "Popen", "check_output", "check_call", "run", "getattr",
    "__import__", "execfile", "loads", "connect", "create_connection",
}
_STRING_OPS = {"SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "UNICODE",
               "SHORT_BINSTRING", "BINSTRING", "STRING"}


def _is_dangerous(module: str, name: str) -> bool:
    return module.split(".")[0] in DANGEROUS_MODULES or name in DANGEROUS_CALLABLES


def _scan_pickle_genops(data: bytes):
    """Собственный genops-скан (baseline/fallback): находки [{module,name,opcode}]."""
    findings, recent = [], []
    try:
        for opcode, arg, _pos in pickletools.genops(data):
            nm = opcode.name
            if nm in _STRING_OPS:
                recent.append(arg)
                del recent[:-4]
            elif nm == "GLOBAL":                        # proto 0-1: arg = "module name"
                module, _, name = (arg or "").partition(" ")
                if _is_dangerous(module, name):
                    findings.append({"module": module, "name": name, "opcode": "GLOBAL"})
            elif nm == "STACK_GLOBAL":                   # proto 2+: module/name со стека
                if len(recent) >= 2:
                    module, name = str(recent[-2]), str(recent[-1])
                    if _is_dangerous(module, name):
                        findings.append({"module": module, "name": name, "opcode": "STACK_GLOBAL"})
    except Exception as e:                               # битый/не-pickle — подозрительно
        findings.append({"module": "?", "name": f"parse-error: {e}", "opcode": "ERROR"})
    return findings


def _picklescan_scan(data: bytes):
    """Реальный сканер picklescan (ядро modelscan). None, если недоступен/ошибся."""
    try:
        from picklescan.scanner import scan_file_path
    except Exception:
        return None
    import os as _os
    import tempfile
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            f.write(data)
            path = f.name
        res = scan_file_path(path)
    except Exception:
        return None
    finally:
        if path:
            try:
                _os.unlink(path)
            except Exception:
                pass
    hits = []
    for g in getattr(res, "globals", None) or []:
        safety = str(getattr(g, "safety", "")).lower()
        if "dangerous" in safety:  # только Dangerous → блок; Suspicious — домен нашей эвристики (VIS-02)
            hits.append({"module": getattr(g, "module", "?"), "name": getattr(g, "name", "?"), "opcode": "picklescan"})
    if not hits and getattr(res, "infected_files", 0):
        hits.append({"module": "?", "name": "picklescan flagged", "opcode": "picklescan"})
    return hits


def scan_pickle(data: bytes):
    """Скан pickle БЕЗ исполнения: собственный genops-baseline ∪ picklescan (если есть).
    Объединение = defense-in-depth; зелёные тесты держатся на baseline, реальный тул добавляет."""
    hits = _scan_pickle_genops(data)
    ps = _picklescan_scan(data)
    if ps:
        seen = {(h["module"], h["name"], h["opcode"]) for h in hits}
        hits = hits + [h for h in ps if (h["module"], h["name"], h["opcode"]) not in seen]
    return hits


_CODE_OPS = {"GLOBAL", "STACK_GLOBAL", "REDUCE", "INST", "OBJ", "NEWOBJ", "NEWOBJ_EX", "BUILD"}


def scan_heuristic(data: bytes):
    """Второй, намеренно «параноидальный» сканер: любой код-несущий опкод.

    Шумнее, чем scan_pickle (флагует и обращения к безопасным модулям) — нужен,
    чтобы вердикты инструментов могли расходиться (VIS-02): один считает чистым,
    другой — подозрительным, оба видны, фолз триажится."""
    try:
        return sorted({op.name for op, _arg, _pos in pickletools.genops(data) if op.name in _CODE_OPS})
    except Exception:
        return ["parse-error"]


def detect_format(data: bytes) -> str:
    """Классификация формата по сигнатуре: safetensors | pickle | unknown."""
    if len(data) >= 8:
        try:
            n = struct.unpack("<Q", data[:8])[0]
            if 0 < n <= len(data) - 8:
                header = data[8:8 + n].decode("utf-8")
                if header.lstrip().startswith("{"):
                    json.loads(header)
                    return "safetensors"
        except Exception:
            pass
    try:
        for _ in pickletools.genops(data):
            pass
        return "pickle"
    except Exception:
        return "unknown"


def assess_artifact(data: bytes, criticality: str = "internal"):
    """Оценка артефакта на приёме: формат + опасные опкоды + политика форматов.

    Возвращает {format, findings:[...], admit:bool}.
    - SUP-01: вредоносный pickle (опасные опкоды) блокируется всегда.
    - SUP-07: для критичных моделей (regulatory/financial) формат с произвольным
      кодом (pickle) отклоняется — безопасная автоконверсия в safetensors без
      десериализации невозможна (fail-closed). Для прочих чистый pickle допускается.
    - Неизвестный формат — fail-closed.
    """
    fmt = detect_format(data)
    findings, admit = [], True
    if fmt == "pickle":
        hits = scan_pickle(data)
        if hits:
            findings.append({"tool": "sirius-pickle-scan", "verdict": "malicious", "severity": "critical",
                             "detail": "; ".join(f"{h['opcode']} {h['module']}.{h['name']}" for h in hits)})
            admit = False
        else:
            susp = scan_heuristic(data)
            if susp:  # код-несущий опкод без опасных модулей → подозрительно, но не блокируем (VIS-02)
                findings.append({"tool": "sirius-heuristic-scan", "verdict": "suspicious", "severity": "medium",
                                 "detail": f"код-несущие опкоды {susp}; опасных модулей не найдено — требует триажа (возможен фолз)"})
        if criticality in ("regulatory", "financial"):
            findings.append({"tool": "sirius-format-policy", "verdict": "unsafe-format", "severity": "high",
                             "detail": f"формат pickle недопустим для критичности '{criticality}': требуется safetensors (convert-or-reject)"})
            admit = False
    elif fmt == "unknown":
        findings.append({"tool": "sirius-format-policy", "verdict": "unknown-format", "severity": "medium",
                         "detail": "неизвестный/неподдерживаемый формат артефакта"})
        admit = False
    return {"format": fmt, "findings": findings, "admit": admit}


_CODE_DANGEROUS_NAMES = {"eval", "exec", "compile", "__import__"}
_CODE_DANGEROUS_ATTRS = {
    ("os", "system"), ("os", "popen"), ("os", "remove"), ("os", "unlink"),
    ("subprocess", "call"), ("subprocess", "Popen"), ("subprocess", "run"),
    ("subprocess", "check_output"), ("subprocess", "check_call"),
    ("pickle", "loads"), ("pickle", "load"), ("marshal", "loads"), ("yaml", "load"),
}


def _extract_code(src: str, filename: str) -> str:
    if filename.endswith(".ipynb"):
        try:
            nb = json.loads(src)
            return "\n".join("".join(c.get("source", [])) for c in nb.get("cells", []) if c.get("cell_type") == "code")
        except Exception:
            return src
    return src


def _scan_code_ast(src: str):
    """Собственный AST-SAST (baseline): опасные вызовы. Код НЕ исполняется (только ast.parse)."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [{"tool": "sirius-code-scan", "verdict": "parse-error", "severity": "low",
                 "detail": f"не разобрать как Python: {e}"}]
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id in _CODE_DANGEROUS_NAMES:
            hits.append(f"{fn.id}() @стр{node.lineno}")
        elif isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) \
                and (fn.value.id, fn.attr) in _CODE_DANGEROUS_ATTRS:
            hits.append(f"{fn.value.id}.{fn.attr}() @стр{node.lineno}")
    if not hits:
        return []
    return [{"tool": "sirius-code-scan", "verdict": "insecure-code", "severity": "high", "detail": "; ".join(hits)}]


_TRIVIAL_NUMS = {-2, -1, 0, 1, 2}  # индексы/счётчики/флаги — не бизнес-пороги


def _scan_hardcoded_logic(src: str):
    """ACC-07: захардкоженные числовые пороги в условной логике (бизнес-правила в коде).

    Сравнение переменной с НЕтривиальным числовым литералом (`if score > 0.75`,
    `if amount >= 1000000`) — кандидат на вынос в конфиг/policy, а не зашитый в код.
    Арифметику (`x * 2`) и сравнения с именованными константами (`!= FEATURES`) НЕ трогаем."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left, *node.comparators]:
            if (isinstance(operand, ast.Constant) and isinstance(operand.value, (int, float))
                    and not isinstance(operand.value, bool) and operand.value not in _TRIVIAL_NUMS):
                hits.append(f"порог {operand.value!r} @стр{node.lineno}")
    if not hits:
        return []
    return [{"tool": "sirius-policy-scan", "verdict": "hardcoded-logic", "severity": "medium",
             "detail": "захардкоженные бизнес-пороги (" + "; ".join(sorted(set(hits))) + ") — вынести в конфиг/policy, review-гейт"}]


def _semgrep_scan(src: str):
    """Реальный Semgrep с локальными офлайн-правилами. None, если недоступен/ошибся."""
    import os as _os
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("semgrep"):
        return None
    rules = _os.path.join(_os.path.dirname(__file__), "semgrep_rules.yml")
    if not _os.path.exists(rules):
        return None
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(src)
            path = f.name
        env = {**_os.environ, "SEMGREP_ENABLE_VERSION_CHECK": "0", "SEMGREP_SEND_METRICS": "off"}
        out = subprocess.run(["semgrep", "scan", "--config", rules, "--json", "--quiet", "--no-git-ignore",
                              "--metrics=off", "--disable-version-check", path],
                             capture_output=True, text=True, timeout=120, env=env)
        data = json.loads(out.stdout or "{}")
        findings = []
        for r in data.get("results", []):
            msg = r.get("extra", {}).get("message", r.get("check_id", "semgrep"))
            ln = r.get("start", {}).get("line", "?")
            findings.append({"tool": "semgrep", "verdict": "insecure-code", "severity": "high", "detail": f"{msg} @стр{ln}"})
        return findings
    except Exception:
        return None
    finally:
        if path:
            try:
                _os.unlink(path)
            except Exception:
                pass


def scan_code(src: str, filename: str = "submitted.py"):
    """ML-aware SAST: собственный AST-baseline ∪ реальный Semgrep (если доступен).
    Код НЕ исполняется. Поддерживает .ipynb (код-ячейки)."""
    code = _extract_code(src, filename)
    findings = _scan_code_ast(code) + _scan_hardcoded_logic(code)  # AST-RCE + ACC-07 пороги
    sg = _semgrep_scan(code)
    if sg:
        seen = {f["detail"] for f in findings}
        findings = findings + [f for f in sg if f["detail"] not in seen]
    return findings


# Крошечная встроенная база известно уязвимых пинов (демо; в проде — pip-audit/OSV/Trivy)
KNOWN_VULNERABLE = {
    "pyyaml": {"5.3.1": "CVE-2020-14343 (RCE через yaml.load)", "5.3": "CVE-2020-14343"},
    "requests": {"2.19.0": "CVE-2018-18074 (утечка Authorization при редиректе)"},
    "flask": {"0.12.2": "CVE-2018-1000656 (DoS)"},
    "jinja2": {"2.10": "CVE-2019-10906 (sandbox escape)"},
    "urllib3": {"1.24.1": "CVE-2019-11324 (обход проверки сертификата)"},
    "numpy": {"1.16.0": "CVE-2019-6446 (небезопасный pickle в np.load)"},
}


# Имя-ориентированные supply-chain эвристики (SUP-02/SUP-08).
# POPULAR — allow-list известных пакетов (вкл. собственные зависимости платформы),
# чтобы не флагать легитимное; typosquat срабатывает на «почти-имя» вне списка.
_POPULAR_PACKAGES = {
    # зависимости платформы (SC-01 — собственные requirements должны быть чисты)
    "fastapi", "uvicorn", "starlette", "sqlalchemy", "psycopg2-binary", "psycopg2",
    "pyjwt", "requests", "jinja2", "redis", "prometheus-client", "picklescan",
    "detect-secrets", "semgrep", "setuptools", "pip-audit", "httpx", "pydantic",
    # широко используемые (топ PyPI)
    "numpy", "pandas", "scipy", "scikit-learn", "sklearn", "matplotlib", "flask",
    "django", "torch", "tensorflow", "keras", "boto3", "botocore", "urllib3",
    "certifi", "click", "pytest", "pyyaml", "pillow", "cryptography", "aiohttp",
    "celery", "gunicorn", "wheel", "pip", "six", "python-dateutil", "packaging",
    "typing-extensions", "attrs", "idna", "charset-normalizer", "markupsafe",
    "werkzeug", "itsdangerous", "greenlet", "anyio", "transformers", "xgboost",
    "lightgbm", "joblib", "threadpoolctl", "mlflow", "minio",
}
_INTERNAL_PREFIXES = ("sirius-", "sirius_")  # внутренние пакеты платформы


def _req_name(line: str) -> str:
    """Имя пакета из строки requirements (без версии/экстры/опций)."""
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        return ""
    m = re.match(r"[A-Za-z0-9._-]+", line)
    return (m.group(0) if m else "").lower().replace("_", "-")


def _edit_distance_le1(a: str, b: str) -> bool:
    """True, если между a и b одна правка по Дамерау-Левенштейну: замена/вставка/удаление
    ИЛИ транспозиция соседних символов (`reqeusts`↔`requests`) — типичный тайпсквоттинг."""
    if a == b:
        return False
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:                        # одна замена
            return True
        return (len(diffs) == 2 and diffs[1] == diffs[0] + 1      # транспозиция соседних (Дамерау)
                and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]])
    if la > lb:                                    # нормализуем: a короче
        a, b, la, lb = b, a, lb, la
    i = j = diff = 0                               # одна вставка/удаление
    while i < la and j < lb:
        if a[i] != b[j]:
            diff += 1
            if diff > 1:
                return False
            j += 1
        else:
            i += 1
            j += 1
    return True


def _scan_deps_supply(requirements_text: str):
    """SUP-02 (typosquat) + SUP-08 (dependency confusion) — имя-ориентированные эвристики."""
    findings = []
    for raw in requirements_text.splitlines():
        name = _req_name(raw)
        if not name:
            continue
        line = raw.split("#", 1)[0].strip()
        if any(name.startswith(p) for p in _INTERNAL_PREFIXES) and "==" not in line:  # SUP-08
            findings.append({"tool": "sirius-dep-scan", "verdict": "dependency-confusion", "severity": "high",
                             "detail": f"{name}: внутренний пакет без пина — риск подмены публичным (dependency confusion); закрепить версию + внутренний индекс"})
            continue
        if name in _POPULAR_PACKAGES:
            continue
        for k in _POPULAR_PACKAGES:                                                     # SUP-02
            if len(k) >= 4 and _edit_distance_le1(name, k):
                findings.append({"tool": "sirius-dep-scan", "verdict": "typosquat-dependency", "severity": "high",
                                 "detail": f"{name}: тайпсквоттинг — в одной правке от '{k}' (allow-list + пины зависимостей)"})
                break
    return findings


def _scan_deps_db(requirements_text: str):
    """Собственная офлайн-база известных CVE (baseline, без egress)."""
    findings = []
    for raw in requirements_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "==" not in line:
            continue
        pkg, _, ver = line.partition("==")
        bad = KNOWN_VULNERABLE.get(pkg.strip().lower(), {})
        if ver.strip() in bad:
            findings.append({"tool": "sirius-dep-scan", "verdict": "vulnerable-dependency", "severity": "high",
                             "detail": f"{pkg.strip()}=={ver.strip()}: {bad[ver.strip()]}"})
    return findings


def _pip_audit_scan(requirements_text: str):
    """Реальный pip-audit (OSV). None, если недоступен или нет egress (internal-сеть).
    Работает при наличии сети (например, в CI); в офлайн-демо — фолбэк на базу."""
    import os as _os
    import shutil
    import subprocess
    import tempfile
    if _os.environ.get("DEPS_AUDIT_ONLINE") != "1":
        return None  # офлайн по умолчанию: не вешаем запрос на сетевой таймаут OSV (вкл. флагом в CI/egress)
    if not shutil.which("pip-audit"):
        return None
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write(requirements_text)
            path = f.name
        out = subprocess.run(["pip-audit", "-r", path, "--format", "json", "--progress-spinner", "off"],
                             capture_output=True, text=True, timeout=60)
        data = json.loads(out.stdout or "{}")
        deps = data.get("dependencies", data) if isinstance(data, dict) else data
        findings = []
        for dep in (deps or []):
            for v in dep.get("vulns", []) or []:
                findings.append({"tool": "pip-audit", "verdict": "vulnerable-dependency", "severity": "high",
                                 "detail": f"{dep.get('name')}=={dep.get('version')}: {v.get('id')}"})
        return findings
    except Exception:
        return None
    finally:
        if path:
            try:
                _os.unlink(path)
            except Exception:
                pass


def scan_dependencies(requirements_text: str):
    """SUP-03/SC-01: офлайн-база CVE (baseline) ∪ pip-audit/OSV (реальный, при egress);
    плюс имя-ориентированные SUP-02 (typosquat) и SUP-08 (dependency confusion)."""
    findings = _scan_deps_db(requirements_text) + _scan_deps_supply(requirements_text)
    pa = _pip_audit_scan(requirements_text)
    if pa:
        seen = {f["detail"] for f in findings}
        findings = findings + [f for f in pa if f["detail"] not in seen]
    return findings


_SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"ghp_[0-9A-Za-z]{36}"), "GitHub token"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"""(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['"][^'"]{6,}['"]"""), "hardcoded secret"),
]


def _scan_secrets_regex(text: str):
    """Собственный regex-скан секретов (baseline/fallback)."""
    findings = []
    for pat, label in _SECRET_PATTERNS:
        if pat.search(text):
            findings.append({"tool": "sirius-secret-scan", "verdict": "secret-exposed", "severity": "high",
                             "detail": label})
    return findings


def _detect_secrets_scan(text: str):
    """Реальный сканер Yelp detect-secrets. None, если недоступен/ошибся.

    Берём только ТОЧНЫЕ детекторы (ключевые слова/AWS/private-key); энтропийные
    (Base64/Hex High Entropy) отключены — они шумят на обычном коде."""
    try:
        from detect_secrets.core import scan as ds_scan
        from detect_secrets.settings import transient_settings
    except Exception:
        return None
    plugins = [{"name": n} for n in ("KeywordDetector", "AWSKeyDetector", "PrivateKeyDetector")]
    try:
        out = []
        with transient_settings({"plugins_used": plugins}):
            for ln, line in enumerate(text.splitlines(), 1):
                for s in ds_scan.scan_line(line):
                    out.append({"tool": "detect-secrets", "verdict": "secret-exposed", "severity": "high",
                                "detail": f"{getattr(s, 'type', 'secret')} @стр{ln}"})
        return out
    except Exception:
        return None


def scan_secrets(text: str):
    """ACC-06: секреты в коде/коммите — собственный regex-baseline ∪ detect-secrets (если есть)."""
    out = _scan_secrets_regex(text)
    ds = _detect_secrets_scan(text)
    if ds:
        seen = {f["detail"] for f in out}
        out = out + [f for f in ds if f["detail"] not in seen]
    return out


# ---------- Качество/целостность данных: DATA-02/03/05 + FB-01 (scoped-детекторы) ----------
# Без реального датасета — поверх статистик/сэмплов/провенанса из payload. Честно scoped:
# демонстрируют ПОВЕДЕНИЕ контроля (аномалия → Finding → карантин), не претендуя на полноту.
_ZERO_WIDTH = ("​", "‌", "‍", "﻿", "⁠")
_TRUSTED_PROVENANCE = {"verified", "curated", "internal", "trusted"}


def scan_dataset(payload: dict):
    """DATA-02 label-flip, DATA-03 UGC-бэкдор-триггер, DATA-05 train-serve skew, FB-01 провенанс петли."""
    findings = []
    # DATA-02: подмена меток поставщиком — метка вне словаря или сдвиг распределения от baseline
    labels = [str(x) for x in (payload.get("labels") or [])]
    expected = {str(x) for x in (payload.get("expected_labels") or [])}
    baseline = payload.get("baseline_dist") or {}
    if labels:
        oov = sorted(set(labels) - expected) if expected else []
        if oov:
            findings.append({"tool": "sirius-data-scan", "verdict": "label-flip", "severity": "high",
                             "detail": f"метки вне словаря: {oov} — подмена меток поставщиком (DATA-02)"})
        elif baseline:
            n = len(labels)
            dist = {k: labels.count(k) / n for k in set(labels) | set(baseline)}
            shifted = sorted(k for k, b in baseline.items() if abs(dist.get(k, 0.0) - b) > 0.3)
            if shifted:
                findings.append({"tool": "sirius-data-scan", "verdict": "label-flip", "severity": "high",
                                 "detail": f"сдвиг распределения меток {shifted} > 0.3 от baseline — возможный label-flip (DATA-02)"})
    # DATA-03: UGC-бэкдор-триггер — невидимые/управляющие символы в сэмплах → карантин
    trig = [i for i, s in enumerate(payload.get("samples") or []) if any(z in str(s) for z in _ZERO_WIDTH)]
    if trig:
        findings.append({"tool": "sirius-data-scan", "verdict": "backdoor-trigger", "severity": "high",
                         "detail": f"невидимые символы-триггеры в сэмплах #{trig} — UGC-бэкдор, карантин (DATA-03)"})
    # DATA-05: train-serving skew — расхождение средних признаков train vs serve
    tr, sv = payload.get("train_stats") or {}, payload.get("serve_stats") or {}
    if tr and sv:
        skew = sorted(k for k in tr if k in sv
                      and abs(float(sv[k]) - float(tr[k])) / (abs(float(tr[k])) + 1e-9) > 0.5)
        if skew:
            findings.append({"tool": "sirius-data-scan", "verdict": "train-serve-skew", "severity": "medium",
                             "detail": f"признаки {skew} расходятся train↔serve > 50% — обучение≠инференс (DATA-05)"})
    # FB-01: отравление петли дообучения — фидбек без доверенного провенанса
    fb = payload.get("feedback") or []
    untrusted = [i for i, e in enumerate(fb)
                 if str((e or {}).get("provenance", "")).lower() not in _TRUSTED_PROVENANCE]
    if fb and untrusted:
        findings.append({"tool": "sirius-data-scan", "verdict": "feedback-poisoning", "severity": "high",
                         "detail": f"фидбек без доверенного провенанса #{untrusted} — отравление петли дообучения (FB-01)"})
    return findings
