// Clicking the chosen decision again clears it, leaving the fix for later
for (const group of document.querySelectorAll(".segmented")) {
  let chosen = group.querySelector("input:checked");
  group.addEventListener("click", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    if (input === chosen) {
      input.checked = false;
      chosen = null;
    } else {
      chosen = input;
    }
  });
}
