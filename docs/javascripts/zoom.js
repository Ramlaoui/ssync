// Click a screenshot to see it at full size; click again or press Escape to close.
// Delegated from the document so it keeps working across instant navigation.
document.addEventListener("click", (event) => {
  const image = event.target.closest(".ss-shot img, img.ss-shot, .ss-phones img");
  const open = document.querySelector(".ss-zoom");
  if (open) {
    open.remove();
    return;
  }
  if (!image) return;
  const overlay = document.createElement("div");
  overlay.className = "ss-zoom";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-label", image.alt || "Screenshot");
  const full = document.createElement("img");
  full.src = image.currentSrc || image.src;
  full.alt = image.alt;
  overlay.append(full);
  document.body.append(overlay);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") document.querySelector(".ss-zoom")?.remove();
});
