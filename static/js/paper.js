/* 报头日期 */
(function () {
    var el = document.getElementById('paper-date');
    if (!el) return;
    var now = new Date();
    var d = new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai', year: 'numeric', month: 'numeric', day: 'numeric'
    }).format(now);
    var w = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', weekday: 'long' }).format(now);
    el.textContent = d + ' · ' + w;
})();

/* 管理菜单开关（子页面沿用） */
document.addEventListener('DOMContentLoaded', function () {
    var toggle = document.getElementById('admin-menu-toggle');
    var menu = document.getElementById('admin-menu');
    if (toggle && menu) {
        toggle.addEventListener('click', function (e) {
            e.stopPropagation();
            menu.classList.toggle('hidden');
        });
        document.addEventListener('click', function (e) {
            if (!toggle.contains(e.target) && !menu.contains(e.target)) {
                menu.classList.add('hidden');
            }
        });
    }
});
