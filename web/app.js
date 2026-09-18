/* AutoResearch M13 panel renderer.
 *
 * Two modes, one code path:
 *   live      -- GET /ui/panels/{panel_id}?project_id=... (BFF over the 24 endpoints)
 *   snapshot  -- window.__PANEL_SNAPSHOT__ inlined by web/dev/build_snapshots.py
 *
 * The renderer never derives a status of its own and never fills a gap: if a
 * section is not `verified` it prints the backend's `unknown_reason` verbatim.
 * There is no code path that renders a "grey / 暂无" placeholder, because that
 * would collapse `unverified` and `blocked` into one indistinguishable look
 * (M13-04 / L1 §4.2 A5).
 *
 * Two spots used to break that rule and were fixed after adversarial review
 * (L3 §9.2): the tab status dot was hardcoded to `unverified` for every panel,
 * and `stateOf()` coerced any unrecognised `verification_state` to `unverified`.
 * Both were the renderer inventing a status. Now:
 *   * a tab dot is rendered only for a state the projection actually carries,
 *     and it is written from the same value the panel header chip uses;
 *   * an unrecognised state is rendered as `INVALID-STATE`, never as one of the
 *     three real states.
 */
(function () {
  "use strict";

  var SNAPSHOT = window.__PANEL_SNAPSHOT__ || null;
  var API_BASE = window.__API_BASE__ || "/api";

  var STATE_LABEL = {
    verified: { glyph: "\u2713", word: "VERIFIED", note: "数据已解析并核对" },
    unverified: { glyph: "?", word: "UNVERIFIED", note: "无法解析 —— 原因见下" },
    blocked: { glyph: "\u2717", word: "BLOCKED", note: "被上游依赖阻塞 —— 原因见下" }
  };

  //: Any value outside K14's three literals. Rendered as its own label so the
  //: renderer never launders a contract violation into a legitimate state.
  var INVALID_STATE = "invalid";
  STATE_LABEL[INVALID_STATE] = {
    glyph: "!",
    word: "INVALID-STATE",
    note: "投影带了 K14 三态以外的取值 —— 契约违规，按未验证处理"
  };

  //: tab dot class per state. Deliberately has NO entry for INVALID_STATE: an
  //: unrecognised state gets no dot rather than a wrong-coloured one.
  var TAB_DOT_CLASS = {
    verified: "tab__dot--verified",
    unverified: "tab__dot--unverified",
    blocked: "tab__dot--blocked"
  };

  var PANEL_TITLES = {
    project: "研究项目",
    evidence: "证据与审核",
    files: "项目文件夹",
    approval: "人工审批"
  };

  var REFS_SHOWN = 12;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  //: Map a raw `verification_state` to a render key. This is a *rename*, not a
  //: default: an unknown value becomes INVALID_STATE and is therefore visibly
  //: not one of the three real states.
  function stateOf(value) {
    return STATE_LABEL[value] && value !== INVALID_STATE ? value : INVALID_STATE;
  }

  function chip(state) {
    var key = stateOf(state);
    var meta = STATE_LABEL[key];
    var node = el("span", "chip chip--" + key + (key === INVALID_STATE ? " chip--invalid" : ""));
    node.appendChild(el("span", "chip__glyph", meta.glyph));
    node.appendChild(el("span", "chip__word", meta.word));
    node.setAttribute("aria-label", meta.word + " — " + meta.note);
    return node;
  }

  function renderSection(section) {
    var state = stateOf(section.verification_state);
    var wrap = el("section", "section section--" + state);

    var head = el("div", "section__head");
    head.appendChild(el("h3", "section__title", section.title));
    head.appendChild(chip(state));
    wrap.appendChild(head);

    // K14-3: the reason is inline and verbatim. Never a tooltip, never omitted.
    if (state !== "verified") {
      var reason = el("p", "reason reason--" + state);
      var label = state === "blocked" ? "阻塞原因"
        : state === INVALID_STATE ? "契约违规" : "未验证原因";
      reason.appendChild(el("span", "reason__label", label));
      reason.appendChild(document.createTextNode(
        section.unknown_reason || "(缺少 unknown_reason — 契约违规)"
      ));
      wrap.appendChild(reason);
    }

    var keys = Object.keys(section.facts || {});
    if (keys.length) {
      var dl = el("dl", "facts");
      keys.forEach(function (key) {
        dl.appendChild(el("dt", null, key));
        dl.appendChild(el("dd", null, section.facts[key]));
      });
      wrap.appendChild(dl);
    }

    var refs = section.refs || [];
    if (refs.length) {
      var box = el("div", "refs");
      box.appendChild(el("span", "refs__label", "refs (" + refs.length + ")"));
      refs.slice(0, REFS_SHOWN).forEach(function (ref) {
        box.appendChild(el("code", "ref", ref));
      });
      if (refs.length > REFS_SHOWN) {
        box.appendChild(el("span", "refs__more", "+" + (refs.length - REFS_SHOWN) + " more"));
      }
      wrap.appendChild(box);
    }
    return wrap;
  }

  // -------------------------------------------------------------- M13-07

  function factLookup(projection, needle, key) {
    var hit = (projection.sections || []).filter(function (s) {
      return s.title.indexOf(needle) >= 0;
    })[0];
    return hit ? (hit.facts || {})[key] : undefined;
  }

  function evidenceRefs(projection) {
    var hit = (projection.sections || []).filter(function (s) {
      return s.title.indexOf("backing evidence") >= 0 || s.title.indexOf("证据项") >= 0;
    })[0];
    return hit ? (hit.refs || []).filter(function (r) { return r.indexOf("ev_") === 0; }) : [];
  }

  function renderActions(projection) {
    var box = el("div", "actions");
    box.appendChild(el("p", "actions__hint", "M13-07 人工审批与打回 —— 每次写入都落到既有端点并写审计"));

    var frozen = !!SNAPSHOT;
    if (frozen) {
      box.appendChild(el("p", "actions__result",
        "静态快照模式：控件按真实状态渲染，但已禁用（页面通过 file:// 打开，没有可写的 API 源）。"));
    }

    var runId = factLookup(projection, "pending human decision", "run_id");
    var pending = factLookup(projection, "pending human decision", "pending") === "true";
    var ev = evidenceRefs(projection);

    // --- approve / reject the pending human interrupt -------------------
    var row1 = el("div", "actions__row");
    var reviewer = el("input", "field__input");
    reviewer.placeholder = "reviewer（写入审计 actor）";
    var note1 = el("input", "field__input");
    note1.placeholder = "note";
    var approve = el("button", "btn btn--approve", "确认 (approve)");
    var reject = el("button", "btn btn--reject", "拒绝 (reject)");
    approve.type = "button";
    reject.type = "button";
    var canResume = !frozen && pending && !!runId && runId !== "unknown";
    approve.disabled = !canResume;
    reject.disabled = !canResume;
    [reviewer, note1, approve, reject].forEach(function (n) { row1.appendChild(n); });
    box.appendChild(row1);
    box.appendChild(el("p", "actions__endpoint",
      "POST " + API_BASE + "/runs/" + (runId || "{run_id}") + "/resume  body={approval, reviewer, note}" +
      (pending ? "" : "   ← 当前无待决 interrupt，两个按钮禁用")));

    var out1 = el("pre", "actions__result");
    out1.hidden = true;
    box.appendChild(out1);
    function resume(approval) {
      call(out1, "POST", API_BASE + "/runs/" + encodeURIComponent(runId) + "/resume",
        { approval: approval, reviewer: reviewer.value || "unnamed-human", note: note1.value || "" });
    }
    approve.addEventListener("click", function () { resume(true); });
    reject.addEventListener("click", function () { resume(false); });

    // --- retract (打回) an evidence item ---------------------------------
    var row2 = el("div", "actions__row");
    var target = el("input", "field__input");
    target.value = ev[0] || "ev_...";
    target.placeholder = "evidence_id";
    var reason = el("input", "field__input");
    reason.placeholder = "打回原因（必填，写审计）";
    var retract = el("button", "btn btn--retract", "打回 (invalidate)");
    retract.type = "button";
    retract.disabled = frozen;
    [target, reason, retract].forEach(function (n) { row2.appendChild(n); });
    box.appendChild(row2);
    box.appendChild(el("p", "actions__endpoint",
      "POST " + API_BASE + "/evidence/{evidence_id}/invalidate  body={reason, actor}  —— 这是 M13-05 回退入口的写侧"));

    var out2 = el("pre", "actions__result");
    out2.hidden = true;
    box.appendChild(out2);
    retract.addEventListener("click", function () {
      call(out2, "POST", API_BASE + "/evidence/" + encodeURIComponent(target.value.trim()) + "/invalidate",
        { reason: reason.value || "retracted from panel", actor: reviewer.value || "unnamed-human" });
    });

    return box;
  }

  function call(out, method, url, body) {
    out.hidden = false;
    out.className = "actions__result";
    out.textContent = method + " " + url + "\n…";
    fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.text().then(function (text) {
        var pretty = text;
        try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch (e) { /* keep raw */ }
        out.className = "actions__result " + (res.ok ? "actions__result--ok" : "actions__result--err");
        out.textContent = method + " " + url + "  ->  " + res.status + "\n" + pretty +
          (res.ok ? "\n\n已写入审计。点「载入」重取面板可见变化。" : "");
      });
    }).catch(function (err) {
      out.className = "actions__result actions__result--err";
      out.textContent = method + " " + url + "  ->  请求失败\n" + err;
    });
  }

  // ------------------------------------------------------------- rendering

  function renderPanel(panelId, projection) {
    var host = document.getElementById("panels");
    host.textContent = "";
    document.querySelectorAll(".tab").forEach(function (tab) {
      tab.setAttribute("aria-selected", String(tab.dataset.panel === panelId));
    });
    // single source of truth: the tab dot is written from the very value the
    // header chip below renders, so the two can never disagree.
    syncTabState(panelId, projection.verification_state);

    var head = el("div", "panel__head");
    var left = el("div");
    left.appendChild(el("h2", "panel__title", PANEL_TITLES[panelId] || panelId));
    left.appendChild(el("div", "panel__meta",
      "panel_id=" + projection.panel_id + " · project_id=" + (projection.project_id || "-")));
    head.appendChild(left);
    head.appendChild(chip(projection.verification_state));
    host.appendChild(head);

    if (Array.isArray(projection.warnings) && projection.warnings.length) {
      var warn = el("p", "reason reason--unverified");
      warn.appendChild(el("span", "reason__label", "读取告警"));
      warn.appendChild(document.createTextNode(projection.warnings.join(" | ")));
      host.appendChild(warn);
    }

    (projection.sections || []).forEach(function (section) {
      host.appendChild(renderSection(section));
    });

    if (panelId === "approval") {
      host.appendChild(renderActions(projection));
    }
  }

  //: The tab dot is the SAME value the panel header chip renders -- both come
  //: from `projection.verification_state`, so they cannot disagree.
  function dotClassFor(state) {
    return TAB_DOT_CLASS[state] || null;
  }

  function syncTabState(panelId, state) {
    var tab = document.querySelector('.tab[data-panel="' + panelId + '"]');
    if (!tab) return;
    var cls = dotClassFor(state);
    var dot = tab.querySelector(".tab__dot");
    if (!cls) {
      // Unknown / unrecognised state: show no dot rather than a wrong one.
      if (dot) dot.remove();
      tab.removeAttribute("data-dot-state");
      return;
    }
    if (!dot) {
      dot = el("span", "tab__dot");
      dot.setAttribute("aria-hidden", "true");
      tab.insertBefore(dot, tab.firstChild);
    }
    dot.className = "tab__dot " + cls;
    tab.setAttribute("data-dot-state", state);
    tab.setAttribute("aria-label", (PANEL_TITLES[panelId] || panelId) + " — " + state);
  }

  function renderTabs(panelIds, onSelect, states) {
    var host = document.getElementById("tabs");
    host.textContent = "";
    var known = states || {};
    panelIds.forEach(function (panelId) {
      var tab = el("button", "tab");
      tab.type = "button";
      tab.dataset.panel = panelId;
      tab.appendChild(document.createTextNode(PANEL_TITLES[panelId] || panelId));
      tab.addEventListener("click", function () { onSelect(panelId); });
      host.appendChild(tab);
      // Only a state the projection actually carries gets a dot.
      if (known[panelId]) syncTabState(panelId, known[panelId]);
    });
  }

  function renderLegend() {
    var host = document.getElementById("legend");
    host.textContent = "";
    ["verified", "unverified", "blocked"].forEach(function (state) {
      var item = el("div", "legend__item");
      item.appendChild(chip(state));
      item.appendChild(el("span", null, STATE_LABEL[state].note));
      host.appendChild(item);
    });
  }

  // ------------------------------------------------------------------ boot

  function currentProjectId() {
    var input = document.getElementById("project-input");
    return (input && input.value.trim()) || "litalpha";
  }

  function loadLive(panelId) {
    var host = document.getElementById("panels");
    host.textContent = "";
    host.appendChild(el("p", "placeholder", "载入 " + panelId + " …"));
    fetch("/ui/panels/" + panelId + "?project_id=" + encodeURIComponent(currentProjectId()))
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (payload) {
        payload.project_id = currentProjectId();
        renderPanel(panelId, payload);
      })
      .catch(function (err) {
        host.textContent = "";
        var bad = el("p", "reason reason--blocked");
        bad.appendChild(el("span", "reason__label", "面板载入失败"));
        bad.appendChild(document.createTextNode(String(err)));
        host.appendChild(bad);
      });
  }

  function bootSnapshot() {
    document.getElementById("snapshot-note").hidden = false;
    document.getElementById("load-btn").disabled = true;
    document.getElementById("project-input").disabled = true;
    var ids = Object.keys(SNAPSHOT.panels);
    var initial = SNAPSHOT.initial && ids.indexOf(SNAPSHOT.initial) >= 0 ? SNAPSHOT.initial : ids[0];
    var states = {};
    ids.forEach(function (panelId) {
      states[panelId] = SNAPSHOT.panels[panelId].verification_state;
    });
    renderTabs(ids, function (panelId) {
      renderPanel(panelId, SNAPSHOT.panels[panelId]);
    }, states);
    renderLegend();
    renderPanel(initial, SNAPSHOT.panels[initial]);
  }

  function selectedPanelId() {
    var active = document.querySelector(".tab[aria-selected='true']");
    return active ? active.dataset.panel : null;
  }

  //: Tabs carry the project's real per-panel states, so the tab bar cannot show
  //: a state the projection did not report. Re-run whenever the project changes.
  function loadTabs(projectId, onReady) {
    fetch("/ui/panels?project_id=" + encodeURIComponent(projectId))
      .then(function (res) { return res.json(); })
      .then(function (meta) {
        var ids = meta.panel_ids || [];
        renderTabs(ids, loadLive, meta.states || {});
        onReady(ids);
      })
      .catch(function (err) {
        var host = document.getElementById("panels");
        host.textContent = "";
        host.appendChild(el("p", "placeholder", "/ui/panels 不可用：" + err));
      });
  }

  function bootLive() {
    document.getElementById("load-btn").addEventListener("click", function () {
      var keep = selectedPanelId();
      loadTabs(currentProjectId(), function (ids) {
        loadLive(ids.indexOf(keep) >= 0 ? keep : ids[0]);
      });
    });
    renderLegend();
    loadTabs(currentProjectId(), function (ids) {
      loadLive(ids[0]);
    });
  }

  if (SNAPSHOT) { bootSnapshot(); } else { bootLive(); }
})();
