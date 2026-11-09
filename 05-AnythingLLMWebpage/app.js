// ============================================================================
// AnythingLLM Web 控制台
// 安全：API Key 只保存在本模块作用域变量（可选 sessionStorage，关页即清），
//       绝不写入 localStorage / Cookie / 代码文件；
//       所有接口返回内容一律经 textContent 渲染（防 XSS）。
// ============================================================================

// ---------- 配置（运行时输入，零硬编码） ----------
let apiKey = sessionStorage.getItem('allm_key') || '';
let baseUrl = (localStorage.getItem('allm_base') || 'http://localhost:3001').replace(/\/+$/, '');
let currentSlug = '';
let lastDocLocation = '';   // 最近一次上传成功的文档 location（供向量化）

// ---------- DOM ----------
const $ = id => document.getElementById(id);

// ---------- 状态展示：加载 / 成功 / 失败 ----------
function setState(el, state, text) {
  el.className = 'st-' + state;
  el.textContent = text;
}

// ---------- AnythingLLM API 封装（端点/鉴权头与官方 API 一致） ----------
async function api(path, { method = 'GET', body, form } = {}) {
  const headers = { 'Authorization': `Bearer ${apiKey}` };
  if (body) headers['Content-Type'] = 'application/json';
  const res = await fetch(baseUrl + path, {
    method, headers,
    body: form ? form : (body ? JSON.stringify(body) : undefined),
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${typeof data === 'string' ? data.slice(0, 200) : JSON.stringify(data).slice(0, 200)}`);
  }
  return data;
}

// ---------- 连接 & 工作区 ----------
async function connect() {
  apiKey = $('api-key').value.trim();
  baseUrl = $('base-url').value.trim().replace(/\/+$/, '');
  if (!apiKey || !baseUrl) { setState($('conn-status'), 'err', '请填写地址与 API Key'); return; }
  setState($('conn-status'), 'loading', '连接中…');
  try {
    const data = await api('/api/v1/workspaces');          // GET /api/v1/workspaces
    sessionStorage.setItem('allm_key', apiKey);            // 仅存会话级存储
    localStorage.setItem('allm_base', baseUrl);            // 地址不含密钥，可持久化
    renderWorkspaces(data.workspaces || []);
    setState($('conn-status'), 'ok', `已连接（${(data.workspaces || []).length} 个工作区）`);
    setState($('conn-hint'), 'ok', 'Key 仅存内存/sessionStorage，关页即清');
  } catch (e) {
    setState($('conn-status'), 'err', '连接失败：' + e.message);
  }
}

function renderWorkspaces(list) {
  const ul = $('ws-list');
  ul.textContent = '';
  if (!list.length) { const li = document.createElement('li'); li.textContent = '（无工作区）'; ul.appendChild(li); return; }
  for (const ws of list) {
    const li = document.createElement('li');
    li.textContent = `${ws.name}  (${ws.slug})`;           // textContent 防 XSS
    li.dataset.slug = ws.slug;
    li.onclick = () => selectWorkspace(ws.slug, li);
    ul.appendChild(li);
  }
  selectWorkspace(list[0].slug, ul.children[0]);
}

async function selectWorkspace(slug, li) {
  currentSlug = slug;
  for (const x of li.parentElement.children) x.classList.remove('active');
  li.classList.add('active');
  $('ws-current').textContent = slug;
  setState($('doc-status'), 'loading', '加载文档…');
  try {
    const data = await api(`/api/v1/workspace/${encodeURIComponent(slug)}`);  // GET /api/v1/workspace/{slug}
    const docs = (data.workspace && data.workspace[0] && data.workspace[0].documents) || [];
    const ul = $('doc-list'); ul.textContent = '';
    if (!docs.length) { const li2 = document.createElement('li'); li2.textContent = '（暂无文档）'; ul.appendChild(li2); }
    for (const d of docs) {
      const li2 = document.createElement('li');
      li2.textContent = d.filename || d.docpath || '(未命名)';
      ul.appendChild(li2);
    }
    setState($('doc-status'), 'ok', `工作区文档 ${docs.length} 个`);
  } catch (e) {
    setState($('doc-status'), 'err', '加载失败：' + e.message);
  }
}

// ---------- 上传 → 向量化（两段流程） ----------
async function uploadAndEmbed() {
  const file = $('file-input').files[0];
  if (!file) { setState($('up-status'), 'err', '请先选择文件'); return; }
  if (!currentSlug) { setState($('up-status'), 'err', '请先连接并选择工作区'); return; }
  $('btn-upload').disabled = true;
  setState($('up-status'), 'loading', `上传中… ${file.name}`);
  try {
    const form = new FormData();
    form.append('file', file);
    const up = await api('/api/v1/document/upload', { method: 'POST', form });   // 上传
    const doc = (up.documents && up.documents[0]) || {};
    lastDocLocation = doc.location || '';
    if (!lastDocLocation) throw new Error('上传响应缺少 location');
    setState($('up-status'), 'loading', '已上传，向量化中…');
    await api(`/api/v1/workspace/${encodeURIComponent(currentSlug)}/update-embeddings`, {   // 向量化
      method: 'POST', body: { adds: [lastDocLocation], deletes: [] },
    });
    setState($('up-status'), 'ok', `已向量化：${file.name}`);
    const active = document.querySelector('#ws-list li.active');
    if (active) selectWorkspace(currentSlug, active);       // 刷新文档列表
  } catch (e) {
    setState($('up-status'), 'err', '失败：' + e.message);
  } finally {
    $('btn-upload').disabled = false;
  }
}

// ---------- 问答 ----------
function addMsg(role, text, sources) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;                                   // textContent 防 XSS
  if (sources && sources.length) {
    const s = document.createElement('span');
    s.className = 'src';
    s.textContent = '来源：' + sources.map(x => x.title || x.doc || '未知文档').slice(0, 3).join('、');
    div.appendChild(s);
  }
  $('messages').appendChild(div);
  $('messages').scrollTop = $('messages').scrollHeight;
}

async function ask() {
  const q = $('question').value.trim();
  if (!q) return;
  if (!currentSlug) { setState($('chat-status'), 'err', '请先连接并选择工作区'); return; }
  addMsg('user', q);
  $('question').value = '';
  $('btn-ask').disabled = true;
  setState($('chat-status'), 'loading', '思考中…');
  try {
    const data = await api(`/api/v1/workspace/${encodeURIComponent(currentSlug)}/chat`, {  // 问答
      method: 'POST', body: { message: q, mode: 'chat' },
    });
    addMsg('bot', data.textResponse || '(空回答)', data.sources);
    setState($('chat-status'), 'ok', '');
  } catch (e) {
    addMsg('sys', '提问失败：' + e.message);
    setState($('chat-status'), 'err', '失败');
  } finally {
    $('btn-ask').disabled = false;
  }
}

// ---------- 事件绑定 ----------
$('btn-connect').onclick = connect;
$('btn-upload').onclick = uploadAndEmbed;
$('btn-ask').onclick = ask;
$('question').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } });

// 恢复上次的地址（Key 不预填，需每次输入）
$('base-url').value = baseUrl;
