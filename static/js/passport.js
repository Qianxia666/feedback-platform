/* 密码显隐 */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.password-toggle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var input = btn.parentElement.querySelector('input');
                var open = btn.querySelector('.eye-open');
                var closed = btn.querySelector('.eye-closed');
                if (!input) return;
                if (input.type === 'password') {
                    input.type = 'text';
                    open.classList.add('hidden');
                    closed.classList.remove('hidden');
                } else {
                    input.type = 'password';
                    open.classList.remove('hidden');
                    closed.classList.add('hidden');
                }
            });
        });
    });
})();
