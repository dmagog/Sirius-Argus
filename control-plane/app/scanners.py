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


def scan_code(src: str, filename: str = "submitted.py"):
    """ML-aware SAST на ast: опасные вызовы в коде/ноутбуке. Код НЕ исполняется —
    только разбирается в AST. Pattern-based MVP; полный Semgrep-гейт на PR — в И3.
    Возвращает список находок ([] = чисто)."""
    if filename.endswith(".ipynb"):
        try:
            nb = json.loads(src)
            src = "\n".join("".join(c.get("source", [])) for c in nb.get("cells", []) if c.get("cell_type") == "code")
        except Exception:
            pass
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
    return [{"tool": "sirius-code-scan", "verdict": "insecure-code", "severity": "high",
             "detail": "; ".join(hits)}]


# Крошечная встроенная база известно уязвимых пинов (демо; в проде — pip-audit/OSV/Trivy)
KNOWN_VULNERABLE = {
    "pyyaml": {"5.3.1": "CVE-2020-14343 (RCE через yaml.load)", "5.3": "CVE-2020-14343"},
    "requests": {"2.19.0": "CVE-2018-18074 (утечка Authorization при редиректе)"},
    "flask": {"0.12.2": "CVE-2018-1000656 (DoS)"},
    "jinja2": {"2.10": "CVE-2019-10906 (sandbox escape)"},
    "urllib3": {"1.24.1": "CVE-2019-11324 (обход проверки сертификата)"},
    "numpy": {"1.16.0": "CVE-2019-6446 (небезопасный pickle в np.load)"},
}


def scan_dependencies(requirements_text: str):
    """SUP-03/SC-01: проверка пинов из requirements против базы известных CVE.
    Возвращает список находок ([] = чисто)."""
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
