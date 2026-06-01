"""Статический скан артефактов моделей — БЕЗ десериализации (SUP-01).

`pickletools.genops` разбирает байткод pickle, НИКОГДА не вызывая pickle.load,
поэтому payload не исполняется. Ловим обращения к опасным глобалам
(os/subprocess/...) — классический pickle-RCE через __reduce__/__setstate__.

Это намеренно простой собственный сканер: его задача — поймать очевидный
pickle-RCE на приёме. Он не претендует на полноту (ShadowLogic, отравление
весов — остаточные риски, см. SUP-06), но честно делает то, что заявляет.
"""
import pickletools

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


def scan_artifact(data: bytes, filename: str = "artifact"):
    """Прогон артефакта через сканеры → список результатов по инструментам.

    Сейчас один инструмент `sirius-pickle-scan`; модель findings рассчитана на
    несколько инструментов (для расхождения вердиктов и триажа — VIS-02/VIS-04).
    """
    hits = scan_pickle(data)
    detail = "; ".join(f"{h['opcode']} {h['module']}.{h['name']}" for h in hits) or "опасных опкодов нет"
    return [{
        "tool": "sirius-pickle-scan",
        "verdict": "malicious" if hits else "clean",
        "severity": "critical" if hits else "info",
        "detail": detail,
    }]
