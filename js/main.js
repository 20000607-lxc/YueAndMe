/* ===== 城市时间 ===== */
function tickClocks() {
  const now = new Date();
  document.querySelectorAll('[data-tz]').forEach(el => {
    el.textContent = new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit', minute: '2-digit', hour12: false, timeZone: el.dataset.tz
    }).format(now);
  });
  document.querySelectorAll('[data-tz-day]').forEach(el => {
    const tz = el.dataset.tzDay;
    const hour = Number(new Intl.DateTimeFormat('en-GB', { hour: 'numeric', hour12: false, timeZone: tz }).format(now));
    const weekday = new Intl.DateTimeFormat('zh-CN', { weekday: 'long', timeZone: tz }).format(now);
    const part = hour < 5 ? '深夜' : hour < 9 ? '清晨' : hour < 12 ? '上午' : hour < 14 ? '中午' : hour < 18 ? '下午' : hour < 22 ? '夜晚' : '深夜';
    el.textContent = `${weekday} · ${part}`;
  });
}
tickClocks();
setInterval(tickClocks, 15000);

/* ===== 画廊 ===== */
const AUTHORS = {
  '越越':   { city: 'Jinan' },
  'Sherry': { city: 'San Francisco' },
  '合照':   { city: 'Together' },
};
const AUTHOR_ORDER = ['越越', 'Sherry', '合照'];

const photos = (window.PHOTOS || []).map((p, i) => ({ ...p, _i: i }));
const root = document.getElementById('gallery-root');
let visible = [];   // 当前展示顺序，用于灯箱前后切换

function groupBy(arr, key) {
  const m = new Map();
  arr.forEach(x => { const k = x[key] || '未命名'; if (!m.has(k)) m.set(k, []); m.get(k).push(x); });
  return m;
}

function render(authorFilter) {
  root.innerHTML = '';
  visible = [];

  const list = authorFilter === 'all' ? photos : photos.filter(p => p.author === authorFilter);
  if (!list.length) {
    root.innerHTML = `<div class="empty-hint">
      这里还没有照片。<br>
      把图片放进 <code>originals/作者/地点/</code>，然后运行 <code>python3 scripts/build_photos.py</code>。
    </div>`;
    return;
  }

  const byAuthor = groupBy(list, 'author');
  const authors = [...AUTHOR_ORDER.filter(a => byAuthor.has(a)), ...[...byAuthor.keys()].filter(a => !AUTHOR_ORDER.includes(a))];

  authors.forEach(author => {
    const items = byAuthor.get(author);
    const block = document.createElement('section');
    block.className = 'author-block';
    block.innerHTML = `
      <div class="author-head">
        <h3>${author}</h3>
        <span class="author-city">${(AUTHORS[author] || {}).city || ''}</span>
        <span class="author-count">${items.length} photos</span>
      </div>`;

    groupBy(items, 'place').forEach((pics, place) => {
      const pb = document.createElement('div');
      pb.className = 'place-block';
      pb.innerHTML = `<p class="place-head">${place}</p><div class="grid"></div>`;
      const grid = pb.querySelector('.grid');
      pics.forEach(p => {
        const idx = visible.push(p) - 1;
        const fig = document.createElement('figure');
        fig.className = 'card';
        fig.innerHTML = `
          <img src="${p.thumb || p.src}" alt="${p.title || ''}" loading="lazy"
               ${p.w && p.h ? `width="${p.w}" height="${p.h}"` : ''}>
          <figcaption>
            <p class="card-title">${p.title || ''}</p>
            <p class="card-meta">${[p.place, p.date].filter(Boolean).join(' · ')}</p>
          </figcaption>`;
        fig.addEventListener('click', () => openLightbox(idx));
        grid.appendChild(fig);
      });
      block.appendChild(pb);
    });
    root.appendChild(block);
  });
}

document.querySelectorAll('.filter').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    render(btn.dataset.author);
  });
});
render('all');

/* ===== 灯箱 ===== */
const lb = document.getElementById('lightbox');
const lbImg = document.getElementById('lb-img');
let cur = -1;

function show(i) {
  cur = (i + visible.length) % visible.length;
  const p = visible[cur];
  lbImg.src = p.src;
  lbImg.alt = p.title || '';
  document.getElementById('lb-title').textContent = p.title || '';
  document.getElementById('lb-meta').textContent = [p.author, p.place, p.date].filter(Boolean).join(' · ');
  document.getElementById('lb-note').textContent = p.note || '';
}
function openLightbox(i) { show(i); lb.classList.add('is-open'); lb.setAttribute('aria-hidden', 'false'); document.body.style.overflow = 'hidden'; }
function closeLightbox() { lb.classList.remove('is-open'); lb.setAttribute('aria-hidden', 'true'); document.body.style.overflow = ''; }

lb.querySelector('.lb-close').addEventListener('click', closeLightbox);
lb.querySelector('.lb-prev').addEventListener('click', e => { e.stopPropagation(); show(cur - 1); });
lb.querySelector('.lb-next').addEventListener('click', e => { e.stopPropagation(); show(cur + 1); });
lb.addEventListener('click', e => { if (e.target === lb) closeLightbox(); });
document.addEventListener('keydown', e => {
  if (!lb.classList.contains('is-open')) return;
  if (e.key === 'Escape') closeLightbox();
  if (e.key === 'ArrowLeft') show(cur - 1);
  if (e.key === 'ArrowRight') show(cur + 1);
});

// 触屏左右滑动
let touchX = null;
lb.addEventListener('touchstart', e => { touchX = e.touches[0].clientX; }, { passive: true });
lb.addEventListener('touchend', e => {
  if (touchX === null) return;
  const dx = e.changedTouches[0].clientX - touchX;
  if (Math.abs(dx) > 50) show(cur + (dx < 0 ? 1 : -1));
  touchX = null;
});
