/* Presentation only. The original design is an offline backup, not a user setting. */
(() => {
  // Ignore old design preferences; never change saved conversations or settings.
  document.documentElement.dataset.design = "modern";
  document.addEventListener("DOMContentLoaded", () => {
    // Keep sticky panels and the composer clear of wrapped multilingual controls.
    if (window.ResizeObserver) {
      const header = document.querySelector(".top-bar");
      const composer = document.querySelector(".composer-area");
      const observer = new ResizeObserver(() => {
        document.documentElement.style.setProperty("--header-height", `${header.offsetHeight}px`);
        document.documentElement.style.setProperty("--composer-height", `${composer.offsetHeight}px`);
      });
      observer.observe(header);
      observer.observe(composer);
    }
  });
})();
