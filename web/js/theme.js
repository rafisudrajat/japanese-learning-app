(function () {
  var saved = localStorage.getItem("theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);

  function sync(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
    fetch("/api/settings/theme", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: theme }),
    }).catch(function () {});
  }

  sync(saved);

  document.addEventListener("click", function (e) {
    if (e.target && e.target.id === "theme-toggle") {
      var current = document.documentElement.getAttribute("data-theme");
      sync(current === "dark" ? "light" : "dark");
    }
  });
})();
