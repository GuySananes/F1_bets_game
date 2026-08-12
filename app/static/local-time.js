// Converts server-rendered UTC timestamps into the viewer's local time.
// Any element with data-utc="<ISO 8601 UTC string>" gets its text replaced.
function renderLocalTimes() {
  document.querySelectorAll("time[data-utc]").forEach(function (el) {
    var parsed = new Date(el.getAttribute("data-utc"));
    if (isNaN(parsed.getTime())) return;
    el.textContent = parsed.toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  });
}

document.addEventListener("DOMContentLoaded", renderLocalTimes);
document.addEventListener("htmx:afterSwap", renderLocalTimes);
