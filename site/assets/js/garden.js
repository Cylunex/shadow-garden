/* 全站共享：API 调用 + 各版块渲染片段（无构建，直接 <script> 引入） */
window.Garden = (function () {
  async function api(path, opts = {}) {
    const resp = await fetch(path, opts);
    if (!resp.ok) {
      let msg = "HTTP " + resp.status;
      try {
        const data = await resp.json();
        if (data.detail) msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } catch (e) { /* 非 JSON 响应就用状态码 */ }
      const err = new Error(msg);
      err.status = resp.status;
      throw err;
    }
    return resp.status === 204 ? null : resp.json();
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  const fmtDate = (iso) => (iso || "").slice(0, 10);
  const stars = (n) => "★".repeat(n) + "☆".repeat(Math.max(0, 5 - n));

  function fmtDateTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return fmtDate(iso);
    const p = (n) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) +
      " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function tagsHtml(tags) {
    if (!tags || !tags.length) return "";
    return '<div class="tags">' + tags.map((t) => '<span class="tag">' + esc(t) + "</span>").join("") + "</div>";
  }

  function postItem(p) {
    return '<li><a href="/blog/post.html?slug=' + encodeURIComponent(p.slug) + '">' + esc(p.title) +
      "</a><time>" + fmtDate(p.published_at) + "</time></li>";
  }

  function projectCard(p) {
    let links = "";
    if (p.link || p.repo) {
      links = '<div class="links-row">' +
        (p.link ? '<a href="' + esc(p.link) + '" target="_blank" rel="noopener">访问 ↗</a>' : "") +
        (p.repo ? '<a href="' + esc(p.repo) + '" target="_blank" rel="noopener">源码 ↗</a>' : "") +
        "</div>";
    }
    return '<div class="card"><h3>' + esc(p.name) + '</h3><p>' + esc(p.description) + "</p>" +
      links + tagsHtml([p.status_label].concat(p.tags)) + "</div>";
  }

  function foodCard(f) {
    const media = f.photo
      ? '<img class="thumb" src="' + esc(f.photo) + '" alt="' + esc(f.title) + '" loading="lazy">'
      : '<div class="emoji">' + esc(f.emoji) + "</div>";
    const meta = [fmtDate(f.eaten_on), f.location].filter(Boolean).map(esc).join(" · ");
    return '<div class="card">' + media +
      "<h3>" + esc(f.title) + '</h3><div class="stars">' + stars(f.rating) + "</div>" +
      (meta ? '<div class="meta">' + meta + "</div>" : "") +
      "<p>" + esc(f.review) + "</p>" + tagsHtml(f.tags) + "</div>";
  }

  function tripDates(t) {
    if (!t.start_date) return "";
    return t.end_date && t.end_date !== t.start_date
      ? t.start_date + " ~ " + t.end_date
      : t.start_date;
  }

  function tripItem(t) {
    const meta = [t.destination, tripDates(t)].filter(Boolean).map(esc).join(" · ");
    return '<li><a href="/travel/trip.html?id=' + t.id + '">' + esc(t.title) +
      (t.summary ? '<span class="meta"> —— ' + esc(t.summary) + "</span>" : "") +
      "</a><time>" + meta + "</time></li>";
  }

  function momentCard(m, withTime) {
    return '<div class="moment"><time>' + (withTime ? fmtDateTime(m.created_at) : fmtDate(m.created_at)) +
      '</time><div class="prose">' + m.content_html + "</div></div>";
  }

  function stateNote(el, msg, isError) {
    el.innerHTML = '<p class="state-note' + (isError ? " error" : "") + '">' + esc(msg) + "</p>";
  }

  /* 主题：空 = 跟随系统，dark / light = 手动指定（localStorage 记忆） */
  const THEME_KEY = "garden-theme";
  function initTheme() {
    const btn = document.getElementById("theme-btn");
    if (!btn) return;
    const icons = { "": "🌗", dark: "🌙", light: "☀️" };
    const titles = { "": "主题：跟随系统", dark: "主题：深色", light: "主题：浅色" };
    let cur = localStorage.getItem(THEME_KEY) || "";
    const apply = () => {
      if (cur) document.documentElement.setAttribute("data-theme", cur);
      else document.documentElement.removeAttribute("data-theme");
      btn.textContent = icons[cur];
      btn.title = titles[cur];
    };
    btn.addEventListener("click", () => {
      cur = cur === "" ? "dark" : cur === "dark" ? "light" : "";
      if (cur) localStorage.setItem(THEME_KEY, cur);
      else localStorage.removeItem(THEME_KEY);
      apply();
    });
    apply();
  }
  initTheme(); // garden.js 以 defer 加载，DOM 已就绪

  /* 图片灯箱：点内容图放大，再点或 Esc 关闭 */
  document.addEventListener("click", (e) => {
    const open = document.getElementById("lightbox");
    if (open) { open.remove(); return; }
    const img = e.target.closest(".photo-grid img, .card .thumb, .prose img");
    if (!img) return;
    const box = document.createElement("div");
    box.id = "lightbox";
    const full = document.createElement("img");
    full.src = img.src;
    full.alt = img.alt || "";
    box.appendChild(full);
    document.body.appendChild(box);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const box = document.getElementById("lightbox");
      if (box) box.remove();
    }
  });

  return { api, esc, fmtDate, fmtDateTime, stars, tagsHtml, postItem, projectCard, foodCard, tripItem, tripDates, momentCard, stateNote };
})();
