(function () {
  try {
    var raw = localStorage.getItem("hydro-app-v1");
    if (raw) {
      var parsed = JSON.parse(raw);
      var theme = parsed && parsed.state && parsed.state.theme;
      if (theme === "light" || theme === "dark") {
        document.documentElement.dataset.theme = theme;
      }
    }
  } catch (e) {}
})();
