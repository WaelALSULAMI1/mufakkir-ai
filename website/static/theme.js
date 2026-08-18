(function () {
  var storageKey = "mufakkir.theme";
  var cookieName = "mufakkir_theme";
  var theme = "light";

  function readCookie() {
    var parts = ("; " + document.cookie).split("; " + cookieName + "=");
    if (parts.length < 2) return "";
    return decodeURIComponent(parts.pop().split(";").shift() || "").trim().toLowerCase();
  }

  try {
    var fromCookie = readCookie();
    var fromStore = "";
    try {
      fromStore = localStorage.getItem(storageKey) || "";
    } catch (_storageError) {
      fromStore = "";
    }
    if (fromCookie === "dark" || fromCookie === "light") theme = fromCookie;
    else if (fromStore === "dark" || fromStore === "light") theme = fromStore;
    else if (document.documentElement.getAttribute("data-theme") === "dark") theme = "dark";
  } catch (_error) {
    theme = "light";
  }

  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
})();
