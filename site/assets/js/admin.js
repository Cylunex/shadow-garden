/* 花园后台：登录 + 五模块增删改查 + Markdown 预览 + 图片上传 */
(function () {
  const G = window.Garden;
  const TOKEN_KEY = "garden_token";
  let token = localStorage.getItem(TOKEN_KEY) || "";

  const $ = (sel) => document.querySelector(sel);
  const loginView = $("#login-view");
  const mainView = $("#main-view");
  const tabsBox = $("#tabs");
  const panel = $("#panel");
  const toastBox = $("#toast");
  const fileInput = $("#file-input");
  const logoutLink = $("#logout-link");

  /* ---------- 基础设施 ---------- */

  function setToken(t) {
    token = t;
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  }

  async function api(path, method, body) {
    const opts = { method: method || "GET", headers: {} };
    if (token) opts.headers["Authorization"] = "Bearer " + token;
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    try {
      return await G.api(path, opts);
    } catch (e) {
      if (e.status === 401) {
        setToken("");
        showLogin("登录已过期，请重新登录");
      }
      throw e;
    }
  }

  let toastTimer = null;
  function toast(msg, isError) {
    toastBox.textContent = msg;
    toastBox.className = "show" + (isError ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toastBox.className = ""), 2600);
  }

  /* ---------- 模块定义 ---------- */

  const RATING_OPTIONS = [5, 4, 3, 2, 1].map((n) => [String(n), "★".repeat(n) + "☆".repeat(5 - n)]);

  const MODULES = [
    {
      key: "posts", label: "博客", api: "/api/posts",
      listLine: (p) =>
        '<span class="title">' + G.esc(p.title) + "</span> " +
        (p.status === "draft" ? '<span class="badge draft">草稿</span>' : '<span class="badge">已发布</span>') +
        '<div class="meta">' + G.fmtDate(p.published_at || p.created_at) +
        " · 阅读 " + p.views +
        (p.tags.length ? " · " + p.tags.map(G.esc).join(" / ") : "") + "</div>",
      detail: (p) => api("/api/posts/" + encodeURIComponent(p.slug)),
      fields: [
        { name: "title", label: "标题", type: "text", required: true },
        { name: "slug", label: "Slug（留空自动生成）", type: "text" },
        { name: "status", label: "状态", type: "select", options: [["draft", "草稿"], ["published", "已发布"]] },
        { name: "tags", label: "标签（逗号分隔）", type: "tags" },
        { name: "summary", label: "摘要", type: "textarea", rows: 2, full: true },
        { name: "content_md", label: "正文（Markdown）", type: "md", full: true },
      ],
    },
    {
      key: "projects", label: "项目", api: "/api/projects",
      listLine: (p) =>
        '<span class="title">' + G.esc(p.name) + "</span> " +
        '<span class="badge">' + G.esc(p.status_label) + "</span>" +
        '<div class="meta">' + G.esc(p.description).slice(0, 60) + "</div>",
      fields: [
        { name: "name", label: "名称", type: "text", required: true },
        { name: "status", label: "状态", type: "select", options: [["active", "进行中"], ["done", "已完成"], ["planned", "计划中"], ["paused", "搁置"]] },
        { name: "sort_order", label: "排序权重（大的在前）", type: "number" },
        { name: "tags", label: "标签（逗号分隔）", type: "tags" },
        { name: "link", label: "访问链接", type: "text" },
        { name: "repo", label: "源码链接", type: "text" },
        { name: "description", label: "简介", type: "textarea", rows: 3, full: true },
      ],
    },
    {
      key: "food", label: "美食", api: "/api/food",
      listLine: (f) =>
        '<span class="title">' + G.esc(f.emoji) + " " + G.esc(f.title) + "</span> " +
        '<span class="stars">' + G.stars(f.rating) + "</span>" +
        '<div class="meta">' + [G.fmtDate(f.eaten_on), f.location].filter(Boolean).map(G.esc).join(" · ") + "</div>",
      fields: [
        { name: "title", label: "名称", type: "text", required: true },
        { name: "emoji", label: "Emoji", type: "text" },
        { name: "rating", label: "评分", type: "select", options: RATING_OPTIONS, toValue: Number },
        { name: "eaten_on", label: "日期", type: "date" },
        { name: "location", label: "地点", type: "text" },
        { name: "photo", label: "照片", type: "image" },
        { name: "tags", label: "标签（逗号分隔）", type: "tags" },
        { name: "review", label: "点评", type: "textarea", rows: 3, full: true },
      ],
    },
    {
      key: "trips", label: "旅行", api: "/api/trips",
      listLine: (t) =>
        '<span class="title">' + G.esc(t.title) + "</span>" +
        '<div class="meta">' + [t.destination, G.tripDates(t)].filter(Boolean).map(G.esc).join(" · ") + "</div>",
      detail: (t) => api("/api/trips/" + t.id),
      fields: [
        { name: "title", label: "标题", type: "text", required: true },
        { name: "destination", label: "目的地", type: "text" },
        { name: "start_date", label: "开始日期", type: "date" },
        { name: "end_date", label: "结束日期", type: "date" },
        { name: "summary", label: "一句话总结", type: "text", full: true },
        { name: "photos", label: "相册（每行一个图片 URL）", type: "images", full: true },
        { name: "content_md", label: "游记正文（Markdown）", type: "md", full: true },
      ],
    },
    {
      key: "moments", label: "说说", api: "/api/moments",
      listLine: (m) =>
        '<span class="title">' + G.esc(m.content_md.slice(0, 40)) + (m.content_md.length > 40 ? "…" : "") + "</span>" +
        '<div class="meta">' + G.fmtDateTime(m.created_at) + "</div>",
      fields: [
        { name: "content_md", label: "内容（Markdown，短一点也行）", type: "md", full: true },
      ],
    },
    { key: "about", label: "关于", api: "/api/about", single: true },
  ];

  /* ---------- 表单 ---------- */

  function fieldHtml(f, value) {
    const v = value == null ? "" : value;
    const req = f.required ? " required" : "";
    let control;
    switch (f.type) {
      case "textarea":
        control = '<textarea name="' + f.name + '" rows="' + (f.rows || 3) + '">' + G.esc(v) + "</textarea>";
        break;
      case "md":
        control =
          '<textarea name="' + f.name + '" rows="14" class="md-input">' + G.esc(v) + "</textarea>" +
          '<div class="md-tools">' +
          '<button type="button" class="btn-sm" data-md-preview="' + f.name + '">预览 / 收起</button>' +
          '<button type="button" class="btn-sm" data-md-image="' + f.name + '">插入图片</button>' +
          "</div>" +
          '<div class="md-preview prose" data-preview-box="' + f.name + '" hidden></div>';
        break;
      case "select":
        control = '<select name="' + f.name + '">' +
          f.options.map(([val, label]) =>
            '<option value="' + G.esc(val) + '"' + (String(v) === String(val) ? " selected" : "") + ">" +
            G.esc(label) + "</option>").join("") +
          "</select>";
        break;
      case "number":
        control = '<input type="number" name="' + f.name + '" value="' + G.esc(v === "" ? 0 : v) + '">';
        break;
      case "date":
        control = '<input type="date" name="' + f.name + '" value="' + G.esc(v) + '">';
        break;
      case "tags":
        control = '<input type="text" name="' + f.name + '" value="' + G.esc((v || []).join(", ")) + '" placeholder="如：nginx, 运维">';
        break;
      case "image":
        control =
          '<div class="row-flex">' +
          '<input type="text" name="' + f.name + '" value="' + G.esc(v) + '" placeholder="/uploads/xxx.jpg">' +
          '<button type="button" class="btn-sm" data-image-for="' + f.name + '">上传</button>' +
          "</div>";
        break;
      case "images":
        control =
          '<textarea name="' + f.name + '" rows="3" placeholder="/uploads/a.jpg&#10;/uploads/b.jpg">' +
          G.esc((v || []).join("\n")) + "</textarea>" +
          '<div class="md-tools"><button type="button" class="btn-sm" data-images-for="' + f.name + '">上传并追加</button></div>';
        break;
      default:
        control = '<input type="text" name="' + f.name + '" value="' + G.esc(v) + '"' + req + ">";
    }
    return '<div class="field' + (f.full ? " full" : "") + '"><label>' + G.esc(f.label) + "</label>" + control + "</div>";
  }

  function collectForm(form, fields) {
    const data = {};
    for (const f of fields) {
      const el = form.querySelector('[name="' + f.name + '"]');
      let v = el.value;
      if (f.type === "tags") v = v.split(/[,，、]/).map((s) => s.trim()).filter(Boolean);
      else if (f.type === "images") v = v.split("\n").map((s) => s.trim()).filter(Boolean);
      else if (f.type === "number") v = parseInt(v || "0", 10);
      else if (f.toValue) v = f.toValue(v);
      data[f.name] = v;
    }
    return data;
  }

  /* ---------- 上传与预览 ---------- */

  let uploadHandler = null; // 文件选择后如何处置

  function pickImage(handler) {
    uploadHandler = handler;
    fileInput.value = "";
    fileInput.click();
  }

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file || !uploadHandler) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const resp = await fetch("/api/uploads", {
        method: "POST",
        headers: token ? { Authorization: "Bearer " + token } : {},
        body: fd,
      });
      if (!resp.ok) throw new Error((await resp.json()).detail || "HTTP " + resp.status);
      const { url } = await resp.json();
      uploadHandler(url);
      toast("图片已上传");
    } catch (e) {
      toast("上传失败：" + e.message, true);
    }
  });

  function insertAtCursor(textarea, text) {
    const start = textarea.selectionStart || 0;
    textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(textarea.selectionEnd || start);
    textarea.focus();
  }

  async function toggleMdPreview(form, name) {
    const box = form.querySelector('[data-preview-box="' + name + '"]');
    if (!box.hidden) { box.hidden = true; return; }
    try {
      const md = form.querySelector('[name="' + name + '"]').value;
      const { content_html } = await api("/api/preview", "POST", { content_md: md });
      box.innerHTML = content_html || '<p class="state-note">（空）</p>';
      box.hidden = false;
    } catch (e) {
      toast("预览失败：" + e.message, true);
    }
  }

  /* ---------- 视图 ---------- */

  let currentModule = null;
  let currentItems = [];

  function renderTabs() {
    const currentKey = currentModule ? currentModule.key : "overview";
    tabsBox.innerHTML =
      '<button data-tab="overview"' + (currentKey === "overview" ? ' class="active"' : "") +
      '><span>⌂</span>总览</button>' +
      MODULES.map((m) =>
      '<button data-tab="' + m.key + '"' + (m.key === currentKey ? ' class="active"' : "") + ">" +
      m.label + "</button>").join("") +
      '<button data-export class="export-btn" title="下载全部内容的 JSON 备份">导出备份</button>';
  }

  async function showOverview() {
    currentModule = null;
    renderTabs();
    panel.innerHTML = '<p class="state-note">正在巡视花园…</p>';
    let data;
    try {
      data = await api("/api/editor/context");
    } catch (e) {
      panel.innerHTML = '<p class="state-note error">加载失败：' + G.esc(e.message) + "</p>";
      return;
    }
    const counts = [
      ["posts", "文章", "篇"],
      ["drafts", "待审草稿", "篇"],
      ["trips", "旅行", "段"],
      ["food", "美食", "条"],
      ["moments", "说说", "条"],
      ["projects", "项目", "个"],
    ];
    const draftHtml = data.drafts.length
      ? '<div class="review-list">' + data.drafts.map((post) =>
          '<button class="review-item" data-overview-edit="' + post.id + '">' +
          '<span><b>' + G.esc(post.title) + '</b><small>更新于 ' + G.fmtDateTime(post.updated_at) +
          '</small></span><em>继续编辑 →</em></button>').join("") + "</div>"
      : '<div class="empty-panel"><b>没有待审草稿</b><span>花园现在很整洁，可以让 Hermes 写点新的。</span></div>';
    panel.innerHTML =
      '<div class="overview-head"><div><span class="workspace-label">OVERVIEW</span>' +
      '<h2>下午好，园丁。</h2><p>内容与 Agent 的工作状态都在这里。</p></div>' +
      '<span class="agent-status ' + (data.agent_configured ? "online" : "offline") + '">' +
      '<i></i>Hermes ' + (data.agent_configured ? "已连接" : "未配置") + "</span></div>" +
      '<div class="overview-counts">' + counts.map(([key, label, unit]) =>
        '<div class="overview-stat"><span>' + label + '</span><b>' + data.counts[key] +
        '</b><small>' + unit + "</small></div>").join("") + "</div>" +
      '<div class="overview-grid"><section class="studio-card review-card">' +
      '<div class="studio-card-head"><div><span class="workspace-label">REVIEW QUEUE</span><h3>草稿待审</h3></div>' +
      '<button class="btn-sm" data-go-module="posts">全部文章</button></div>' + draftHtml + "</section>" +
      '<section class="studio-card agent-card"><span class="workspace-label">ASK HERMES</span>' +
      '<h3>一句话，帮你照料花园</h3><p>在 QQ 里 @机器人，说明素材和发布意图即可。</p>' +
      '<div class="prompt-list"><button data-copy-prompt>“把今天这顿饭记到美食里，地点是…”</button>' +
      '<button data-copy-prompt>“根据这些照片写一篇杭州游记，先存草稿”</button>' +
      '<button data-copy-prompt>“把这段开发记录整理成博客，不要直接发布”</button></div>' +
      '<small>Agent 可以新增和修改内容，但不能删除，也不能改项目与关于页。</small></section></div>' +
      '<section class="quick-create"><div><span class="workspace-label">QUICK START</span><h3>自己动手种一篇</h3></div>' +
      '<div><button class="btn btn-primary" data-quick-new="posts">写博客</button>' +
      '<button class="btn btn-ghost" data-quick-new="moments">发说说</button>' +
      '<button class="btn btn-ghost" data-quick-new="food">记美食</button>' +
      '<button class="btn btn-ghost" data-quick-new="trips">写游记</button></div></section>';
  }

  async function exportBackup() {
    try {
      const data = await api("/api/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "garden-export-" + new Date().toISOString().slice(0, 10) + ".json";
      a.click();
      URL.revokeObjectURL(a.href);
      toast("备份已下载");
    } catch (e) {
      toast("导出失败：" + e.message, true);
    }
  }

  async function showList() {
    renderTabs();
    if (currentModule.single) return showAbout();
    panel.innerHTML = '<p class="state-note">加载中…</p>';
    try {
      currentItems = (await api(currentModule.api)).items;
    } catch (e) {
      panel.innerHTML = '<p class="state-note error">加载失败：' + G.esc(e.message) + "</p>";
      return;
    }
    panel.innerHTML =
      '<div class="admin-bar"><h2>' + currentModule.label + '（' + currentItems.length + '）</h2>' +
      '<button class="btn btn-primary btn-sm" data-new>新建</button></div>' +
      (currentItems.length
        ? '<ul class="item-list">' + currentItems.map((item, i) =>
            '<li><div class="grow">' + currentModule.listLine(item) + "</div>" +
            '<button class="btn-sm" data-edit="' + i + '">编辑</button>' +
            '<button class="btn-sm danger" data-del="' + i + '">删除</button></li>').join("") + "</ul>"
        : '<p class="state-note">还没有内容，点「新建」开始。</p>');
  }

  async function showForm(item) {
    const m = currentModule;
    let full = item;
    if (item && m.detail) {
      try { full = await m.detail(item); }
      catch (e) { toast("读取详情失败：" + e.message, true); return; }
    }
    panel.innerHTML =
      '<div class="admin-bar"><h2>' + (item ? "编辑" : "新建") + m.label + "</h2></div>" +
      '<form class="form-card" id="edit-form"><div class="form-grid">' +
      m.fields.map((f) => fieldHtml(f, full ? full[f.name] : undefined)).join("") +
      "</div>" +
      '<div class="form-actions">' +
      '<button class="btn btn-primary" type="submit">保存</button>' +
      '<button class="btn btn-ghost" type="button" data-cancel>取消</button>' +
      "</div></form>";

    $("#edit-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = collectForm(e.target, m.fields);
      try {
        if (item) await api(m.api + "/" + full.id, "PUT", payload);
        else await api(m.api, "POST", payload);
        toast("已保存");
        showList();
      } catch (err) {
        toast("保存失败：" + err.message, true);
      }
    });
  }

  async function showAbout() {
    panel.innerHTML = '<p class="state-note">加载中…</p>';
    let data;
    try { data = await api("/api/about"); }
    catch (e) { panel.innerHTML = '<p class="state-note error">加载失败：' + G.esc(e.message) + "</p>"; return; }

    const linkLines = data.links.map((l) => l.label + " | " + l.url).join("\n");
    panel.innerHTML =
      '<div class="admin-bar"><h2>关于页</h2></div>' +
      '<form class="form-card" id="edit-form"><div class="form-grid">' +
      fieldHtml({ name: "content_md", label: "自我介绍（Markdown）", type: "md", full: true }, data.content_md) +
      fieldHtml({ name: "links", label: "联系方式（每行：名称 | 链接）", type: "textarea", rows: 3, full: true }, linkLines) +
      "</div>" +
      '<div class="form-actions"><button class="btn btn-primary" type="submit">保存</button></div></form>';

    $("#edit-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const links = e.target.querySelector('[name="links"]').value
        .split("\n").map((s) => s.trim()).filter(Boolean)
        .map((line) => {
          const [label, ...rest] = line.split("|");
          return { label: (label || "").trim(), url: rest.join("|").trim() };
        })
        .filter((l) => l.label && l.url);
      try {
        await api("/api/about", "PUT", {
          content_md: e.target.querySelector('[name="content_md"]').value,
          links,
        });
        toast("已保存");
      } catch (err) {
        toast("保存失败：" + err.message, true);
      }
    });
  }

  /* 全局点击代理：标签页、列表操作、上传、预览 */
  document.addEventListener("click", async (e) => {
    const tab = e.target.closest("[data-tab]");
    if (tab) {
      if (tab.dataset.tab === "overview") {
        showOverview();
        return;
      }
      currentModule = MODULES.find((m) => m.key === tab.dataset.tab);
      showList();
      return;
    }
    const goModule = e.target.closest("[data-go-module]");
    if (goModule) {
      currentModule = MODULES.find((m) => m.key === goModule.dataset.goModule);
      showList();
      return;
    }
    const quickNew = e.target.closest("[data-quick-new]");
    if (quickNew) {
      currentModule = MODULES.find((m) => m.key === quickNew.dataset.quickNew);
      renderTabs();
      showForm(null);
      return;
    }
    const overviewEdit = e.target.closest("[data-overview-edit]");
    if (overviewEdit) {
      currentModule = MODULES.find((m) => m.key === "posts");
      try {
        currentItems = (await api(currentModule.api)).items;
        const post = currentItems.find((item) => item.id === Number(overviewEdit.dataset.overviewEdit));
        renderTabs();
        if (post) showForm(post);
      } catch (err) {
        toast("读取草稿失败：" + err.message, true);
      }
      return;
    }
    const copyPrompt = e.target.closest("[data-copy-prompt]");
    if (copyPrompt) {
      try {
        await navigator.clipboard.writeText(copyPrompt.textContent.replace(/[“”]/g, ""));
        toast("示例指令已复制");
      } catch (err) {
        toast("复制失败，请手动选择", true);
      }
      return;
    }
    if (e.target.closest("[data-export]")) { exportBackup(); return; }
    if (e.target.closest("[data-new]")) { showForm(null); return; }

    const editBtn = e.target.closest("[data-edit]");
    if (editBtn) { showForm(currentItems[Number(editBtn.dataset.edit)]); return; }

    const delBtn = e.target.closest("[data-del]");
    if (delBtn) {
      const item = currentItems[Number(delBtn.dataset.del)];
      const label = item.title || item.name || (item.content_md || "").slice(0, 20) || "这条内容";
      if (!confirm("确定删除「" + label + "」？此操作不可恢复。")) return;
      try {
        await api(currentModule.api + "/" + item.id, "DELETE");
        toast("已删除");
        showList();
      } catch (err) {
        toast("删除失败：" + err.message, true);
      }
      return;
    }

    const form = e.target.closest("form");
    const mdPreview = e.target.closest("[data-md-preview]");
    if (mdPreview) { toggleMdPreview(form, mdPreview.dataset.mdPreview); return; }

    const mdImage = e.target.closest("[data-md-image]");
    if (mdImage) {
      const textarea = form.querySelector('[name="' + mdImage.dataset.mdImage + '"]');
      pickImage((url) => insertAtCursor(textarea, "\n![图片](" + url + ")\n"));
      return;
    }
    const imageFor = e.target.closest("[data-image-for]");
    if (imageFor) {
      const input = form.querySelector('[name="' + imageFor.dataset.imageFor + '"]');
      pickImage((url) => (input.value = url));
      return;
    }
    const imagesFor = e.target.closest("[data-images-for]");
    if (imagesFor) {
      const textarea = form.querySelector('[name="' + imagesFor.dataset.imagesFor + '"]');
      pickImage((url) => {
        textarea.value = (textarea.value.trim() ? textarea.value.trim() + "\n" : "") + url;
      });
      return;
    }
    if (e.target.closest("[data-cancel]")) { e.preventDefault(); showList(); }
  });

  /* ---------- 登录 ---------- */

  function showLogin(msg) {
    mainView.hidden = true;
    logoutLink.hidden = true;
    loginView.hidden = false;
    const err = $("#login-error");
    err.hidden = !msg;
    if (msg) err.textContent = msg;
  }

  function showMain() {
    loginView.hidden = true;
    mainView.hidden = false;
    logoutLink.hidden = false;
    currentModule = null;
    showOverview();
  }

  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const { token: t } = await api("/api/auth/login", "POST", { password: $("#password").value });
      setToken(t);
      $("#password").value = "";
      showMain();
    } catch (err) {
      showLogin(err.message);
    }
  });

  logoutLink.addEventListener("click", async (e) => {
    e.preventDefault();
    try { await api("/api/auth/logout", "POST"); } catch (err) { /* 忽略 */ }
    setToken("");
    showLogin();
    toast("已退出");
  });

  /* ---------- 启动 ---------- */

  (async function init() {
    if (!token) return showLogin();
    try {
      const { admin } = await api("/api/auth/me");
      admin ? showMain() : showLogin();
    } catch (e) {
      showLogin("无法连接后端：" + e.message);
    }
  })();
})();
