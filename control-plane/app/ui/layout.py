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


# Счётчики «требует внимания» в сайдбаре: открытые сработки и узлы под тревогой/вниманием.
# Источник — тот же /api/map/status (open/severity по узлам), без нового эндпоинта; обновление 10с.
_NAV_JS = """<script>
(function(){
  function setB(key,val,danger){
    var el=document.querySelector('.sb-badge[data-badge="'+key+'"]'); if(!el)return;
    if(val>0){el.textContent=val>99?'99+':val; el.style.display='inline-flex';
      el.classList.toggle('sb-badge-alert',!!danger); el.classList.toggle('sb-badge-warn',!danger);}
    else{el.textContent=''; el.style.display='none';}
  }
  async function navBadges(){
    try{
      var s=await fetch('/api/map/status').then(function(r){return r.json();});
      var N=s.nodes||{},open=0,attn=0,anyAlert=false,sOpen=0,sAlert=false;
      for(var k in N){var n=N[k];open+=(n.open||0);
        if(n.status==='alert'){attn++;anyAlert=true;}else if(n.status==='warn'){attn++;}
        if(k==='serving'){sOpen=(n.open||0);sAlert=(n.status==='alert');}}
      setB('findings',open,anyAlert);
      setB('map',attn,anyAlert);
      setB('serving',sOpen,sAlert);
    }catch(e){}
  }
  navBadges(); setInterval(navBadges,10000);
})();
</script>"""


# Переключатели темы и акцента (сквозные: те же ключи 'sa-theme'/'sa-accent', что и в /map).
_THEME_JS = """<script>
function saTheme(){var c=document.documentElement.getAttribute('data-sa-theme')||'dark';var n=c==='light'?'dark':'light';
 document.documentElement.setAttribute('data-sa-theme',n);try{localStorage.setItem('sa-theme',n);}catch(e){}saThemeIcon();}
function saThemeIcon(){var t=document.documentElement.getAttribute('data-sa-theme')||'dark';var i=document.getElementById('sa-theme-ic');
 if(i)i.className='bi '+(t==='light'?'bi-sun':'bi-moon-stars');}
function saAccent(a){var d=document.documentElement;
 if(a){d.style.setProperty('--sa-accent',a);d.style.setProperty('--sa-accent-ink',a);d.style.setProperty('--accent',a);}
 else{d.style.removeProperty('--sa-accent');d.style.removeProperty('--sa-accent-ink');d.style.removeProperty('--accent');}
 try{a?localStorage.setItem('sa-accent',a):localStorage.removeItem('sa-accent');}catch(e){}saAccentMark();}
function saAccentMark(){var cur='';try{cur=localStorage.getItem('sa-accent')||'';}catch(e){}
 document.querySelectorAll('.sb-accent-pick [data-a]').forEach(function(b){
  b.setAttribute('aria-current',(b.getAttribute('data-a')||'')===cur?'true':'false');});}
saThemeIcon();saAccentMark();
</script>"""


# Тёмная SOC-консоль: палитра-токены + сайдбар + re-skin Tailwind-утилит через CSS-слой
# (тёмные карточки/таблицы/бейджи без правки каждой страницы). Акцент — золото под лого.
_THEME = """<style>
:root{--bg:#0b1220;--panel:#111a2e;--panel2:#0e1626;--line:#1f2a44;--text:#cbd5e1;--text2:#94a3b8;--muted:#64748b;--head:#f1f5f9;--accent:#facc15;
--sa-bg:#0b1220;--sa-panel:#111a2e;--sa-panel2:#0e1626;--sa-panel3:#15203a;--sa-line:#1f2a44;--sa-line2:#28344f;--sa-text:#cbd5e1;--sa-text2:#94a3b8;--sa-muted:#64748b;--sa-head:#f1f5f9;--sa-accent:#facc15;--sa-accent-ink:#facc15;--sa-ok:#10b981;--sa-warn:#f59e0b;--sa-alert:#ef4444;--sa-blue:#38bdf8;--sa-card-grad:linear-gradient(180deg,#121d33,#0e1626);--sa-hover:#16203a;--sa-rail:#0a111f;}
[data-sa-theme='light']{--bg:#eef1f5;--panel:#ffffff;--panel2:#f6f8fb;--line:#e2e8f0;--text:#334155;--text2:#64748b;--muted:#94a3b8;--head:#0f172a;--accent:#eab308;
--sa-bg:#eef1f5;--sa-panel:#ffffff;--sa-panel2:#f6f8fb;--sa-panel3:#ffffff;--sa-line:#e2e8f0;--sa-line2:#dbe3ec;--sa-text:#334155;--sa-text2:#64748b;--sa-muted:#94a3b8;--sa-head:#0f172a;--sa-accent:#eab308;--sa-accent-ink:#a16207;--sa-ok:#059669;--sa-warn:#d97706;--sa-alert:#dc2626;--sa-blue:#0284c7;--sa-card-grad:linear-gradient(180deg,#ffffff,#f7f9fc);--sa-hover:#eef2f7;--sa-rail:#f1f4f8;}
body{background:var(--bg)!important;color:var(--text)!important;font-family:'Inter',ui-sans-serif,system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased;}
table{font-variant-numeric:tabular-nums;}
h1,h2,h3{color:var(--head);}
.app-shell{display:flex;min-height:100vh;}
.app-main{flex:1;min-width:0;max-width:1180px;margin:0 auto;padding:26px 32px;}
.sb{width:250px;flex-shrink:0;background:var(--sa-rail);border-right:1px solid var(--line);display:flex;flex-direction:column;position:sticky;top:0;height:100vh;}
.sb-brand{display:flex;align-items:center;gap:.6rem;padding:18px 16px 14px;border-bottom:1px solid var(--line);color:var(--head);text-decoration:none;}
.sb-brand .sirius-badge{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:999px;flex-shrink:0;}
.sb-logo{width:32px;height:32px;}
.sb-title{display:flex;flex-direction:column;line-height:1.05;font-weight:700;letter-spacing:.3px;font-size:15px;}
.sb-title small{font-weight:500;font-size:9px;letter-spacing:1.6px;text-transform:uppercase;color:var(--text2);margin-top:2px;}
.sb-nav{display:flex;flex-direction:column;gap:2px;padding:12px 10px;overflow-y:auto;}
.sb-link{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 12px;border-radius:8px;color:var(--text2);font-size:.9rem;font-weight:500;text-decoration:none;transition:background .15s,color .15s;}
.sb-link:hover{background:var(--sa-hover);color:var(--head);}
.sb-active{background:var(--sa-panel3);color:var(--head);box-shadow:inset 3px 0 0 var(--accent);}
.sb-link .lbl{display:flex;align-items:center;gap:10px;min-width:0;}
.sb-link .lbl i{font-size:14px;width:18px;text-align:center;color:var(--muted);flex:none;}
.sb-link:hover .lbl i,.sb-active .lbl i{color:var(--accent);}
.sb-theme{width:30px;height:30px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--text2);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:14px;}
.sb-theme:hover{border-color:var(--accent);color:var(--accent);}
.sb-accent-pick{display:inline-flex;align-items:center;gap:5px;}
.sb-accent-pick button{width:15px;height:15px;border-radius:999px;border:2px solid transparent;background:var(--sw);cursor:pointer;padding:0;box-shadow:0 0 0 1px var(--line);}
.sb-accent-pick button[aria-current='true']{border-color:var(--head);}
.sb-badge{min-width:20px;height:18px;padding:0 6px;border-radius:999px;font-size:10.5px;font-weight:700;align-items:center;justify-content:center;display:none;font-variant-numeric:tabular-nums;line-height:1;}
.sb-badge-warn{background:rgba(245,158,11,.18);color:#fcd34d;box-shadow:inset 0 0 0 1px rgba(245,158,11,.35);}
.sb-badge-alert{background:rgba(239,68,68,.20);color:#fca5a5;box-shadow:inset 0 0 0 1px rgba(239,68,68,.42);}
.sb-foot{margin-top:auto;padding:14px 16px;border-top:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:8px;}
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
.hover\\:bg-slate-50:hover,.hover\\:bg-slate-100:hover{background:var(--sa-hover)!important;}
.bg-red-100{background:rgba(239,68,68,.16)!important;}.text-red-700{color:#fca5a5!important;}
.bg-orange-100{background:rgba(249,115,22,.16)!important;}.text-orange-700{color:#fdba74!important;}
.bg-amber-100{background:rgba(245,158,11,.16)!important;}.text-amber-700{color:#fcd34d!important;}
.bg-sky-100{background:rgba(56,189,248,.16)!important;}.text-sky-700{color:#7dd3fc!important;}
.bg-emerald-100{background:rgba(16,185,129,.16)!important;}.text-emerald-700{color:#6ee7b7!important;}
.bg-violet-100{background:rgba(139,92,246,.16)!important;}.text-violet-700{color:#c4b5fd!important;}
code{color:#e2e8f0;}
/* ── SA-контент-кит: компоненты дизайн-языка для разделов (в рамках общего sidebar) ── */
.sa-mono{font-family:'JetBrains Mono','SFMono-Regular',ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;}
.bi{line-height:1;vertical-align:-.05em;}
.sa-eye{display:flex;align-items:center;gap:8px;font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--sa-text2);font-weight:600;margin:0 0 12px;}
.sa-eye::before{content:'';width:14px;height:2px;background:var(--sa-accent);border-radius:2px;flex:none;}
.sa-panel{border:1px solid var(--sa-line);border-radius:14px;background:var(--sa-panel);overflow:hidden;}
.sa-kpi{position:relative;border:1px solid var(--sa-line);border-radius:14px;padding:14px 16px;background:var(--sa-card-grad);overflow:hidden;}
.sa-kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--sa-accent),transparent);}
.sa-kpi .l{font-size:10px;letter-spacing:1.4px;text-transform:uppercase;color:var(--sa-text2);font-weight:600;}
.sa-kpi .v{font-size:26px;font-weight:700;color:var(--sa-head);margin-top:6px;line-height:1.05;font-variant-numeric:tabular-nums;}
.sa-kpi .s{font-size:10.5px;color:var(--sa-muted);margin-top:3px;}
.sa-chip2{font-size:11px;color:var(--sa-text2);border:1px solid var(--sa-line);border-radius:999px;padding:5px 12px;text-decoration:none;display:inline-block;transition:border-color .15s,color .15s;}
.sa-chip2:hover{border-color:var(--sa-accent);color:var(--sa-head);}
.sa-chip2.on{background:var(--sa-accent);color:#0b1220;border-color:var(--sa-accent);font-weight:600;}
.sa-badge{font-size:10px;font-weight:700;border-radius:5px;padding:2px 6px;display:inline-block;}
.sa-table{width:100%;border-collapse:collapse;font-size:13px;}
.sa-table thead th{text-align:left;padding:9px 12px;font-size:10px;letter-spacing:.8px;text-transform:uppercase;color:var(--sa-text2);background:var(--sa-panel2);font-weight:600;white-space:nowrap;}
.sa-table tbody td{padding:8px 12px;border-top:1px solid var(--sa-line);color:var(--sa-text);vertical-align:top;}
.sa-table tbody tr:hover{background:var(--sa-hover);}
.sa-h1{font-size:21px;font-weight:700;color:var(--sa-head);margin:0;}
.sa-sub{font-size:12.5px;color:var(--sa-text2);margin-top:5px;line-height:1.5;}
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
    ("/dashboard", "Дашборд", "dashboard"),
    ("/registry", "Реестр", "registry"),
    ("/findings", "Сработки", "findings"),
    ("/coverage", "Карта покрытия", "coverage"),
    ("/serving", "Сервинг", "serving"),
    ("/services", "Сервисы", "services"),
    ("/roles", "Роли (RBAC)", "roles"),
)

# Bootstrap-иконки разделов (тот же набор, что в SA-рейле /map) — для сквозного меню.
_NAV_ICON = {"map": "bi-diagram-3", "dashboard": "bi-speedometer2", "registry": "bi-box-seam",
             "findings": "bi-exclamation-triangle", "coverage": "bi-shield-check",
             "serving": "bi-hdd-network", "services": "bi-hdd-stack", "roles": "bi-people"}


def _page(title, body, nav="dashboard"):
    def link(href, label, key):
        active = " sb-active" if key == nav else ""
        icon = _NAV_ICON.get(key, "bi-dot")
        return (f'<a class="sb-link{active}" data-nav="{key}" href="{href}">'
                f'<span class="lbl"><i class="bi {icon}"></i>{_e(label)}</span>'
                f'<span class="sb-badge" data-badge="{key}"></span></a>')
    nav_html = "".join(link(h, l, k) for h, l, k in _NAV)
    return (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        "<script>try{var _t=localStorage.getItem('sa-theme');if(_t)document.documentElement.setAttribute('data-sa-theme',_t);"
        "var _a=localStorage.getItem('sa-accent');if(_a){var _d=document.documentElement.style;_d.setProperty('--sa-accent',_a);_d.setProperty('--sa-accent-ink',_a);_d.setProperty('--accent',_a);}}catch(e){}</script>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title>"
        "<link rel=icon type=image/png href='/static/avatar.png'>"
        "<link rel=preconnect href='https://fonts.googleapis.com'>"
        "<link rel=preconnect href='https://fonts.gstatic.com' crossorigin>"
        "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap' rel=stylesheet>"
        "<link href='https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css' rel=stylesheet>"
        f"{_CDN}{_STYLE}{_THEME}</head>"
        "<body>"
        "<div class='app-shell'>"
        "<aside class='sb'>"
        "<a href='/map' class='sb-brand'>"
        "<span class='sirius-badge'><img src='/static/avatar.png' alt='Sirius Argus' class='sb-logo'></span>"
        "<span class='sb-title'>Sirius Argus<small>MLSecOps Platform</small></span></a>"
        f"<nav class='sb-nav'>{nav_html}</nav>"
        "<div class='sb-foot'><span class='env-chip'>local · dev</span>"
        "<span style='display:flex;align-items:center;gap:8px'>"
        "<span class='sb-accent-pick' title='Акцент'>"
        "<button data-a='' style='--sw:#facc15' onclick=\"saAccent('')\" title='Золото'></button>"
        "<button data-a='#fb923c' style='--sw:#fb923c' onclick=\"saAccent('#fb923c')\" title='Оранжевый'></button>"
        "<button data-a='#38bdf8' style='--sw:#38bdf8' onclick=\"saAccent('#38bdf8')\" title='Голубой'></button></span>"
        "<button class='sb-theme' onclick='saTheme()' title='Светлая / тёмная тема'><i id='sa-theme-ic' class='bi bi-moon-stars'></i></button></span></div>"
        "</aside>"
        f"<main class='app-main'>{body}</main>"
        "</div>"
        f"{_SORT_JS}{_NAV_JS}{_THEME_JS}</body></html>"
    )


def _card(label, value, accent="text-slate-900"):
    return (f"<div class='bg-white rounded-xl shadow-sm border border-slate-200 p-4'>"
            f"<div class='text-xs uppercase tracking-wide text-slate-400'>{_e(label)}</div>"
            f"<div class='text-2xl font-semibold {accent}'>{_e(value)}</div></div>")
