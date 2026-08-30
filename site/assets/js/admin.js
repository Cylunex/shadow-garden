/* 花园后台：登录 + 五模块增删改查 + Markdown 预览 + 图片上传 */
(function () {
  const G = window.Garden;

  const $ = (sel) => document.querySelector(sel);
  const loginView = $("#login-view");
  const mainView = $("#main-view");
  const tabsBox = $("#tabs");
  const panel = $("#panel");
  const toastBox = $("#toast");
  const fileInput = $("#file-input");
  const logoutLink = $("#logout-link");

  /* ---------- 基础设施 ---------- */

  async function api(path, method, body) {
    const opts = { method: method || "GET", headers: {}, credentials: "same-origin" };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    try {
      return await G.api(path, opts);
    } catch (e) {
      if (e.status === 401) {
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
  const POST_STATES = {
    draft: "草稿", preview: "已预览", revision: "修订中",
    published: "已发布", withdrawn: "已撤回",
  };

  const MODULES = [
    {
      key: "posts", label: "博客", api: "/api/posts",
      listLine: (p) =>
        '<span class="title">' + G.esc(p.title) + "</span> " +
        '<span class="badge ' + (p.status === "published" ? "" : "draft") + '">' +
        G.esc(POST_STATES[p.status] || p.status) + "</span>" +
        '<div class="meta">' + G.fmtDate(p.published_at || p.created_at) +
        " · 阅读 " + p.views +
        (p.tags.length ? " · " + p.tags.map(G.esc).join(" / ") : "") + "</div>",
      detail: (p) => api("/api/posts/" + encodeURIComponent(p.slug)),
      fields: [
        { name: "title", label: "标题", type: "text", required: true },
        { name: "slug", label: "Slug（留空自动生成）", type: "text" },
        { name: "tags", label: "标签（逗号分隔）", type: "tags" },
        { name: "source_refs", label: "来源引用（每行一个 Archive / Travel 稳定引用）", type: "lines", full: true },
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
        { name: "photo", label: "封面图（留空时使用相册第一张）", type: "image" },
        { name: "photos", label: "相册（可一次选择多张）", type: "images", full: true },
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
      key: "moments", label: "日常", api: "/api/moments",
      listLine: (m) =>
        '<span class="title">' + G.esc(m.title || m.content_md.slice(0, 40) || "一组照片") +
        (!m.title && m.content_md.length > 40 ? "…" : "") + "</span> " +
        '<span class="badge">' + (m.kind === "scenery" ? "日常风景" : "日常记录") + "</span>" +
        '<div class="meta">' + G.fmtDateTime(m.created_at) +
        (m.collections.length ? " · " + m.collections.map(G.esc).join(" / ") : "") + "</div>",
      fields: [
        { name: "title", label: "标题（可选）", type: "text" },
        { name: "kind", label: "类型", type: "select", options: [["note", "日常记录"], ["scenery", "日常风景"]] },
        { name: "collections", label: "合集（可填多个，如：晚霞, 散步）", type: "tags", full: true },
        { name: "photos", label: "照片（可一次选择多张）", type: "images", full: true },
        { name: "content_md", label: "内容（Markdown，可选）", type: "md", full: true },
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
        const imageValues = v || [];
        control =
          '<textarea name="' + f.name + '" rows="3" placeholder="/uploads/a.jpg&#10;/uploads/b.jpg">' +
          G.esc(imageValues.join("\n")) + "</textarea>" +
          '<div class="md-tools"><button type="button" class="btn-sm" data-images-for="' + f.name + '">选择多张并追加</button></div>' +
          '<div class="image-preview-grid" data-images-preview="' + f.name + '">' +
          imageValues.map((url) => '<img src="' + G.esc(url) + '" alt="相册预览">').join("") + "</div>";
        break;
      case "lines":
        control = '<textarea name="' + f.name + '" rows="3" placeholder="shadow://archive/records/…">' +
          G.esc((v || []).join("\n")) + "</textarea>";
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
      else if (f.type === "lines") v = v.split("\n").map((s) => s.trim()).filter(Boolean);
      else if (f.type === "number") v = parseInt(v || "0", 10);
      else if (f.toValue) v = f.toValue(v);
      data[f.name] = v;
    }
    return data;
  }

  /* ---------- 上传与预览 ---------- */

  let uploadHandler = null; // 文件选择后如何处置

  function pickImage(handler, multiple) {
    uploadHandler = handler;
    fileInput.multiple = !!multiple;
    fileInput.value = "";
    fileInput.click();
  }

  async function legacyUpload(file) {
    const fd = new FormData();
    fd.append("file", file);
    const resp = await fetch("/api/uploads", {
      method: "POST",
      credentials: "same-origin",
      body: fd,
    });
    if (!resp.ok) throw new Error((await resp.json()).detail || "HTTP " + resp.status);
    return resp.json();
  }

  async function probeUploadTarget(target) {
    if (target.route === "canonical") return true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2500);
    try {
      await fetch(target.url, {
        method: "OPTIONS",
        mode: "cors",
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      return true;
    } catch (_) {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  async function directUpload(file) {
    const initialized = await fetch("/api/uploads/init", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name || "image",
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
      }),
    });
    if (initialized.status === 409) return legacyUpload(file);
    if (!initialized.ok) {
      throw new Error((await initialized.json()).detail || "HTTP " + initialized.status);
    }
    const session = await initialized.json();
    let uploaded = false;
    let lastError = null;
    for (const target of session.targets || []) {
      if (!(await probeUploadTarget(target))) continue;
      try {
        const sent = await fetch(target.url, {
          method: target.method || "PUT",
          mode: "cors",
          credentials: "omit",
          headers: target.headers || {},
          body: file,
        });
        if (!sent.ok) {
          const rejected = new Error("文件写入失败：HTTP " + sent.status);
          rejected.uploadRejected = true;
          throw rejected;
        }
        uploaded = true;
        break;
      } catch (error) {
        lastError = error;
        if (error && error.uploadRejected) throw error;
        if (target.route !== "canonical") continue;
      }
    }
    if (!uploaded) throw lastError || new Error("没有可用的上传线路");

    const completed = await fetch("/api/uploads/complete", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: session.upload_id }),
    });
    if (!completed.ok) {
      throw new Error((await completed.json()).detail || "HTTP " + completed.status);
    }
    return completed.json();
  }

  fileInput.addEventListener("change", async () => {
    const files = Array.from(fileInput.files || []);
    if (!files.length || !uploadHandler) return;
    try {
      for (const file of files) {
        const { url } = await directUpload(file);
        uploadHandler(url);
      }
      toast(files.length > 1 ? files.length + " 张图片已上传" : "图片已上传");
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
    let suggestions = [];
    try {
      [data, suggestions] = await Promise.all([
        api("/api/editor/context"),
        api("/api/editor/suggestions").then((value) => value.items).catch(() => []),
      ]);
    } catch (e) {
      panel.innerHTML = '<p class="state-note error">加载失败：' + G.esc(e.message) + "</p>";
      return;
    }
    const counts = [
      ["posts", "文章", "篇"],
      ["drafts", "待审草稿", "篇"],
      ["trips", "旅行", "段"],
      ["food", "美食", "条"],
      ["moments", "日常", "条"],
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
      (suggestions.length ? '<section class="studio-card review-card"><div class="studio-card-head"><div>' +
        '<span class="workspace-label">GENTLE REDISCOVERY</span><h3>想回看时再打开</h3></div></div>' +
        '<div class="review-list">' + suggestions.map((item) =>
          '<button class="review-item" data-suggestion-uri="' + G.esc(item.subject_uri) + '"><span><b>' +
          G.esc(item.title) + '</b><small>' + G.esc(item.reason) + '</small></span><em>查看 →</em></button>'
        ).join("") + '</div></section>' : "") +
      '<section class="quick-create"><div><span class="workspace-label">QUICK START</span><h3>自己动手种一篇</h3></div>' +
      '<div><button class="btn btn-primary" data-quick-new="posts">写博客</button>' +
      '<button class="btn btn-ghost" data-quick-new="moments">记日常</button>' +
      '<button class="btn btn-ghost" data-quick-new="food">记美食</button>' +
      '<button class="btn btn-ghost" data-quick-new="trips">写游记</button></div></section>';
  }

  async function exportBackup() {
    try {
      const response = await fetch("/api/export", { credentials: "same-origin" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const blob = await response.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "garden-portable-" + new Date().toISOString().slice(0, 10) + ".zip";
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
      (m.key === "posts" && full ? '<div class="md-preview prose" id="post-health" hidden></div>' : "") +
      '<div class="form-actions">' +
      '<button class="btn btn-primary" type="submit">保存</button>' +
      (m.key === "posts" && full && ["draft", "revision"].includes(full.status)
        ? '<button class="btn btn-ghost" type="button" data-post-action="preview">校验并预览</button>' : "") +
      (m.key === "posts" && full && full.status === "preview"
        ? '<button class="btn btn-primary" type="button" data-post-action="publish">发布当前预览</button>' : "") +
      (m.key === "posts" && full && full.status === "published"
        ? '<button class="btn btn-ghost" type="button" data-post-action="withdraw">撤回公开版本</button>' : "") +
      '<button class="btn btn-ghost" type="button" data-cancel>取消</button>' +
      "</div></form>";

    $("#edit-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = collectForm(e.target, m.fields);
      if (m.key === "posts" && full) payload.status = full.status;
      try {
        if (item) await api(m.api + "/" + full.id, "PUT", payload);
        else await api(m.api, "POST", payload);
        toast("已保存");
        showList();
      } catch (err) {
        toast("保存失败：" + err.message, true);
      }
    });

    const action = $("[data-post-action]");
    if (action) action.addEventListener("click", async () => {
      try {
        const result = await api(
          m.api + "/" + full.id + "/" + action.dataset.postAction,
          "POST",
          action.dataset.postAction === "preview" ? { check_external: null } : undefined
        );
        if (result.validation) {
          const box = $("#post-health");
          box.hidden = false;
          box.innerHTML = '<b>' + (result.validation.valid ? "预览校验通过" : "预览校验未通过") + '</b>' +
            (result.validation.issues.length ? '<ul>' + result.validation.issues.map((issue) =>
              '<li>' + G.esc(issue.message) + ' <small>' + G.esc(issue.reference) + '</small></li>'
            ).join("") + '</ul>' : '<p>站内链接、资源与来源引用均可用。</p>');
          if (!result.validation.valid) return;
          full = result.post;
        } else {
          full = result;
        }
        toast("文章状态已更新");
        showForm(full);
      } catch (err) {
        toast("操作失败：" + err.message, true);
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
    const suggestion = e.target.closest("[data-suggestion-uri]");
    if (suggestion) {
      const match = suggestion.dataset.suggestionUri.match(/\/posts\/(\d+)$/);
      if (match) {
        currentModule = MODULES.find((m) => m.key === "posts");
        currentItems = (await api(currentModule.api)).items;
        const post = currentItems.find((item) => item.id === Number(match[1]));
        renderTabs();
        if (post) showForm(post);
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
      const preview = form.querySelector('[data-images-preview="' + imagesFor.dataset.imagesFor + '"]');
      pickImage((url) => {
        textarea.value = (textarea.value.trim() ? textarea.value.trim() + "\n" : "") + url;
        preview.insertAdjacentHTML("beforeend", '<img src="' + G.esc(url) + '" alt="相册预览">');
      }, true);
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

  logoutLink.addEventListener("click", async (e) => {
    e.preventDefault();
    try { await api("/auth/logout", "POST"); } catch (err) { /* 忽略 */ }
    showLogin();
    toast("已退出");
  });

  /* ---------- 启动 ---------- */

  (async function init() {
    try {
      const { admin } = await api("/api/auth/me");
      admin ? showMain() : showLogin();
    } catch (e) {
      showLogin("无法连接后端：" + e.message);
    }
  })();
})();
