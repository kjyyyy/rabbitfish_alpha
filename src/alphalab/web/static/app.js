// Client-side filter + sort. No framework: the server already sent every row.
document.addEventListener('input', e => {
  if (!e.target.matches('input[data-filter]')) return;
  const q = e.target.value.toLowerCase();
  const table = document.querySelector(e.target.dataset.filter);
  if (!table) return;
  let shown = 0;
  table.querySelectorAll('tbody tr').forEach(tr => {
    const hit = tr.textContent.toLowerCase().includes(q);
    tr.hidden = !hit;
    if (hit) shown++;
  });
  const c = document.querySelector('[data-count]');
  if (c) c.textContent = shown + ' of ' + table.querySelectorAll('tbody tr').length + ' rows';
});

document.addEventListener('click', e => {
  const th = e.target.closest('th[data-sort]');
  if (!th) return;
  const table = th.closest('table'), body = table.querySelector('tbody');
  const idx = [...th.parentNode.children].indexOf(th);
  const numeric = th.classList.contains('num');
  const dir = th.dataset.dir === 'asc' ? -1 : 1;
  th.parentNode.querySelectorAll('th').forEach(x => delete x.dataset.dir);
  th.dataset.dir = dir === 1 ? 'asc' : 'desc';
  const val = tr => {
    const t = tr.children[idx].textContent.trim();
    if (!numeric) return t.toLowerCase();
    const n = parseFloat(t.replace(/[,%+]/g, ''));
    return isNaN(n) ? -Infinity : n;
  };
  [...body.querySelectorAll('tr')]
    .sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * dir)
    .forEach(tr => body.appendChild(tr));
});
