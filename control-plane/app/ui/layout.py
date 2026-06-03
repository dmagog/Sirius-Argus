"""ui.layout — каркас: _page, навигация, бейджи, _e/_card."""
import html


_CDN = ('<script src="https://cdn.tailwindcss.com"></script>'
        '<script src="https://unpkg.com/htmx.org@2.0.3"></script>')


_STYLE = (
    "<style>"
    "@keyframes siriusPulse{"
    "0%,100%{box-shadow:0 0 3px 1px rgba(250,204,21,.20);transform:scale(1)}"
    "50%{box-shadow:0 0 9px 3px rgba(250,204,21,.45);transform:scale(1.04)}}"
    ".sirius-badge{background:radial-gradient(circle at 50% 45%,rgba(248,250,252,.30) 0%,rgba(226,232,240,.12) 60%,rgba(226,232,240,0) 100%);"
    "animation:siriusPulse 5.2s ease-in-out infinite}"
    "@media(prefers-reduced-motion:reduce){.sirius-badge{animation:none}}"
    "</style>"
)


# Клиентская сортировка ЛЮБОЙ таблицы по клику на заголовок столбца (числа/текст, asc↔desc).
# Вешается на все <table> страницы и на таблицы, подгружаемые через HTMX (htmx:afterSwap).
_SORT_JS = """<script>
(function(){
  function num(v){var n=parseFloat(String(v).replace(/[\\s\\u00a0]/g,'').replace(',','.'));return isNaN(n)?null:n;}
  function sortable(scope){
    (scope||document).querySelectorAll('table').forEach(function(t){
      if(t.dataset.srt)return; t.dataset.srt='1';
      var ths=t.querySelectorAll('thead th');
      ths.forEach(function(th,i){
        th.style.cursor='pointer'; th.style.userSelect='none'; if(!th.title)th.title='сортировать';
        th.addEventListener('click',function(){
          var tb=t.querySelector('tbody'); if(!tb)return;
          var rows=Array.prototype.slice.call(tb.children).filter(function(r){return r.tagName==='TR';});
          var asc=th.dataset.asc!=='1';
          ths.forEach(function(o){o.dataset.asc='';var s=o.querySelector('.srt-i');if(s)s.remove();});
          th.dataset.asc=asc?'1':'';
          rows.sort(function(a,b){
            var ca=a.children[i],cb=b.children[i];
            var x=ca?ca.innerText.trim():'', y=cb?cb.innerText.trim():'';
            var nx=num(x),ny=num(y),c;
            if(nx!==null&&ny!==null)c=nx-ny; else c=x.localeCompare(y,'ru',{numeric:true});
            return asc?c:-c;
          });
          rows.forEach(function(r){tb.appendChild(r);});
          var ind=document.createElement('span'); ind.className='srt-i'; ind.textContent=asc?' \\u25b2':' \\u25bc'; th.appendChild(ind);
        });
      });
    });
  }
  sortable(document);
  if(document.body)document.body.addEventListener('htmx:afterSwap',function(e){sortable(e.target);});
})();
</script>"""


# Тёмная SOC-консоль: палитра-токены + сайдбар + re-skin Tailwind-утилит через CSS-слой
# (тёмные карточки/таблицы/бейджи без правки каждой страницы). Акцент — золото под лого.
_THEME = """<style>
:root{--bg:#0b1220;--panel:#111a2e;--panel2:#0e1626;--line:#1f2a44;--text:#cbd5e1;--text2:#94a3b8;--muted:#64748b;--head:#f1f5f9;--accent:#facc15;}
body{background:var(--bg)!important;color:var(--text)!important;font-family:'Inter',ui-sans-serif,system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased;}
table{font-variant-numeric:tabular-nums;}
h1,h2,h3{color:var(--head);}
.app-shell{display:flex;min-height:100vh;}
.app-main{flex:1;min-width:0;max-width:1180px;margin:0 auto;padding:26px 32px;}
.sb{width:236px;flex-shrink:0;background:#0a111f;border-right:1px solid var(--line);display:flex;flex-direction:column;position:sticky;top:0;height:100vh;}
.sb-brand{display:flex;align-items:center;gap:.6rem;padding:18px 16px 14px;border-bottom:1px solid var(--line);color:var(--head);text-decoration:none;}
.sb-brand .sirius-badge{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:999px;flex-shrink:0;}
.sb-logo{width:32px;height:32px;}
.sb-title{display:flex;flex-direction:column;line-height:1.05;font-weight:700;letter-spacing:.3px;font-size:15px;}
.sb-title small{font-weight:500;font-size:9px;letter-spacing:1.6px;text-transform:uppercase;color:var(--text2);margin-top:2px;}
.sb-nav{display:flex;flex-direction:column;gap:2px;padding:12px 10px;overflow-y:auto;}
.sb-link{display:flex;align-items:center;padding:9px 12px;border-radius:8px;color:var(--text2);font-size:.9rem;font-weight:500;text-decoration:none;transition:background .15s,color .15s;}
.sb-link:hover{background:#16203a;color:var(--head);}
.sb-active{background:#172339;color:#fff;box-shadow:inset 3px 0 0 var(--accent);}
.sb-foot{margin-top:auto;padding:14px 16px;border-top:1px solid var(--line);}
.env-chip{font-size:11px;color:var(--text2);border:1px solid var(--line);border-radius:999px;padding:3px 10px;}
/* re-skin Tailwind-утилит под тёмное */
.bg-white{background:var(--panel)!important;}
.bg-slate-50{background:var(--panel2)!important;}
.bg-slate-100{background:#1b2740!important;}
.bg-slate-200{background:#28344f!important;}
.bg-slate-900{background:#293548!important;}
.border-slate-100,.border-slate-200,.border-slate-300{border-color:var(--line)!important;}
.shadow-sm,.shadow{box-shadow:0 1px 2px rgba(0,0,0,.45)!important;}
.text-slate-800,.text-slate-600{color:var(--text)!important;}
.text-slate-900{color:var(--head)!important;}
.text-slate-500{color:var(--text2)!important;}
.text-slate-400{color:var(--muted)!important;}
.text-red-600{color:#f87171!important;}.text-emerald-600{color:#34d399!important;}
.text-amber-600{color:#fbbf24!important;}.text-orange-600{color:#fb923c!important;}
.text-sky-600{color:var(--accent)!important;}
.hover\\:bg-slate-50:hover,.hover\\:bg-slate-100:hover{background:#16203a!important;}
.bg-red-100{background:rgba(239,68,68,.16)!important;}.text-red-700{color:#fca5a5!important;}
.bg-orange-100{background:rgba(249,115,22,.16)!important;}.text-orange-700{color:#fdba74!important;}
.bg-amber-100{background:rgba(245,158,11,.16)!important;}.text-amber-700{color:#fcd34d!important;}
.bg-sky-100{background:rgba(56,189,248,.16)!important;}.text-sky-700{color:#7dd3fc!important;}
.bg-emerald-100{background:rgba(16,185,129,.16)!important;}.text-emerald-700{color:#6ee7b7!important;}
.bg-violet-100{background:rgba(139,92,246,.16)!important;}.text-violet-700{color:#c4b5fd!important;}
code{color:#e2e8f0;}
</style>"""


_SEV = {
    "critical": "bg-red-100 text-red-700", "high": "bg-orange-100 text-orange-700",
    "medium": "bg-amber-100 text-amber-700", "low": "bg-slate-100 text-slate-600",
    "info": "bg-slate-100 text-slate-500",
}


_STATUS = {
    "open": "bg-amber-100 text-amber-700", "triaged": "bg-sky-100 text-sky-700",
    "TP": "bg-red-100 text-red-700", "FP": "bg-slate-200 text-slate-500",
}


_CRIT = {
    "regulatory": "bg-red-100 text-red-700", "financial": "bg-orange-100 text-orange-700",
    "internal": "bg-slate-100 text-slate-600",
}


_STAGE = {
    "prod": "bg-emerald-100 text-emerald-700", "dev": "bg-sky-100 text-sky-700",
    "retired": "bg-slate-200 text-slate-500",
}


def _e(s):
    return html.escape(str(s if s is not None else ""))


_NAV = (
    ("/map", "Пайплайн", "map"),
    ("/", "Дашборд", "dashboard"),
    ("/registry", "Реестр", "registry"),
    ("/findings", "Сработки", "findings"),
    ("/coverage", "Карта покрытия", "coverage"),
    ("/serving", "Сервинг", "serving"),
    ("/services", "Сервисы", "services"),
    ("/roles", "Роли (RBAC)", "roles"),
)


def _page(title, body, nav="dashboard"):
    def link(href, label, key):
        active = " sb-active" if key == nav else ""
        return f'<a class="sb-link{active}" href="{href}">{_e(label)}</a>'
    nav_html = "".join(link(h, l, k) for h, l, k in _NAV)
    return (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title>"
        "<link rel=icon type=image/png href='/static/avatar.png'>"
        "<link rel=preconnect href='https://fonts.googleapis.com'>"
        "<link rel=preconnect href='https://fonts.gstatic.com' crossorigin>"
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap' rel=stylesheet>"
        f"{_CDN}{_STYLE}{_THEME}</head>"
        "<body>"
        "<div class='app-shell'>"
        "<aside class='sb'>"
        "<a href='/map' class='sb-brand'>"
        "<span class='sirius-badge'><img src='/static/avatar.png' alt='Sirius Argus' class='sb-logo'></span>"
        "<span class='sb-title'>Sirius Argus<small>MLSecOps Platform</small></span></a>"
        f"<nav class='sb-nav'>{nav_html}</nav>"
        "<div class='sb-foot'><span class='env-chip'>local · dev</span></div>"
        "</aside>"
        f"<main class='app-main'>{body}</main>"
        "</div>"
        f"{_SORT_JS}</body></html>"
    )


def _card(label, value, accent="text-slate-900"):
    return (f"<div class='bg-white rounded-xl shadow-sm border border-slate-200 p-4'>"
            f"<div class='text-xs uppercase tracking-wide text-slate-400'>{_e(label)}</div>"
            f"<div class='text-2xl font-semibold {accent}'>{_e(value)}</div></div>")
