(() => {
  const $ = id => document.getElementById(id);
  const form = $("evidenceForm"), status = $("evidenceStatus"), workspace = $("evidenceWorkspace");
  const treeNode = $("fileTree"), card = $("evidenceCard"), shortcuts = $("shortcuts");
  const createButton = $("createSnapshot"), treeStatus = $("treeStatus"), breadcrumbs = $("breadcrumbs");
  let currentSession = null, generation = 0, fileRequest = 0, treeRequest = 0;
  let currentPath = "", selectedPath = "", entries = [], knownFiles = new Map();
  let history = [], historyIndex = -1;

  function el(tag, text = "", className = "") {
    const node = document.createElement(tag); node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, action) {
    const node = el("button", text); node.type = "button"; node.addEventListener("click", action); return node;
  }
  async function request(url, options) {
    let response;
    try { response = await fetch(url, options); }
    catch (_) { throw new Error("无法连接本地服务，请检查服务是否启动后重试。"); }
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.toLowerCase().includes("application/json")) {
      throw new Error(`服务返回非 JSON 响应（HTTP ${response.status}），请检查本地服务。`);
    }
    let body;
    try { body = await response.json(); }
    catch (_) { throw new Error("服务返回的数据无法解析，请重试。"); }
    if (!response.ok) throw new Error(body.detail?.message || `请求失败（HTTP ${response.status}）。`);
    return body;
  }
  function active(session) { return currentSession === session && session.generation === generation; }
  function reset() {
    ++generation; ++fileRequest; ++treeRequest; currentSession = null;
    currentPath = ""; selectedPath = ""; entries = []; knownFiles = new Map(); history = []; historyIndex = -1;
    treeNode.replaceChildren(); card.replaceChildren(); shortcuts.replaceChildren(); breadcrumbs.replaceChildren();
    $("snapshotInfo").replaceChildren(); treeStatus.textContent = ""; workspace.hidden = true;
  }
  function copyValue(label, value) {
    const wrap = el("span", "", "copy-value");
    const short = el("code", `${value.slice(0, 12)}…`); short.title = value;
    const feedback = el("span", "", "copy-feedback"); feedback.setAttribute("role", "status");
    wrap.append(el("span", `${label} `), short, button("复制", async () => {
      try { await navigator.clipboard.writeText(value); feedback.textContent = "已复制"; }
      catch (_) { feedback.textContent = `复制失败，完整值：${value}`; }
    }), feedback);
    return wrap;
  }
  function renderBreadcrumbs(session, path) {
    breadcrumbs.replaceChildren(button("根目录", () => loadTree(session, "")));
    let accumulated = "";
    for (const part of path ? path.split("/") : []) {
      accumulated = accumulated ? `${accumulated}/${part}` : part;
      const destination = accumulated;
      breadcrumbs.append(el("span", " / "), button(part, () => loadTree(session, destination)));
    }
  }
  function renderShortcuts(session) {
    shortcuts.replaceChildren(el("strong", "已读取目录中的常用文件： "));
    const candidates = [...knownFiles.keys()].filter(path => /^(readme(?:\.[^/]*)?|requirements(?:[-_.][^/]*)?\.txt|pyproject\.toml|pipfile|poetry\.lock|dockerfile(?:\.[^/]*)?|(?:docker-)?compose[^/]*\.ya?ml)$/i.test(path.split("/").pop()));
    if (!candidates.length) shortcuts.append(el("span", "当前已读取目录中暂无；其他目录尚未检查。"));
    for (const path of candidates) shortcuts.append(button(path, () => chooseFile(session, path)));
  }
  function renderTree(session) {
    treeNode.replaceChildren();
    for (const entry of entries) {
      if (entry.type !== "tree" && entry.type !== "blob") continue;
      const path = currentPath ? `${currentPath}/${entry.name}` : entry.name;
      const node = button(`${entry.type === "tree" ? "📁" : "📄"} ${entry.name}`, () => {
        if (!active(session)) return;
        if (entry.type === "tree") loadTree(session, path); else chooseFile(session, path);
      });
      node.className = "tree-item";
      if (entry.type === "blob" && selectedPath === path) { node.classList.add("selected"); node.setAttribute("aria-current", "true"); }
      treeNode.append(node);
    }
  }
  async function loadTree(session, path) {
    if (!active(session)) return;
    const requestId = ++treeRequest;
    treeNode.replaceChildren(); treeStatus.textContent = "读取目录中…";
    renderBreadcrumbs(session, path);
    try {
      const data = await request(`/api/snapshots/${encodeURIComponent(session.id)}/tree?path=${encodeURIComponent(path)}`);
      if (!active(session) || requestId !== treeRequest) return;
      currentPath = path; entries = data.entries.sort((a, b) => a.type === b.type ? a.name.localeCompare(b.name) : a.type === "tree" ? -1 : 1);
      for (const item of entries) if (item.type === "blob") knownFiles.set(path ? `${path}/${item.name}` : item.name, true);
      treeStatus.textContent = data.truncated ? "此目录已截断，未列出条目的状态未知。" : "选择目录或文件。";
      renderTree(session); renderShortcuts(session);
      if (!path && !session.rootLoaded) {
        session.rootLoaded = true;
        const readme = entries.find(e => e.type === "blob" && /^readme(?:\.[^/]+)?$/i.test(e.name));
        if (readme) chooseFile(session, readme.name);
        else card.textContent = data.truncated ? "目录不完整，无法判断 README 是否存在。" : "根目录没有 README，请选择其他文件。";
      }
      status.textContent = "快照已创建。";
    } catch (error) {
      if (!active(session) || requestId !== treeRequest) return;
      treeStatus.replaceChildren(el("span", `${error.message} `), button("重试目录", () => loadTree(session, path)));
      status.textContent = "目录读取失败，可以重试。";
    }
  }
  function renderFragment(session, data) {
    if (!active(session)) return;
    card.replaceChildren(el("h4", data.path));
    card.append(el("p", data.empty ? "空文件（没有原始行）" : `原始行 ${data.start_line}–${data.end_line}`));
    card.append(el("p", `抓取 ${data.fetched_at} · ${data.cache_hit ? "缓存命中" : "GitHub 读取"}`));
    card.append(copyValue("完整文件 SHA-256", data.content_sha256), copyValue("片段 SHA-256", data.fragment_sha256), copyValue("证据 ID", data.evidence_id));
    const source = el("a", "打开固定版本来源"); source.href = data.source_url; source.target = "_blank"; source.rel = "noopener noreferrer"; card.append(source);
    if (data.partial_line) card.append(el("p", "单行超过 16 KiB，显示原始前缀；请打开来源查看完整行。", "notice"));
    else if (data.truncated) card.append(el("p", "片段已截断，可读取下一段。", "notice"));
    const details = el("details"); details.append(el("summary", "展开原文"));
    const pre = el("pre", "", "evidence-lines");
    if (!data.empty) {
      const lines = data.text.split("\n"); if (lines.at(-1) === "") lines.pop();
      lines.forEach((line, index) => {
        const row = el("span", "", "evidence-line");
        const number = el("span", String(data.start_line + index), "line-number"); number.setAttribute("aria-hidden", "true");
        const content = el("span", line, "line-content"); row.append(number, content); pre.append(row);
      });
    }
    details.append(pre); card.append(details);
    const controls = el("div", "", "page-controls");
    const prev = button("上一段", () => { if (historyIndex > 0) { historyIndex--; renderFragment(session, history[historyIndex]); } });
    prev.disabled = historyIndex <= 0; controls.append(prev);
    const next = button("下一段", () => {
      if (historyIndex < history.length - 1) { historyIndex++; renderFragment(session, history[historyIndex]); }
      else if (data.truncated && !data.partial_line) loadFile(session, data.path, data.end_line + 1);
    });
    next.disabled = !(historyIndex < history.length - 1 || (data.truncated && !data.partial_line)); controls.append(next);
    const label = el("label", "跳转起始行 "); const input = document.createElement("input");
    input.type = "number"; input.min = "1"; input.value = String(data.start_line || 1); input.setAttribute("aria-label", "跳转起始行"); label.append(input);
    controls.append(label, button("跳转", () => {
      const line = Number(input.value);
      if (!Number.isSafeInteger(line) || line < 1) { status.textContent = "请输入大于等于 1 的整数行号。"; return; }
      loadFile(session, data.path, line);
    }));
    card.append(controls);
  }
  function chooseFile(session, path) {
    if (!active(session)) return;
    selectedPath = path; history = []; historyIndex = -1; renderTree(session); loadFile(session, path, 1);
  }
  async function loadFile(session, path, start) {
    if (!active(session)) return;
    const requestId = ++fileRequest; card.textContent = "读取中…";
    try {
      const data = await request(`/api/snapshots/${encodeURIComponent(session.id)}/fragment?path=${encodeURIComponent(path)}&start=${start}`);
      if (!active(session) || requestId !== fileRequest) return;
      history = history.slice(0, historyIndex + 1); history.push(data); historyIndex = history.length - 1;
      renderFragment(session, data);
    } catch (error) {
      if (!active(session) || requestId !== fileRequest) return;
      card.replaceChildren(el("p", error.message), button("重试文件", () => loadFile(session, path, start)));
    }
  }
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (createButton.disabled) return;
    reset(); const requestGeneration = generation; status.textContent = "正在固定版本…";
    try {
      const data = await request("/api/snapshots", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({repository:$("repositoryInput").value})});
      if (requestGeneration !== generation) return;
      const session = {...data, generation:requestGeneration, rootLoaded:false}; currentSession = session;
      workspace.hidden = false; $("snapshotInfo").append(el("span", `${data.repo} · 创建于 ${data.created_at} · `), copyValue("commit", data.sha));
      card.textContent = "选择文件以读取文本。"; await loadTree(session, "");
    } catch (error) { if (requestGeneration === generation) status.textContent = `读取失败：${error.message} 请重新提交重试。`; }
  });
  (async () => {
    status.textContent = "正在检测本地证据服务…";
    try {
      const data = await request("/api/capabilities");
      if (data.service !== "github-hot-monitor-evidence") throw new Error("未发现证据服务。");
      createButton.disabled = false; status.textContent = "输入仓库后读取默认分支当前版本。";
    } catch (_) {
      createButton.disabled = true;
      status.textContent = "当前页面没有可用的证据服务。静态榜单可正常使用；请启动本地服务并访问 http://127.0.0.1:8768。";
    }
  })();
})();
