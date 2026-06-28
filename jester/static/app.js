/* hermes-jester UI — progressive enhancement.
   The app works without JS (plain form posts); this layer adds the niceties
   from the design mock: theme switching, copy/toast, items view toggle,
   bulk selection, and styled confirm dialogs. */
(function () {
  "use strict";

  // ---------- theme ----------
  var THEMES = ["midnight", "paper", "console"];
  function currentTheme() {
    var t = localStorage.getItem("hj-theme");
    return THEMES.indexOf(t) >= 0 ? t : "midnight";
  }
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("hj-theme", t);
    document.querySelectorAll("[data-theme-name]").forEach(function (el) {
      el.classList.toggle("active", el.getAttribute("data-theme-name") === t);
    });
  }
  // apply ASAP (also set inline in <head> to avoid flash; this re-syncs controls)
  applyTheme(currentTheme());

  // ---------- toast ----------
  var toastTimer = null;
  function toast(msg) {
    var existing = document.querySelector(".toast");
    if (existing) existing.remove();
    var el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = '<span class="ok">✓</span> ' + msg;
    document.body.appendChild(el);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.remove(); }, 1900);
  }

  function copyText(text, label) {
    var done = function () { toast(label || "Copied"); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
    } else {
      fallbackCopy(text);
      done();
    }
  }
  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    ta.remove();
  }

  // ---------- confirm modal ----------
  function confirmModal(opts, onConfirm) {
    var overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML =
      '<div class="modal" role="dialog" aria-modal="true">' +
      '<h3></h3><p></p>' +
      '<div class="actions">' +
      '<button class="btn ghost" data-cancel>Cancel</button>' +
      '<button class="btn ' + (opts.danger ? "danger" : "primary") + '" data-ok></button>' +
      "</div></div>";
    overlay.querySelector("h3").textContent = opts.title || "Are you sure?";
    overlay.querySelector("p").textContent = opts.body || "";
    overlay.querySelector("[data-ok]").textContent = opts.confirmLabel || "Confirm";
    function close() { overlay.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    overlay.querySelector("[data-cancel]").addEventListener("click", close);
    overlay.querySelector("[data-ok]").addEventListener("click", function () { close(); onConfirm(); });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    overlay.querySelector("[data-ok]").focus();
  }

  // ---------- wire up on load ----------
  document.addEventListener("DOMContentLoaded", function () {
    // theme dots / pills
    document.querySelectorAll("[data-theme-name]").forEach(function (el) {
      el.addEventListener("click", function () { applyTheme(el.getAttribute("data-theme-name")); });
    });
    applyTheme(currentTheme());

    // copy buttons: data-copy holds the text (or data-copy-target a selector)
    document.querySelectorAll("[data-copy], [data-copy-target]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-copy");
        if (!text) {
          var sel = btn.getAttribute("data-copy-target");
          var target = sel && document.querySelector(sel);
          text = target ? target.textContent : "";
        }
        copyText(text, btn.getAttribute("data-copy-label") || "Copied");
      });
    });

    // confirm-guarded forms (delete / revoke)
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (form.dataset.confirmed === "1") return;
        e.preventDefault();
        confirmModal(
          {
            title: form.getAttribute("data-confirm-title") || "Are you sure?",
            body: form.getAttribute("data-confirm"),
            confirmLabel: form.getAttribute("data-confirm-label") || "Confirm",
            danger: true,
          },
          function () { form.dataset.confirmed = "1"; form.submit(); }
        );
      });
    });

    // auto-submit filter selects
    document.querySelectorAll("[data-autosubmit]").forEach(function (sel) {
      sel.addEventListener("change", function () { sel.form.submit(); });
    });

    // items view toggle (table / compact / grouped)
    var views = document.querySelectorAll("[data-view]");
    if (views.length) {
      var saved = localStorage.getItem("hj-view") || "table";
      setView(saved);
      document.querySelectorAll("[data-view-btn]").forEach(function (b) {
        b.addEventListener("click", function () { setView(b.getAttribute("data-view-btn")); });
      });
    }
    function setView(name) {
      var any = false;
      document.querySelectorAll("[data-view]").forEach(function (v) {
        var match = v.getAttribute("data-view") === name;
        v.classList.toggle("hide", !match);
        if (match) any = true;
      });
      if (!any) name = "table"; // fallback if requested view absent
      document.querySelectorAll("[data-view]").forEach(function (v) {
        v.classList.toggle("hide", v.getAttribute("data-view") !== name);
      });
      document.querySelectorAll("[data-view-btn]").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-view-btn") === name);
      });
      localStorage.setItem("hj-view", name);
    }

    // bulk selection
    var bulkBar = document.querySelector("[data-bulk-bar]");
    if (bulkBar) {
      var bulkForm = document.querySelector("[data-bulk-form]");
      function selectedIds() {
        return Array.prototype.slice
          .call(document.querySelectorAll("[data-row-check]:checked"))
          .map(function (c) { return c.value; });
      }
      function refresh() {
        var ids = selectedIds();
        bulkBar.classList.toggle("hide", ids.length === 0);
        var n = bulkBar.querySelector("[data-bulk-count]");
        if (n) n.textContent = ids.length + " selected";
        // sync select-all checkboxes
        var all = document.querySelectorAll("[data-row-check]");
        document.querySelectorAll("[data-select-all]").forEach(function (sa) {
          sa.checked = all.length > 0 && ids.length === all.length;
        });
      }
      document.querySelectorAll("[data-row-check]").forEach(function (c) {
        c.addEventListener("change", refresh);
      });
      document.querySelectorAll("[data-select-all]").forEach(function (sa) {
        sa.addEventListener("change", function () {
          document.querySelectorAll("[data-row-check]").forEach(function (c) { c.checked = sa.checked; });
          refresh();
        });
      });
      var clear = bulkBar.querySelector("[data-bulk-clear]");
      if (clear) clear.addEventListener("click", function () {
        document.querySelectorAll("[data-row-check]").forEach(function (c) { c.checked = false; });
        refresh();
      });
      // submit bulk action: write ids into hidden inputs of the bulk form
      bulkBar.querySelectorAll("[data-bulk-action]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var ids = selectedIds();
          if (!ids.length) return;
          var action = btn.getAttribute("data-bulk-action");
          var run = function () {
            bulkForm.querySelector("[name=action]").value = action;
            bulkForm.querySelectorAll("input[name=ids]").forEach(function (i) { i.remove(); });
            ids.forEach(function (id) {
              var inp = document.createElement("input");
              inp.type = "hidden"; inp.name = "ids"; inp.value = id;
              bulkForm.appendChild(inp);
            });
            bulkForm.submit();
          };
          if (action === "delete") {
            confirmModal({ title: "Delete " + ids.length + " items?", body: "This permanently removes the selected items.", confirmLabel: "Delete", danger: true }, run);
          } else {
            run();
          }
        });
      });
      refresh();
    }
  });
})();
