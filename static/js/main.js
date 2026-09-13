/* RentFlow — global shell behaviour */
(function () {
  "use strict";

  // Sidebar collapse
  const burger = document.getElementById("nav-burger");
  if (burger) {
    burger.addEventListener("click", () => {
      if (window.innerWidth <= 900) {
        document.body.classList.toggle("nav-open");
      } else {
        document.body.classList.toggle("nav-collapsed");
        localStorage.setItem(
          "rf-nav",
          document.body.classList.contains("nav-collapsed") ? "1" : "0"
        );
      }
    });
    if (localStorage.getItem("rf-nav") === "1" && window.innerWidth > 900) {
      document.body.classList.add("nav-collapsed");
    }
  }

  // User dropdown
  const chip = document.getElementById("user-chip");
  if (chip) {
    chip.addEventListener("click", (e) => {
      e.stopPropagation();
      chip.classList.toggle("open");
    });
    document.addEventListener("click", () => chip.classList.remove("open"));
  }

  // Toasts ------------------------------------------------------------------
  window.rfToast = function (msg, type = "info", ms = 4200) {
    let zone = document.querySelector(".toast-zone");
    if (!zone) {
      zone = document.createElement("div");
      zone.className = "toast-zone";
      document.body.appendChild(zone);
    }
    const t = document.createElement("div");
    t.className = "toast " + type;
    t.innerHTML = "<div>" + msg + "</div>";
    zone.appendChild(t);
    setTimeout(() => {
      t.classList.add("leaving");
      setTimeout(() => t.remove(), 260);
    }, ms);
  };

  // Django messages → toasts
  document.querySelectorAll("[data-django-message]").forEach((el) => {
    window.rfToast(el.dataset.text, el.dataset.level || "info");
    el.remove();
  });

  // Modals --------------------------------------------------------------------
  window.rfModal = {
    open(id) {
      const m = document.getElementById(id);
      if (m) { m.classList.add("open"); document.body.style.overflow = "hidden"; }
    },
    close(id) {
      const m = document.getElementById(id);
      if (m) { m.classList.remove("open"); document.body.style.overflow = ""; }
    },
  };
  document.querySelectorAll(".modal-backdrop").forEach((bd) => {
    bd.addEventListener("click", (e) => {
      if (e.target === bd) { bd.classList.remove("open"); document.body.style.overflow = ""; }
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-backdrop.open").forEach((m) => m.classList.remove("open"));
      document.body.style.overflow = "";
    }
  });

  // CSRF helper
  window.rfCsrf = function () {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  };

  // Money formatter
  window.rfMoney = function (v) {
    return "৳ " + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });
  };

  // Radio-card + check-row visual state
  document.addEventListener("change", (e) => {
    const input = e.target;
    if (input.matches(".radio-card input[type=radio]")) {
      document
        .querySelectorAll(`input[name="${input.name}"]`)
        .forEach((r) => r.closest(".radio-card")?.classList.toggle("checked", r.checked));
    }
    if (input.matches(".check-row input[type=checkbox]")) {
      input.closest(".check-row").classList.toggle("checked", input.checked);
    }
  });
})();
