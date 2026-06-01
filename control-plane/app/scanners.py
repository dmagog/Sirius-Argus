"""Статический скан артефактов моделей — БЕЗ десериализации (SUP-01).

`pickletools.genops` разбирает байткод pickle, НИКОГДА не вызывая pickle.load,
поэтому payload не исполняется. Ловим обращения к опасным глобалам
(os/subprocess/...) — классический pickle-RCE через __reduce__/__setstate__.

Это намеренно простой собственный сканер: его задача — поймать очевидный
pickle-RCE на приёме. Он не претендует на полноту (ShadowLogic, отравление
весов — остаточные риски, см. SUP-06), но честно делает то, что заявляет.
"""
import json
import pickletools
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


def scan_pickle(data: bytes):
    """Находки [{module,name,opcode}]; пусто = чисто. Артефакт НЕ исполняется."""
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
