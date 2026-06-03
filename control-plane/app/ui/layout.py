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
        cls = ("bg-slate-700 text-white" if key == nav
               else "text-slate-300 hover:text-white hover:bg-slate-800")
        return f'<a class="px-2.5 py-1 rounded-md transition-colors {cls}" href="{href}">{label}</a>'
    tabs = "".join(link(h, l, k) for h, l, k in _NAV)
    return (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title>"
        "<link rel=icon type=image/png href='/static/avatar.png'>"
        f"{_CDN}{_STYLE}</head>"
        "<body class='bg-slate-50 text-slate-800'>"
        "<header class='bg-slate-900 text-white px-6 py-3 shadow sticky top-0 z-20 "
        "flex flex-wrap items-center gap-x-5 gap-y-2'>"
        "<a href='/' class='flex items-center gap-2 font-bold tracking-wide hover:opacity-90'>"
        "<span class='sirius-badge relative inline-flex h-8 w-8 items-center justify-center rounded-full'>"
        "<img src='/static/avatar.png' alt='Sirius Argus' width=28 height=28 class='relative h-7 w-7'>"
        "</span>"
        "<span>Sirius Argus</span></a>"
        f"<nav class='flex flex-wrap gap-1 text-sm'>{tabs}</nav></header>"
        f"<main class='max-w-6xl mx-auto p-6 space-y-6'>{body}</main>{_SORT_JS}</body></html>"
    )


def _card(label, value, accent="text-slate-900"):
    return (f"<div class='bg-white rounded-xl shadow-sm border border-slate-200 p-4'>"
            f"<div class='text-xs uppercase tracking-wide text-slate-400'>{_e(label)}</div>"
            f"<div class='text-2xl font-semibold {accent}'>{_e(value)}</div></div>")
