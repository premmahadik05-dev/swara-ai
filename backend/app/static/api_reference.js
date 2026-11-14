/* SWARA AI API reference. Reads /openapi.json and draws it. No libraries, no third-party requests, nothing is parsed as markup:
   every string from the schema goes in with textContent, so the page works under the strict content-security-policy. */
(function () {
  'use strict';
  var root = document.getElementById('app');
  var state = { spec: null, q: '' };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function deref(spec, node) {
    var guard = 0;
    while (node && node.$ref && guard++ < 8) {
      var parts = node.$ref.replace(/^#\//, '').split('/');
      var cur = spec;
      for (var i = 0; i < parts.length && cur; i++) cur = cur[parts[i]];
      node = cur;
    }
    return node || {};
  }
  function typeOf(spec, schema) {
    schema = deref(spec, schema);
    if (schema.anyOf || schema.oneOf) return (schema.anyOf || schema.oneOf).map(function (s) { return typeOf(spec, s); }).filter(function (t) { return t !== 'null'; }).join(' or ') || 'any';
    if (schema.type === 'array') return 'list of ' + typeOf(spec, schema.items || {});
    if (schema.enum) return schema.enum.map(String).join(' | ');
    return (schema.type || (schema.properties ? 'object' : 'any')) + (schema.format ? ' (' + schema.format + ')' : '');
  }
  function row(cells, head) {
    var tr = el('tr');
    cells.forEach(function (c) { tr.appendChild(el(head ? 'th' : 'td', null, c)); });
    return tr;
  }
  function table(headers, rows) {
    var t = el('table', 'tbl'), th = el('thead'), tb = el('tbody');
    th.appendChild(row(headers, true));
    rows.forEach(function (r) { tb.appendChild(row(r)); });
    t.appendChild(th); t.appendChild(tb);
    return t;
  }
  function operation(spec, path, method, op) {
    var d = el('details', 'op m-' + method);
    var s = el('summary');
    s.appendChild(el('span', 'verb', method.toUpperCase()));
    s.appendChild(el('code', 'path', path));
    s.appendChild(el('span', 'sum', op.summary || ''));
    d.appendChild(s);
    var body = el('div', 'body');
    if (op.description) body.appendChild(el('p', 'desc', op.description));
    var params = (op.parameters || []).map(function (p) { p = deref(spec, p); return [p.name, p.in, p.required ? 'yes' : 'no', typeOf(spec, p.schema || {})]; });
    if (params.length) { body.appendChild(el('h4', null, 'Parameters')); body.appendChild(table(['Name', 'In', 'Required', 'Type'], params)); }
    var rb = op.requestBody && deref(spec, op.requestBody);
    if (rb && rb.content) {
      Object.keys(rb.content).forEach(function (ct) {
        var sch = deref(spec, rb.content[ct].schema || {});
        body.appendChild(el('h4', null, 'Request body (' + ct + ')'));
        var props = sch.properties || {}, req = sch.required || [];
        var rows = Object.keys(props).map(function (k) { return [k, req.indexOf(k) >= 0 ? 'yes' : 'no', typeOf(spec, props[k])]; });
        if (rows.length) body.appendChild(table(['Field', 'Required', 'Type'], rows));
        else body.appendChild(el('p', 'muted', typeOf(spec, sch)));
      });
    }
    var codes = Object.keys(op.responses || {});
    if (codes.length) {
      body.appendChild(el('h4', null, 'Responses'));
      body.appendChild(table(['Status', 'Meaning'], codes.map(function (c) { return [c, (op.responses[c] || {}).description || '']; })));
    }
    d.appendChild(body);
    return d;
  }
  function render() {
    var spec = state.spec, q = state.q.trim().toLowerCase();
    var list = document.getElementById('list');
    list.textContent = '';
    var groups = {}, shown = 0, total = 0;
    Object.keys(spec.paths).sort().forEach(function (path) {
      ['get', 'post', 'put', 'patch', 'delete'].forEach(function (m) {
        var op = spec.paths[path][m];
        if (!op) return;
        total++;
        var hay = (m + ' ' + path + ' ' + (op.summary || '') + ' ' + (op.tags || []).join(' ')).toLowerCase();
        if (q && hay.indexOf(q) < 0) return;
        var tag = (op.tags && op.tags[0]) || 'other';
        (groups[tag] = groups[tag] || []).push([path, m, op]);
        shown++;
      });
    });
    Object.keys(groups).sort().forEach(function (tag) {
      var sec = el('section', 'grp');
      sec.appendChild(el('h2', null, tag));
      groups[tag].forEach(function (g) { sec.appendChild(operation(spec, g[0], g[1], g[2])); });
      list.appendChild(sec);
    });
    document.getElementById('count').textContent = shown + ' of ' + total + ' operations';
    if (!shown) list.appendChild(el('p', 'muted', 'Nothing matches "' + state.q + '".'));
  }
  function start(spec) {
    state.spec = spec;
    root.textContent = '';
    var info = spec.info || {};
    root.appendChild(el('h1', null, (info.title || 'API') + ' API reference'));
    root.appendChild(el('p', 'muted', 'Version ' + (info.version || '?') + '. ' + (info.summary || '')));
    var note = el('p', 'note');
    note.textContent = 'Every route except the open ones (health, sign-up and sign-in, the landing-page parser, the contact form) needs a signed-in session cookie. ' +
      'Every POST, PUT, PATCH and DELETE must also send the X-CSRF-Token header. Owner-only routes answer 403 to staff. The full rules, with who may call what, are in docs/API.md.';
    root.appendChild(note);
    var tools = el('div', 'tools');
    var input = el('input'); input.type = 'search'; input.placeholder = 'Filter by path, method or area'; input.setAttribute('aria-label', 'Filter operations');
    input.addEventListener('input', function () { state.q = input.value; render(); });
    tools.appendChild(input);
    var count = el('span', 'muted'); count.id = 'count'; count.setAttribute('aria-live', 'polite'); tools.appendChild(count);
    var raw = el('a', null, 'openapi.json'); raw.href = '/openapi.json'; tools.appendChild(raw);
    root.appendChild(tools);
    var list = el('div'); list.id = 'list'; root.appendChild(list);
    render();
  }
  fetch('/openapi.json', { headers: { Accept: 'application/json' } })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(start)
    .catch(function (e) { root.textContent = 'Could not load /openapi.json (' + e.message + ').'; });
})();
