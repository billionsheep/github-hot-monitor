(() => {
  const $ = id => document.getElementById(id);
  const form = $('agentForm'), status = $('agentStatus'), submit = $('agentSubmit');
  const progress = $('agentProgress'), result = $('agentResult');
  let runNumber = 0;
  function el(tag, text) { const node = document.createElement(tag); node.textContent = text; return node; }
  async function request(url, options) {
    let response;
    try { response = await fetch(url, options); } catch (_) { throw new Error('本地服务不可用，请检查服务。'); }
    if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error(`服务返回非 JSON 数据（HTTP ${response.status}）。`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.message || `请求失败（HTTP ${response.status}）。`);
    return data;
  }
  function render(data) {
    result.replaceChildren();
    result.append(el('p', `${data.repository || '仓库读取失败'} · ${data.commit || '无固定提交'} · ${data.stop_reason}`));
    result.append(el('p', `模型请求 ${data.model_requests} 次，工具调用 ${data.tool_calls} 次，用时 ${data.elapsed_seconds} 秒；输入 ${data.usage.input_tokens} / 输出 ${data.usage.output_tokens} tokens。`));
    const table = document.createElement('table');
    const head = document.createElement('tr'); for (const text of ['要求','证据','判断','下一步验证']) head.append(el('th',text)); table.append(head);
    const evidence = new Map(data.evidence.map(item => [item.evidence_id, item]));
    for (const row of data.rows) {
      const tr = document.createElement('tr');
      tr.append(el('td', row.requirement));
      const refs = document.createElement('td');
      for (const id of row.evidence_ids) {
        const item = evidence.get(id); if (!item) continue;
        const a = el('a', `${item.path}${item.empty ? '（空文件）' : ` L${item.start_line}–L${item.end_line}`}`);
        a.href = item.source_url; a.target = '_blank'; a.rel = 'noopener noreferrer'; refs.append(a, el('br',''));
      }
      if (!row.evidence_ids.length) refs.textContent = '无已登记引用';
      tr.append(refs, el('td', `${row.verdict}：${row.rationale}`), el('td', row.next_checks)); table.append(tr);
    }
    const wrap = el('div',''); wrap.className = 'agent-table'; wrap.append(table); result.append(wrap);
    result.append(el('p','引用已校验属于本次读取；判断是否得到原文支持仍需核对。'));
  }
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (submit.disabled) return;
    const requirements = [['python','agentPython'],['container','agentContainer'],['model_service','agentModel']]
      .map(([category,id]) => ({id:category, category, description:$(id).value.trim()})).filter(x => x.description);
    if (!requirements.length) { status.textContent = '请至少填写一项具体核查要求。'; return; }
    const labels = new Map(requirements.map(x => [x.id,x.description]));
    const seq = ++runNumber; submit.disabled = true; progress.replaceChildren(); result.replaceChildren(); status.textContent = '正在开始核查…';
    try {
      const run = await request('/api/agent/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({repository:$('agentRepository').value.trim(),requirements})});
      // Keep the user-provided wording local when displaying each returned row.
      const originalRender = render;
      await (async () => {
        while (seq === runNumber) {
          const data = await request(`/api/agent/runs/${encodeURIComponent(run.id)}`);
          if (seq !== runNumber) return;
          progress.replaceChildren(...data.progress.map(line => el('li', line)));
          if (data.status === 'done') { data.rows.forEach(row => {row.requirement = labels.get(row.requirement_id) || row.requirement_id;}); originalRender(data); status.textContent='核查完成。'; submit.disabled=false; return; }
          await new Promise(resolve => setTimeout(resolve,1000));
        }
      })();
    } catch (error) { if (seq === runNumber) { status.textContent = error.message; submit.disabled = false; } }
  });
  (async () => {
    try {
      const capability = await request('/api/capabilities');
      if (capability.service !== 'github-hot-monitor-evidence') throw new Error();
      const config = await request('/api/agent/config');
      if (!config.configured) { status.textContent = '请在本机 .env.local 填写 API 密钥并保持官方模型配置，然后刷新页面。'; return; }
      submit.disabled = false; status.textContent = '填写仓库和至少一项要求后开始。';
    } catch (_) { status.textContent = '核查功能需要本地服务；静态榜单仍可使用。'; }
  })();
})();
